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
* individual item failures are counted (PARTIAL) and listed in run details.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import psycopg
from psycopg.types.json import Jsonb

from lfhe_shared.jobs import PermanentJobError, RetryableJobError

from .adapters import AdapterConfigError, DiscoveredItem, build_adapter, url_within_domain
from .http import FetchError, FetchResult, PoliteHttpClient, SourceUnavailable
from .urls import canonicalize_url

MAX_ITEM_ERRORS_IN_DETAILS = 50


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
    seen: set[str] = set()
    item_errors: list[dict] = []
    unavailable_items = 0

    for item in items:
        canonical = canonicalize_url(item.url)
        if canonical in seen:
            counts["skipped"] += 1
            continue
        seen.add(canonical)
        if not allow_external and not url_within_domain(canonical, source["canonical_domain"]):
            counts["skipped"] += 1
            item_errors.append({"url": canonical, "code": "EXTERNAL_LINK_SKIPPED"})
            continue
        try:
            fetched = http.get(canonical)
            outcome = sink.store(source, item, canonical, fetched, run_id)
        except FetchError as exc:
            counts["failed"] += 1
            unavailable_items += isinstance(exc, SourceUnavailable)
            item_errors.append({"url": canonical, "code": exc.code, "message": str(exc)[:500]})
            continue
        except Exception as exc:  # storage failure: counted, never silent
            counts["failed"] += 1
            item_errors.append({"url": canonical, "code": "STORE_FAILED",
                                "message": f"{type(exc).__name__}: {exc}"[:500]})
            continue
        counts[outcome.lower()] += 1

    attempted = counts["discovered"] - counts["skipped"]
    if counts["failed"] == 0:
        status = "SUCCESS"
    elif counts["failed"] < attempted:
        status = "PARTIAL"
    elif unavailable_items == counts["failed"]:
        status = "SOURCE_UNAVAILABLE"
    else:
        status = "FAILED"

    details = {"item_errors": item_errors[:MAX_ITEM_ERRORS_IN_DETAILS],
               "item_errors_truncated": len(item_errors) > MAX_ITEM_ERRORS_IN_DETAILS}
    _finish(conn, run_id, status, counts,
            None if status == "SUCCESS" else "ITEM_FAILURES",
            None if status == "SUCCESS" else f"{counts['failed']} item(s) failed", details)

    if status in ("FAILED", "SOURCE_UNAVAILABLE"):
        _record(conn, f"COLLECTION_{status}", "WARNING" if status == "SOURCE_UNAVAILABLE" else "ERROR",
                f"all {attempted} item fetch(es) failed", source_id, job_id, {"run_id": run_id})
        raise RetryableJobError(f"collection run {run_id} {status}")
    return CollectionOutcome(run_id, status, counts, item_errors)


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
