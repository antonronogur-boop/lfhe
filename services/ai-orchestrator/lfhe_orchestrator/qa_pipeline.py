"""Phase 6 orchestration: M10-D (deterministic) → M10-S (semantic) → combined QA result.

* M10-D is ordinary deterministic software (lfhe.run_m10d): no model, no model_run.
* M10-S follows the same fail-closed rules as Phases 2–5: one immutable model_run per provider call,
  SCHEMA_VALIDATION_FAILED → at most one transparent repair run with identical inputs (a repair
  repairs malformed model OUTPUT only, never the report), ingestion is one database call.
* M10-S runs even when M10-D found a CRITICAL failure — for diagnosis only; it can never turn a
  deterministic failure into a pass.
* The combined status (PASS / PASS_WITH_WARNINGS / FAIL) is computed by the database
  (lfhe.record_qa_result) from the two exact runs. Nothing here edits the report, acknowledges a
  warning, approves content, reviews security or releases.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .claim_pipeline import _run_with_repair
from .event_pipeline import _ingest
from .providers import Provider
from .qa_inputs import M10_MODULE, build_m10s_inputs


@dataclass
class QaOutcome:
    deterministic_qa_run_id: str
    semantic_qa_run_id: str
    qa_result_id: str
    status: str
    fail_reasons: list[str] = field(default_factory=list)
    model_run_ids: list[str] = field(default_factory=list)
    semantic_outcome: str = ""
    semantic_rejection_reasons: list[str] = field(default_factory=list)


def run_m10d(conn, report_version_id: str, report_version_hash: str, qa_request_id: str) -> dict:
    return conn.execute("SELECT lfhe.run_m10d(%s, %s, %s) AS r",
                        (str(report_version_id), report_version_hash, str(qa_request_id))).fetchone()["r"]


def run_report_qa(conn, report_version_id: str, report_version_hash: str, qa_request_id: str, *,
                  model_configuration_id: str, provider: Provider, worker_id: str, job_id: str | None = None) -> QaOutcome:
    d = run_m10d(conn, report_version_id, report_version_hash, qa_request_id)
    d_run = str(d["qa_run_id"])
    ai = build_m10s_inputs(conn, report_version_id, report_version_hash, d_run)
    extra = {"qa_request_id": str(qa_request_id), "deterministic_qa_run_id": d_run}

    def ingest(run_id, parsed, repair_of):
        return _ingest(conn, "ingest_qa_semantic", run_id, parsed, repair_of,
                       {**extra, "result": (parsed or {}).get("result")})

    result, runs, repaired_from = _run_with_repair(
        conn, module_code=M10_MODULE, task=ai.task, inputs=ai.inputs, context=ai.context,
        model_configuration_id=model_configuration_id, provider=provider, worker_id=worker_id, job_id=job_id,
        record_failed=lambda run_id, repair_of: ingest(run_id, None, repair_of))
    s = ingest(result.run_id, result.parsed_output if result.status == "SUCCEEDED" else None, repaired_from)
    q = conn.execute("SELECT lfhe.record_qa_result(%s, %s) AS r", (d_run, str(s["qa_run_id"]))).fetchone()["r"]
    return QaOutcome(d_run, str(s["qa_run_id"]), str(q["qa_result_id"]), q["status"], list(q.get("fail_reasons") or []),
                     runs, s["outcome"], list(s.get("rejection_reasons") or []))
