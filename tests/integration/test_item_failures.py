"""CG1-01 — item failures are classified RETRYABLE / NON_RETRYABLE and a job-level
retry never re-requests an access-controlled (or otherwise permanent) item."""
import uuid

import pytest

from conftest import make_collectable_source
from lfhe_collector.collector import classify_run, collect_source, make_collect_handler
from lfhe_shared.jobs import JobQueue, PermanentJobError, RetryableJobError
from test_collection import MemorySink

pytestmark = pytest.mark.db

PERMANENT = [
    ("/unauthorized.html", "ACCESS_DENIED"),   # 401
    ("/paywall.html", "ACCESS_DENIED"),        # 402
    ("/forbidden.html", "ACCESS_DENIED"),      # 403
    ("/private/internal.html", "ROBOTS_DISALLOWED"),
    ("/binary.bin", "CONTENT_REJECTED"),       # content type not allowed
]


def enqueue(c, src):
    q = JobQueue(c, "item-failure-test")
    job_id = q.enqueue("COLLECT_SOURCE", "source", str(src["id"]), f"test:{uuid.uuid4()}", priority=1)
    return q, job_id


def run_job(c, q, job_id, http_client, sink):
    handlers = {"COLLECT_SOURCE": make_collect_handler(c, http_client, sink, q.worker_id)}
    q.run_once(handlers, limit=1)
    return c.execute("SELECT * FROM lfhe.processing_jobs WHERE id=%s", (job_id,)).fetchone()


def make_due(pg, job_id):
    with pg.admin() as c:
        c.execute("UPDATE lfhe.processing_jobs SET next_attempt_at = now() - interval '1 second' WHERE id=%s", (job_id,))


@pytest.mark.parametrize("path,code", PERMANENT)
def test_permanent_item_failure_fails_job_permanently_without_retry(pg, site, http_client, path, code):
    src = make_collectable_source(pg, "HTTP_FETCH", {"urls": [site.url(path)]})
    before = site.requests.count(path)
    with pg.worker() as c:
        q, job_id = enqueue(c, src)
        job = run_job(c, q, job_id, http_client, MemorySink())
        assert job["status"] == "FAILED" and job["last_error"].startswith("PERMANENT")
        run = c.execute("SELECT status, details FROM lfhe.collection_runs WHERE job_id=%s", (job_id,)).fetchone()
        assert run["status"] == "FAILED"
        assert run["details"]["failed_permanent"] == 1 and run["details"]["failed_retryable"] == 0
        assert run["details"]["job_retry_requested"] is False
        assert run["details"]["item_errors"][0] == {**run["details"]["item_errors"][0], "code": code, "retryable": False}
        # nothing left to retry: further worker cycles never request the item again
        make_due(pg, job_id)
        run_job(c, q, job_id, http_client, MemorySink())
        assert c.execute("SELECT count(*) AS n FROM lfhe.collection_runs WHERE job_id=%s", (job_id,)).fetchone()["n"] == 1
    expected = 0 if code == "ROBOTS_DISALLOWED" else 1
    assert site.requests.count(path) - before == expected


def test_transient_5xx_item_failure_is_retried(pg, site, http_client):
    src = make_collectable_source(pg, "HTTP_FETCH", {"urls": [site.url("/down/item-a.html")]})
    with pg.worker() as c:
        with pytest.raises(RetryableJobError):
            collect_source(c, src, http_client, MemorySink(), worker_id="test-worker")
        q, job_id = enqueue(c, src)
        job = run_job(c, q, job_id, http_client, MemorySink())
        run = c.execute("SELECT status, details FROM lfhe.collection_runs WHERE job_id=%s", (job_id,)).fetchone()
    assert job["status"] == "PENDING" and job["attempt_count"] == 1 and job["next_attempt_at"] > job["updated_at"]
    assert run["status"] == "SOURCE_UNAVAILABLE" and run["details"]["job_retry_requested"] is True


def test_mixed_failure_retries_only_transient_items(pg, site, http_client):
    src = make_collectable_source(pg, "HTTP_FETCH", {"urls": [site.url("/forbidden.html"),
                                                              site.url("/unauthorized.html"),
                                                              site.url("/down/item-b.html")]})
    forbidden, unauthorized, down = (site.requests.count(p) for p in
                                     ("/forbidden.html", "/unauthorized.html", "/down/item-b.html"))
    with pg.worker() as c:
        q, job_id = enqueue(c, src)
        job = run_job(c, q, job_id, http_client, MemorySink())
        assert job["status"] == "PENDING", "a retry can recover the transient item"
        for _ in range(2):  # two more job-level retries
            make_due(pg, job_id)
            run_job(c, q, job_id, http_client, MemorySink())
        runs = c.execute("SELECT status, details FROM lfhe.collection_runs WHERE job_id=%s ORDER BY started_at",
                         (job_id,)).fetchall()
    assert [r["status"] for r in runs] == ["FAILED", "SOURCE_UNAVAILABLE", "SOURCE_UNAVAILABLE"]
    assert runs[0]["details"]["failed_permanent"] == 2 and runs[0]["details"]["failed_retryable"] == 1
    later_codes = {e["url"].rsplit("/", 1)[-1]: e["code"] for e in runs[1]["details"]["item_errors"]}
    assert later_codes == {"forbidden.html": "PERMANENT_FAILURE_NOT_RETRIED",
                           "unauthorized.html": "PERMANENT_FAILURE_NOT_RETRIED",
                           "item-b.html": "SOURCE_UNAVAILABLE"}
    # access controls requested exactly once across all job attempts; the transient item each time
    assert site.requests.count("/forbidden.html") - forbidden == 1
    assert site.requests.count("/unauthorized.html") - unauthorized == 1
    assert site.requests.count("/down/item-b.html") - down == 3


def test_partial_success_with_permanent_failure_is_not_retried(pg, site, http_client):
    src = make_collectable_source(pg, "HTTP_FETCH", {"urls": [site.url("/news/no-date-en.html"),
                                                              site.url("/forbidden.html")]})
    with pg.worker() as c:
        out = collect_source(c, src, http_client, MemorySink(), worker_id="test-worker")
    assert out.status == "PARTIAL" and out.counts["new"] == 1 and out.counts["failed"] == 1


@pytest.mark.parametrize("failed,retryable,permanent,expected", [
    (0, 0, 0, ("SUCCESS", False)),
    (1, 1, 0, ("PARTIAL", False)),
    (3, 3, 0, ("SOURCE_UNAVAILABLE", True)),
    (3, 0, 3, ("FAILED", False)),
    (3, 1, 2, ("FAILED", True)),
])
def test_classify_run_is_deterministic(failed, retryable, permanent, expected):
    counts = {"discovered": 3, "skipped": 0, "failed": failed}
    if expected[0] == "PARTIAL":
        counts["discovered"] = 3
    assert classify_run(counts, retryable, permanent) == expected
