"""Polite, bounded HTTP fetching for public OSINT sources (DS §28, §30).

Guarantees:
* identifies itself with a configured User-Agent; sends no credentials,
  cookies or custom auth headers (none can be configured);
* respects robots.txt (fail-closed semantics, see _fetch_robots) unless
  explicitly disabled; temporary robots failures are never cached permanently;
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
    """Base class. ``retryable`` tells the job layer whether a retry may help.

    Only SourceUnavailable (network errors, timeouts, 429, 5xx, robots.txt
    temporarily unreachable) is retryable. Every other subclass describes a
    permanent condition (access control, robots disallow, rejected content,
    refused destination, domain policy) that a retry cannot change."""
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


class ExternalRedirectRejected(FetchError):
    """A redirect hop left the approved source domain while external links are
    not allowed. The external destination is never requested."""
    code = "EXTERNAL_REDIRECT_REJECTED"


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
                 transport: httpx.BaseTransport | None = None,
                 robots_cache_ttl: float = 24 * 3600.0, robots_failure_ttl: float = 60.0):
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
        self.robots_cache_ttl = robots_cache_ttl
        self.robots_failure_ttl = robots_failure_ttl
        # origin -> (expires_at monotonic, RobotFileParser | SourceUnavailable)
        self._robots: dict[str, tuple[float, object]] = {}
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

    # -- robots.txt (CG1-07: fail closed, no poisoned cache) -------------------
    # Semantics (docs/collection-semantics.md, "robots.txt"):
    #   2xx            parse; policy cached for robots_cache_ttl (default 24 h)
    #   401 / 403      disallow all (fail closed); cached
    #   404 / 410      no robots policy → allow all (RFC 9309 §2.3.1.3); cached
    #   other 4xx      disallow all (fail closed, conservative); cached
    #   429, 5xx       SourceUnavailable (retryable); target NOT fetched
    #   network error  SourceUnavailable (retryable); target NOT fetched
    #   3xx            followed up to ROBOTS_MAX_REDIRECTS hops, every hop through
    #                  the same destination (SSRF) checks; missing Location or
    #                  too many hops → SourceUnavailable; never allow-all
    #   other status   SourceUnavailable (retryable)
    # A temporary failure is remembered only for robots_failure_ttl (default
    # 60 s, shorter than the minimum job backoff) and then retried, so a later
    # attempt with the same client recovers. Body > max_bytes → disallow all.
    ROBOTS_MAX_REDIRECTS = 5

    def _robots_state(self, origin: str):
        now = time.monotonic()
        with self._lock:
            cached = self._robots.get(origin)
        if cached is not None and cached[0] > now:
            return cached[1]
        state = self._fetch_robots(origin)
        ttl = self.robots_failure_ttl if isinstance(state, SourceUnavailable) else self.robots_cache_ttl
        with self._lock:
            self._robots[origin] = (time.monotonic() + ttl, state)
        return state

    def _fetch_robots(self, origin: str):
        """Returns a RobotFileParser, or a SourceUnavailable instance (temporary)."""
        parser = robotparser.RobotFileParser()
        url = urljoin(origin, "/robots.txt")
        try:
            for _ in range(self.ROBOTS_MAX_REDIRECTS + 1):
                resp = self._raw_get(url, check_robots=False)
                code = resp.status_code
                if code in (301, 302, 303, 307, 308):
                    location = resp.headers.get("location")
                    if not location:
                        return SourceUnavailable(f"robots.txt redirect without Location at {url}")
                    url = urljoin(url, location)
                    continue
                if 200 <= code < 300:
                    parser.parse(resp.content.decode("utf-8", errors="replace").splitlines())
                elif code in (404, 410):
                    parser.allow_all = True
                elif code == 429 or code >= 500:
                    return SourceUnavailable(f"robots.txt for {origin} temporarily unavailable (HTTP {code})")
                elif 400 <= code < 500:  # 401, 403 and any other client error: fail closed
                    parser.disallow_all = True
                else:
                    return SourceUnavailable(f"robots.txt for {origin}: unexpected HTTP {code}")
                return parser
            return SourceUnavailable(f"robots.txt for {origin}: too many redirects")
        except SourceUnavailable as exc:
            return exc
        except ContentRejected:
            parser.disallow_all = True  # oversized robots.txt: fail closed
            return parser

    def _robots_allows(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parts = urlsplit(url)
        state = self._robots_state(f"{parts.scheme}://{parts.netloc}")
        if isinstance(state, SourceUnavailable):
            raise SourceUnavailable(f"robots.txt unavailable, {url} not fetched: {state}")
        return state.can_fetch(self.user_agent, url)

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

    def get(self, url: str, *, redirect_guard=None) -> FetchResult:
        """Fetch *url*, following redirects manually.

        ``redirect_guard(next_url)`` (optional) is called for every redirect
        target BEFORE it is requested; it may raise a FetchError (e.g.
        ExternalRedirectRejected) to stop the chain."""
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
                if redirect_guard is not None:
                    redirect_guard(current)
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
