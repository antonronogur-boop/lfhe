"""Collection orchestration (P1-08).

One call = one collection run for one source:

    start run → build adapter → discover items → fetch each item through the
    polite client → hand to the snapshot sink → finish run with counts.

Failure semantics (DS §31, Handoff §41, §48):
* source unreachable during discovery → run SOURCE_UNAVAILABLE, warning
  recorded, job retried with backoff. This is a collection outcome, never an
  analytical conclusion.
* access control (401/403), robots disallow, refused destination, invalid
  config → run FAILED, error recorded, job fails permanently (needs a human);
  nothing is worked around.
* item failures are classified RETRYABLE / NON_RETRYABLE (FetchError.retryable);
  the run status and job retry decision follow classify_run() — a job-level
  retry is only requested when it can recover at least one item, and it never
  re-requests an item that failed permanently earlier in the same job.
* with allow_external_links=false, redirect hops leaving the source domain are
  rejected before they are requested (EXTERNAL_REDIRECT_REJECTED).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import psycopg
from psycopg.types.json import Jsonb

from lfhe_shared.jobs import PermanentJobError, RetryableJobError

from .adapters import AdapterConfigError, DiscoveredItem, build_adapter, url_within_domain
from .http import ExternalRedirectRejected, FetchError, FetchResult, PoliteHttpClient, SourceUnavailable
from .urls import canonicalize_url

MAX_ITEM_ERRORS_IN_DETAILS = 50
MAX_PERMANENT_URLS = 500


class SnapshotSink(Protocol):
    def store(self, source: dict, item: DiscoveredItem, canonical_url: str,
              fetched: FetchResult, run_id: str) -> str:
        """Persist the fetched item. Returns 'NEW', 'REVISED' or 'DUPLICATE'."""


@dataclass
class CollectionOutcome:
    run_id: str
    status: str
    counts: dict[str, int]
    item_errors: list[dict] = field(default_factory=list)


def _finish(conn, run_id, status, counts, code=None, message=None, details=None):
    conn.execute(
        "SELECT lfhe.finish_collection_run(%s, %s::lfhe.collection_run_status, %s::jsonb, %s, %s, %s::jsonb)",
        (run_id, status, Jsonb(counts), code, message, Jsonb(details or {})),
    )


def _record(conn, code, severity, message, source_id, job_id, details=None):
    conn.execute("SELECT lfhe.record_system_error('collector', %s, %s, %s, %s, %s, %s::jsonb)",
                 (code, severity, message, source_id, job_id, Jsonb(details or {})))


def collect_source(conn: psycopg.Connection, source: dict, http: PoliteHttpClient,
                   sink: SnapshotSink, *, worker_id: str, job_id: str | None = None) -> CollectionOutcome:
    source_id = str(source["id"])
    run_id = str(conn.execute("SELECT lfhe.start_collection_run(%s, %s, %s) AS id",
                              (source_id, job_id, worker_id)).fetchone()["id"])
    counts = {"discovered": 0, "new": 0, "revised": 0, "duplicate": 0, "skipped": 0, "failed": 0}

    try:
        adapter = build_adapter(source["collection_method"], source["collection_config"])
        items = adapter.discover(http)
    except AdapterConfigError as exc:
        _finish(conn, run_id, "FAILED", counts, "ADAPTER_CONFIG_INVALID", str(exc))
        _record(conn, "ADAPTER_CONFIG_INVALID", "ERROR", str(exc), source_id, job_id, {"run_id": run_id})
        raise PermanentJobError(str(exc)) from exc
    except SourceUnavailable as exc:
        _finish(conn, run_id, "SOURCE_UNAVAILABLE", counts, exc.code, str(exc))
        _record(conn, exc.code, "WARNING", str(exc), source_id, job_id, {"run_id": run_id})
        raise RetryableJobError(str(exc)) from exc
    except FetchError as exc:
        _finish(conn, run_id, "FAILED", counts, exc.code, str(exc))
        _record(conn, exc.code, "ERROR", str(exc), source_id, job_id, {"run_id": run_id})
        raise PermanentJobError(str(exc)) from exc

    counts["discovered"] = len(items)
    allow_external = bool(source["collection_config"].get("allow_external_links", False))
    redirect_guard = None if allow_external else _domain_redirect_guard(source["canonical_domain"])
    not_retried = _permanently_failed_in_this_job(conn, job_id, run_id)
    seen: set[str] = set()
    item_errors: list[dict] = []
    failed_retryable = failed_permanent = 0

    for item in items:
        canonical = canonicalize_url(item.url)
        if canonical in seen:
            counts["skipped"] += 1
            continue
        seen.add(canonical)
        if not allow_external and not url_within_domain(canonical, source["canonical_domain"]):
            counts["skipped"] += 1
            item_errors.append({"url": canonical, "code": "EXTERNAL_LINK_SKIPPED", "retryable": False})
            continue
        if canonical in not_retried:
            counts["skipped"] += 1
            item_errors.append({"url": canonical, "code": "PERMANENT_FAILURE_NOT_RETRIED", "retryable": False,
                                "message": "failed permanently in an earlier attempt of this job"})
            continue
        try:
            fetched = http.get(canonical, redirect_guard=redirect_guard)
            outcome = sink.store(source, item, canonical, fetched, run_id)
        except ExternalRedirectRejected as exc:
            counts["skipped"] += 1
            item_errors.append({"url": canonical, "code": exc.code, "retryable": False, "message": str(exc)[:500]})
            continue
        except FetchError as exc:
            counts["failed"] += 1
            failed_retryable += exc.retryable
            failed_permanent += not exc.retryable
            item_errors.append({"url": canonical, "code": exc.code, "retryable": exc.retryable,
                                "message": str(exc)[:500]})
            continue
        except Exception as exc:  # storage failure: counted, never silent; may be transient
            counts["failed"] += 1
            failed_retryable += 1
            item_errors.append({"url": canonical, "code": "STORE_FAILED", "retryable": True,
                                "message": f"{type(exc).__name__}: {exc}"[:500]})
            continue
        counts[outcome.lower()] += 1

    status, retry = classify_run(counts, failed_retryable, failed_permanent)
    permanent_urls = sorted({e["url"] for e in item_errors
                             if e["code"] not in ("EXTERNAL_LINK_SKIPPED",) and not e["retryable"]})
    details = {"item_errors": item_errors[:MAX_ITEM_ERRORS_IN_DETAILS],
               "item_errors_truncated": len(item_errors) > MAX_ITEM_ERRORS_IN_DETAILS,
               "failed_retryable": failed_retryable, "failed_permanent": failed_permanent,
               "permanent_failure_urls": permanent_urls[:MAX_PERMANENT_URLS],
               "job_retry_requested": retry}
    _finish(conn, run_id, status, counts,
            None if status == "SUCCESS" else "ITEM_FAILURES",
            None if status == "SUCCESS" else f"{counts['failed']} item(s) failed", details)

    if status in ("FAILED", "SOURCE_UNAVAILABLE"):
        attempted = counts["discovered"] - counts["skipped"]
        _record(conn, f"COLLECTION_{status}", "WARNING" if status == "SOURCE_UNAVAILABLE" else "ERROR",
                f"all {attempted} item fetch(es) failed ({failed_retryable} transient, "
                f"{failed_permanent} permanent)", source_id, job_id, {"run_id": run_id})
        if retry:
            raise RetryableJobError(f"collection run {run_id} {status}: {failed_retryable} transient item failure(s)")
        raise PermanentJobError(f"collection run {run_id} {status}: all item failures are permanent")
    return CollectionOutcome(run_id, status, counts, item_errors)


def classify_run(counts: dict, failed_retryable: int, failed_permanent: int) -> tuple[str, bool]:
    """Deterministic run status and job-retry decision (docs/collection-semantics.md).

    * no failures                         → SUCCESS, no retry
    * some items succeeded                → PARTIAL, no job retry (the next
                                            scheduled run re-attempts items)
    * all attempted items failed:
        - all transient                   → SOURCE_UNAVAILABLE, retry
        - all permanent                   → FAILED, permanent job failure
        - mixed                           → FAILED, retry; the retry re-attempts
                                            ONLY the transient items (permanent
                                            failures of the same job are skipped)
    """
    attempted = counts["discovered"] - counts["skipped"]
    if counts["failed"] == 0:
        return "SUCCESS", False
    if counts["failed"] < attempted:
        return "PARTIAL", False
    if failed_permanent == 0:
        return "SOURCE_UNAVAILABLE", True
    if failed_retryable == 0:
        return "FAILED", False
    return "FAILED", True


def _domain_redirect_guard(canonical_domain: str):
    def guard(next_url: str) -> None:
        if not url_within_domain(next_url, canonical_domain):
            raise ExternalRedirectRejected(
                f"redirect to {next_url} leaves approved source domain {canonical_domain}; not followed")
    return guard


def _permanently_failed_in_this_job(conn, job_id: str | None, run_id: str) -> set[str]:
    """URLs that failed permanently in earlier collection runs of the SAME job.
    A job-level retry never re-requests them (access controls are not retried)."""
    if job_id is None:
        return set()
    rows = conn.execute(
        "SELECT details -> 'permanent_failure_urls' AS urls FROM lfhe.collection_runs "
        "WHERE job_id = %s AND id <> %s", (job_id, run_id)).fetchall()
    return {u for r in rows for u in (r["urls"] or [])}


def make_collect_handler(conn: psycopg.Connection, http: PoliteHttpClient, sink: SnapshotSink,
                         worker_id: str):
    """Job handler for COLLECT_SOURCE. A source that is no longer collectable
    (deactivated or approval revoked since enqueueing) is SKIPPED."""
    def handle(job):
        source = conn.execute("SELECT * FROM lfhe.collectable_sources WHERE id = %s",
                              (job.object_id,)).fetchone()
        if source is None:
            return "SKIPPED"
        collect_source(conn, source, http, sink, worker_id=worker_id, job_id=job.id)
        return "SUCCESS"
    return handle
