"""Phase 1 acceptance criteria F1–F10 (Handoff Pack v1.1 §17), one test each.

Each test exercises the criterion end-to-end through the real database
functions, roles and collector; detailed edge cases live in the integration
and security suites (referenced per test).
"""
import json
import subprocess
import sys
import uuid

import psycopg
import pytest

from conftest import REPO_ROOT, make_collectable_source
from lfhe_collector.collector import make_collect_handler
from lfhe_collector.snapshots import DatabaseSnapshotSink
from lfhe_shared.audit import verify_chain
from lfhe_shared.jobs import JobQueue
from lfhe_shared.spans import locate_unique, resolve_span
from lfhe_shared.storage import LocalObjectStore

pytestmark = pytest.mark.db


def source_payload(**over):
    return {"name": f"acceptance-{uuid.uuid4().hex[:8]}", "canonical_domain": "127.0.0.1",
            "source_type": "OFFICIAL_GOVERNMENT", "primary_language": "en",
            "collection_method": "HTTP_FETCH", "collection_config": {"urls": ["http://127.0.0.1/x"]},
            "retention_mode": "FULL", **over}


def run_queue_until_done(pg, http_client, store, source_id):
    with pg.worker() as c:
        c.execute("SELECT lfhe.enqueue_due_collections()")
        q = JobQueue(c, "acceptance-worker")
        handlers = {"COLLECT_SOURCE": make_collect_handler(c, http_client, DatabaseSnapshotSink(c, store), q.worker_id)}
        for _ in range(30):
            q.run_once(handlers, limit=10)
            row = c.execute("SELECT status, attempt_count FROM lfhe.processing_jobs WHERE object_id=%s "
                            "ORDER BY created_at DESC LIMIT 1", (str(source_id),)).fetchone()
            if row and (row["status"] != "PENDING" or row["attempt_count"] > 0):
                return row["status"]
    return None


def test_F1_authorised_user_can_create_source_others_cannot(pg, make_user):
    analyst, viewer = make_user("ANALYST"), make_user("VIEWER")
    with pg.as_user(analyst) as c:
        sid = c.execute("SELECT lfhe.create_source(%s::jsonb) AS id", (json.dumps(source_payload()),)).fetchone()["id"]
        row = c.execute("SELECT active, collection_method_approved FROM lfhe.sources WHERE id=%s", (sid,)).fetchone()
    assert row == {"active": False, "collection_method_approved": False}, "new sources start inactive/unapproved"
    with pg.as_user(viewer) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("SELECT lfhe.create_source(%s::jsonb)", (json.dumps(source_payload()),))


def test_F2_activation_follows_permissions(pg, make_user):
    analyst, reviewer = make_user("ANALYST"), make_user("REVIEWER")
    with pg.as_user(analyst) as c:
        sid = c.execute("SELECT lfhe.create_source(%s::jsonb) AS id", (json.dumps(source_payload()),)).fetchone()["id"]
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("SELECT lfhe.set_source_active(%s, true, 'analyst attempt')", (sid,))
    with pg.as_user(reviewer) as c:
        with pytest.raises(psycopg.errors.CheckViolation):
            c.execute("SELECT lfhe.set_source_active(%s, true, 'not yet approved')", (sid,))
        c.execute("SELECT lfhe.set_collection_method_approval(%s, true, 'acceptance approval')", (sid,))
        c.execute("SELECT lfhe.set_source_active(%s, true, 'acceptance activation')", (sid,))
        assert c.execute("SELECT active FROM lfhe.sources WHERE id=%s", (sid,)).fetchone()["active"] is True
        c.execute("SELECT lfhe.set_source_active(%s, false, 'acceptance deactivation')", (sid,))
        assert c.execute("SELECT active FROM lfhe.sources WHERE id=%s", (sid,)).fetchone()["active"] is False
    with pg.worker() as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("SELECT lfhe.set_source_active(%s, true, 'worker attempt')", (sid,))


def test_F3_approved_method_retrieves_article_via_scheduled_job(pg, site, http_client, tmp_path):
    src = make_collectable_source(pg, "RSS_ATOM", {"feed_url": site.url("/feeds/rss.xml")})
    assert run_queue_until_done(pg, http_client, LocalObjectStore(tmp_path), src["id"]) == "SUCCESS"
    with pg.worker() as c:
        urls = {r["canonical_url"] for r in c.execute("SELECT canonical_url FROM lfhe.articles WHERE source_id=%s",
                                                      (src["id"],)).fetchall()}
    assert site.url("/news/logistics-training-en.html") in urls and site.url("/news/navchannia-uk.html") in urls


def test_F4_provenance_is_complete(pg, site, http_client, tmp_path):
    store = LocalObjectStore(tmp_path)
    src = make_collectable_source(pg, "RSS_ATOM", {"feed_url": site.url("/feeds/rss.xml")})
    run_queue_until_done(pg, http_client, store, src["id"])
    with pg.worker() as c:
        s = c.execute("SELECT s.*, a.source_id FROM lfhe.article_snapshots s JOIN lfhe.articles a ON a.id=s.article_id "
                      "WHERE a.source_id=%s AND a.canonical_url LIKE '%%logistics-training-en.html'", (src["id"],)).fetchone()
        t = c.execute("SELECT * FROM lfhe.text_representations WHERE snapshot_id=%s", (s["id"],)).fetchone()
    provenance = {
        "source": s["source_id"], "URL": s["final_url"], "title": s["title_original"],
        "permitted content representation": t["text_content"], "publication metadata": s["publication_datetime"],
        "public-availability metadata": (s["public_availability_datetime"], s["public_availability_basis"],
                                         s["public_availability_confidence"]),
        "retrieval metadata": (s["system_retrieval_datetime"], s["http_status"], s["collection_run_id"]),
        "language": s["language"], "content hash": (s["raw_content_sha256"], t["text_sha256"]),
        "snapshot metadata": (s["snapshot_version"], s["retention_mode_applied"], s["raw_storage_key"]),
    }
    missing = [k for k, v in provenance.items() if v is None or (isinstance(v, tuple) and None in v)]
    assert missing == []
    assert store.get(s["raw_storage_key"])  # raw bytes retrievable and hash-verified


def test_F5_rerun_creates_no_uncontrolled_duplicates(pg, site, http_client, tmp_path):
    store = LocalObjectStore(tmp_path)
    src = make_collectable_source(pg, "RSS_ATOM", {"feed_url": site.url("/feeds/rss.xml")})
    from lfhe_collector.collector import collect_source
    counts = []
    for _ in range(3):
        with pg.worker() as c:
            counts.append(collect_source(c, src, http_client, DatabaseSnapshotSink(c, store),
                                         worker_id="acceptance-worker").counts)
    assert [x["new"] for x in counts] == [2, 0, 0] and [x["duplicate"] for x in counts] == [0, 2, 2]
    with pg.worker() as c:
        n = c.execute("SELECT count(*) AS a, count(DISTINCT s.id) AS s FROM lfhe.articles a "
                      "JOIN lfhe.article_snapshots s ON s.article_id=a.id WHERE a.source_id=%s", (src["id"],)).fetchone()
    assert n == {"a": 2, "s": 2}


def test_F6_runs_and_errors_are_logged(pg, site, http_client, tmp_path):
    src = make_collectable_source(pg, "RSS_ATOM", {"feed_url": site.url("/down/feed.xml")})
    assert run_queue_until_done(pg, http_client, LocalObjectStore(tmp_path), src["id"]) == "PENDING", "retry scheduled with backoff"
    with pg.worker() as c:
        run = c.execute("SELECT status, completed_at FROM lfhe.collection_runs WHERE source_id=%s", (src["id"],)).fetchone()
        err = c.execute("SELECT error_code FROM lfhe.system_errors WHERE source_id=%s", (src["id"],)).fetchone()
        job = c.execute("SELECT attempt_count, last_error FROM lfhe.processing_jobs WHERE object_id=%s", (str(src["id"]),)).fetchone()
    assert run["status"] == "SOURCE_UNAVAILABLE" and run["completed_at"] is not None
    assert err["error_code"] == "SOURCE_UNAVAILABLE" and job["attempt_count"] == 1 and job["last_error"]


def test_F7_required_actions_are_audited_in_a_verifiable_chain(pg, site, http_client, tmp_path, make_user):
    admin = make_user("ADMIN")
    src = make_collectable_source(pg, "HTTP_FETCH", {"urls": [site.url("/news/gyakorlat-hu.html")]}, language="hu")
    from lfhe_collector.collector import collect_source
    with pg.worker() as c:
        collect_source(c, src, http_client, DatabaseSnapshotSink(c, LocalObjectStore(tmp_path)), worker_id="acceptance-worker")
    with pg.as_user(admin) as c:
        c.execute("SELECT lfhe.set_source_active(%s, false, 'acceptance audit check')", (src["id"],))
    with pg.admin() as c:
        events = {r["event_type"] for r in c.execute(
            "SELECT event_type FROM lfhe.audit_log WHERE object_id=%s OR object_id IN "
            "(SELECT id::text FROM lfhe.articles WHERE source_id=%s) OR object_id IN "
            "(SELECT s.id::text FROM lfhe.article_snapshots s JOIN lfhe.articles a ON a.id=s.article_id WHERE a.source_id=%s)",
            (str(src["id"]), src["id"], src["id"])).fetchall()}
        assert {"SOURCE_CREATED", "SOURCE_COLLECTION_METHOD_APPROVED", "SOURCE_ACTIVATED", "SOURCE_DEACTIVATED",
                "ARTICLE_CREATED", "ARTICLE_SNAPSHOT_CREATED"} <= events
        assert verify_chain(c).ok
    with pg.as_user(admin) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("DELETE FROM lfhe.audit_log")


def test_F8_no_secret_committed():
    out = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "secret_scan.py")],
                         capture_output=True, text=True, cwd=REPO_ROOT)
    assert out.returncode == 0, out.stdout + out.stderr
    tracked = subprocess.run(["git", "ls-files"], capture_output=True, text=True, cwd=REPO_ROOT).stdout.split()
    assert not [f for f in tracked if f.split("/")[-1].startswith(".env") and f != ".env.example"]


def test_F9_authentication_and_server_side_authorisation(pg, make_user):
    viewer = make_user("VIEWER")
    with pg.as_anon() as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("SELECT * FROM lfhe.sources")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("SELECT lfhe.create_source('{}'::jsonb)")
    with pg.as_role("authenticated", {"sub": str(uuid.uuid4()), "role": "authenticated"}) as c:  # forged / unknown user
        assert c.execute("SELECT count(*) AS n FROM lfhe.sources").fetchone()["n"] == 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("SELECT lfhe.create_source(%s::jsonb)", (json.dumps(source_payload()),))
    with pg.as_service_role() as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("SELECT lfhe.create_source(%s::jsonb)", (json.dumps(source_payload()),))
    with pg.as_user(viewer) as c:
        assert {r["p"] for r in c.execute("SELECT lfhe.my_permissions() AS p").fetchall()} == \
            {"SOURCE_READ", "ARTICLE_READ"}
        assert c.execute("SELECT count(*) AS n FROM lfhe.audit_log").fetchone()["n"] == 0, "no AUDIT_READ → no rows"
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("SELECT lfhe.set_source_active(%s, true, 'viewer attempt')", (uuid.uuid4(),))


def test_F10_exact_original_language_snapshot_grounding(pg, site, http_client, tmp_path):
    src = make_collectable_source(pg, "HTTP_FETCH", {"urls": [site.url("/news/navchannia-uk.html")]}, language="uk")
    from lfhe_collector.collector import collect_source
    with pg.worker() as c:
        collect_source(c, src, http_client, DatabaseSnapshotSink(c, LocalObjectStore(tmp_path)), worker_id="acceptance-worker")
        t = c.execute("SELECT t.* FROM lfhe.text_representations t JOIN lfhe.article_snapshots s ON s.id=t.snapshot_id "
                      "JOIN lfhe.articles a ON a.id=s.article_id WHERE a.source_id=%s", (src["id"],)).fetchone()
    assert t["is_original_language"] and t["language"] == "uk" and t["offset_unit"] == "UNICODE_CODE_POINT"
    quote = "щорічні логістичні навчання відбудуться наступного місяця"
    span = locate_unique(t["text_content"], quote)
    assert resolve_span(t["text_content"], span.start, span.end, quote).text == quote
    with pg.admin() as c:  # the grounded text can never change underneath a future evidence span
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("UPDATE lfhe.text_representations SET text_content = 'x' WHERE id=%s", (t["id"],))
