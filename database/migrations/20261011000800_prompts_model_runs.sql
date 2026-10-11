-- ============================================================================
-- P1-10  Prompt-version and model-run foundation (PO guardrail 3)
--
-- Source of truth (documented in docs/prompt-versioning.md):
--   * Git is where prompt artifacts are authored and preserved:
--       packages/prompts/<MODULE>/<semver>/{manifest.json, system.md, task.md,
--       output_schema.json}
--   * The database stores, immutably, the exact registered artifact (all file
--     contents) plus a content hash that the DATABASE ITSELF computes
--     (lfhe.prompt_bundle_sha256, format 'lfhe-prompt-bundle/1'). A
--     prompt_versions row can therefore never refer to different content:
--       - rows are immutable (no UPDATE/DELETE, even for the owner);
--       - UNIQUE (module_code, semver);
--       - CHECK content_hash = prompt_bundle_sha256(module, semver, files);
--       - registering an existing (module, semver) with different content is
--         rejected (PROMPT_VERSION_CONFLICT) — a new semver is required.
--   * Activation is a separate, append-only, human-only, audited act per
--     deployment environment (prompt_activations).
--   * Every model_run carries prompt_version_id, prompt semver, exact content
--     hash, module version and model/provider configuration, bound by
--     composite foreign keys so the copied identifiers cannot disagree with
--     the registered records.
--
-- Phase 1 contains NO M02–M10 prompts and no analytical behaviour; only a
-- test-fixture module is registered by the test-suite (never in PROD).
-- ============================================================================

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lfhe_registrar') THEN
    -- Deployment pipeline role: registers Git artifacts. Cannot activate.
    CREATE ROLE lfhe_registrar NOLOGIN NOINHERIT;
  END IF;
END $$;
GRANT USAGE ON SCHEMA lfhe TO lfhe_registrar;

INSERT INTO lfhe.audit_event_types (code, spec_source) VALUES
  ('MODEL_CONFIGURATION_REGISTERED', 'Phase 1 impl.');

CREATE TYPE lfhe.model_run_status AS ENUM (
  'RUNNING', 'SUCCEEDED', 'SCHEMA_VALIDATION_FAILED', 'PROVIDER_ERROR'
);

-- ---------------------------------------------------------------------------
-- Bundle hashing and validation (pure functions; mirrored in lfhe_shared.prompts)
--   lines = ['lfhe-prompt-bundle/1', module_code, semver,
--            '<file name> <sha256(file UTF-8)>' for each file sorted by name (C order)]
--   content_hash = sha256(UTF-8 of lines joined with '\n')
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.prompt_bundle_sha256(p_module text, p_semver text, p_files jsonb)
RETURNS text LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
  SELECT pg_catalog.encode(extensions.digest(
    'lfhe-prompt-bundle/1' || E'\n' || p_module || E'\n' || p_semver ||
    coalesce((SELECT pg_catalog.string_agg(E'\n' || f.key || ' ' ||
                pg_catalog.encode(extensions.digest(f.value, 'sha256'), 'hex'), '' ORDER BY f.key COLLATE "C")
              FROM pg_catalog.jsonb_each_text(p_files) f), ''),
    'sha256'), 'hex')
$$;
REVOKE ALL ON FUNCTION lfhe.prompt_bundle_sha256(text, text, jsonb) FROM PUBLIC;

CREATE OR REPLACE FUNCTION lfhe.prompt_bundle_valid(
  p_module text, p_semver text, p_module_version text, p_is_fixture boolean, p_files jsonb)
RETURNS boolean LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_manifest jsonb;
  v_schema   jsonb;
BEGIN
  IF pg_catalog.jsonb_typeof(p_files) <> 'object' THEN
    RETURN false;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_catalog.jsonb_each(p_files) f
             WHERE f.key !~ '^[a-z0-9][a-z0-9_.-]{0,63}$' OR pg_catalog.jsonb_typeof(f.value) <> 'string') THEN
    RETURN false;
  END IF;
  IF NOT (p_files ?& ARRAY['manifest.json', 'system.md', 'task.md', 'output_schema.json']) THEN
    RETURN false;
  END IF;
  BEGIN
    v_manifest := (p_files ->> 'manifest.json')::jsonb;
    v_schema   := (p_files ->> 'output_schema.json')::jsonb;
  EXCEPTION WHEN others THEN
    RETURN false;
  END;
  RETURN pg_catalog.jsonb_typeof(v_schema) = 'object'
     AND v_manifest ->> 'format' = 'lfhe-prompt-manifest/1'
     AND v_manifest ->> 'module_code' = p_module
     AND v_manifest ->> 'semver' = p_semver
     AND v_manifest ->> 'module_version' = p_module_version
     AND coalesce((v_manifest ->> 'test_fixture')::boolean, false) = p_is_fixture;
END $$;
REVOKE ALL ON FUNCTION lfhe.prompt_bundle_valid(text, text, text, boolean, jsonb) FROM PUBLIC;

-- ---------------------------------------------------------------------------
-- prompt_versions (immutable registry of Git artifacts)
-- ---------------------------------------------------------------------------
CREATE TABLE lfhe.prompt_versions (
  id                 uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  module_code        text NOT NULL CHECK (module_code ~ '^[A-Z][A-Z0-9_]{1,39}$'),
  semver             text NOT NULL CHECK (semver ~ '^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$'),
  module_version     text NOT NULL CHECK (length(module_version) BETWEEN 1 AND 100),
  is_test_fixture    boolean NOT NULL,
  files              jsonb NOT NULL,
  content_hash       text NOT NULL,
  git_path           text NOT NULL,
  git_commit         text CHECK (git_commit ~ '^[0-9a-f]{40}$'),
  git_tree_clean     boolean NOT NULL,
  registered_at      timestamptz NOT NULL DEFAULT now(),
  registered_by_role text NOT NULL DEFAULT session_user,
  UNIQUE (module_code, semver),
  UNIQUE (id, module_code),
  UNIQUE (id, module_code, semver, content_hash, module_version),
  CONSTRAINT prompt_content_hash_matches CHECK (
    content_hash = lfhe.prompt_bundle_sha256(module_code, semver, files)),
  CONSTRAINT prompt_bundle_valid CHECK (
    lfhe.prompt_bundle_valid(module_code, semver, module_version, is_test_fixture, files)),
  CONSTRAINT prompt_git_path_consistent CHECK (
    git_path = 'packages/prompts/' || module_code || '/' || semver
    OR (is_test_fixture AND git_path LIKE 'tests/fixtures/prompts/%'))
);
CREATE TRIGGER prompt_versions_immutable BEFORE UPDATE OR DELETE ON lfhe.prompt_versions
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();

CREATE OR REPLACE FUNCTION lfhe.audit_prompt_version()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  -- File contents are integrity-protected by content_hash; audit records hashes.
  PERFORM lfhe.write_audit('PROMPT_VERSION_CREATED', 'prompt_version', NEW.id::text, NULL,
    pg_catalog.to_jsonb(NEW) - 'files',
    pg_catalog.jsonb_build_object('file_sha256', (
      SELECT pg_catalog.jsonb_object_agg(f.key, pg_catalog.encode(extensions.digest(f.value, 'sha256'), 'hex'))
      FROM pg_catalog.jsonb_each_text(NEW.files) f)));
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION lfhe.audit_prompt_version() FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
CREATE TRIGGER prompt_versions_audit AFTER INSERT ON lfhe.prompt_versions
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_prompt_version();

-- Registration (deployment pipeline). Idempotent for identical content;
-- same (module, semver) with different content → PROMPT_VERSION_CONFLICT.
-- p: {module_code, semver, module_version, is_test_fixture, files{}, git_path,
--     git_commit|null, git_tree_clean, expected_content_hash}
CREATE OR REPLACE FUNCTION lfhe.register_prompt_version(p jsonb)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_hash     text := lfhe.prompt_bundle_sha256(p ->> 'module_code', p ->> 'semver', p -> 'files');
  v_existing lfhe.prompt_versions%ROWTYPE;
  v_id       uuid;
BEGIN
  IF p ->> 'expected_content_hash' IS DISTINCT FROM v_hash THEN
    RAISE EXCEPTION 'PROMPT_HASH_MISMATCH: client hash % ≠ database hash %', p ->> 'expected_content_hash', v_hash
      USING ERRCODE = 'data_exception';
  END IF;
  PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtext('lfhe.prompt:' || (p ->> 'module_code')));
  SELECT * INTO v_existing FROM lfhe.prompt_versions
  WHERE module_code = p ->> 'module_code' AND semver = p ->> 'semver';
  IF FOUND THEN
    IF v_existing.content_hash = v_hash THEN
      RETURN v_existing.id;
    END IF;
    RAISE EXCEPTION 'PROMPT_VERSION_CONFLICT: % % is already registered with content %; a new semver is required',
      v_existing.module_code, v_existing.semver, v_existing.content_hash
      USING ERRCODE = 'unique_violation';
  END IF;
  INSERT INTO lfhe.prompt_versions (module_code, semver, module_version, is_test_fixture, files,
                                    content_hash, git_path, git_commit, git_tree_clean)
  VALUES (p ->> 'module_code', p ->> 'semver', p ->> 'module_version',
          coalesce((p ->> 'is_test_fixture')::boolean, false), p -> 'files', v_hash,
          p ->> 'git_path', p ->> 'git_commit', coalesce((p ->> 'git_tree_clean')::boolean, false))
  RETURNING id INTO v_id;
  RETURN v_id;
END $$;
REVOKE ALL ON FUNCTION lfhe.register_prompt_version(jsonb) FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator;
GRANT EXECUTE ON FUNCTION lfhe.register_prompt_version(jsonb) TO lfhe_registrar;

-- ---------------------------------------------------------------------------
-- prompt_activations (append-only, human-only, audited)
-- ---------------------------------------------------------------------------
CREATE TABLE lfhe.prompt_activations (
  seq                        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id                         uuid NOT NULL UNIQUE DEFAULT pg_catalog.gen_random_uuid(),
  module_code                text NOT NULL,
  action                     text NOT NULL CHECK (action IN ('ACTIVATE', 'DEACTIVATE')),
  prompt_version_id          uuid,
  previous_prompt_version_id uuid REFERENCES lfhe.prompt_versions(id),
  environment                text NOT NULL CHECK (environment IN ('DEV', 'TEST', 'PROD')),
  actor_user_id              uuid NOT NULL,
  reason                     text NOT NULL CHECK (length(btrim(reason)) >= 5),
  created_at                 timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (prompt_version_id, module_code) REFERENCES lfhe.prompt_versions(id, module_code),
  CHECK ((action = 'ACTIVATE') = (prompt_version_id IS NOT NULL)),
  CHECK (action = 'ACTIVATE' OR previous_prompt_version_id IS NOT NULL)
);
CREATE TRIGGER prompt_activations_append_only BEFORE UPDATE OR DELETE ON lfhe.prompt_activations
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();

CREATE OR REPLACE FUNCTION lfhe.audit_prompt_activation()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  PERFORM lfhe.write_audit(
    CASE NEW.action WHEN 'ACTIVATE' THEN 'PROMPT_VERSION_ACTIVATED' ELSE 'PROMPT_VERSION_DEACTIVATED' END,
    'prompt_version', coalesce(NEW.prompt_version_id, NEW.previous_prompt_version_id)::text,
    NULL, pg_catalog.to_jsonb(NEW), pg_catalog.jsonb_build_object('module_code', NEW.module_code));
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION lfhe.audit_prompt_activation() FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
CREATE TRIGGER prompt_activations_audit AFTER INSERT ON lfhe.prompt_activations
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_prompt_activation();

-- Current state is derived from the append-only log (no mutable "active" flag).
CREATE VIEW lfhe.active_prompt_versions WITH (security_invoker = true) AS
SELECT pv.module_code, pv.id AS prompt_version_id, pv.semver, pv.content_hash, pv.module_version,
       latest.created_at AS activated_at, latest.actor_user_id AS activated_by
FROM (SELECT DISTINCT ON (a.module_code) a.*
      FROM lfhe.prompt_activations a ORDER BY a.module_code, a.seq DESC) latest
JOIN lfhe.prompt_versions pv ON pv.id = latest.prompt_version_id
WHERE latest.action = 'ACTIVATE';

CREATE OR REPLACE FUNCTION lfhe.current_prompt_version(p_module text)
RETURNS uuid LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT CASE WHEN a.action = 'ACTIVATE' THEN a.prompt_version_id END
  FROM lfhe.prompt_activations a WHERE a.module_code = p_module ORDER BY a.seq DESC LIMIT 1
$$;
REVOKE ALL ON FUNCTION lfhe.current_prompt_version(text) FROM PUBLIC, anon, service_role, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.current_prompt_version(text) TO authenticated, lfhe_worker;

CREATE OR REPLACE FUNCTION lfhe.activate_prompt_version(p_prompt_version_id uuid, p_reason text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('PROMPT_ACTIVATE');
  v_pv    lfhe.prompt_versions%ROWTYPE;
  v_env   text := (SELECT environment FROM lfhe.deployment_environment);
  v_prev  uuid;
BEGIN
  IF p_reason IS NULL OR length(btrim(p_reason)) < 5 THEN
    RAISE EXCEPTION 'a reason is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  IF v_env IS NULL THEN
    RAISE EXCEPTION 'deployment environment not recorded' USING ERRCODE = 'object_not_in_prerequisite_state';
  END IF;
  SELECT * INTO v_pv FROM lfhe.prompt_versions WHERE id = p_prompt_version_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'unknown prompt version %', p_prompt_version_id USING ERRCODE = 'no_data_found';
  END IF;
  IF v_env = 'PROD' AND (v_pv.is_test_fixture OR v_pv.git_commit IS NULL OR NOT v_pv.git_tree_clean) THEN
    RAISE EXCEPTION 'PROD activation requires a non-fixture prompt registered from a clean, committed Git tree'
      USING ERRCODE = 'check_violation';
  END IF;
  PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtext('lfhe.prompt:' || v_pv.module_code));
  v_prev := lfhe.current_prompt_version(v_pv.module_code);
  IF v_prev = v_pv.id THEN
    RAISE EXCEPTION 'prompt version % is already active', v_pv.id USING ERRCODE = 'object_not_in_prerequisite_state';
  END IF;
  INSERT INTO lfhe.prompt_activations (module_code, action, prompt_version_id, previous_prompt_version_id,
                                       environment, actor_user_id, reason)
  VALUES (v_pv.module_code, 'ACTIVATE', v_pv.id, v_prev, v_env, v_actor, p_reason);
END $$;
COMMENT ON FUNCTION lfhe.activate_prompt_version(uuid, text) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.deactivate_prompt_module(p_module_code text, p_reason text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('PROMPT_ACTIVATE');
  v_env   text := (SELECT environment FROM lfhe.deployment_environment);
  v_prev  uuid;
BEGIN
  IF p_reason IS NULL OR length(btrim(p_reason)) < 5 THEN
    RAISE EXCEPTION 'a reason is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtext('lfhe.prompt:' || p_module_code));
  v_prev := lfhe.current_prompt_version(p_module_code);
  IF v_prev IS NULL THEN
    RAISE EXCEPTION 'module % has no active prompt version', p_module_code
      USING ERRCODE = 'object_not_in_prerequisite_state';
  END IF;
  INSERT INTO lfhe.prompt_activations (module_code, action, prompt_version_id, previous_prompt_version_id,
                                       environment, actor_user_id, reason)
  VALUES (p_module_code, 'DEACTIVATE', NULL, v_prev, v_env, v_actor, p_reason);
END $$;
COMMENT ON FUNCTION lfhe.deactivate_prompt_module(text, text) IS 'HUMAN_ONLY';

REVOKE ALL ON FUNCTION lfhe.activate_prompt_version(uuid, text) FROM PUBLIC, anon, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
REVOKE ALL ON FUNCTION lfhe.deactivate_prompt_module(text, text) FROM PUBLIC, anon, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.activate_prompt_version(uuid, text), lfhe.deactivate_prompt_module(text, text)
  TO authenticated;

-- ---------------------------------------------------------------------------
-- model_configurations (immutable; hash computed by the database)
--   config_hash = sha256('lfhe-model-config/1\n' || provider || '\n' || model
--                        || '\n' || settings::jsonb::text)
-- ---------------------------------------------------------------------------
CREATE TABLE lfhe.model_configurations (
  id            uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  provider      text NOT NULL CHECK (provider ~ '^[a-z][a-z0-9_-]{1,39}$'),
  model         text NOT NULL CHECK (length(model) BETWEEN 1 AND 200),
  settings      jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(settings) = 'object'),
  config_hash   text GENERATED ALWAYS AS (pg_catalog.encode(extensions.digest(
                  'lfhe-model-config/1' || E'\n' || provider || E'\n' || model || E'\n' || settings::text,
                  'sha256'), 'hex')) STORED,
  registered_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (config_hash),
  UNIQUE (id, provider, model, config_hash),
  CONSTRAINT model_settings_have_no_credentials CHECK (NOT (settings ?| ARRAY[
    'api_key', 'apikey', 'key', 'token', 'secret', 'password', 'authorization', 'headers', 'auth']))
);
CREATE TRIGGER model_configurations_immutable BEFORE UPDATE OR DELETE ON lfhe.model_configurations
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();
CREATE TRIGGER model_configurations_audit AFTER INSERT ON lfhe.model_configurations
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_row_change('MODEL_CONFIGURATION_REGISTERED', '-', '-', 'model_configuration');

CREATE OR REPLACE FUNCTION lfhe.register_model_configuration(p_provider text, p_model text, p_settings jsonb)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_id uuid;
BEGIN
  INSERT INTO lfhe.model_configurations (provider, model, settings)
  VALUES (p_provider, p_model, coalesce(p_settings, '{}'::jsonb))
  ON CONFLICT (config_hash) DO NOTHING
  RETURNING id INTO v_id;
  IF v_id IS NULL THEN
    SELECT id INTO v_id FROM lfhe.model_configurations
    WHERE provider = p_provider AND model = p_model AND settings = coalesce(p_settings, '{}'::jsonb);
  END IF;
  RETURN v_id;
END $$;
REVOKE ALL ON FUNCTION lfhe.register_model_configuration(text, text, jsonb) FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator;
GRANT EXECUTE ON FUNCTION lfhe.register_model_configuration(text, text, jsonb) TO lfhe_registrar;

-- ---------------------------------------------------------------------------
-- model_runs (one row per provider call; terminal rows immutable)
-- ---------------------------------------------------------------------------
CREATE TABLE lfhe.model_runs (
  id                     uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  module_code            text NOT NULL,
  prompt_version_id      uuid NOT NULL,
  prompt_semver          text NOT NULL,
  prompt_content_hash    text NOT NULL,
  module_version         text NOT NULL,
  model_configuration_id uuid NOT NULL,
  provider               text NOT NULL,
  model                  text NOT NULL,
  model_config_hash      text NOT NULL,
  environment            text NOT NULL CHECK (environment IN ('DEV', 'TEST', 'PROD')),
  input_sha256           text NOT NULL CHECK (input_sha256 ~ '^[0-9a-f]{64}$'),
  input_refs             jsonb NOT NULL DEFAULT '{}'::jsonb,
  status                 lfhe.model_run_status NOT NULL DEFAULT 'RUNNING',
  raw_output             text,
  raw_output_sha256      text,
  parsed_output          jsonb,
  validation_errors      jsonb,
  error_code             text,
  error_message          text,
  usage                  jsonb NOT NULL DEFAULT '{}'::jsonb,
  worker_id              text NOT NULL CHECK (length(worker_id) BETWEEN 3 AND 200),
  job_id                 uuid REFERENCES lfhe.processing_jobs(id),
  started_at             timestamptz NOT NULL DEFAULT now(),
  completed_at           timestamptz,
  FOREIGN KEY (prompt_version_id, module_code, prompt_semver, prompt_content_hash, module_version)
    REFERENCES lfhe.prompt_versions (id, module_code, semver, content_hash, module_version),
  FOREIGN KEY (model_configuration_id, provider, model, model_config_hash)
    REFERENCES lfhe.model_configurations (id, provider, model, config_hash),
  CONSTRAINT model_run_raw_hash CHECK (
    (raw_output IS NULL AND raw_output_sha256 IS NULL) OR
    raw_output_sha256 = pg_catalog.encode(extensions.digest(raw_output, 'sha256'), 'hex')),
  CONSTRAINT model_run_status_consistent CHECK (CASE status
    WHEN 'RUNNING' THEN completed_at IS NULL AND raw_output IS NULL AND parsed_output IS NULL
                        AND validation_errors IS NULL AND error_code IS NULL
    WHEN 'SUCCEEDED' THEN completed_at IS NOT NULL AND raw_output IS NOT NULL AND parsed_output IS NOT NULL
                          AND validation_errors IS NULL AND error_code IS NULL
    WHEN 'SCHEMA_VALIDATION_FAILED' THEN completed_at IS NOT NULL AND raw_output IS NOT NULL
                          AND parsed_output IS NULL AND validation_errors IS NOT NULL
                          AND error_code = 'SCHEMA_VALIDATION_FAILED'
    WHEN 'PROVIDER_ERROR' THEN completed_at IS NOT NULL AND parsed_output IS NULL AND error_code IS NOT NULL
  END)
);
CREATE INDEX model_runs_prompt_idx ON lfhe.model_runs (prompt_version_id);

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
      NEW.environment, NEW.input_sha256, NEW.input_refs, NEW.worker_id, NEW.job_id, NEW.started_at)
     IS DISTINCT FROM
     (OLD.id, OLD.module_code, OLD.prompt_version_id, OLD.prompt_semver, OLD.prompt_content_hash,
      OLD.module_version, OLD.model_configuration_id, OLD.provider, OLD.model, OLD.model_config_hash,
      OLD.environment, OLD.input_sha256, OLD.input_refs, OLD.worker_id, OLD.job_id, OLD.started_at) THEN
    RAISE EXCEPTION 'model run identity fields are immutable' USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION lfhe.model_runs_guard() FROM PUBLIC;
CREATE TRIGGER model_runs_guard BEFORE UPDATE OR DELETE ON lfhe.model_runs
  FOR EACH ROW EXECUTE FUNCTION lfhe.model_runs_guard();

-- Starting a run requires the prompt version to be the ACTIVE version of its
-- module in this environment; identifiers are copied from the registry.
CREATE OR REPLACE FUNCTION lfhe.start_model_run(
  p_prompt_version_id uuid, p_model_configuration_id uuid, p_input_sha256 text,
  p_input_refs jsonb, p_worker text, p_job uuid DEFAULT NULL)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_pv  lfhe.prompt_versions%ROWTYPE;
  v_mc  lfhe.model_configurations%ROWTYPE;
  v_id  uuid;
BEGIN
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
    input_sha256, input_refs, worker_id, job_id)
  VALUES (v_pv.module_code, v_pv.id, v_pv.semver, v_pv.content_hash, v_pv.module_version,
    v_mc.id, v_mc.provider, v_mc.model, v_mc.config_hash,
    (SELECT environment FROM lfhe.deployment_environment),
    p_input_sha256, coalesce(p_input_refs, '{}'::jsonb), p_worker, p_job)
  RETURNING id INTO v_id;
  RETURN v_id;
END $$;

CREATE OR REPLACE FUNCTION lfhe.finish_model_run(
  p_run uuid, p_status lfhe.model_run_status, p_raw_output text, p_parsed_output jsonb,
  p_validation_errors jsonb, p_error_code text, p_error_message text, p_usage jsonb)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  IF p_status = 'RUNNING' THEN
    RAISE EXCEPTION 'finish_model_run requires a terminal status' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  UPDATE lfhe.model_runs SET
    status = p_status, completed_at = now(), raw_output = p_raw_output,
    raw_output_sha256 = CASE WHEN p_raw_output IS NULL THEN NULL
                             ELSE pg_catalog.encode(extensions.digest(p_raw_output, 'sha256'), 'hex') END,
    parsed_output = p_parsed_output, validation_errors = p_validation_errors,
    error_code = p_error_code, error_message = left(p_error_message, 4000),
    usage = coalesce(p_usage, '{}'::jsonb)
  WHERE id = p_run AND status = 'RUNNING';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'model run % is not running', p_run USING ERRCODE = 'object_not_in_prerequisite_state';
  END IF;
END $$;

REVOKE ALL ON FUNCTION lfhe.start_model_run(uuid, uuid, text, jsonb, text, uuid) FROM PUBLIC, anon, authenticated, service_role, lfhe_evaluator, lfhe_registrar;
REVOKE ALL ON FUNCTION lfhe.finish_model_run(uuid, lfhe.model_run_status, text, jsonb, jsonb, text, text, jsonb) FROM PUBLIC, anon, authenticated, service_role, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.start_model_run(uuid, uuid, text, jsonb, text, uuid),
  lfhe.finish_model_run(uuid, lfhe.model_run_status, text, jsonb, jsonb, text, text, jsonb) TO lfhe_worker;

-- ---------------------------------------------------------------------------
-- Read access (no direct writes for any application role)
-- ---------------------------------------------------------------------------
REVOKE ALL ON lfhe.prompt_versions, lfhe.prompt_activations, lfhe.model_configurations, lfhe.model_runs
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT SELECT ON lfhe.prompt_versions, lfhe.prompt_activations, lfhe.model_configurations, lfhe.model_runs
  TO authenticated, lfhe_worker;
GRANT SELECT ON lfhe.prompt_versions, lfhe.model_configurations TO lfhe_registrar;
GRANT SELECT ON lfhe.active_prompt_versions TO authenticated, lfhe_worker;

ALTER TABLE lfhe.prompt_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE lfhe.prompt_activations ENABLE ROW LEVEL SECURITY;
ALTER TABLE lfhe.model_configurations ENABLE ROW LEVEL SECURITY;
ALTER TABLE lfhe.model_runs ENABLE ROW LEVEL SECURITY;
CREATE POLICY prompt_versions_read_human ON lfhe.prompt_versions FOR SELECT TO authenticated
  USING (lfhe.has_permission('SYSTEM_READ') OR lfhe.has_permission('PROMPT_ACTIVATE'));
CREATE POLICY prompt_versions_read_service ON lfhe.prompt_versions FOR SELECT TO lfhe_worker, lfhe_registrar USING (true);
CREATE POLICY prompt_activations_read_human ON lfhe.prompt_activations FOR SELECT TO authenticated
  USING (lfhe.has_permission('SYSTEM_READ') OR lfhe.has_permission('PROMPT_ACTIVATE'));
CREATE POLICY prompt_activations_read_worker ON lfhe.prompt_activations FOR SELECT TO lfhe_worker USING (true);
CREATE POLICY model_configurations_read_human ON lfhe.model_configurations FOR SELECT TO authenticated
  USING (lfhe.has_permission('SYSTEM_READ') OR lfhe.has_permission('PROMPT_ACTIVATE'));
CREATE POLICY model_configurations_read_service ON lfhe.model_configurations FOR SELECT TO lfhe_worker, lfhe_registrar USING (true);
CREATE POLICY model_runs_read_human ON lfhe.model_runs FOR SELECT TO authenticated
  USING (lfhe.has_permission('SYSTEM_READ'));
CREATE POLICY model_runs_read_worker ON lfhe.model_runs FOR SELECT TO lfhe_worker USING (true);
