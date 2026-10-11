"""CG1-04 — redirects must not silently attribute an external document to a source."""
from datetime import datetime, timezone

import httpx
import psycopg
import pytest

from conftest import make_collectable_source
from lfhe_collector.adapters import DiscoveredItem
from lfhe_collector.collector import collect_source
from lfhe_collector.http import FetchResult, PoliteHttpClient
from lfhe_collector.snapshots import DatabaseSnapshotSink
from lfhe_shared.storage import LocalObjectStore

pytestmark = pytest.mark.db
HTML = "<html lang='en'><head><title>{t}</title></head><body><p>Synthetic redirect target served by {t}.</p></body></html>"
REDIRECTS = {
    ("example.org", "/same"): "/article",
    ("example.org", "/sub"): "https://news.example.org/article",
    ("example.org", "/ext"): "https://other.example.net/article",
    ("example.org", "/sub-then-ext"): "https://news.example.org/hop",
    ("news.example.org", "/hop"): "https://other.example.net/article",
}


@pytest.fixture
def mock_http():
    requested = []

    def handler(request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        requested.append(f"{host}{path}")
        if (host, path) in REDIRECTS:
            return httpx.Response(302, headers={"location": REDIRECTS[(host, path)]})
        if path == "/article":
            return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"},
                                  content=HTML.format(t=host).encode())
        return httpx.Response(404)

    client = PoliteHttpClient("LFHE-Test/0.1", min_interval=0, respect_robots=False, allow_private_hosts=True,
                              transport=httpx.MockTransport(handler))
    client.requested = requested
    yield client
    client.close()


def collect(pg, src, http, tmp_path):
    with pg.worker() as c:
        out = collect_source(c, src, http, DatabaseSnapshotSink(c, LocalObjectStore(tmp_path)), worker_id="redirect-test")
        snaps = c.execute("SELECT s.* FROM lfhe.article_snapshots s JOIN lfhe.articles a ON a.id=s.article_id "
                          "WHERE a.source_id=%s", (src["id"],)).fetchall()
    return out, snaps


def test_same_domain_redirect_is_followed(pg, mock_http, tmp_path):
    src = make_collectable_source(pg, "HTTP_FETCH", {"urls": ["https://example.org/same"]}, domain="example.org")
    out, [s] = collect(pg, src, mock_http, tmp_path)
    assert out.status == "SUCCESS"
    assert s["final_url"] == "https://example.org/article" and s["redirect_chain"] == ["https://example.org/same"]
    assert (s["final_origin_host"], s["final_url_in_source_domain"]) == ("example.org", True)


def test_permitted_subdomain_redirect_is_followed(pg, mock_http, tmp_path):
    src = make_collectable_source(pg, "HTTP_FETCH", {"urls": ["https://example.org/sub"]}, domain="example.org")
    out, [s] = collect(pg, src, mock_http, tmp_path)
    assert (s["final_origin_host"], s["final_url_in_source_domain"]) == ("news.example.org", True)


@pytest.mark.parametrize("start", ["/ext", "/sub-then-ext"])
def test_external_redirect_rejected_when_external_links_not_allowed(pg, mock_http, tmp_path, start):
    src = make_collectable_source(pg, "HTTP_FETCH", {"urls": [f"https://example.org{start}"]}, domain="example.org")
    out, snaps = collect(pg, src, mock_http, tmp_path)
    assert snaps == [], "external document is not attributed to the source"
    assert out.counts["skipped"] == 1 and out.counts["failed"] == 0
    assert out.item_errors[0]["code"] == "EXTERNAL_REDIRECT_REJECTED" and out.item_errors[0]["retryable"] is False
    assert not any(r.startswith("other.example.net") for r in mock_http.requested), "external hop never requested"


def test_external_redirect_kept_and_flagged_when_external_links_allowed(pg, mock_http, tmp_path):
    src = make_collectable_source(pg, "HTTP_FETCH", {"urls": ["https://example.org/ext"], "allow_external_links": True},
                                  domain="example.org")
    out, [s] = collect(pg, src, mock_http, tmp_path)
    assert s["requested_url"] == "https://example.org/ext" and s["final_url"] == "https://other.example.net/article"
    assert (s["final_origin_host"], s["final_url_in_source_domain"]) == ("other.example.net", False)
    assert s["source_state"]["final_url"] == "https://other.example.net/article"
    assert s["title_original"] == "other.example.net"


def test_database_refuses_external_origin_when_not_allowed(pg, tmp_path):
    src = make_collectable_source(pg, "HTTP_FETCH", {"urls": ["https://example.org/x"]}, domain="example.org")
    fetched = FetchResult("https://example.org/x", "https://evil.example.net/x", 200,
                          HTML.format(t="x").encode(), "text/html; charset=utf-8", {}, datetime.now(timezone.utc),
                          ("https://example.org/x",))
    with pg.worker() as c:
        run = c.execute("SELECT lfhe.start_collection_run(%s, NULL, 'redirect-test') AS id", (src["id"],)).fetchone()["id"]
        with pytest.raises(psycopg.errors.CheckViolation, match="EXTERNAL_ORIGIN_NOT_ALLOWED"):
            DatabaseSnapshotSink(c, LocalObjectStore(tmp_path)).store(
                src, DiscoveredItem(url="https://example.org/x"), "https://example.org/x", fetched, str(run))
        # look-alike suffix is not a subdomain
        assert c.execute("SELECT lfhe.url_host('https://User@NotExample.org:8443/a?b') AS h").fetchone()["h"] == "notexample.org"
