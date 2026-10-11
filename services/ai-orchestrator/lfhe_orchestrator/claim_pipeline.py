"""Claim pipeline orchestration (Phase 2): M01 inputs → M02 → QA-D18/QA-S18 →
atomic ingestion → M03 → taxonomy ingestion.

Fail-closed rules
* Every provider call is one immutable model_run (lfhe_orchestrator.runner).
* SCHEMA_VALIDATION_FAILED: at most MAX_REPAIR_ATTEMPTS transparent repair
  runs. A repair is a NEW model_run of the same active prompt version with the
  IDENTICAL input/context objects (same input/context set hashes); the task
  parameters additionally carry {"repair": {"of_model_run_id", "validation_errors"}}.
  The failed run stays recorded as SCHEMA_VALIDATION_FAILED, and the repaired
  result names the run it repaired. Evidence is never edited by the repair
  logic: the repaired output goes through the same grounding as any output.
* PROVIDER_ERROR / exhausted repairs: an extraction result is recorded with
  that outcome and no claim exists.
* Ingestion is one database call (lfhe.ingest_claim_extraction /
  lfhe.ingest_classification) = one transaction: claims, status history,
  mentions and entity links are written together or not at all.
* Candidates failing QA-D18 are recorded as rejections, never as claims.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from psycopg.types.json import Jsonb

from lfhe_shared.grounding import NOT_GROUNDED, ground

from .claim_inputs import M02_MODULE, M03_MODULE, build_m02_inputs, build_m03_inputs
from .fidelity import instruction_like, review_flags
from .providers import Provider
from .runner import ModelRunResult, run_structured_task

log = logging.getLogger("lfhe.claims")
MAX_REPAIR_ATTEMPTS = 1
MODEL_REVIEW_STATUSES = {"AMBIGUOUS", "HUMAN_REVIEW_REQUIRED", "INSUFFICIENT_INFORMATION"}


@dataclass
class StageOutcome:
    outcome: str
    model_run_ids: list[str] = field(default_factory=list)
    final_run_id: str | None = None
    claim_ids: list[str] = field(default_factory=list)
    rejected: int = 0
    assignments: int = 0
    rejection_reasons: list[str] = field(default_factory=list)


def _run_with_repair(conn, *, module_code, task, inputs, context, model_configuration_id, provider,
                     worker_id, job_id, record_failed) -> tuple[ModelRunResult, list[str], str | None]:
    runs: list[str] = []
    repaired_from = None
    result = run_structured_task(conn, module_code=module_code, task=task, inputs=inputs, context=context,
                                 model_configuration_id=model_configuration_id, provider=provider,
                                 worker_id=worker_id, job_id=job_id)
    runs.append(result.run_id)
    attempts = 0
    while result.status == "SCHEMA_VALIDATION_FAILED" and attempts < MAX_REPAIR_ATTEMPTS:
        record_failed(result.run_id, repaired_from)
        attempts += 1
        repaired_from = result.run_id
        repair_task = {**task, "repair": {"of_model_run_id": result.run_id,
                                          "validation_errors": (result.validation_errors or [])[:20]}}
        result = run_structured_task(conn, module_code=module_code, task=repair_task, inputs=inputs,
                                     context=context, model_configuration_id=model_configuration_id,
                                     provider=provider, worker_id=worker_id, job_id=job_id)
        runs.append(result.run_id)
    return result, runs, repaired_from


# ---------------------------------------------------------------------------
# M02
# ---------------------------------------------------------------------------
def _ingest_extraction(conn, run_id, snapshot_id, rep_id, *, output_status=None, claims=(), pre_rejections=(),
                       warnings=(), human_review_required=False, repair_of=None) -> dict:
    payload = {"model_run_id": run_id, "article_snapshot_id": snapshot_id, "text_representation_id": rep_id,
               "output_status": output_status, "claims": list(claims), "pre_rejections": list(pre_rejections),
               "warnings": list(warnings), "human_review_required": human_review_required,
               "repair_of_model_run_id": repair_of}
    return conn.execute("SELECT lfhe.ingest_claim_extraction(%s::jsonb) AS r", (Jsonb(payload),)).fetchone()["r"]


def prepare_claims(output: dict, *, snapshot_id: str, rep_id: str, original_text: str, language: str,
                   high_impact: bool) -> tuple[list[dict], list[dict], list[str]]:
    """Deterministic post-processing of a schema-valid M02 output:
    (claims to ingest, pre-rejections, warnings)."""
    result = output.get("result") or {}
    status = output.get("status")
    warnings = [str(w) for w in output.get("warnings") or []]
    claims, rejections = [], []
    raw = result.get("claims") or []
    if result.get("article_snapshot_id") != snapshot_id or result.get("text_representation_id") != rep_id:
        return [], [{"claim_local_id": c.get("claim_local_id"), "reason_codes": ["OUTPUT_OBJECT_ID_MISMATCH"],
                     "candidate": c} for c in raw], warnings
    if status == "FAILED":
        return [], [{"claim_local_id": c.get("claim_local_id"), "reason_codes": ["MODEL_REPORTED_FAILED"],
                     "candidate": c} for c in raw], warnings
    suspicious = instruction_like(original_text)
    if suspicious:
        warnings.append("source text contains instruction-like content (possible prompt injection); "
                        "every claim from it requires human review")
    seen: set[str] = set()
    for c in raw:
        local = c.get("claim_local_id")
        if local in seen:
            rejections.append({"claim_local_id": local, "reason_codes": ["DUPLICATE_CLAIM_LOCAL_ID"], "candidate": c})
            continue
        seen.add(local)
        g = ground(original_text, language, c.get("evidence_span_original"), c.get("claim_text_original"))
        if not g.ok:
            rejections.append({"claim_local_id": local, "reason_codes": [NOT_GROUNDED, *g.problems], "candidate": c})
            continue
        flags, fw = review_flags(c, g.span["exact_text"], language, high_impact=high_impact)
        warnings.extend(f"{local}: {w}" for w in fw)
        if status in MODEL_REVIEW_STATUSES:
            flags = sorted(set(flags) | {"MODEL_REQUESTED_HUMAN_REVIEW"})
        if suspicious:
            flags = sorted(set(flags) | {"SOURCE_CONTAINS_INSTRUCTION_LIKE_TEXT"})
        if g.offset_method == "UNIQUE_EXACT_MATCH":
            warnings.append(f"{local}: offsets located by unique exact match of exact_text")
        claims.append({**{k: c.get(k) for k in (
            "claim_local_id", "claim_text_original", "claim_text_normalised", "claim_type", "source_statement_status",
            "attribution", "event_date", "event_date_confidence", "entities", "locations", "quantity", "unit",
            "evidence_type", "evidence_directness", "source_uncertainty_preserved", "potential_contradiction")},
            "evidence_span_original": g.span, "review_flags": flags,
            "human_review_required": bool(flags) or bool(c.get("human_review_required"))})
    return claims, rejections, warnings


def extract_claims(conn, text_representation_id: str, *, model_configuration_id: str, provider: Provider,
                   worker_id: str, job_id: str | None = None, high_impact_context: dict | None = None) -> StageOutcome:
    ti = build_m02_inputs(conn, text_representation_id, high_impact_context=high_impact_context)
    content = ti.inputs[0].content
    snapshot_id, rep_id = content["article_snapshot_id"], content["text_representation_id"]

    def record_failed(run_id, repair_of):
        _ingest_extraction(conn, run_id, snapshot_id, rep_id, repair_of=repair_of)

    result, runs, repaired_from = _run_with_repair(
        conn, module_code=M02_MODULE, task=ti.task, inputs=ti.inputs, context=ti.context,
        model_configuration_id=model_configuration_id, provider=provider, worker_id=worker_id, job_id=job_id,
        record_failed=record_failed)
    if result.status != "SUCCEEDED":
        out = _ingest_extraction(conn, result.run_id, snapshot_id, rep_id, repair_of=repaired_from)
        return StageOutcome(out["outcome"], runs, result.run_id)
    claims, rejections, warnings = prepare_claims(
        result.parsed_output, snapshot_id=snapshot_id, rep_id=rep_id, original_text=content["content_original"],
        language=content["language_original"], high_impact=bool(ti.task["high_impact_context"].get("high_impact")))
    out = _ingest_extraction(
        conn, result.run_id, snapshot_id, rep_id, output_status=result.parsed_output.get("status"), claims=claims,
        pre_rejections=rejections, warnings=warnings,
        human_review_required=bool(result.parsed_output.get("human_review_required")), repair_of=repaired_from)
    return StageOutcome(out["outcome"], runs, result.run_id, [str(i) for i in out["claim_ids"]],
                        rejected=out.get("claims_rejected", 0))


# ---------------------------------------------------------------------------
# M03
# ---------------------------------------------------------------------------
def _ingest_classification(conn, run_id, *, parsed=None, repair_of=None) -> dict:
    parsed = parsed or {}
    result = parsed.get("result") or {}
    payload = {"model_run_id": run_id, "output_status": parsed.get("status"),
               "classification_confidence": result.get("classification_confidence"),
               "human_review_required": bool(parsed.get("human_review_required")),
               "warnings": [str(w) for w in parsed.get("warnings") or []],
               "assignments": result.get("assignments") or [], "repair_of_model_run_id": repair_of}
    return conn.execute("SELECT lfhe.ingest_classification(%s::jsonb) AS r", (Jsonb(payload),)).fetchone()["r"]


def classify_claims(conn, claim_ids: list[str], *, model_configuration_id: str, provider: Provider,
                    worker_id: str, job_id: str | None = None) -> StageOutcome:
    ti = build_m03_inputs(conn, [str(i) for i in claim_ids])

    def record_failed(run_id, repair_of):
        _ingest_classification(conn, run_id, repair_of=repair_of)

    result, runs, repaired_from = _run_with_repair(
        conn, module_code=M03_MODULE, task=ti.task, inputs=ti.inputs, context=ti.context,
        model_configuration_id=model_configuration_id, provider=provider, worker_id=worker_id, job_id=job_id,
        record_failed=record_failed)
    out = _ingest_classification(conn, result.run_id, parsed=result.parsed_output if result.status == "SUCCEEDED" else None,
                                 repair_of=repaired_from)
    return StageOutcome(out["outcome"], runs, result.run_id, assignments=out.get("assignments", 0),
                        rejection_reasons=list(out.get("rejection_reasons") or []))
