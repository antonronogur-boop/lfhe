-- LFHÉ CR7-01 (PO instruction 2026-10-24, docs/cr7-01-proposal.md, option B) — provider-fixed sampling.
--
-- Current Anthropic models (Haiku / Sonnet / Opus 5.5) reject the `temperature` request parameter
-- ("`temperature` is deprecated for this model", HTTP 400). The closed low-variance rule was implemented
-- as an explicit temperature ≤ 0.2. This forward-only migration adds ONE allow-listed, explicit anthropic
-- setting:
--
--   provider_fixed_sampling : JSON true   — the adapter sends no sampling parameter (no temperature,
--                                            no top_p); sampling is fixed by the provider for that model.
--
-- Rules: the value must be exactly `true`; it cannot be combined with `temperature` or `top_p`; it is
-- available for provider `anthropic` only. The setting is part of the registered configuration and so of
-- `model_config_hash` and every model_run, i.e. visible on every run (CR7-01). Nothing else changes:
-- schema validation, ingestion, QA, human approvals and release are untouched. Earlier migrations are
-- not edited; this re-defines lfhe.model_settings_problems (the CHECK constraint and the registration
-- trigger call it), keeping every previous rule.

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
    WHEN 'anthropic' THEN ARRAY['temperature', 'max_tokens', 'top_p', 'timeout_seconds', 'provider_fixed_sampling']
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
    IF v_key = 'provider_fixed_sampling' THEN
      IF v_val <> 'true'::jsonb THEN
        v_out := v_out || ('$.' || v_key || ' (MUST_BE_TRUE)');
      ELSIF p_settings ? 'temperature' OR p_settings ? 'top_p' THEN
        v_out := v_out || ('$.' || v_key || ' (CONFLICTS_WITH_SAMPLING_PARAMETER)');
      END IF;
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
