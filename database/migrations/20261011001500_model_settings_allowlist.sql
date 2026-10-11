-- ============================================================================
-- P2-01  Provider-specific allow-listed, non-secret model settings (L-13)
--
-- model_configurations.settings may contain ONLY the keys allow-listed for its
-- provider, with typed, bounded values. Everything else (base URLs, headers,
-- keys, tokens, organisation IDs, tools, …) is rejected. Provider credentials
-- never live in the database: adapters read them from the environment, which
-- the platform secret manager populates (docs/providers.md).
--
--   provider   allowed settings
--   fake       temperature [0,1], max_tokens [1,64000]
--   anthropic  temperature [0,1], max_tokens [1,64000], top_p (0,1],
--              timeout_seconds [1,600]
-- A new provider or setting requires a new migration (controlled change).
-- ============================================================================

CREATE OR REPLACE FUNCTION lfhe.model_settings_problems(p_provider text, p_model text, p_settings jsonb)
RETURNS text[] LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_out     text[] := '{}';
  v_allowed text[];
  v_key     text;
  v_val     jsonb;
  v_num     numeric;
BEGIN
  v_allowed := CASE p_provider
    WHEN 'fake' THEN ARRAY['temperature', 'max_tokens']
    WHEN 'anthropic' THEN ARRAY['temperature', 'max_tokens', 'top_p', 'timeout_seconds']
  END;
  IF v_allowed IS NULL THEN
    RETURN ARRAY['provider (PROVIDER_NOT_ALLOWED)'];
  END IF;
  IF p_model IS NULL OR p_model !~ '^[a-z0-9][a-z0-9._:-]{1,99}$' THEN
    v_out := v_out || 'model (INVALID_MODEL_IDENTIFIER)'::text;
  END IF;
  IF p_settings IS NULL OR pg_catalog.jsonb_typeof(p_settings) <> 'object' THEN
    RETURN v_out || '$ (NOT_AN_OBJECT)'::text;
  END IF;
  FOR v_key, v_val IN SELECT e.key, e.value FROM pg_catalog.jsonb_each(p_settings) e ORDER BY e.key COLLATE "C" LOOP
    IF NOT (v_key = ANY (v_allowed)) THEN
      v_out := v_out || ('$.' || v_key || ' (SETTING_NOT_ALLOWED_FOR_PROVIDER)');
      CONTINUE;
    END IF;
    IF pg_catalog.jsonb_typeof(v_val) <> 'number' THEN
      v_out := v_out || ('$.' || v_key || ' (NOT_A_NUMBER)');
      CONTINUE;
    END IF;
    v_num := (v_val #>> '{}')::numeric;
    IF (v_key = 'temperature' AND NOT (v_num BETWEEN 0 AND 1))
       OR (v_key = 'max_tokens' AND NOT (v_num BETWEEN 1 AND 64000 AND v_num = pg_catalog.trunc(v_num)))
       OR (v_key = 'top_p' AND NOT (v_num > 0 AND v_num <= 1))
       OR (v_key = 'timeout_seconds' AND NOT (v_num BETWEEN 1 AND 600)) THEN
      v_out := v_out || ('$.' || v_key || ' (OUT_OF_RANGE)');
    END IF;
  END LOOP;
  RETURN v_out;
END $$;
REVOKE ALL ON FUNCTION lfhe.model_settings_problems(text, text, jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION lfhe.model_settings_problems(text, text, jsonb) TO authenticated, lfhe_worker, lfhe_registrar;

CREATE OR REPLACE FUNCTION lfhe.validate_model_configuration()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_problems text[] := lfhe.model_settings_problems(NEW.provider, NEW.model, NEW.settings);
BEGIN
  IF pg_catalog.cardinality(v_problems) > 0 THEN
    RAISE EXCEPTION 'MODEL_SETTINGS_INVALID: % configuration rejected (found at %)',
      NEW.provider, pg_catalog.array_to_string(v_problems, ', ')
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION lfhe.validate_model_configuration() FROM PUBLIC;
-- fires after model_configurations_reject_credential_keys (name order)
CREATE TRIGGER model_configurations_validate_settings BEFORE INSERT ON lfhe.model_configurations
  FOR EACH ROW EXECUTE FUNCTION lfhe.validate_model_configuration();

ALTER TABLE lfhe.model_configurations ADD CONSTRAINT model_settings_allow_listed
  CHECK (pg_catalog.cardinality(lfhe.model_settings_problems(provider, model, settings)) = 0);
