-- ============================================================================
-- P3-04  Phase 3 job types: ANALYSE_LINEAGE (M04) and BUILD_EVENTS (M05).
-- Payload: {claim_ids[], report_mode, information_cutoff}. Enqueued explicitly
-- (lfhe.enqueue_job by the worker / operator); no automatic chaining in Phase 3
-- (same decision as SD-11 for Phase 2).
-- ============================================================================
ALTER TABLE lfhe.processing_jobs DROP CONSTRAINT processing_jobs_job_type_check;
ALTER TABLE lfhe.processing_jobs ADD CONSTRAINT processing_jobs_job_type_check
  CHECK (job_type IN ('COLLECT_SOURCE', 'EXTRACT_CLAIMS', 'CLASSIFY_CLAIMS', 'ANALYSE_LINEAGE', 'BUILD_EVENTS'));
