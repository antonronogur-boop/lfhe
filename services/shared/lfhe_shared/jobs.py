"""Worker-side job queue client (P1-07).

Handlers raise ``RetryableJobError`` for transient problems (network, source
temporarily unavailable) and ``PermanentJobError`` for problems a retry cannot
fix (invalid configuration). Any other exception is treated as retryable but
remains bounded by the job's ``max_attempts`` — a failure is never silently
ignored (Handoff §41, DS §31).
"""
from __future__ import annotations

import logging
import socket
import os
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable

import psycopg

log = logging.getLogger("lfhe.jobs")


class RetryableJobError(Exception):
    pass


class PermanentJobError(Exception):
    pass


@dataclass(frozen=True)
class Job:
    id: str
    job_type: str
    object_type: str
    object_id: str
    payload: dict
    attempt_count: int
    max_attempts: int


def default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


class JobQueue:
    def __init__(self, conn: psycopg.Connection, worker_id: str | None = None):
        # Expect an autocommit connection: each queue operation is its own transaction.
        self.conn = conn
        self.worker_id = worker_id or default_worker_id()

    def enqueue(self, job_type: str, object_type: str, object_id: str, idempotency_key: str,
                payload: dict | None = None, priority: int = 100, max_attempts: int = 5) -> str:
        row = self.conn.execute(
            "SELECT lfhe.enqueue_job(%s, %s, %s, %s, %s::jsonb, %s::smallint, %s) AS id",
            (job_type, object_type, object_id, idempotency_key,
             psycopg.types.json.Jsonb(payload or {}), priority, max_attempts),
        ).fetchone()
        return str(_get(row, "id"))

    def claim(self, job_types: list[str], limit: int = 1, lease: timedelta = timedelta(minutes=10)) -> list[Job]:
        rows = self.conn.execute(
            "SELECT * FROM lfhe.claim_jobs(%s, %s, %s, %s)",
            (self.worker_id, job_types, limit, lease),
        ).fetchall()
        return [Job(str(_get(r, "id")), _get(r, "job_type"), _get(r, "object_type"), _get(r, "object_id"),
                    _get(r, "payload") or {}, _get(r, "attempt_count"), _get(r, "max_attempts"))
                for r in rows]

    def complete(self, job: Job, status: str = "SUCCESS") -> None:
        self.conn.execute("SELECT lfhe.complete_job(%s, %s, %s::lfhe.job_status)",
                          (job.id, self.worker_id, status))

    def fail(self, job: Job, error: str, retryable: bool = True) -> str:
        row = self.conn.execute("SELECT lfhe.fail_job(%s, %s, %s, %s) AS status",
                                (job.id, self.worker_id, error, retryable)).fetchone()
        return str(_get(row, "status"))

    def record_error(self, component: str, code: str, severity: str, message: str,
                     source_id: str | None = None, job_id: str | None = None,
                     details: dict | None = None) -> None:
        self.conn.execute(
            "SELECT lfhe.record_system_error(%s, %s, %s, %s, %s, %s, %s::jsonb)",
            (component, code, severity, message, source_id, job_id,
             psycopg.types.json.Jsonb(details or {})),
        )

    def run_once(self, handlers: dict[str, Callable[[Job], Any]], limit: int = 1) -> int:
        """Claim up to ``limit`` jobs of the handled types and process them."""
        jobs = self.claim(list(handlers), limit=limit)
        for job in jobs:
            try:
                result = handlers[job.job_type](job)
                self.complete(job, result if result in {"SUCCESS", "SKIPPED", "HUMAN_REVIEW"} else "SUCCESS")
            except PermanentJobError as exc:
                log.error("job %s permanent failure: %s", job.id, exc)
                self.fail(job, f"PERMANENT: {exc}", retryable=False)
            except Exception as exc:  # noqa: BLE001 — bounded by max_attempts
                log.warning("job %s failed (attempt %s/%s): %s", job.id, job.attempt_count,
                            job.max_attempts, exc)
                self.fail(job, f"{type(exc).__name__}: {exc}", retryable=True)
        return len(jobs)


def _get(row, key):
    return row[key] if isinstance(row, dict) else getattr(row, key)
