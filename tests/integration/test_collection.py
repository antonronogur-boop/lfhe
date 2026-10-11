"""P1-08 — collection runs, failure semantics, scheduling (F3, F6)."""
import psycopg
import pytest

from conftest import make_collectable_source
from lfhe_collector.collector import collect_source, make_collect_handler
from lfhe_shared.jobs import Job, JobQueue, PermanentJobError, RetryableJobError

pytestmark = pytest.mark.db


class MemorySink:
    def __init__(self):
        self.stored = {}

    def store(self, source, item, canonical_url, fetched, run_id):
        previous = self.stored.get(canonical_url)
        self.stored[canonical_url] = fetched.content
        if previous is None:
            return "NEW"
        return "DUPLICATE" if previous == fetched.content else "REVISED"


def run_row(pg, run_id):
    with pg.worker() as c:
        return c.execute("SELECT * FROM lfhe.collection_runs WHERE id=%s", (run_id,)).fetchone()


def test_f3_rss_collection_retrieves_articles_and_counts_outcomes(pg, site, http_client):
    src = make_collectable_source(pg, "RSS_ATOM", {"feed_url": site.url("/feeds/rss.xml")})
    sink = MemorySink()
    with pg.worker() as c:
        out = collect_source(c, src, http_client, sink, worker_id="test-worker")
    assert out.status == "PARTIAL"
    assert out.counts == {"discovered": 5, "new": 2, "revised": 0, "duplicate": 0, "skipped": 2, "failed": 1}
    assert site.url("/news/logistics-training-en.html") in sink.stored
    codes = {e["code"] for e in out.item_errors}
    assert codes == {"EXTERNAL_LINK_SKIPPED", "ROBOTS_DISALLOWED"}
    assert "/private/internal.html" not in site.requests
    row = run_row(pg, out.run_id)
    assert row["status"] == "PARTIAL" and row["items_new"] == 2 and row["items_failed"] == 1
    assert row["completed_at"] is not None and row["worker_id"] == "test-worker"


def test_f6_unavailable_source_is_logged_and_retryable(pg, site, http_client):
    src = make_collectable_source(pg, "RSS_ATOM", {"feed_url": site.url("/down/feed.xml")})
    with pg.worker() as c:
        with pytest.raises(RetryableJobError):
            collect_source(c, src, http_client, MemorySink(), worker_id="test-worker")
        run = c.execute("SELECT * FROM lfhe.collection_runs WHERE source_id=%s", (src["id"],)).fetchone()
        err = c.execute("SELECT error_code, severity FROM lfhe.system_errors WHERE source_id=%s",
                        (src["id"],)).fetchone()
    assert run["status"] == "SOURCE_UNAVAILABLE" and run["error_code"] == "SOURCE_UNAVAILABLE"
    assert err == {"error_code": "SOURCE_UNAVAILABLE", "severity": "WARNING"}


def test_access_denied_source_fails_permanently_without_bypass(pg, site, http_client):
    src = make_collectable_source(pg, "HTTP_FETCH", {"urls": [site.url("/forbidden.html")]})
    with pg.worker() as c:
        with pytest.raises(RetryableJobError):  # all items failed → run FAILED, job retried with backoff
            collect_source(c, src, http_client, MemorySink(), worker_id="test-worker")
        run = c.execute("SELECT status, details FROM lfhe.collection_runs WHERE source_id=%s",
                        (src["id"],)).fetchone()
    assert run["status"] == "FAILED"
    assert run["details"]["item_errors"][0]["code"] == "ACCESS_DENIED"

    feed_forbidden = make_collectable_source(pg, "RSS_ATOM", {"feed_url": site.url("/forbidden.html")})
    with pg.worker() as c:
        with pytest.raises(PermanentJobError):
            collect_source(c, feed_forbidden, http_client, MemorySink(), worker_id="test-worker")


def test_invalid_config_fails_permanently(pg, site, http_client):
    src = make_collectable_source(pg, "OFFICIAL_API", {"endpoint": site.url("/api/items.json"),
                                                       "items_path": "missing.path"})
    with pg.worker() as c:
        with pytest.raises(PermanentJobError):
            collect_source(c, src, http_client, MemorySink(), worker_id="test-worker")
        assert c.execute("SELECT status FROM lfhe.collection_runs WHERE source_id=%s",
                         (src["id"],)).fetchone()["status"] == "FAILED"


def test_non_collectable_source_cannot_start_a_run(pg, site):
    src = make_collectable_source(pg, "HTTP_FETCH", {"urls": [site.url("/news/no-date-en.html")]})
    with pg.admin() as c:
        admin_id = c.execute("SELECT user_id FROM lfhe.user_roles WHERE role_code='ADMIN' LIMIT 1").fetchone()["user_id"]
    with pg.as_user(admin_id) as c:
        c.execute("SELECT lfhe.set_source_active(%s, false, 'pause for test')", (src["id"],))
    with pg.worker() as c:
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            c.execute("SELECT lfhe.start_collection_run(%s, NULL, 'test-worker')", (src["id"],))
        handler = make_collect_handler(c, None, MemorySink(), "test-worker")
        job = Job("00000000-0000-0000-0000-000000000000", "COLLECT_SOURCE", "source", str(src["id"]), {}, 1, 5)
        assert handler(job) == "SKIPPED"


def test_finished_runs_are_immutable(pg, site, http_client):
    src = make_collectable_source(pg, "HTTP_FETCH", {"urls": [site.url("/news/no-date-en.html")]})
    with pg.worker() as c:
        out = collect_source(c, src, http_client, MemorySink(), worker_id="test-worker")
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            c.execute("SELECT lfhe.finish_collection_run(%s, 'FAILED', '{}'::jsonb)", (out.run_id,))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("UPDATE lfhe.collection_runs SET status='FAILED' WHERE id=%s", (out.run_id,))
    with pg.admin() as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="immutable"):
            c.execute("UPDATE lfhe.collection_runs SET items_new = 99 WHERE id=%s", (out.run_id,))


def test_scheduler_enqueues_due_sources_once_and_job_runs_end_to_end(pg, site, http_client):
    src = make_collectable_source(pg, "HTTP_FETCH", {"urls": [site.url("/news/gyakorlat-hu.html")]},
                                  language="hu")
    with pg.worker() as c:
        c.execute("SELECT lfhe.enqueue_due_collections()")
        c.execute("SELECT lfhe.enqueue_due_collections()")  # repeated tick: no duplicate
        jobs = c.execute("SELECT * FROM lfhe.processing_jobs WHERE object_id=%s", (str(src["id"]),)).fetchall()
        assert len(jobs) == 1 and jobs[0]["status"] == "PENDING"

        q = JobQueue(c, "scheduler-test")
        sink = MemorySink()
        handlers = {"COLLECT_SOURCE": make_collect_handler(c, http_client, sink, q.worker_id)}
        for _ in range(20):  # other tests' jobs may be pending; process until ours is done
            q.run_once(handlers, limit=10)
            status = c.execute("SELECT status FROM lfhe.processing_jobs WHERE id=%s", (jobs[0]["id"],)).fetchone()["status"]
            if status != "PENDING":
                break
        assert status == "SUCCESS"
        assert site.url("/news/gyakorlat-hu.html") in sink.stored
        # a fresh run exists → not due again
        c.execute("SELECT lfhe.enqueue_due_collections()")
        assert c.execute("SELECT count(*) AS n FROM lfhe.processing_jobs WHERE object_id=%s",
                         (str(src["id"]),)).fetchone()["n"] == 1
        status_row = c.execute("SELECT * FROM lfhe.source_collection_status WHERE source_id=%s",
                               (src["id"],)).fetchone()
        assert status_row["last_run_status"] == "SUCCESS" and status_row["last_success_at"] is not None
