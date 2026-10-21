"""Phase 5 orchestration: M09 Executive Editor (+ deterministic preview rendering).

Same fail-closed rules as Phases 2–4: one immutable model_run per provider call,
SCHEMA_VALIDATION_FAILED → at most one transparent repair run with identical inputs,
ingestion is one database call = one transaction that rejects the whole output on any
invalid item. Nothing here selects report content, decides a removal or approves anything.
"""
from __future__ import annotations

from .assessment_pipeline import _run
from .claim_pipeline import StageOutcome
from .providers import Provider
from .report_inputs import M09_MODULE, build_m09_inputs


def run_report_edit(conn, selection_set_id: str, selection_set_hash: str, *, model_configuration_id: str,
                    provider: Provider, worker_id: str, job_id: str | None = None) -> StageOutcome:
    ai = build_m09_inputs(conn, selection_set_id, selection_set_hash)
    return _run(conn, M09_MODULE, ai, "ingest_report_edit", lambda parsed: {"result": (parsed or {}).get("result")},
                model_configuration_id=model_configuration_id, provider=provider, worker_id=worker_id, job_id=job_id)
