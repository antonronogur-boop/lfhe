"""P1-07 — job queue: idempotency, SKIP LOCKED, backoff, bounded retries (F5/F6 basis)."""
import threading
import uuid
from datetime import timedelta

import psycopg
import pytest

from lfhe_shared.jobs import JobQueue, PermanentJobError

pytestmark = pytest.mark.db

Denied = psycopg.errors.InsufficientPrivilege


def key() -> str:
    return f"test:{uuid.uuid4()}"


def test_enqueue_is_idempotent(pg):
    with pg.worker() as c:
        q = JobQueue(c, "worker-a")
        k = key()
        first = q.enqueue("COLLECT_SOURCE", "test", "x", k)
        second = q.enqueue("COLLECT_SOURCE", "test", "x", k)
        assert first == second
        assert c.execute("SELECT count(*) AS n FROM lfhe.processing_jobs WHERE idempotency_key=%s",
                         (k,)).fetchone()["n"] == 1


def test_concurrent_claims_never_hand_out_the_same_job(pg):
    with pg.worker() as c:
        q = JobQueue(c, "setup")
        ids = {q.enqueue("COLLECT_SOURCE", "test", f"o{i}", key(), priority=1) for i in range(20)}
    claimed: dict[str, list[str]] = {}
    barrier = threading.Barrier(4)

    def run(name: str):
        with pg.worker() as c:
            q = JobQueue(c, name)
            barrier.wait()
            got = []
            while True:
                batch = q.claim(["COLLECT_SOURCE"], limit=3)
                batch = [j for j in batch if j.id in ids]
                if not batch:
                    break
                got.extend(j.id for j in batch)
                for j in batch:
                    q.complete(j)
            claimed[name] = got

    threads = [threading.Thread(target=run, args=(f"worker-{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    all_claimed = [j for v in claimed.values() for j in v]
    assert len(all_claimed) == len(set(all_claimed)), "a job was claimed twice"
    assert set(all_claimed) == ids


def test_backoff_then_permanent_failure_records_system_error(pg):
    with pg.worker() as c:
        q = JobQueue(c, "worker-b")
        k = key()
        jid = q.enqueue("COLLECT_SOURCE", "test", "flaky", k, max_attempts=3, priority=-10)
        delays = []
        for attempt in range(1, 4):
            # Jobs are not directly writable by the worker; move time forward via an owner session.
            with pg.admin() as a:
                a.execute("UPDATE lfhe.processing_jobs SET next_attempt_at = now() - interval '1 second' WHERE id=%s", (jid,))
            jobs = [j for j in q.claim(["COLLECT_SOURCE"], limit=10) if j.id == jid]
            assert jobs and jobs[0].attempt_count == attempt
            status = q.fail(jobs[0], f"transient {attempt}")
            row = c.execute("SELECT status, next_attempt_at - now() AS d FROM lfhe.processing_jobs WHERE id=%s",
                            (jid,)).fetchone()
            assert row["status"] == status
            if status == "PENDING":
                delays.append(row["d"])
        assert status == "FAILED"
        assert delays[0] < delays[1], "backoff must grow"
        err = c.execute("SELECT error_code, severity FROM lfhe.system_errors WHERE job_id=%s", (jid,)).fetchone()
        assert err == {"error_code": "JOB_FAILED_PERMANENTLY", "severity": "ERROR"}


def test_run_once_permanent_error_fails_immediately(pg):
    with pg.worker() as c:
        q = JobQueue(c, "worker-c")
        jid = q.enqueue("COLLECT_SOURCE", "test", "badcfg", key(), priority=-20)

        def handler(job):
            if job.id == jid:
                raise PermanentJobError("invalid collection config")
            return "SUCCESS"

        q.run_once({"COLLECT_SOURCE": handler}, limit=50)
        row = c.execute("SELECT status, attempt_count FROM lfhe.processing_jobs WHERE id=%s", (jid,)).fetchone()
        assert row == {"status": "FAILED", "attempt_count": 1}


def test_expired_lease_is_reclaimable_and_only_holder_may_complete(pg):
    with pg.worker() as c:
        a, b = JobQueue(c, "holder-a"), JobQueue(c, "holder-b")
        jid = a.enqueue("COLLECT_SOURCE", "test", "lease", key(), priority=-30)
        job = [j for j in a.claim(["COLLECT_SOURCE"], limit=50, lease=timedelta(seconds=1)) if j.id == jid][0]
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            b.complete(job)
        with pg.admin() as adm:
            adm.execute("UPDATE lfhe.processing_jobs SET lock_expires_at = now() - interval '1 second' WHERE id=%s", (jid,))
        again = [j for j in b.claim(["COLLECT_SOURCE"], limit=50) if j.id == jid]
        assert again and again[0].attempt_count == 2
        b.complete(again[0])
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            a.complete(job)


def test_queue_tables_not_directly_writable_and_closed_to_humans(pg, make_user):
    with pg.worker() as c:
        with pytest.raises(Denied):
            c.execute("UPDATE lfhe.processing_jobs SET status='SUCCESS'")
        with pytest.raises(Denied):
            c.execute("DELETE FROM lfhe.system_errors")
    analyst = make_user("ANALYST")
    with pg.as_user(analyst) as c:
        with pytest.raises(Denied):
            c.execute("SELECT lfhe.enqueue_job('COLLECT_SOURCE','test','x','human-key-123')")
        assert c.execute("SELECT count(*) AS n FROM lfhe.processing_jobs").fetchone()["n"] >= 0
    viewer = make_user("VIEWER")
    with pg.as_user(viewer) as c:
        assert c.execute("SELECT count(*) AS n FROM lfhe.processing_jobs").fetchone()["n"] == 0
    with pg.admin() as c:
        with pytest.raises(Denied, match="append-only"):
            c.execute("DELETE FROM lfhe.system_errors")
