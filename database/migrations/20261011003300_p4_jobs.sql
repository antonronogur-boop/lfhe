-- ============================================================================
-- P4-08  Phase 4 job types:
--   ASSESS_RELEVANCE     (M06)  object event_version; payload {event_version_hash, report_mode,
--                               information_cutoff, baseline_code?}
--   ASSESS_EVENT         (M07)  object event_version; payload {event_version_hash, report_mode,
--                               information_cutoff, baseline_code?, reference_context_codes?,
--                               previous_assessment_version_id?}
--   CHALLENGE_ASSESSMENT (M08)  object assessment_version; payload {assessment_version_hash}
-- A recorded M07 draft deterministically enqueues its M08 challenge (the workflow
-- requires DRAFT → CHALLENGED → IN_REVIEW before any human review). M06 never enqueues
-- M07 (M06 is not a gatekeeper; assessment requests are human or operator actions).
-- ============================================================================
ALTER TABLE lfhe.processing_jobs DROP CONSTRAINT processing_jobs_job_type_check;
ALTER TABLE lfhe.processing_jobs ADD CONSTRAINT processing_jobs_job_type_check
  CHECK (job_type IN ('COLLECT_SOURCE', 'EXTRACT_CLAIMS', 'CLASSIFY_CLAIMS', 'ANALYSE_LINEAGE', 'BUILD_EVENTS',
                      'ASSESS_RELEVANCE', 'ASSESS_EVENT', 'CHALLENGE_ASSESSMENT'));
