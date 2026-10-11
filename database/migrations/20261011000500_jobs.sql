-- ============================================================================
-- P1-07  Jobs and scheduling (DS §31, §36, §37, §91; Handoff §41, §42)
--
-- * processing_jobs: table queue. Idempotency key UNIQUE (a retry or a
--   duplicate enqueue never creates a second job). Workers claim with
--   FOR UPDATE SKIP LOCKED under a time-limited lease; an expired lease is
--   reclaimable. Failures back off exponentially up to max_attempts, then the
--   job is FAILED and a system_error is recorded (operator visibility).
-- * system_errors: append-only operational error log.
-- * Workers have NO direct write privileges on these tables; they act only
--   through the functions below (narrow, auditable surface).
-- ============================================================================

CREATE TABLE lfhe.processing_jobs (
  id               uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  job_type         text NOT NULL CHECK (job_type IN ('COLLECT_SOURCE')),
  object_type      text NOT NULL,
  object_id        text NOT NULL,
  idempotency_key  text NOT NULL UNIQUE CHECK (length(idempotency_key) BETWEEN 8 AND 400),
  payload          jsonb NOT NULL DEFAULT '{}'::jsonb,
  priority         smallint NOT NULL DEFAULT 100,
  status           lfhe.job_status NOT NULL DEFAULT 'PENDING',
  attempt_count    integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  max_attempts     integer NOT NULL DEFAULT 5 CHECK (max_attempts BETWEEN 1 AND 20),
  scheduled_at     timestamptz NOT NULL DEFAULT now(),
  next_attempt_at  timestamptz NOT NULL DEFAULT now(),
  started_at       timestamptz,
  completed_at     timestamptz,
  locked_by        text,
  lock_expires_at  timestamptz,
  last_error       text,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  CHECK (status <> 'RUNNING' OR (locked_by IS NOT NULL AND lock_expires_at IS NOT NULL)),
  CHECK (attempt_count <= max_attempts)
);
CREATE INDEX processing_jobs_claim_idx ON lfhe.processing_jobs (status, next_attempt_at, priority);
CREATE INDEX processing_jobs_object_idx ON lfhe.processing_jobs (job_type, object_type, object_id);

CREATE TABLE lfhe.system_errors (
  id          uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  occurred_at timestamptz NOT NULL DEFAULT now(),
  component   text NOT NULL,
  error_code  text NOT NULL CHECK (error_code ~ '^[A-Z][A-Z0-9_]*$'),
  severity    text NOT NULL CHECK (severity IN ('INFO', 'WARNING', 'ERROR', 'CRITICAL')),
  message     text NOT NULL,
  source_id   uuid REFERENCES lfhe.sources(id),
  job_id      uuid REFERENCES lfhe.processing_jobs(id),
  details     jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX system_errors_recent_idx ON lfhe.system_errors (occurred_at DESC);

CREATE OR REPLACE FUNCTION lfhe.block_mutation()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  RAISE EXCEPTION '% is append-only (% blocked)', TG_TABLE_NAME, TG_OP
    USING ERRCODE = 'insufficient_privilege';
END $$;
REVOKE ALL ON FUNCTION lfhe.block_mutation() FROM PUBLIC;

CREATE TRIGGER system_errors_append_only
  BEFORE UPDATE OR DELETE ON lfhe.system_errors
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();

-- ---------------------------------------------------------------------------
-- Queue functions (worker surface)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.enqueue_job(
  p_job_type text, p_object_type text, p_object_id text, p_idempotency_key text,
  p_payload jsonb DEFAULT '{}'::jsonb, p_priority smallint DEFAULT 100,
  p_max_attempts integer DEFAULT 5, p_not_before timestamptz DEFAULT NULL
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_id uuid;
BEGIN
  INSERT INTO lfhe.processing_jobs (job_type, object_type, object_id, idempotency_key,
                                    payload, priority, max_attempts, next_attempt_at)
  VALUES (p_job_type, p_object_type, p_object_id, p_idempotency_key,
          coalesce(p_payload, '{}'::jsonb), p_priority, p_max_attempts, coalesce(p_not_before, now()))
  ON CONFLICT (idempotency_key) DO NOTHING
  RETURNING id INTO v_id;
  IF v_id IS NULL THEN
    SELECT id INTO v_id FROM lfhe.processing_jobs WHERE idempotency_key = p_idempotency_key;
  END IF;
  RETURN v_id;
END $$;

CREATE OR REPLACE FUNCTION lfhe.claim_jobs(
  p_worker text, p_job_types text[], p_limit integer DEFAULT 1,
  p_lease interval DEFAULT interval '10 minutes'
) RETURNS SETOF lfhe.processing_jobs LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  IF p_worker IS NULL OR length(p_worker) < 3 THEN
    RAISE EXCEPTION 'worker identity required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  RETURN QUERY
  UPDATE lfhe.processing_jobs j SET
    status = 'RUNNING',
    attempt_count = j.attempt_count + 1,
    locked_by = p_worker,
    lock_expires_at = now() + p_lease,
    started_at = now(),
    updated_at = now()
  WHERE j.id IN (
    SELECT c.id FROM lfhe.processing_jobs c
    WHERE c.job_type = ANY (p_job_types)
      AND c.attempt_count < c.max_attempts
      AND ((c.status = 'PENDING' AND c.next_attempt_at <= now())
           OR (c.status = 'RUNNING' AND c.lock_expires_at < now()))
    ORDER BY c.priority, c.next_attempt_at
    LIMIT greatest(p_limit, 1)
    FOR UPDATE SKIP LOCKED
  )
  RETURNING j.*;
END $$;

CREATE OR REPLACE FUNCTION lfhe.complete_job(p_job uuid, p_worker text, p_status lfhe.job_status DEFAULT 'SUCCESS')
RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  IF p_status NOT IN ('SUCCESS', 'SKIPPED', 'HUMAN_REVIEW') THEN
    RAISE EXCEPTION 'complete_job: status % not allowed', p_status USING ERRCODE = 'invalid_parameter_value';
  END IF;
  UPDATE lfhe.processing_jobs SET status = p_status, completed_at = now(), locked_by = NULL,
         lock_expires_at = NULL, updated_at = now()
  WHERE id = p_job AND status = 'RUNNING' AND locked_by = p_worker;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'job % is not running under worker %', p_job, p_worker
      USING ERRCODE = 'object_not_in_prerequisite_state';
  END IF;
END $$;

CREATE OR REPLACE FUNCTION lfhe.fail_job(
  p_job uuid, p_worker text, p_error text, p_retryable boolean DEFAULT true,
  p_backoff_base interval DEFAULT interval '1 minute', p_backoff_max interval DEFAULT interval '6 hours'
) RETURNS lfhe.job_status LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_job lfhe.processing_jobs%ROWTYPE;
  v_delay interval;
BEGIN
  SELECT * INTO v_job FROM lfhe.processing_jobs
  WHERE id = p_job AND status = 'RUNNING' AND locked_by = p_worker FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'job % is not running under worker %', p_job, p_worker
      USING ERRCODE = 'object_not_in_prerequisite_state';
  END IF;

  IF p_retryable AND v_job.attempt_count < v_job.max_attempts THEN
    v_delay := least(p_backoff_base * power(2, v_job.attempt_count - 1), p_backoff_max);
    UPDATE lfhe.processing_jobs SET status = 'PENDING', next_attempt_at = now() + v_delay,
           locked_by = NULL, lock_expires_at = NULL, last_error = left(p_error, 4000), updated_at = now()
    WHERE id = p_job;
    RETURN 'PENDING';
  END IF;

  UPDATE lfhe.processing_jobs SET status = 'FAILED', completed_at = now(), locked_by = NULL,
         lock_expires_at = NULL, last_error = left(p_error, 4000), updated_at = now()
  WHERE id = p_job;
  INSERT INTO lfhe.system_errors (component, error_code, severity, message, job_id, source_id, details)
  VALUES ('jobs', 'JOB_FAILED_PERMANENTLY', 'ERROR', left(p_error, 4000), p_job,
          CASE WHEN v_job.object_type = 'source' THEN v_job.object_id::uuid END,
          jsonb_build_object('job_type', v_job.job_type, 'attempts', v_job.attempt_count,
                             'retryable', p_retryable));
  RETURN 'FAILED';
END $$;

-- Stale RUNNING jobs whose lease expired after the last allowed attempt.
CREATE OR REPLACE FUNCTION lfhe.fail_exhausted_stale_jobs()
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_n integer;
BEGIN
  WITH stale AS (
    UPDATE lfhe.processing_jobs SET status = 'FAILED', completed_at = now(), locked_by = NULL,
           lock_expires_at = NULL, last_error = coalesce(last_error, 'lease expired after final attempt'),
           updated_at = now()
    WHERE status = 'RUNNING' AND lock_expires_at < now() AND attempt_count >= max_attempts
    RETURNING id, job_type, object_type, object_id, attempt_count
  )
  INSERT INTO lfhe.system_errors (component, error_code, severity, message, job_id, details)
  SELECT 'jobs', 'JOB_LEASE_EXPIRED_EXHAUSTED', 'ERROR', 'lease expired after final attempt', id,
         jsonb_build_object('job_type', job_type, 'attempts', attempt_count)
  FROM stale;
  GET DIAGNOSTICS v_n = ROW_COUNT;
  RETURN v_n;
END $$;

CREATE OR REPLACE FUNCTION lfhe.record_system_error(
  p_component text, p_error_code text, p_severity text, p_message text,
  p_source_id uuid DEFAULT NULL, p_job_id uuid DEFAULT NULL, p_details jsonb DEFAULT '{}'::jsonb
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_id uuid;
BEGIN
  INSERT INTO lfhe.system_errors (component, error_code, severity, message, source_id, job_id, details)
  VALUES (p_component, p_error_code, p_severity, left(p_message, 4000), p_source_id, p_job_id,
          coalesce(p_details, '{}'::jsonb))
  RETURNING id INTO v_id;
  RETURN v_id;
END $$;

-- Grants: worker surface only.
DO $$
DECLARE
  f text;
BEGIN
  FOREACH f IN ARRAY ARRAY[
    'lfhe.enqueue_job(text, text, text, text, jsonb, smallint, integer, timestamptz)',
    'lfhe.claim_jobs(text, text[], integer, interval)',
    'lfhe.complete_job(uuid, text, lfhe.job_status)',
    'lfhe.fail_job(uuid, text, text, boolean, interval, interval)',
    'lfhe.fail_exhausted_stale_jobs()',
    'lfhe.record_system_error(text, text, text, text, uuid, uuid, jsonb)'
  ] LOOP
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC, anon, authenticated, service_role, lfhe_evaluator', f);
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO lfhe_worker', f);
  END LOOP;
END $$;

REVOKE ALL ON lfhe.processing_jobs, lfhe.system_errors
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator;
GRANT SELECT ON lfhe.processing_jobs, lfhe.system_errors TO authenticated, lfhe_worker;
ALTER TABLE lfhe.processing_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE lfhe.system_errors ENABLE ROW LEVEL SECURITY;
CREATE POLICY processing_jobs_read_human ON lfhe.processing_jobs FOR SELECT TO authenticated
  USING (lfhe.has_permission('SYSTEM_READ'));
CREATE POLICY processing_jobs_read_worker ON lfhe.processing_jobs FOR SELECT TO lfhe_worker USING (true);
CREATE POLICY system_errors_read_human ON lfhe.system_errors FOR SELECT TO authenticated
  USING (lfhe.has_permission('SYSTEM_READ'));
CREATE POLICY system_errors_read_worker ON lfhe.system_errors FOR SELECT TO lfhe_worker USING (true);
