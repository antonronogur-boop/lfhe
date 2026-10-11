-- ============================================================================
-- CG1-05  Model-run traceability: envelope / input set / context set
--
-- Every model_run now proves separately (docs/model-run-traceability.md):
--   envelope_sha256          RFC 8785 SHA-256 of the exact task envelope sent
--                            to the provider ('lfhe-task-envelope/1'; computed
--                            by the runner — formerly input_sha256)
--   input_manifest           [{object_type, object_id, content_sha256}] of every
--                            evidence/input object in the envelope
--   input_snapshot_sha256    = lfhe.object_set_sha256('lfhe-input-set/1', input_manifest)
--   context_manifest         same for supplied context objects
--   context_snapshot_sha256  = lfhe.object_set_sha256('lfhe-context-set/1', context_manifest)
--   task_parameters          non-object task parameters included in the envelope
-- The two set hashes are computed AND enforced by the database (CHECK), from
-- manifests that name each object and the hash of its exact content — not
-- only opaque ids. Prompt version/hash and model configuration were already
-- bound by composite foreign keys (P1-10).
--
-- Set hash format (order-independent, duplicate-free):
--   sha256( <format> || for each item sorted by (object_type, object_id) in C order:
--           '\n' || object_type || ' ' || object_id || ' ' || content_sha256 )
-- ============================================================================

CREATE OR REPLACE FUNCTION lfhe.object_manifest_valid(p jsonb)
RETURNS boolean LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
  SELECT pg_catalog.jsonb_typeof(p) = 'array'
     AND NOT EXISTS (
       SELECT 1 FROM pg_catalog.jsonb_array_elements(p) e(v)
       WHERE pg_catalog.jsonb_typeof(e.v) <> 'object'
          OR NOT (e.v ?& ARRAY['object_type', 'object_id', 'content_sha256'])
          OR (SELECT count(*) FROM pg_catalog.jsonb_object_keys(e.v)) <> 3
          OR coalesce(e.v ->> 'object_type', '') !~ '^[a-z][a-z0-9_]{1,62}$'
          OR coalesce(e.v ->> 'object_id', '') !~ '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$'
          OR coalesce(e.v ->> 'content_sha256', '') !~ '^[0-9a-f]{64}$')
     AND (SELECT count(*) FROM pg_catalog.jsonb_array_elements(p))
       = (SELECT count(DISTINCT (e.v ->> 'object_type', e.v ->> 'object_id')) FROM pg_catalog.jsonb_array_elements(p) e(v))
$$;
REVOKE ALL ON FUNCTION lfhe.object_manifest_valid(jsonb) FROM PUBLIC;

CREATE OR REPLACE FUNCTION lfhe.object_set_sha256(p_format text, p jsonb)
RETURNS text LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
  SELECT pg_catalog.encode(extensions.digest(
    p_format || coalesce((
      SELECT pg_catalog.string_agg(E'\n' || (e.v ->> 'object_type') || ' ' || (e.v ->> 'object_id') || ' '
                                   || (e.v ->> 'content_sha256'), ''
                                   ORDER BY (e.v ->> 'object_type') COLLATE "C", (e.v ->> 'object_id') COLLATE "C")
      FROM pg_catalog.jsonb_array_elements(p) e(v)), ''),
    'sha256'), 'hex')
$$;
REVOKE ALL ON FUNCTION lfhe.object_set_sha256(text, jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION lfhe.object_set_sha256(text, jsonb) TO lfhe_worker, authenticated;

-- Phase 1 contains only test runs; existing rows (if any) are not rewritten.
ALTER TABLE lfhe.model_runs RENAME COLUMN input_sha256 TO envelope_sha256;
ALTER TABLE lfhe.model_runs DROP COLUMN input_refs;
ALTER TABLE lfhe.model_runs
  ADD COLUMN task_parameters jsonb,
  ADD COLUMN input_manifest jsonb,
  ADD COLUMN input_snapshot_sha256 text,
  ADD COLUMN context_manifest jsonb,
  ADD COLUMN context_snapshot_sha256 text;
ALTER TABLE lfhe.model_runs
  ADD CONSTRAINT model_run_trace_present CHECK (
    task_parameters IS NOT NULL AND input_manifest IS NOT NULL AND context_manifest IS NOT NULL
    AND input_snapshot_sha256 IS NOT NULL AND context_snapshot_sha256 IS NOT NULL) NOT VALID,
  ADD CONSTRAINT model_run_input_manifest_valid CHECK (
    input_manifest IS NULL OR lfhe.object_manifest_valid(input_manifest)),
  ADD CONSTRAINT model_run_context_manifest_valid CHECK (
    context_manifest IS NULL OR lfhe.object_manifest_valid(context_manifest)),
  ADD CONSTRAINT model_run_input_set_hash CHECK (
    input_manifest IS NULL OR input_snapshot_sha256 = lfhe.object_set_sha256('lfhe-input-set/1', input_manifest)),
  ADD CONSTRAINT model_run_context_set_hash CHECK (
    context_manifest IS NULL OR context_snapshot_sha256 = lfhe.object_set_sha256('lfhe-context-set/1', context_manifest)),
  ADD CONSTRAINT model_run_task_parameters_object CHECK (
    task_parameters IS NULL OR pg_catalog.jsonb_typeof(task_parameters) = 'object');
CREATE INDEX model_runs_input_set_idx ON lfhe.model_runs (input_snapshot_sha256);

CREATE OR REPLACE FUNCTION lfhe.model_runs_guard()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'model runs are never deleted' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF OLD.status <> 'RUNNING' THEN
    RAISE EXCEPTION 'model run % is finished and immutable', OLD.id USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF (NEW.id, NEW.module_code, NEW.prompt_version_id, NEW.prompt_semver, NEW.prompt_content_hash,
      NEW.module_version, NEW.model_configuration_id, NEW.provider, NEW.model, NEW.model_config_hash,
      NEW.environment, NEW.envelope_sha256, NEW.task_parameters, NEW.input_manifest, NEW.input_snapshot_sha256,
      NEW.context_manifest, NEW.context_snapshot_sha256, NEW.worker_id, NEW.job_id, NEW.started_at)
     IS DISTINCT FROM
     (OLD.id, OLD.module_code, OLD.prompt_version_id, OLD.prompt_semver, OLD.prompt_content_hash,
      OLD.module_version, OLD.model_configuration_id, OLD.provider, OLD.model, OLD.model_config_hash,
      OLD.environment, OLD.envelope_sha256, OLD.task_parameters, OLD.input_manifest, OLD.input_snapshot_sha256,
      OLD.context_manifest, OLD.context_snapshot_sha256, OLD.worker_id, OLD.job_id, OLD.started_at) THEN
    RAISE EXCEPTION 'model run identity fields are immutable' USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION lfhe.model_runs_guard() FROM PUBLIC;

DROP FUNCTION lfhe.start_model_run(uuid, uuid, text, jsonb, text, uuid);

CREATE OR REPLACE FUNCTION lfhe.start_model_run(
  p_prompt_version_id uuid, p_model_configuration_id uuid, p_envelope_sha256 text,
  p_task_parameters jsonb, p_input_manifest jsonb, p_context_manifest jsonb,
  p_worker text, p_job uuid DEFAULT NULL)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_pv  lfhe.prompt_versions%ROWTYPE;
  v_mc  lfhe.model_configurations%ROWTYPE;
  v_id  uuid;
BEGIN
  IF p_envelope_sha256 IS NULL OR p_envelope_sha256 !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'envelope_sha256 must be a SHA-256 hex digest' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  IF NOT lfhe.object_manifest_valid(p_input_manifest) OR NOT lfhe.object_manifest_valid(p_context_manifest) THEN
    RAISE EXCEPTION 'input/context manifests must be arrays of {object_type, object_id, content_sha256} without duplicates'
      USING ERRCODE = 'invalid_parameter_value';
  END IF;
  SELECT * INTO v_pv FROM lfhe.prompt_versions WHERE id = p_prompt_version_id;
  IF NOT FOUND OR lfhe.current_prompt_version(v_pv.module_code) IS DISTINCT FROM v_pv.id THEN
    RAISE EXCEPTION 'prompt version % is not the active version of its module', p_prompt_version_id
      USING ERRCODE = 'object_not_in_prerequisite_state';
  END IF;
  SELECT * INTO v_mc FROM lfhe.model_configurations WHERE id = p_model_configuration_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'unknown model configuration %', p_model_configuration_id USING ERRCODE = 'no_data_found';
  END IF;
  INSERT INTO lfhe.model_runs (module_code, prompt_version_id, prompt_semver, prompt_content_hash,
    module_version, model_configuration_id, provider, model, model_config_hash, environment,
    envelope_sha256, task_parameters, input_manifest, input_snapshot_sha256,
    context_manifest, context_snapshot_sha256, worker_id, job_id)
  VALUES (v_pv.module_code, v_pv.id, v_pv.semver, v_pv.content_hash, v_pv.module_version,
    v_mc.id, v_mc.provider, v_mc.model, v_mc.config_hash,
    (SELECT environment FROM lfhe.deployment_environment),
    p_envelope_sha256, coalesce(p_task_parameters, '{}'::jsonb),
    p_input_manifest, lfhe.object_set_sha256('lfhe-input-set/1', p_input_manifest),
    p_context_manifest, lfhe.object_set_sha256('lfhe-context-set/1', p_context_manifest),
    p_worker, p_job)
  RETURNING id INTO v_id;
  RETURN v_id;
END $$;
REVOKE ALL ON FUNCTION lfhe.start_model_run(uuid, uuid, text, jsonb, jsonb, jsonb, text, uuid) FROM PUBLIC, anon, authenticated, service_role, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.start_model_run(uuid, uuid, text, jsonb, jsonb, jsonb, text, uuid) TO lfhe_worker;
