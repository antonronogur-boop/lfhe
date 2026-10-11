"""CG1-02 — snapshot identity = source state; clean-text identity is separate;
routine duplicates write no object-store data."""
import threading
from datetime import datetime, timezone

import pytest

from conftest import make_collectable_source
from lfhe_collector.adapters import DiscoveredItem
from lfhe_collector.collector import collect_source
from lfhe_collector.http import FetchResult
from lfhe_collector.snapshots import DatabaseSnapshotSink
from lfhe_shared.canonical_json import canonical_sha256
from lfhe_shared.integrity import verify_snapshot_states
from lfhe_shared.storage import LocalObjectStore, find_unreferenced_objects

pytestmark = pytest.mark.db
BODY = "<body><article><p>Same synthetic body text for identity tests.</p></article></body>"


def page(title="Notice A", published="2026-10-05T08:30:00+00:00", modified=None, script="t1", spaces=""):
    meta = f'<meta property="article:published_time" content="{published}">' if published else ""
    if modified:
        meta += f'<meta property="article:modified_time" content="{modified}">'
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>{title}</title>{meta}"
            f"<script>var token='{script}';</script></head>{spaces}{BODY}</html>")


@pytest.fixture
def setup(pg, site, http_client, tmp_path):
    store = LocalObjectStore(tmp_path / "objects")
    src = make_collectable_source(pg, "HTTP_FETCH", {"urls": [site.url("/changing.html")]})

    def collect(body):
        site.changing_body = body
        with pg.worker() as c:
            return collect_source(c, src, http_client, DatabaseSnapshotSink(c, store), worker_id="identity-test")

    def versions():
        with pg.worker() as c:
            return c.execute(
                "SELECT s.*, t.text_sha256, t.text_content FROM lfhe.article_snapshots s "
                "JOIN lfhe.articles a ON a.id=s.article_id "
                "LEFT JOIN lfhe.text_representations t ON t.snapshot_id=s.id "
                "WHERE a.source_id=%s ORDER BY s.snapshot_version", (src["id"],)).fetchall()

    def objects():
        return list(store.iter_keys())

    return src, store, collect, versions, objects


def test_identical_raw_content_is_duplicate_and_writes_nothing(pg, setup):
    src, store, collect, versions, objects = setup
    assert collect(page()).counts["new"] == 1
    assert collect(page()).counts["duplicate"] == 1
    assert len(versions()) == 1 and len(objects()) == 1
    with pg.worker() as c:
        assert find_unreferenced_objects(store, c) == []


def test_cosmetic_raw_change_is_duplicate_and_creates_no_orphan(pg, setup):
    src, store, collect, versions, objects = setup
    collect(page())
    out = collect(page(script="t2-volatile", spaces="\n\n   "))  # raw bytes differ, evidence/provenance do not
    assert out.counts["duplicate"] == 1
    assert len(versions()) == 1 and len(objects()) == 1, "routine duplicate must not write a raw object"
    with pg.worker() as c:
        assert find_unreferenced_objects(store, c) == []


def test_same_body_text_changed_title_is_new_version(pg, setup):
    src, store, collect, versions, objects = setup
    collect(page(title="Notice A"))
    assert collect(page(title="Notice A — corrected headline")).counts["revised"] == 1
    v1, v2 = versions()
    assert (v1["title_original"], v2["title_original"]) == ("Notice A", "Notice A — corrected headline")
    assert v1["text_sha256"] == v2["text_sha256"], "clean-text identity unchanged → spans stay stable"
    assert v1["content_identity_sha256"] == v2["content_identity_sha256"]
    assert v1["source_state_sha256"] != v2["source_state_sha256"]


def test_same_body_text_changed_publication_and_update_metadata(pg, setup):
    src, store, collect, versions, objects = setup
    collect(page(published="2026-10-05T08:30:00+00:00"))
    assert collect(page(published="2026-10-04T06:00:00+00:00")).counts["revised"] == 1
    assert collect(page(published="2026-10-04T06:00:00+00:00",
                        modified="2026-10-06T09:00:00+00:00")).counts["revised"] == 1
    assert collect(page(published=None, modified="2026-10-06T09:00:00+00:00")).counts["revised"] == 1
    v1, v2, v3, v4 = versions()
    assert v1["public_availability_datetime"] == datetime(2026, 10, 5, 8, 30, tzinfo=timezone.utc)
    assert v2["public_availability_datetime"] == datetime(2026, 10, 4, 6, 0, tzinfo=timezone.utc)
    assert v3["source_updated_datetime"] == datetime(2026, 10, 6, 9, 0, tzinfo=timezone.utc)
    assert v4["public_availability_basis"] == "UNKNOWN" and v4["date_status"] == "DATE_UNCERTAIN"
    assert len({v["text_sha256"] for v in (v1, v2, v3, v4)}) == 1
    assert len({v["source_state_sha256"] for v in (v1, v2, v3, v4)}) == 4
    # earlier versions are untouched (replay integrity)
    assert v1["publication_datetime"] == datetime(2026, 10, 5, 8, 30, tzinfo=timezone.utc)


def test_body_text_revision_is_new_version(pg, setup):
    src, store, collect, versions, objects = setup
    collect(page())
    assert collect(page().replace("Same synthetic body text", "Revised synthetic body text")).counts["revised"] == 1
    v1, v2 = versions()
    assert v1["text_sha256"] != v2["text_sha256"]
    assert "Same synthetic" in v1["text_content"] and "Revised synthetic" in v2["text_content"]


def test_source_state_is_stored_and_independently_verifiable(pg, setup):
    src, store, collect, versions, objects = setup
    collect(page())
    [v] = versions()
    assert v["source_state"]["format"] == "lfhe-snapshot-state/1"
    assert canonical_sha256(v["source_state"]) == v["source_state_sha256"]
    assert "system_retrieval_datetime" not in str(v["source_state"]) and "token" not in str(v["source_state"])
    with pg.worker() as c:
        assert verify_snapshot_states(c, str(src["id"])) == []


def test_repeated_concurrent_ingestion_creates_one_version(pg, site, tmp_path):
    store = LocalObjectStore(tmp_path / "objects")
    src = make_collectable_source(pg, "HTTP_FETCH", {"urls": [site.url("/concurrent.html")]})
    url = site.url("/concurrent.html")
    fetched = FetchResult(url, url, 200, page(title="Concurrent").encode(), "text/html; charset=utf-8", {},
                          datetime.now(timezone.utc))
    n = 6
    barrier, outcomes, errors = threading.Barrier(n), [], []

    def worker():
        try:
            with pg.worker() as c:
                run = c.execute("SELECT lfhe.start_collection_run(%s, NULL, 'concurrency-test') AS id",
                                (src["id"],)).fetchone()["id"]
                barrier.wait()
                outcomes.append(DatabaseSnapshotSink(c, store).store(src, DiscoveredItem(url=url), url, fetched, str(run)))
        except Exception as exc:  # surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert sorted(outcomes) == ["DUPLICATE"] * (n - 1) + ["NEW"]
    with pg.worker() as c:
        rows = c.execute("SELECT s.id FROM lfhe.article_snapshots s JOIN lfhe.articles a ON a.id=s.article_id "
                         "WHERE a.source_id=%s", (src["id"],)).fetchall()
        assert len(rows) == 1
        assert find_unreferenced_objects(store, c) == []
