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

from .assessment_inputs import (M06_MODULE, M07_MODULE, M08_MODULE, build_m06_inputs, build_m07_inputs,
                                build_m08_inputs)
from .claim_pipeline import StageOutcome, _run_with_repair
from .event_pipeline import _ingest
from .providers import Provider
from .runner import run_structured_task

# CR7-04: the attribution rule is decided by the workflow (deterministic database function), not by the
# model. A real M07 run that violates only that rule gets ONE additional, separately traceable model run
# with the exact findings fed back. The database ingestion is unchanged: if the second output still
# violates the rule it is rejected as before (fail-closed); nothing is ever edited or auto-accepted.
ATTRIBUTION_REASONS = ("ATTRIBUTION_MISSING", "ATTRIBUTION_CONTRADICTS_WORKFLOW_STATE")
MAX_ATTRIBUTION_REPAIRS = 1


def attribution_only(reasons) -> bool:
    reasons = [str(r) for r in reasons or []]
    return bool(reasons) and all(r.split(":", 1)[0] in ATTRIBUTION_REASONS for r in reasons)


def attribution_feedback(conn, parsed: dict | None, reasons, task: dict, claims: list[dict]) -> dict:
    """Per flagged statement: whether the workflow requires attribution and which attribution(s) the cited
    claims carry. Purely derived from the database rule and the supplied claims."""
    by_claim = {c["claim_id"]: c.get("attribution") for c in claims}
    stmts = {s.get("statement_local_id"): s for s in ((parsed or {}).get("result") or {}).get("assessment_statements") or []}
    findings = []
    for reason in dict.fromkeys(str(r) for r in reasons):
        code, _, local = reason.partition(":")
        s = stmts.get(local) or {}
        ids = [str(i) for i in s.get("supporting_claim_ids") or []]
        required = conn.execute(
            "SELECT lfhe.p4_attribution_required(%s::lfhe.assessment_statement_type, %s::uuid[], %s::uuid[], %s, %s) AS r",
            (s.get("statement_type"), ids, [str(i) for i in s.get("supporting_reference_context_ids") or []],
             task["report_mode"], datetime.fromisoformat(task["information_cutoff"]))).fetchone()["r"] if s else None
        findings.append({"rule": code, "statement_local_id": local, "attribution_required_by_workflow": required,
                         "attributions_of_cited_claims": [by_claim[i] for i in ids if by_claim.get(i)]})
    return {"kind": "ATTRIBUTION_RULE", "findings": findings, "instruction": (
        "Your previous output was rejected only because of the attribution rule. For every statement listed: "
        "set attribution_required exactly to attribution_required_by_workflow; when it is true, put a non-empty "
        "attribution_text AND write that exact text, character for character, inside statement_text (for example "
        "'According to <attribution>, ...'); when it is false, attribution_required must be false. Change nothing else.")}


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

    def ingest(run_id, parsed, repair_of):
        return _ingest(conn, "ingest_assessment", run_id, parsed, repair_of, {"result": (parsed or {}).get("result")})

    result, runs, repaired_from = _run_with_repair(
        conn, module_code=M07_MODULE, task=ai.task, inputs=ai.inputs, context=ai.context,
        model_configuration_id=model_configuration_id, provider=provider, worker_id=worker_id, job_id=job_id,
        record_failed=lambda run_id, repair_of: ingest(run_id, None, repair_of))
    out = ingest(result.run_id, result.parsed_output if result.status == "SUCCEEDED" else None, repaired_from)
    repairs = 0
    while (out["outcome"] == "OUTPUT_REJECTED" and repairs < MAX_ATTRIBUTION_REPAIRS
           and result.parsed_output is not None and attribution_only(out.get("rejection_reasons"))):
        repairs += 1
        claims = ai.inputs[0].content["claims"]
        feedback = attribution_feedback(conn, result.parsed_output, out["rejection_reasons"], ai.task, claims)
        previous = result.run_id
        result = run_structured_task(
            conn, module_code=M07_MODULE, task={**ai.task, "repair": {"of_model_run_id": previous, **feedback}},
            inputs=ai.inputs, context=ai.context, model_configuration_id=model_configuration_id,
            provider=provider, worker_id=worker_id, job_id=job_id)
        runs.append(result.run_id)
        out = ingest(result.run_id, result.parsed_output if result.status == "SUCCEEDED" else None, previous)
    return StageOutcome(out["outcome"], runs, result.run_id, rejection_reasons=list(out.get("rejection_reasons") or []))


def run_challenge(conn, assessment_version_id: str, assessment_version_hash: str, *, model_configuration_id: str,
                  provider: Provider, worker_id: str, job_id: str | None = None) -> StageOutcome:
    ai = build_m08_inputs(conn, assessment_version_id, assessment_version_hash)
    return _run(conn, M08_MODULE, ai, "ingest_challenge", lambda parsed: {"result": (parsed or {}).get("result")},
                model_configuration_id=model_configuration_id, provider=provider, worker_id=worker_id, job_id=job_id)
