"""K-05 validation script: discovery never guesses, and the two-pass evaluation
works against the real collector (local synthetic site; the real run is the PO's)."""
import importlib.util
import json

import pytest

from conftest import REPO_ROOT, make_collectable_source
from lfhe_collector.collector import make_collect_handler
from lfhe_collector.snapshots import DatabaseSnapshotSink
from lfhe_shared.jobs import JobQueue
from lfhe_shared.storage import LocalObjectStore

pytestmark = pytest.mark.db

_spec = importlib.util.spec_from_file_location("k05", REPO_ROOT / "scripts" / "k05_validate_sources.py")
k05 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(k05)


def test_feed_discovery_reads_the_page_and_never_constructs_urls(site, http_client):
    url, detail = k05.resolve_feed(http_client, site.url("/feeds/rss.xml"), "127.0.0.1", None)
    assert url == site.url("/feeds/rss.xml") and detail["method"] == "DISCOVERY_PAGE_IS_FEED"
    url, detail = k05.resolve_feed(http_client, site.url("/k05/index.html"), "127.0.0.1", None)
    assert url is None                                       # two verified feeds → ambiguous → unresolved
    assert set(detail["verified"]) == {site.url("/feeds/rss.xml"), site.url("/feeds/atom.xml")}
    assert all("elsewhere.invalid" not in c for c in detail["candidates"])     # off-site links ignored
    url, _ = k05.resolve_feed(http_client, site.url("/k05/index.html"), "127.0.0.1", "Top Stories")
    assert url == site.url("/feeds/atom.xml")
    url, detail = k05.resolve_feed(http_client, site.url("/k05/index.html"), "127.0.0.1", "Archived")
    assert url is None and detail["verified"] == []          # listed but not a working feed → unresolved


def test_sitemap_discovery_follows_only_the_official_index(site, http_client):
    url, detail = k05.resolve_sitemap(http_client, site.url("/k05/sitemap-index.xml"), "127.0.0.1", None)
    assert url is None and len(detail["urlsets"]) == 2
    url, _ = k05.resolve_sitemap(http_client, site.url("/k05/sitemap-index.xml"), "127.0.0.1", "news")
    assert url == site.url("/k05/sitemap-news.xml")


def test_two_pass_evaluation_with_the_real_job_handler(pg, site, http_client, tmp_path):
    src = make_collectable_source(pg, "RSS_ATOM", {"feed_url": site.url("/feeds/rss.xml"), "max_items": 3},
                                  retention="PERMITTED_EXCERPT")
    with pg.worker() as db:
        queue = JobQueue(db, "k05-test")
        handler = make_collect_handler(db, http_client, DatabaseSnapshotSink(db, LocalObjectStore(tmp_path)), "k05-test")
        runs = [k05.run_pass(db, queue, handler, str(src["id"]), "pass1"),
                k05.run_pass(db, queue, handler, str(src["id"]), "pass2")]
        result = k05.evaluate(db, str(src["id"]), runs, None)
    assert runs[0]["counts"]["new"] >= 1 and runs[1]["counts"]["new"] == 0
    assert result["F3_job_collection"] == result["F4_provenance_complete"] == "PASS"
    assert result["F5_second_pass_no_uncontrolled_duplicates"] == "PASS" and result["duplicate_state_groups"] == 0


def test_template_requires_po_confirmation_for_every_source():
    template = json.loads((REPO_ROOT / "scripts" / "k05_sources.template.json").read_text(encoding="utf-8"))
    ids = [s["id"] for s in template["sources"]]
    assert ids == [f"K05-0{i}" for i in range(1, 9)]
    assert all(s["po_confirmed"] is False and s["discovery_page"] is None for s in template["sources"])
    assert {s["method"] for s in template["sources"]} == {"RSS_ATOM", "HTTP_FETCH", "STRUCTURED_FEED"}
