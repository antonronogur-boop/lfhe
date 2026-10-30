"""CR7-05 report autopilot: the worker chains the existing pipeline steps for ONE human-selected analysis context.

A human switches the autopilot on for exactly one report (mode + information cutoff). Afterwards the worker only
ENQUEUES the jobs a human could request by hand, with the report's own mode and cutoff:

    M03 classified claims → M05 (events) → M06 (relevance) → M07 (assessment, only if M06 recommends it, capped) → M08

It never approves, reviews, promotes, changes a state or sets a confidence; every output stays a draft for the human
decision queues. Idempotent (deterministic ``AUTO:`` keys) and never raises into the model step that triggered it.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime

log = logging.getLogger(__name__)

MAX_AUTO_ASSESSMENTS = 20      # cost guard per analysis context (an extra assessment stays a manual request)


def _context(conn):
    return conn.execute("SELECT report_id, report_mode, information_cutoff FROM lfhe.auto_analysis_context()").fetchone()


def _same_context(ctx, payload: dict) -> bool:
    try:
        return (ctx is not None and payload.get("report_mode") == ctx["report_mode"]
                and datetime.fromisoformat(payload["information_cutoff"]) == ctx["information_cutoff"])
    except (KeyError, TypeError, ValueError):
        return False


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def after_classification(conn, queue, claim_ids) -> int:
    """New classified claims → one M05 job for the cutoff-eligible, not rejected ones."""
    try:
        ctx = _context(conn)
        if ctx is None or not claim_ids:
            return 0
        eligible = [str(i) for i in conn.execute(
            "SELECT lfhe.auto_analysis_eligible_claims(%s::uuid[], %s, %s) AS ids",
            ([str(i) for i in claim_ids], ctx["report_mode"], ctx["information_cutoff"])).fetchone()["ids"]]
        if not eligible:
            return 0
        digest = hashlib.md5(",".join(sorted(eligible)).encode()).hexdigest()   # noqa: S324 - idempotency key only
        queue.enqueue("BUILD_EVENTS", "claim_set", digest,
                      f"AUTO:BUILD_EVENTS:{digest}:{ctx['report_mode']}:{_iso(ctx['information_cutoff'])}",
                      {"claim_ids": sorted(eligible), "report_mode": ctx["report_mode"],
                       "information_cutoff": _iso(ctx["information_cutoff"])}, max_attempts=3)
        return 1
    except Exception:   # noqa: BLE001 - the chain must never fail the finished model step
        log.exception("autopilot: could not enqueue M05")
        return 0


def after_event_build(conn, queue, run_id: str | None, payload: dict) -> int:
    """Event versions written by an M05 run → M06 for each."""
    try:
        if not run_id or not _same_context(_context(conn), payload):
            return 0
        n = 0
        for v in conn.execute("SELECT id, content_hash FROM lfhe.event_versions WHERE created_by_model_run_id = %s",
                              (run_id,)).fetchall():
            queue.enqueue("ASSESS_RELEVANCE", "event_version", str(v["id"]),
                          f"AUTO:ASSESS_RELEVANCE:{v['id']}:{payload['report_mode']}:{payload['information_cutoff']}",
                          {"event_version_hash": v["content_hash"], "report_mode": payload["report_mode"],
                           "information_cutoff": payload["information_cutoff"]}, max_attempts=3)
            n += 1
        return n
    except Exception:   # noqa: BLE001
        log.exception("autopilot: could not enqueue M06")
        return 0


def after_relevance(conn, queue, event_version_id: str, payload: dict) -> int:
    """M06 recommended assessment → M07 (capped). Otherwise the event waits in the inbox ('assess anyway' is manual)."""
    try:
        if not _same_context(_context(conn), payload):
            return 0
        row = conn.execute(
            "SELECT v.content_hash FROM lfhe.event_versions v WHERE v.id = %s AND EXISTS ("
            "SELECT 1 FROM lfhe.relevance_results r WHERE r.event_version_id = v.id AND r.automatic_assessment_recommended)",
            (event_version_id,)).fetchone()
        if row is None:
            return 0
        used = conn.execute("SELECT count(*) AS n FROM lfhe.processing_jobs WHERE job_type = 'ASSESS_EVENT' "
                            "AND idempotency_key LIKE %s", (f"AUTO:ASSESS_EVENT:%:{payload['report_mode']}:{payload['information_cutoff']}",)
                            ).fetchone()["n"]
        if used >= MAX_AUTO_ASSESSMENTS:
            log.warning("autopilot: %d automatic assessments reached for this context; further ones are manual", used)
            return 0
        queue.enqueue("ASSESS_EVENT", "event_version", event_version_id,
                      f"AUTO:ASSESS_EVENT:{event_version_id}:{payload['report_mode']}:{payload['information_cutoff']}",
                      {"event_version_hash": row["content_hash"], "report_mode": payload["report_mode"],
                       "information_cutoff": payload["information_cutoff"]}, max_attempts=3)
        return 1
    except Exception:   # noqa: BLE001
        log.exception("autopilot: could not enqueue M07")
        return 0
