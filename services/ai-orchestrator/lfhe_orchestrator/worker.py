"""Claim-pipeline worker (Phase 2).

    python -m lfhe_orchestrator.worker --once        # one batch
    python -m lfhe_orchestrator.worker --enqueue     # also enqueue pending extractions

Job types
* EXTRACT_CLAIMS  (object: text_representation) → M02 → grounding → ingestion;
                  on persisted claims enqueues CLASSIFY_CLAIMS for them.
* CLASSIFY_CLAIMS (object: the M02 model run; payload.claim_ids) → M03.
* ANALYSE_LINEAGE / BUILD_EVENTS (payload: claim_ids, report_mode,
  information_cutoff) → M04 / M05 proposals (Phase 3). Proposals always end
  as HUMAN_REVIEW: lineage, status and structural decisions are human-only.
* ASSESS_RELEVANCE (object: event_version; payload: event_version_hash, report_mode,
                  information_cutoff, baseline_code?) → M06 (Phase 4).
* ASSESS_EVENT    (object: event_version; payload: as above + reference_context_codes?,
                  previous_assessment_version_id?) → M07 draft; a recorded draft enqueues
                  CHALLENGE_ASSESSMENT for its exact version + hash.
* CHALLENGE_ASSESSMENT (object: assessment_version; payload: assessment_version_hash) → M08;
                  ends in HUMAN_REVIEW: approval / final confidence / flag disposition are
                  human-only database functions.
* EDIT_REPORT     (object: report_selection_set; payload: selection_set_hash) → M09 draft report
                  version (enqueued only by the HUMAN_ONLY lfhe.freeze_report_selection).
* RENDER_REPORT   (object: report_version; payload: report_version_hash) → deterministic HTML
                  preview (enqueued by every new report version).
* RUN_REPORT_QA   (object: report_version; payload: report_version_hash, qa_request_id) → M10-D
                  (deterministic) → M10-S (semantic, model) → combined QA result computed by the
                  database (enqueued only by the HUMAN_ONLY lfhe.request_report_qa).
* RENDER_RELEASE_PDF (object: report_version; payload: report_version_hash, security_review_id) →
                  release HTML → headless Chromium PDF → write-once storage → release PDF artifact
                  (enqueued by an APPROVED human security review). Never releases anything.

Model configurations: LFHE_M02_MODEL_CONFIGURATION_ID / LFHE_M03_MODEL_CONFIGURATION_ID
(registered rows). Provider credentials come only from the secret-managed
environment (AnthropicProvider.from_environment); a missing key fails the job
as PROVIDER_ERROR, never silently.
"""
from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime

from lfhe_shared.jobs import Job, JobQueue, PermanentJobError, default_worker_id

from .claim_inputs import InputBuildError
from .claim_pipeline import classify_claims, extract_claims
from .assessment_pipeline import run_assessment, run_challenge, run_relevance
from .event_pipeline import run_event_builder, run_lineage
from .report_pipeline import run_report_edit
from .report_render import render_and_record
from .qa_pipeline import run_report_qa
from .report_pdf import PdfRenderError, render_release_pdf
from .providers import Provider

log = logging.getLogger("lfhe.claims.worker")


def make_handlers(conn, queue: JobQueue, provider: Provider, *, m02_config: str | None, m03_config: str | None,
                  worker_id: str, m04_config: str | None = None, m05_config: str | None = None,
                  m06_config: str | None = None, m07_config: str | None = None, m08_config: str | None = None,
                  m09_config: str | None = None, m10_config: str | None = None, store=None) -> dict:
    def extract(job: Job):
        if not m02_config:
            raise PermanentJobError("M02 model configuration is not configured")
        try:
            out = extract_claims(conn, job.object_id, model_configuration_id=m02_config, provider=provider,
                                 worker_id=worker_id, job_id=job.id)
        except InputBuildError as exc:
            raise PermanentJobError(str(exc)) from exc
        log.info("EXTRACT_CLAIMS %s → %s (%d claim(s), %d rejected)", job.object_id, out.outcome,
                 len(out.claim_ids), out.rejected)
        if out.claim_ids:
            queue.enqueue("CLASSIFY_CLAIMS", "claim_extraction_result", out.final_run_id,
                          f"CLASSIFY_CLAIMS:{out.final_run_id}", {"claim_ids": out.claim_ids}, max_attempts=3)
        if out.outcome == "PROVIDER_ERROR":
            raise RuntimeError("provider error (recorded as model run); will retry within max_attempts")
        return "HUMAN_REVIEW" if out.outcome in ("HUMAN_REVIEW_REQUIRED", "SCHEMA_VALIDATION_FAILED") else "SUCCESS"

    def classify(job: Job):
        if not m03_config:
            raise PermanentJobError("M03 model configuration is not configured")
        try:
            out = classify_claims(conn, job.payload.get("claim_ids") or [], model_configuration_id=m03_config,
                                  provider=provider, worker_id=worker_id, job_id=job.id)
        except InputBuildError as exc:
            raise PermanentJobError(str(exc)) from exc
        log.info("CLASSIFY_CLAIMS %s → %s (%d assignment(s))", job.object_id, out.outcome, out.assignments)
        if out.outcome == "PROVIDER_ERROR":
            raise RuntimeError("provider error (recorded as model run); will retry within max_attempts")
        return "HUMAN_REVIEW" if out.outcome in ("OUTPUT_REJECTED", "HUMAN_REVIEW_REQUIRED",
                                                 "SCHEMA_VALIDATION_FAILED") else "SUCCESS"

    def analysis(module_config, runner, label, review_outcomes):
        def handle(job: Job):
            if not module_config:
                raise PermanentJobError(f"{label} model configuration is not configured")
            p = job.payload
            try:
                out = runner(conn, p.get("claim_ids") or [], report_mode=p.get("report_mode"),
                             information_cutoff=datetime.fromisoformat(p["information_cutoff"]),
                             model_configuration_id=module_config, provider=provider, worker_id=worker_id,
                             job_id=job.id)
            except (InputBuildError, KeyError, ValueError) as exc:
                raise PermanentJobError(str(exc)) from exc
            log.info("%s %s → %s", label, job.object_id, out.outcome)
            if out.outcome == "PROVIDER_ERROR":
                raise RuntimeError("provider error (recorded as model run); will retry within max_attempts")
            return "HUMAN_REVIEW" if out.outcome in review_outcomes else "SUCCESS"
        return handle

    def phase4(module_config, label, call, after=None):
        def handle(job: Job):
            if not module_config:
                raise PermanentJobError(f"{label} model configuration is not configured")
            try:
                out = call(job, module_config)
            except (InputBuildError, KeyError, ValueError) as exc:
                raise PermanentJobError(str(exc)) from exc
            log.info("%s %s → %s", label, job.object_id, out.outcome)
            if out.outcome == "PROVIDER_ERROR":
                raise RuntimeError("provider error (recorded as model run); will retry within max_attempts")
            if after is not None:
                after(job, out)
            return "SUCCESS" if out.outcome in ("RELEVANCE_RECORDED", "ASSESSMENT_RECORDED", "REPORT_VERSION_RECORDED") \
                else "HUMAN_REVIEW"
        return handle

    def cutoff_args(p):
        return {"report_mode": p.get("report_mode"), "information_cutoff": datetime.fromisoformat(p["information_cutoff"])}

    def relevance(job, mc):
        p = job.payload
        return run_relevance(conn, job.object_id, p["event_version_hash"], **cutoff_args(p), baseline_code=p.get("baseline_code"),
                             model_configuration_id=mc, provider=provider, worker_id=worker_id, job_id=job.id)

    def assessment(job, mc):
        p = job.payload
        return run_assessment(conn, job.object_id, p["event_version_hash"], **cutoff_args(p),
                              baseline_code=p.get("baseline_code"),
                              reference_context_codes=tuple(p.get("reference_context_codes") or ()),
                              previous_assessment_version_id=p.get("previous_assessment_version_id"),
                              model_configuration_id=mc, provider=provider, worker_id=worker_id, job_id=job.id)

    def enqueue_challenge(job, out):
        if out.outcome != "ASSESSMENT_RECORDED":
            return
        row = conn.execute("SELECT id, content_hash FROM lfhe.assessment_versions WHERE created_by_model_run_id = %s",
                           (out.final_run_id,)).fetchone()
        queue.enqueue("CHALLENGE_ASSESSMENT", "assessment_version", str(row["id"]), f"CHALLENGE_ASSESSMENT:{row['id']}",
                      {"assessment_version_hash": row["content_hash"]}, max_attempts=3)

    def challenge(job, mc):
        return run_challenge(conn, job.object_id, job.payload["assessment_version_hash"], model_configuration_id=mc,
                             provider=provider, worker_id=worker_id, job_id=job.id)

    def report_edit(job, mc):
        return run_report_edit(conn, job.object_id, job.payload["selection_set_hash"], model_configuration_id=mc,
                               provider=provider, worker_id=worker_id, job_id=job.id)

    def render(job: Job):
        try:
            out = render_and_record(conn, job.object_id, job.payload["report_version_hash"], worker_id=worker_id)
        except (KeyError, ValueError) as exc:
            raise PermanentJobError(str(exc)) from exc
        log.info("RENDER_REPORT %s → %s", job.object_id, out.get("content_sha256"))
        return "SUCCESS"

    def report_qa(job: Job):
        if not m10_config:
            raise PermanentJobError("M10 model configuration is not configured")
        try:
            out = run_report_qa(conn, job.object_id, job.payload["report_version_hash"], job.payload["qa_request_id"],
                                model_configuration_id=m10_config, provider=provider, worker_id=worker_id, job_id=job.id)
        except (InputBuildError, KeyError, ValueError) as exc:
            raise PermanentJobError(str(exc)) from exc
        log.info("RUN_REPORT_QA %s → %s", job.object_id, out.status)
        return "SUCCESS" if out.status == "PASS" else "HUMAN_REVIEW"

    def release_pdf(job: Job):
        if store is None:
            raise PermanentJobError("object storage is not configured")
        try:
            out = render_release_pdf(conn, job.object_id, job.payload["report_version_hash"], store=store, worker_id=worker_id)
        except (KeyError, ValueError, PdfRenderError) as exc:
            raise PermanentJobError(str(exc)) from exc
        log.info("RENDER_RELEASE_PDF %s → %s", job.object_id, out.get("pdf_sha256"))
        return "SUCCESS"

    review = ("OUTPUT_REJECTED", "HUMAN_REVIEW_REQUIRED", "SCHEMA_VALIDATION_FAILED", "PROPOSALS_RECORDED")
    return {"EDIT_REPORT": phase4(m09_config, "EDIT_REPORT", report_edit), "RENDER_REPORT": render,
            "RUN_REPORT_QA": report_qa, "RENDER_RELEASE_PDF": release_pdf,
            "EXTRACT_CLAIMS": extract, "CLASSIFY_CLAIMS": classify,
            "ANALYSE_LINEAGE": analysis(m04_config, run_lineage, "ANALYSE_LINEAGE", review),
            "BUILD_EVENTS": analysis(m05_config, run_event_builder, "BUILD_EVENTS", review),
            "ASSESS_RELEVANCE": phase4(m06_config, "ASSESS_RELEVANCE", relevance),
            "ASSESS_EVENT": phase4(m07_config, "ASSESS_EVENT", assessment, enqueue_challenge),
            "CHALLENGE_ASSESSMENT": phase4(m08_config, "CHALLENGE_ASSESSMENT", challenge)}


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - process entry point
    from lfhe_shared.config import load_settings
    from lfhe_shared.db import connect
    from lfhe_shared.storage import build_object_store

    from .providers import AnthropicProvider

    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--enqueue", action="store_true")
    parser.add_argument("--batch", type=int, default=2)
    parser.add_argument("--idle-seconds", type=float, default=30.0)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = load_settings()
    worker_id = default_worker_id()
    provider = AnthropicProvider.from_environment()
    with connect(settings, autocommit=True) as conn:
        queue = JobQueue(conn, worker_id)
        handlers = make_handlers(conn, queue, provider, m02_config=settings.m02_model_configuration_id,
                                 m03_config=settings.m03_model_configuration_id, worker_id=worker_id,
                                 m04_config=settings.m04_model_configuration_id,
                                 m05_config=settings.m05_model_configuration_id,
                                 m06_config=settings.m06_model_configuration_id,
                                 m07_config=settings.m07_model_configuration_id,
                                 m08_config=settings.m08_model_configuration_id,
                                 m09_config=settings.m09_model_configuration_id,
                                 m10_config=settings.m10_model_configuration_id, store=build_object_store(settings))
        while True:
            if args.enqueue:
                conn.execute("SELECT lfhe.enqueue_pending_claim_extractions(50)")
            processed = queue.run_once(handlers, limit=args.batch)
            if args.once:
                return 0
            if processed == 0:
                time.sleep(args.idle_seconds)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
