"""Polite, bounded HTTP fetching for public OSINT sources (DS §28, §30).

Guarantees:
* identifies itself with a configured User-Agent; sends no credentials,
  cookies or custom auth headers (none can be configured);
* respects robots.txt (cached per origin) unless explicitly disabled;
* enforces a minimum interval between requests to the same host (per process);
* bounds response size and total time; streams and aborts oversized bodies;
* accepts only allow-listed content types;
* refuses non-http(s) schemes and, unless explicitly allowed (tests),
  destinations that resolve to loopback/private/link-local addresses —
  re-checked on every redirect hop;
* records the system retrieval time immediately after the response arrives.

401/402/403 are treated as access controls and are never retried or worked
around (no paywall or access-control bypass).
"""
from __future__ import annotations

import ipaddress
import socket
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib import robotparser
from urllib.parse import urljoin, urlsplit

import httpx

ALLOWED_CONTENT_TYPES = (
    "text/html", "application/xhtml+xml", "application/xml", "text/xml",
    "application/rss+xml", "application/atom+xml", "application/json",
    "application/feed+json", "text/plain",
)
KEPT_HEADERS = ("content-type", "content-language", "last-modified", "etag", "date", "content-length")


class FetchError(Exception):
    """Base class. ``retryable`` tells the job layer whether a retry may help."""
    retryable = False
    code = "FETCH_ERROR"


class SourceUnavailable(FetchError):
    retryable = True
    code = "SOURCE_UNAVAILABLE"


class AccessDenied(FetchError):
    code = "ACCESS_DENIED"


class RobotsDisallowed(FetchError):
    code = "ROBOTS_DISALLOWED"


class ContentRejected(FetchError):
    code = "CONTENT_REJECTED"


class DestinationRefused(FetchError):
    code = "DESTINATION_REFUSED"


@dataclass(frozen=True)
class FetchResult:
    requested_url: str
    final_url: str
    status_code: int
    content: bytes
    content_type: str
    headers: dict[str, str]
    retrieved_at: datetime
    redirects: tuple[str, ...] = field(default_factory=tuple)

    @property
    def charset(self) -> str | None:
        for part in self.content_type.split(";")[1:]:
            k, _, v = part.strip().partition("=")
            if k.lower() == "charset" and v:
                return v.strip('"').lower()
        return None

    @property
    def media_type(self) -> str:
        return self.content_type.split(";")[0].strip().lower()


class PoliteHttpClient:
    def __init__(self, user_agent: str, *, timeout: float = 30.0, max_bytes: int = 10 * 1024 * 1024,
                 min_interval: float = 5.0, respect_robots: bool = True,
                 allow_private_hosts: bool = False, max_redirects: int = 5,
                 transport: httpx.BaseTransport | None = None):
        self.user_agent = user_agent
        self.max_bytes = max_bytes
        self.min_interval = min_interval
        self.respect_robots = respect_robots
        self.allow_private_hosts = allow_private_hosts
        self.max_redirects = max_redirects
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout), follow_redirects=False, transport=transport,
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
            cookies=None, trust_env=False,
        )
        self._last_request: dict[str, float] = {}
        self._robots: dict[str, robotparser.RobotFileParser | None] = {}
        self._lock = threading.Lock()

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- safety checks -------------------------------------------------------
    def _check_destination(self, url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https"):
            raise DestinationRefused(f"scheme not allowed: {parts.scheme!r}")
        if parts.username or parts.password:
            raise DestinationRefused("credentials in URL are not allowed")
        host = parts.hostname
        if not host:
            raise DestinationRefused("URL has no host")
        if self.allow_private_hosts:
            return
        try:
            infos = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80))
        except socket.gaierror as exc:
            raise SourceUnavailable(f"DNS resolution failed for {host}: {exc}") from exc
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                raise DestinationRefused(f"{host} resolves to a non-public address")

    def _throttle(self, host: str) -> None:
        with self._lock:
            last = self._last_request.get(host)
            now = time.monotonic()
            wait = 0.0 if last is None else self.min_interval - (now - last)
            self._last_request[host] = now + max(wait, 0.0)
        if wait > 0:
            time.sleep(wait)

    def _robots_allows(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            parser: robotparser.RobotFileParser | None = robotparser.RobotFileParser()
            try:
                resp = self._raw_get(urljoin(origin, "/robots.txt"), check_robots=False)
                if resp.status_code == 200:
                    parser.parse(resp.content.decode("utf-8", errors="replace").splitlines())
                elif resp.status_code in (401, 403):
                    parser.disallow_all = True
                else:
                    parser.allow_all = True
            except SourceUnavailable:
                parser = None  # robots unknown: do not fetch now, retry later
            self._robots[origin] = parser
        parser = self._robots[origin]
        if parser is None:
            raise SourceUnavailable(f"robots.txt for {origin} could not be retrieved")
        return parser.can_fetch(self.user_agent, url)

    # -- fetching --------------------------------------------------------------
    def _raw_get(self, url: str, *, check_robots: bool = True) -> FetchResult:
        self._check_destination(url)
        if check_robots and not self._robots_allows(url):
            raise RobotsDisallowed(f"robots.txt disallows {url}")
        self._throttle(urlsplit(url).hostname or "")
        try:
            with self._client.stream("GET", url) as resp:
                retrieved_at = datetime.now(timezone.utc)
                chunks, size = [], 0
                if resp.status_code < 300 or resp.status_code >= 400:
                    declared = resp.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > self.max_bytes:
                        raise ContentRejected(f"declared size {declared} exceeds limit {self.max_bytes}")
                    for chunk in resp.iter_bytes():
                        size += len(chunk)
                        if size > self.max_bytes:
                            raise ContentRejected(f"response exceeds {self.max_bytes} bytes")
                        chunks.append(chunk)
                headers = {k: resp.headers[k] for k in KEPT_HEADERS if k in resp.headers}
                if "location" in resp.headers:
                    headers["location"] = resp.headers["location"]
                return FetchResult(url, str(resp.url), resp.status_code, b"".join(chunks),
                                   resp.headers.get("content-type", ""), headers, retrieved_at)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            raise SourceUnavailable(f"{type(exc).__name__} fetching {url}: {exc}") from exc

    def get(self, url: str) -> FetchResult:
        redirects: list[str] = []
        current = url
        for _ in range(self.max_redirects + 1):
            result = self._raw_get(current)
            if result.status_code in (301, 302, 303, 307, 308):
                location = result.headers.get("location")
                if not location:
                    raise SourceUnavailable(f"redirect without Location from {current}")
                redirects.append(current)
                current = urljoin(current, location)
                continue
            break
        else:
            raise SourceUnavailable(f"too many redirects starting at {url}")

        if result.status_code in (401, 402, 403):
            raise AccessDenied(f"HTTP {result.status_code} for {current} (access control respected; not bypassed)")
        if result.status_code == 429 or result.status_code >= 500:
            raise SourceUnavailable(f"HTTP {result.status_code} for {current}")
        if result.status_code >= 400:
            raise ContentRejected(f"HTTP {result.status_code} for {current}")
        if not result.media_type.startswith(ALLOWED_CONTENT_TYPES):
            raise ContentRejected(f"content type {result.media_type!r} not allowed for {current}")
        return FetchResult(url, current, result.status_code, result.content, result.content_type,
                           result.headers, result.retrieved_at, tuple(redirects))
