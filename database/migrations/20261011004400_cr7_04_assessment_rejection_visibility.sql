-- CR7-04 — an M07 output rejected by the closed ingestion rules (e.g. attribution rule) recorded nothing.
-- * lfhe.cr7_03_enqueue: a human (audited reason) may re-request M07 for the SAME event version after such a
--   rejection (outcome REQUEUED_AFTER_REJECTION, at most 3 re-requests). Everything else is unchanged:
--   ALREADY_ACTIVE while queued/running, ALREADY_COMPLETED after a recorded assessment or any other outcome.
-- * lfhe.job_rejection_detail: read model that shows WHY an M07 output was rejected (reasons, warnings).
-- No applied migration is modified; no analytical state is changed; no permission is widened.

DO $$
DECLARE
  c text;
BEGIN
  FOR c IN SELECT conname FROM pg_catalog.pg_constraint
           WHERE conrelid = 'lfhe.workflow_job_requests'::regclass AND contype = 'c'
             AND pg_catalog.pg_get_constraintdef(oid) LIKE '%REQUEUED_AFTER_FAILURE%' LOOP
    EXECUTE format('ALTER TABLE lfhe.workflow_job_requests DROP CONSTRAINT %I', c);
  END LOOP;
END $$;
ALTER TABLE lfhe.workflow_job_requests ADD CONSTRAINT workflow_job_requests_outcome_check
  CHECK (outcome IN ('ENQUEUED', 'ALREADY_ACTIVE', 'ALREADY_COMPLETED', 'REQUEUED_AFTER_FAILURE', 'REQUEUED_AFTER_REJECTION'));

CREATE OR REPLACE FUNCTION lfhe.cr7_03_enqueue(p_actor uuid, p_job_type text, p_object_type text, p_object_id text,
                                               p_key text, p_payload jsonb, p_mode text, p_cutoff timestamptz,
                                               p_reason text, p_max_attempts integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_job      lfhe.processing_jobs;
  v_retries  integer;
  v_key      text := p_key;
  v_outcome  text;
  v_job_id   uuid;
  v_req      uuid;
BEGIN
  IF length(p_key) > 380 THEN
    RAISE EXCEPTION 'idempotency key too long' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  -- serialise concurrent requests for the same base key (no duplicate retry jobs)
  PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(p_key, 7303));
  SELECT * INTO v_job FROM lfhe.processing_jobs
   WHERE idempotency_key = p_key OR idempotency_key LIKE p_key || ':retry:%'
   ORDER BY created_at DESC, id DESC LIMIT 1;
  IF NOT FOUND THEN
    v_outcome := 'ENQUEUED';
  ELSIF v_job.status IN ('PENDING', 'RUNNING') THEN
    v_outcome := 'ALREADY_ACTIVE';
    v_job_id := v_job.id;
    v_key := v_job.idempotency_key;
  ELSIF v_job.status = 'FAILED' THEN
    SELECT count(*) INTO v_retries FROM lfhe.processing_jobs WHERE idempotency_key LIKE p_key || ':retry:%';
    v_key := p_key || ':retry:' || (v_retries + 1);
    v_outcome := 'REQUEUED_AFTER_FAILURE';
  ELSIF v_job.status = 'HUMAN_REVIEW' AND p_job_type = 'ASSESS_EVENT'
        AND EXISTS (SELECT 1 FROM lfhe.model_runs r JOIN lfhe.assessment_ingestion_results i ON i.model_run_id = r.id
                    WHERE r.job_id = v_job.id AND i.outcome IN ('OUTPUT_REJECTED', 'SCHEMA_VALIDATION_FAILED'))
        AND NOT EXISTS (SELECT 1 FROM lfhe.model_runs r JOIN lfhe.assessment_ingestion_results i ON i.model_run_id = r.id
                        WHERE r.job_id = v_job.id AND i.outcome = 'ASSESSMENT_RECORDED')
        AND (SELECT count(*) FROM lfhe.processing_jobs WHERE idempotency_key LIKE p_key || ':retry:%') < 3 THEN
    -- CR7-04: a REJECTED model output recorded nothing; an audited human re-request may run it again (max 3)
    SELECT count(*) INTO v_retries FROM lfhe.processing_jobs WHERE idempotency_key LIKE p_key || ':retry:%';
    v_key := p_key || ':retry:' || (v_retries + 1);
    v_outcome := 'REQUEUED_AFTER_REJECTION';
  ELSE                                              -- SUCCESS / HUMAN_REVIEW / SKIPPED: the run exists; no re-run
    v_outcome := 'ALREADY_COMPLETED';
    v_job_id := v_job.id;
    v_key := v_job.idempotency_key;
  END IF;
  IF v_job_id IS NULL THEN
    v_job_id := lfhe.enqueue_job(p_job_type, p_object_type, p_object_id, v_key, p_payload, 100::smallint,
                                 p_max_attempts, NULL);
  END IF;
  INSERT INTO lfhe.workflow_job_requests (job_type, object_type, object_id, job_id, idempotency_key, outcome,
                                          report_mode, information_cutoff, payload, requested_by, reason)
  VALUES (p_job_type, p_object_type, p_object_id, v_job_id, v_key, v_outcome, p_mode, p_cutoff, p_payload,
          p_actor, btrim(p_reason))
  RETURNING id INTO v_req;
  PERFORM lfhe.write_audit('WORKFLOW_JOB_REQUESTED', 'processing_job', v_job_id::text, NULL,
    pg_catalog.jsonb_build_object('request_id', v_req, 'job_type', p_job_type, 'object_type', p_object_type,
                                  'object_id', p_object_id, 'outcome', v_outcome, 'idempotency_key', v_key,
                                  'report_mode', p_mode, 'information_cutoff', p_cutoff, 'reason', btrim(p_reason)),
    '{}'::jsonb);
  RETURN pg_catalog.jsonb_build_object('request_id', v_req, 'job_id', v_job_id, 'outcome', v_outcome,
                                       'idempotency_key', v_key,
                                       'job_status', (SELECT status::text FROM lfhe.processing_jobs WHERE id = v_job_id));
END $$;


CREATE VIEW lfhe.job_rejection_detail AS
SELECT j.id AS job_id, r.id AS model_run_id, i.outcome, i.rejection_reasons, i.warnings, r.completed_at
FROM lfhe.processing_jobs j
JOIN lfhe.model_runs r ON r.job_id = j.id
JOIN lfhe.assessment_ingestion_results i ON i.model_run_id = r.id
WHERE lfhe.has_permission('CLAIM_READ');
COMMENT ON VIEW lfhe.job_rejection_detail IS 'CR7-04: why an M07 output was rejected (UI read model)';
REVOKE ALL ON lfhe.job_rejection_detail FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT SELECT ON lfhe.job_rejection_detail TO authenticated;
