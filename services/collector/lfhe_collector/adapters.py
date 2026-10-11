"""Collection adapters (DS §28 preferred order: official API → RSS/Atom →
structured feed → HTTP fetch). Browser automation has no adapter in Phase 1.

An adapter only *discovers* candidate items (URL + whatever timestamps the
feed/API states). Fetching and storing the article itself is done by the
collector so that every item goes through the same polite client and the
same snapshot rules.

Timestamps are recorded exactly as the source states them, with their basis;
nothing is inferred. "updated" values are never treated as publication time.
"""
from __future__ import annotations

import calendar
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar
from urllib.parse import urljoin, urlsplit

import defusedxml.ElementTree as SafeET
import feedparser
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError, model_validator

from lfhe_shared.credentials import credential_key_paths, credential_url_paths, source_config_problems

from .http import FetchResult, PoliteHttpClient


class AdapterConfigError(ValueError):
    pass


@dataclass(frozen=True)
class DiscoveredItem:
    url: str
    title: str | None = None
    published_at: datetime | None = None          # stated publication time (UTC)
    published_basis: str | None = None             # lfhe.public_availability_basis value
    published_field: str | None = None             # where it came from, e.g. "rss:pubDate"
    updated_at: datetime | None = None             # stated last-modified time (not publication)
    language_hint: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class _StrictConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    allow_external_links: bool = False
    max_items: int = Field(default=50, ge=1, le=500)
    # Used only when the source's retention_mode is PERMITTED_EXCERPT.
    excerpt_max_chars: int = Field(default=500, ge=50, le=5000)

    @model_validator(mode="before")
    @classmethod
    def _no_credentials(cls, data):
        # Mirror of the database rule (CG1-03 / CG1-08); paths only, never values.
        problems = credential_key_paths(data) + credential_url_paths(data)
        if problems:
            raise ValueError(f"credentials not allowed in collection config (found at {', '.join(problems)})")
        return data


class Adapter:
    method: ClassVar[str]
    config_model: ClassVar[type[_StrictConfig]]

    def __init__(self, config: dict):
        try:
            self.config = self.config_model.model_validate(config)
        except ValidationError as exc:
            # never echo input values (they could contain a secret)
            detail = "; ".join(f"{'.'.join(map(str, e['loc'])) or '$'}: {e['msg']}"
                               for e in exc.errors(include_input=False, include_url=False))
            raise AdapterConfigError(f"{self.method} config invalid: {detail}") from None

    def discover(self, http: PoliteHttpClient) -> list[DiscoveredItem]:  # pragma: no cover
        raise NotImplementedError


def _struct_to_dt(value) -> datetime | None:
    if not value:
        return None
    return datetime.fromtimestamp(calendar.timegm(value), tz=timezone.utc)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None  # a timestamp without zone is ambiguous: do not guess
    return dt.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
class RssAtomConfig(_StrictConfig):
    feed_url: HttpUrl


class RssAtomAdapter(Adapter):
    method = "RSS_ATOM"
    config_model = RssAtomConfig

    def discover(self, http: PoliteHttpClient) -> list[DiscoveredItem]:
        feed_resp = http.get(str(self.config.feed_url))
        # No base URI is given to feedparser: it would otherwise rewrite
        # source-stated identifiers (e.g. GUIDs) relative to the feed URL.
        # Item links are resolved explicitly below with urljoin.
        parsed = feedparser.parse(feed_resp.content, response_headers={
            "content-type": feed_resp.content_type,
        })
        if parsed.bozo and not parsed.entries:
            raise AdapterConfigError(f"feed could not be parsed: {parsed.get('bozo_exception')}")
        language = (parsed.feed.get("language") or None)
        items = []
        for entry in parsed.entries[: self.config.max_items]:
            # dict.get bypasses feedparser's FeedParserDict key fallbacks (it maps
            # a missing updated_parsed to published_parsed and similar), which
            # would blur publication vs. update time.
            raw = lambda key: dict.get(entry, key)  # noqa: E731
            link = raw("link")
            if not link:
                continue
            published = _struct_to_dt(raw("published_parsed"))
            items.append(DiscoveredItem(
                url=urljoin(feed_resp.final_url, link),
                title=raw("title"),
                published_at=published,
                published_basis="RSS_TIMESTAMP" if published else None,
                published_field=("feed:published" if published else None),
                updated_at=_struct_to_dt(raw("updated_parsed")),
                language_hint=language,
                metadata={k: v for k, v in {
                    "guid": raw("id"),
                    "author": raw("author"),
                    "feed_url": str(self.config.feed_url),
                    "feed_version": parsed.get("version"),
                }.items() if v},
            ))
        return items


# ---------------------------------------------------------------------------
class SitemapConfig(_StrictConfig):
    sitemap_url: HttpUrl


class SitemapAdapter(Adapter):
    """STRUCTURED_FEED: XML sitemap. <lastmod> is a modification time, so it is
    recorded as updated_at with basis SITEMAP_TIMESTAMP — never as publication."""
    method = "STRUCTURED_FEED"
    config_model = SitemapConfig
    NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    def discover(self, http: PoliteHttpClient) -> list[DiscoveredItem]:
        resp = http.get(str(self.config.sitemap_url))
        try:
            root = SafeET.fromstring(resp.content)
        except Exception as exc:  # defusedxml raises on entities / malformed XML
            raise AdapterConfigError(f"sitemap could not be parsed safely: {exc}") from exc
        items = []
        for url_el in root.findall("sm:url", self.NS)[: self.config.max_items]:
            loc = url_el.findtext("sm:loc", default="", namespaces=self.NS).strip()
            if not loc:
                continue
            lastmod = _parse_iso(url_el.findtext("sm:lastmod", default=None, namespaces=self.NS))
            items.append(DiscoveredItem(
                url=loc, updated_at=lastmod,
                metadata={"sitemap_url": str(self.config.sitemap_url),
                          **({"sitemap_lastmod_basis": "SITEMAP_TIMESTAMP"} if lastmod else {})},
            ))
        return items


# ---------------------------------------------------------------------------
class OfficialApiConfig(_StrictConfig):
    endpoint: HttpUrl
    items_path: str = Field(default="items", pattern=r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$")
    url_field: str = "url"
    title_field: str | None = "title"
    published_field: str | None = "published"


class OfficialApiAdapter(Adapter):
    """OFFICIAL_API: unauthenticated public JSON API (authenticated APIs need a
    secret-manager integration and are out of Phase 1 scope)."""
    method = "OFFICIAL_API"
    config_model = OfficialApiConfig

    def discover(self, http: PoliteHttpClient) -> list[DiscoveredItem]:
        resp = http.get(str(self.config.endpoint))
        try:
            data: Any = json.loads(resp.content.decode(resp.charset or "utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise AdapterConfigError(f"API response is not valid JSON: {exc}") from exc
        for part in self.config.items_path.split("."):
            data = data.get(part) if isinstance(data, dict) else None
        if not isinstance(data, list):
            raise AdapterConfigError(f"items_path {self.config.items_path!r} did not yield a list")
        items = []
        for obj in data[: self.config.max_items]:
            if not isinstance(obj, dict) or not obj.get(self.config.url_field):
                continue
            published = _parse_iso(obj.get(self.config.published_field)) if self.config.published_field else None
            items.append(DiscoveredItem(
                url=urljoin(resp.final_url, str(obj[self.config.url_field])),
                title=obj.get(self.config.title_field) if self.config.title_field else None,
                published_at=published,
                published_basis="SOURCE_PUBLISHED_TIMESTAMP" if published else None,
                published_field=f"api:{self.config.published_field}" if published else None,
                metadata={"api_endpoint": str(self.config.endpoint)},
            ))
        return items


# ---------------------------------------------------------------------------
class HttpFetchConfig(_StrictConfig):
    urls: list[HttpUrl] = Field(min_length=1, max_length=100)


class HttpFetchAdapter(Adapter):
    """HTTP_FETCH: an explicit list of pages to snapshot (no crawling)."""
    method = "HTTP_FETCH"
    config_model = HttpFetchConfig

    def discover(self, http: PoliteHttpClient) -> list[DiscoveredItem]:
        return [DiscoveredItem(url=str(u)) for u in self.config.urls[: self.config.max_items]]


ADAPTERS: dict[str, type[Adapter]] = {
    a.method: a for a in (RssAtomAdapter, SitemapAdapter, OfficialApiAdapter, HttpFetchAdapter)
}


def build_adapter(method: str, config: dict) -> Adapter:
    if method not in ADAPTERS:
        raise AdapterConfigError(f"no adapter for collection method {method!r} in Phase 1")
    problems = source_config_problems(method, config)  # mirror of the database rule (CG1-08A)
    if problems:
        raise AdapterConfigError(f"{method} config invalid (found at {', '.join(problems)})")
    return ADAPTERS[method](config)


def url_within_domain(url: str, canonical_domain: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    domain = canonical_domain.lower()
    return host == domain or host.endswith("." + domain)


__all__ = ["ADAPTERS", "Adapter", "AdapterConfigError", "DiscoveredItem", "FetchResult",
           "build_adapter", "url_within_domain"]
