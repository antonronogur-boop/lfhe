"""Phase 3 orchestration: M04 lineage and M05 event building.

Same fail-closed rules as the claim pipeline (claim_pipeline.py):
* each provider call is one immutable model_run bound to prompt version/hash,
  module version, model configuration, envelope, input and context manifests;
* SCHEMA_VALIDATION_FAILED → at most one transparent repair run with the
  identical input/context objects; failed runs are recorded, never repaired
  silently;
* ingestion is one database call (lfhe.ingest_lineage /
  lfhe.ingest_event_proposals) = one transaction, which rejects the whole output
  on any invalid item, so no partial authoritative state can survive.
Nothing here changes a claim status, validates lineage or performs a structural
event action: those are HUMAN_ONLY database functions.
"""
from __future__ import annotations

from datetime import datetime

from psycopg.types.json import Jsonb

from .claim_pipeline import StageOutcome, _run_with_repair
from .event_inputs import M04_MODULE, M05_MODULE, build_m04_inputs, build_m05_inputs
from .providers import Provider


def _ingest(conn, fn: str, run_id: str, parsed: dict | None, repair_of: str | None, value: dict) -> dict:
    parsed = parsed or {}
    payload = {"model_run_id": run_id, "output_status": parsed.get("status"),
               "human_review_required": bool(parsed.get("human_review_required")),
               "warnings": [str(w) for w in parsed.get("warnings") or []],
               "repair_of_model_run_id": repair_of, **value}
    return conn.execute(f"SELECT lfhe.{fn}(%s::jsonb) AS r", (Jsonb(payload),)).fetchone()["r"]


def run_lineage(conn, claim_ids, *, report_mode: str, information_cutoff: datetime, model_configuration_id: str,
                provider: Provider, worker_id: str, job_id: str | None = None) -> StageOutcome:
    ai = build_m04_inputs(conn, claim_ids, report_mode=report_mode, information_cutoff=information_cutoff)

    def ingest(run_id, parsed, repair_of):
        result = (parsed or {}).get("result") or {}
        return _ingest(conn, "ingest_lineage", run_id, parsed, repair_of, {
            "claim_relationships": result.get("claim_relationships") or [],
            "corroboration_recommendations": result.get("corroboration_recommendations") or []})

    result, runs, repaired_from = _run_with_repair(
        conn, module_code=M04_MODULE, task=ai.task, inputs=ai.inputs, context=ai.context,
        model_configuration_id=model_configuration_id, provider=provider, worker_id=worker_id, job_id=job_id,
        record_failed=lambda run_id, repair_of: ingest(run_id, None, repair_of))
    out = ingest(result.run_id, result.parsed_output if result.status == "SUCCEEDED" else None, repaired_from)
    return StageOutcome(out["outcome"], runs, result.run_id,
                        rejection_reasons=list(out.get("rejection_reasons") or []))


def run_event_builder(conn, claim_ids, *, report_mode: str, information_cutoff: datetime,
                      model_configuration_id: str, provider: Provider, worker_id: str,
                      job_id: str | None = None) -> StageOutcome:
    ai = build_m05_inputs(conn, claim_ids, report_mode=report_mode, information_cutoff=information_cutoff)

    def ingest(run_id, parsed, repair_of):
        result = (parsed or {}).get("result") or {}
        return _ingest(conn, "ingest_event_proposals", run_id, parsed, repair_of,
                       {"proposals": result.get("proposals") or []})

    result, runs, repaired_from = _run_with_repair(
        conn, module_code=M05_MODULE, task=ai.task, inputs=ai.inputs, context=ai.context,
        model_configuration_id=model_configuration_id, provider=provider, worker_id=worker_id, job_id=job_id,
        record_failed=lambda run_id, repair_of: ingest(run_id, None, repair_of))
    out = ingest(result.run_id, result.parsed_output if result.status == "SUCCEEDED" else None, repaired_from)
    return StageOutcome(out["outcome"], runs, result.run_id,
                        rejection_reasons=list(out.get("rejection_reasons") or []))
