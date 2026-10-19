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
from .event_pipeline import run_event_builder, run_lineage
from .providers import Provider

log = logging.getLogger("lfhe.claims.worker")


def make_handlers(conn, queue: JobQueue, provider: Provider, *, m02_config: str | None, m03_config: str | None,
                  worker_id: str, m04_config: str | None = None, m05_config: str | None = None) -> dict:
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

    review = ("OUTPUT_REJECTED", "HUMAN_REVIEW_REQUIRED", "SCHEMA_VALIDATION_FAILED", "PROPOSALS_RECORDED")
    return {"EXTRACT_CLAIMS": extract, "CLASSIFY_CLAIMS": classify,
            "ANALYSE_LINEAGE": analysis(m04_config, run_lineage, "ANALYSE_LINEAGE", review),
            "BUILD_EVENTS": analysis(m05_config, run_event_builder, "BUILD_EVENTS", review)}


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - process entry point
    from lfhe_shared.config import load_settings
    from lfhe_shared.db import connect

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
                                 m05_config=settings.m05_model_configuration_id)
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
