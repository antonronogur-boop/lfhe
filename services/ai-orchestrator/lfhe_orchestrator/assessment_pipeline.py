"""Phase 4 orchestration: M06 relevance, M07 assessment, M08 challenge.

Same fail-closed rules as Phases 2–3: one immutable model_run per provider call
(prompt version/hash, module version, model configuration/hash, envelope, input
and context manifests); SCHEMA_VALIDATION_FAILED → at most one transparent repair
run with identical inputs; ingestion is one database call = one transaction that
rejects the whole output on any invalid item. Nothing here approves, sets
final_analytic_confidence or disposes of a challenge flag — those are HUMAN_ONLY
database functions.
"""
from __future__ import annotations

from datetime import datetime

from .assessment_inputs import M06_MODULE, M07_MODULE, build_m06_inputs, build_m07_inputs
from .claim_pipeline import StageOutcome, _run_with_repair
from .event_pipeline import _ingest
from .providers import Provider


def _run(conn, module_code, ai, fn, value_of, *, model_configuration_id, provider, worker_id, job_id) -> StageOutcome:
    def ingest(run_id, parsed, repair_of):
        return _ingest(conn, fn, run_id, parsed, repair_of, value_of(parsed))

    result, runs, repaired_from = _run_with_repair(
        conn, module_code=module_code, task=ai.task, inputs=ai.inputs, context=ai.context,
        model_configuration_id=model_configuration_id, provider=provider, worker_id=worker_id, job_id=job_id,
        record_failed=lambda run_id, repair_of: ingest(run_id, None, repair_of))
    out = ingest(result.run_id, result.parsed_output if result.status == "SUCCEEDED" else None, repaired_from)
    return StageOutcome(out["outcome"], runs, result.run_id, rejection_reasons=list(out.get("rejection_reasons") or []))


def run_relevance(conn, event_version_id: str, event_version_hash: str, *, report_mode: str,
                  information_cutoff: datetime, model_configuration_id: str, provider: Provider, worker_id: str,
                  baseline_code: str | None = None, job_id: str | None = None) -> StageOutcome:
    ai = build_m06_inputs(conn, event_version_id, event_version_hash, report_mode=report_mode,
                          information_cutoff=information_cutoff, baseline_code=baseline_code)
    return _run(conn, M06_MODULE, ai, "ingest_relevance", lambda parsed: {"result": (parsed or {}).get("result")},
                model_configuration_id=model_configuration_id, provider=provider, worker_id=worker_id, job_id=job_id)


def run_assessment(conn, event_version_id: str, event_version_hash: str, *, report_mode: str,
                   information_cutoff: datetime, model_configuration_id: str, provider: Provider, worker_id: str,
                   baseline_code: str | None = None, reference_context_codes=(),
                   previous_assessment_version_id: str | None = None, job_id: str | None = None) -> StageOutcome:
    ai = build_m07_inputs(conn, event_version_id, event_version_hash, report_mode=report_mode,
                          information_cutoff=information_cutoff, baseline_code=baseline_code,
                          reference_context_codes=reference_context_codes,
                          previous_assessment_version_id=previous_assessment_version_id)
    return _run(conn, M07_MODULE, ai, "ingest_assessment", lambda parsed: {"result": (parsed or {}).get("result")},
                model_configuration_id=model_configuration_id, provider=provider, worker_id=worker_id, job_id=job_id)
