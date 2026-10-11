-- ============================================================================
-- P1-08  Collection runs and the scheduling entry point (DS §29, §31, §91)
--
-- * collection_runs: one row per execution; coverage and failures measurable.
--   A run is RUNNING until finished exactly once; finished runs are immutable.
--   SOURCE_UNAVAILABLE is a collection outcome, never evidence that no event
--   occurred (Handoff §48).
-- * lfhe.enqueue_due_collections(): the single scheduling entry point. It
--   enqueues COLLECT_SOURCE jobs for collectable sources whose frequency has
--   elapsed. In Supabase it is invoked by pg_cron (migration 0601); idempotency
--   keys make repeated or concurrent invocations harmless.
-- ============================================================================

CREATE TABLE lfhe.collection_runs (
  id               uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  source_id        uuid NOT NULL REFERENCES lfhe.sources(id),
  job_id           uuid REFERENCES lfhe.processing_jobs(id),
  worker_id        text NOT NULL,
  started_at       timestamptz NOT NULL DEFAULT now(),
  completed_at     timestamptz,
  status           lfhe.collection_run_status NOT NULL DEFAULT 'RUNNING',
  items_discovered integer NOT NULL DEFAULT 0 CHECK (items_discovered >= 0),
  items_new        integer NOT NULL DEFAULT 0 CHECK (items_new >= 0),
  items_revised    integer NOT NULL DEFAULT 0 CHECK (items_revised >= 0),
  items_duplicate  integer NOT NULL DEFAULT 0 CHECK (items_duplicate >= 0),
  items_skipped    integer NOT NULL DEFAULT 0 CHECK (items_skipped >= 0),
  items_failed     integer NOT NULL DEFAULT 0 CHECK (items_failed >= 0),
  error_code       text,
  error_message    text,
  details          jsonb NOT NULL DEFAULT '{}'::jsonb,
  CHECK ((status = 'RUNNING') = (completed_at IS NULL))
);
CREATE INDEX collection_runs_source_idx ON lfhe.collection_runs (source_id, started_at DESC);

CREATE OR REPLACE FUNCTION lfhe.collection_runs_guard()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'collection runs are never deleted' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF OLD.status <> 'RUNNING' THEN
    RAISE EXCEPTION 'collection run % is finished and immutable', OLD.id USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF NEW.id <> OLD.id OR NEW.source_id <> OLD.source_id OR NEW.started_at <> OLD.started_at
     OR NEW.worker_id <> OLD.worker_id THEN
    RAISE EXCEPTION 'collection run identity fields are immutable' USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION lfhe.collection_runs_guard() FROM PUBLIC;

CREATE TRIGGER collection_runs_guard
  BEFORE UPDATE OR DELETE ON lfhe.collection_runs
  FOR EACH ROW EXECUTE FUNCTION lfhe.collection_runs_guard();

CREATE OR REPLACE FUNCTION lfhe.start_collection_run(p_source uuid, p_job uuid, p_worker text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_id uuid;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM lfhe.collectable_sources s WHERE s.id = p_source) THEN
    RAISE EXCEPTION 'source % is not collectable (inactive or method not approved)', p_source
      USING ERRCODE = 'object_not_in_prerequisite_state';
  END IF;
  INSERT INTO lfhe.collection_runs (source_id, job_id, worker_id) VALUES (p_source, p_job, p_worker)
  RETURNING id INTO v_id;
  RETURN v_id;
END $$;

CREATE OR REPLACE FUNCTION lfhe.finish_collection_run(
  p_run uuid, p_status lfhe.collection_run_status, p_counts jsonb,
  p_error_code text DEFAULT NULL, p_error_message text DEFAULT NULL, p_details jsonb DEFAULT '{}'::jsonb
) RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  IF p_status = 'RUNNING' THEN
    RAISE EXCEPTION 'finish_collection_run requires a terminal status' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  UPDATE lfhe.collection_runs SET
    status = p_status,
    completed_at = now(),
    items_discovered = coalesce((p_counts ->> 'discovered')::int, 0),
    items_new        = coalesce((p_counts ->> 'new')::int, 0),
    items_revised    = coalesce((p_counts ->> 'revised')::int, 0),
    items_duplicate  = coalesce((p_counts ->> 'duplicate')::int, 0),
    items_skipped    = coalesce((p_counts ->> 'skipped')::int, 0),
    items_failed     = coalesce((p_counts ->> 'failed')::int, 0),
    error_code = p_error_code,
    error_message = left(p_error_message, 4000),
    details = coalesce(p_details, '{}'::jsonb)
  WHERE id = p_run AND status = 'RUNNING';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'collection run % is not running', p_run USING ERRCODE = 'object_not_in_prerequisite_state';
  END IF;
END $$;

-- Collection coverage per source (derived; nothing stored on sources).
CREATE VIEW lfhe.source_collection_status WITH (security_invoker = true) AS
SELECT s.id AS source_id, s.name, s.active, s.collection_method_approved, s.collection_frequency,
       last_run.started_at AS last_run_started_at, last_run.status AS last_run_status,
       last_ok.completed_at AS last_success_at,
       (SELECT count(*) FROM lfhe.collection_runs r
         WHERE r.source_id = s.id AND r.status IN ('FAILED', 'SOURCE_UNAVAILABLE')
           AND r.started_at > now() - interval '7 days') AS failures_7d
FROM lfhe.sources s
LEFT JOIN LATERAL (SELECT started_at, status FROM lfhe.collection_runs r
                   WHERE r.source_id = s.id ORDER BY started_at DESC LIMIT 1) last_run ON true
LEFT JOIN LATERAL (SELECT completed_at FROM lfhe.collection_runs r
                   WHERE r.source_id = s.id AND r.status IN ('SUCCESS', 'PARTIAL')
                   ORDER BY started_at DESC LIMIT 1) last_ok ON true;

-- ---------------------------------------------------------------------------
-- Scheduling entry point
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.enqueue_due_collections()
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_src record;
  v_n integer := 0;
  v_bucket bigint;
BEGIN
  PERFORM lfhe.fail_exhausted_stale_jobs();
  FOR v_src IN
    SELECT s.id, s.collection_frequency, s.collection_priority
    FROM lfhe.collectable_sources s
    WHERE NOT EXISTS (SELECT 1 FROM lfhe.collection_runs r
                      WHERE r.source_id = s.id AND r.started_at > now() - s.collection_frequency)
      AND NOT EXISTS (SELECT 1 FROM lfhe.processing_jobs j
                      WHERE j.job_type = 'COLLECT_SOURCE' AND j.object_type = 'source'
                        AND j.object_id = s.id::text AND j.status IN ('PENDING', 'RUNNING'))
  LOOP
    v_bucket := floor(extract(epoch FROM now()) / extract(epoch FROM v_src.collection_frequency))::bigint;
    PERFORM lfhe.enqueue_job('COLLECT_SOURCE', 'source', v_src.id::text,
      format('collect:%s:%s', v_src.id, v_bucket), '{}'::jsonb,
      (v_src.collection_priority * 10)::smallint, 5, NULL);
    v_n := v_n + 1;
  END LOOP;
  RETURN v_n;
END $$;

DO $$
DECLARE
  f text;
BEGIN
  FOREACH f IN ARRAY ARRAY[
    'lfhe.start_collection_run(uuid, uuid, text)',
    'lfhe.finish_collection_run(uuid, lfhe.collection_run_status, jsonb, text, text, jsonb)',
    'lfhe.enqueue_due_collections()'
  ] LOOP
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC, anon, authenticated, service_role, lfhe_evaluator', f);
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO lfhe_worker', f);
  END LOOP;
END $$;

REVOKE ALL ON lfhe.collection_runs FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator;
GRANT SELECT ON lfhe.collection_runs TO authenticated, lfhe_worker;
GRANT SELECT ON lfhe.source_collection_status TO authenticated, lfhe_worker;
ALTER TABLE lfhe.collection_runs ENABLE ROW LEVEL SECURITY;
CREATE POLICY collection_runs_read_human ON lfhe.collection_runs FOR SELECT TO authenticated
  USING (lfhe.has_permission('SYSTEM_READ') OR lfhe.has_permission('SOURCE_READ'));
CREATE POLICY collection_runs_read_worker ON lfhe.collection_runs FOR SELECT TO lfhe_worker USING (true);
