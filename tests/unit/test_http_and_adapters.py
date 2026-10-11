"""P1-08 — polite HTTP client, adapters, URL canonicalisation (no database)."""
import time
from datetime import datetime, timezone

import pytest

from lfhe_collector.adapters import AdapterConfigError, build_adapter, url_within_domain
from lfhe_collector.http import (AccessDenied, ContentRejected, DestinationRefused, PoliteHttpClient,
                                 RobotsDisallowed, SourceUnavailable)
from lfhe_collector.urls import canonicalize_url


# -- HTTP client ---------------------------------------------------------------
def test_successful_fetch_records_retrieval_time_and_headers(site, http_client):
    before = datetime.now(timezone.utc)
    r = http_client.get(site.url("/news/logistics-training-en.html"))
    assert r.status_code == 200 and r.media_type == "text/html" and r.charset == "utf-8"
    assert before <= r.retrieved_at <= datetime.now(timezone.utc)
    assert b"annual logistics training" in r.content


def test_robots_txt_is_respected_and_disallowed_page_never_requested(site, http_client):
    with pytest.raises(RobotsDisallowed):
        http_client.get(site.url("/private/internal.html"))
    assert "/private/internal.html" not in site.requests


def test_access_controls_are_not_bypassed(site, http_client):
    with pytest.raises(AccessDenied):
        http_client.get(site.url("/forbidden.html"))
    with pytest.raises(AccessDenied):
        http_client.get(site.url("/paywall.html"))
    assert site.requests.count("/forbidden.html") == 1, "no retry / workaround on 403"


def test_server_errors_are_source_unavailable(site, http_client):
    with pytest.raises(SourceUnavailable):
        http_client.get(site.url("/down/feed.xml"))


def test_size_and_content_type_limits(site, http_client):
    with pytest.raises(ContentRejected, match="exceeds"):
        http_client.get(site.url("/big.html"))
    with pytest.raises(ContentRejected, match="content type"):
        http_client.get(site.url("/binary.bin"))


def test_redirects_followed_and_recorded(site, http_client):
    r = http_client.get(site.url("/redirect.html"))
    assert r.final_url.endswith("/news/logistics-training-en.html")
    assert r.redirects == (site.url("/redirect.html"),)


def test_destination_rules(site):
    strict = PoliteHttpClient("t/0", min_interval=0, allow_private_hosts=False)
    with pytest.raises(DestinationRefused, match="non-public"):
        strict.get(site.url("/news/logistics-training-en.html"))
    with pytest.raises(DestinationRefused, match="scheme"):
        strict.get("file:///etc/passwd")
    with pytest.raises(DestinationRefused, match="credentials"):
        strict.get("http://user:pw@example.org/")
    strict.close()


def test_per_host_minimum_interval(site):
    client = PoliteHttpClient("t/0", min_interval=0.3, allow_private_hosts=True, respect_robots=False)
    start = time.monotonic()
    for _ in range(3):
        client.get(site.url("/news/no-date-en.html"))
    assert time.monotonic() - start >= 0.55
    client.close()


def test_unreachable_host_is_source_unavailable():
    client = PoliteHttpClient("t/0", min_interval=0, allow_private_hosts=True, respect_robots=False, timeout=2)
    with pytest.raises(SourceUnavailable):
        client.get("http://127.0.0.1:9/never")
    client.close()


# -- Adapters -------------------------------------------------------------------
def test_rss_adapter_preserves_stated_timestamps_only(site, http_client):
    items = build_adapter("RSS_ATOM", {"feed_url": site.url("/feeds/rss.xml")}).discover(http_client)
    by_guid = {i.metadata["guid"]: i for i in items}
    assert by_guid["synthetic-001"].published_at == datetime(2026, 10, 5, 8, 30, tzinfo=timezone.utc)
    assert by_guid["synthetic-001"].published_basis == "RSS_TIMESTAMP"
    assert by_guid["synthetic-002"].published_at is None, "no date stated → none invented"
    assert by_guid["synthetic-002"].published_basis is None
    assert all(i.language_hint == "en" for i in items)


def test_atom_updated_is_not_publication(site, http_client):
    [item] = build_adapter("RSS_ATOM", {"feed_url": site.url("/feeds/atom.xml")}).discover(http_client)
    assert item.published_at is None
    assert item.updated_at == datetime(2026, 10, 6, 10, 0, tzinfo=timezone.utc)


def test_sitemap_lastmod_is_an_update_time(site, http_client):
    items = build_adapter("STRUCTURED_FEED", {"sitemap_url": site.url("/sitemap.xml")}).discover(http_client)
    assert items[0].updated_at is not None and items[0].published_at is None
    assert items[0].metadata["sitemap_lastmod_basis"] == "SITEMAP_TIMESTAMP"
    assert items[1].updated_at is None


def test_api_adapter_rejects_ambiguous_timestamps(site, http_client):
    items = build_adapter("OFFICIAL_API", {
        "endpoint": site.url("/api/items.json"), "items_path": "data.items",
        "url_field": "link", "title_field": "headline", "published_field": "date",
    }).discover(http_client)
    assert items[0].published_at == datetime(2026, 10, 5, 8, 30, tzinfo=timezone.utc)
    assert items[0].published_basis == "SOURCE_PUBLISHED_TIMESTAMP"
    assert items[1].published_at is None, "timestamp without timezone is not guessed"


def test_adapter_config_is_strict():
    with pytest.raises(AdapterConfigError):
        build_adapter("RSS_ATOM", {"feed_url": "https://x.example.org/f.xml", "headers": {"a": "b"}})
    with pytest.raises(AdapterConfigError):
        build_adapter("RSS_ATOM", {})
    with pytest.raises(AdapterConfigError, match="no adapter"):
        build_adapter("BROWSER_AUTOMATION", {"url": "https://x.example.org"})
    with pytest.raises(AdapterConfigError):
        build_adapter("HTTP_FETCH", {"urls": ["ftp://x.example.org/a"]})


def test_sitemap_entity_expansion_is_refused(site, http_client, tmp_path):
    bomb = (b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;">]>'
            b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>&b;</loc></url></urlset>')
    from lfhe_collector.adapters import SitemapAdapter
    adapter = SitemapAdapter({"sitemap_url": "https://x.example.org/s.xml"})

    class FakeHttp:
        def get(self, url):
            from lfhe_collector.http import FetchResult
            return FetchResult(url, url, 200, bomb, "application/xml", {}, datetime.now(timezone.utc))
    with pytest.raises(AdapterConfigError, match="safely"):
        adapter.discover(FakeHttp())


# -- URLs -------------------------------------------------------------------------
@pytest.mark.parametrize("raw,expected", [
    ("HTTP://Example.ORG:80/a?utm_source=x&b=2&a=1#frag", "http://example.org/a?a=1&b=2"),
    ("https://example.org", "https://example.org/"),
    ("https://example.org:8443/x?fbclid=1", "https://example.org:8443/x"),
])
def test_canonicalize_url(raw, expected):
    assert canonicalize_url(raw) == expected


def test_url_within_domain():
    assert url_within_domain("https://news.example.org/x", "example.org")
    assert not url_within_domain("https://example.org.evil.test/x", "example.org")
