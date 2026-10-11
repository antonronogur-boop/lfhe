-- ============================================================================
-- CG1-03  One recursive credential-key validator (database is authoritative)
--
-- Rule 'lfhe-credential-keys/1' (mirrored exactly by
-- lfhe_shared.credentials and apps/web/lib/credentials.ts):
--   normalise key: split camelCase (aB → a_B), lower-case, every run of
--   non [a-z0-9] → '_', trim '_'; split into segments on '_'.
--   REJECT when any segment is one of
--     headers header auth authorization authentication cookies cookie
--     password passwords passwd token secret secrets apikey credential
--     credentials bearer
--   or the LAST segment is 'key' / 'keys' (key, api_key, x-api-key,
--   private_key, accessKey, …).
--   Applied at EVERY depth, including objects inside arrays.
-- Decisions: plain 'key' is rejected only as a whole key or final segment, so
-- e.g. 'keyword' is allowed; 'tokens' (plural) is allowed because 'max_tokens'
-- is a standard, non-secret model setting. A legitimate field that would
-- match (e.g. 'sort_key') must use another name ('sort_field').
--
-- Enforcement: BEFORE INSERT/UPDATE triggers raise with the offending PATHS
-- only (never the values), so a secret is neither stored, audited nor echoed
-- in an error message; CHECK constraints are the backstop.
-- Applied to: sources.collection_config, model_configurations.settings,
-- processing_jobs.payload (future provider/HTTP configuration can only
-- travel through these).
-- ============================================================================

CREATE OR REPLACE FUNCTION lfhe.is_credential_key(p_key text)
RETURNS boolean LANGUAGE sql IMMUTABLE STRICT SET search_path = pg_catalog, pg_temp AS $$
  WITH n AS (
    SELECT pg_catalog.btrim(pg_catalog.regexp_replace(pg_catalog.lower(
             pg_catalog.regexp_replace(p_key, '([a-z0-9])([A-Z])', '\1_\2', 'g')),
             '[^a-z0-9]+', '_', 'g'), '_') AS k
  ), s AS (
    SELECT pg_catalog.string_to_array(k, '_') AS seg FROM n
  )
  SELECT seg && ARRAY['headers', 'header', 'auth', 'authorization', 'authentication', 'cookies', 'cookie',
                      'password', 'passwords', 'passwd', 'token', 'secret', 'secrets', 'apikey',
                      'credential', 'credentials', 'bearer']
      OR seg[pg_catalog.array_length(seg, 1)] IN ('key', 'keys')
  FROM s
$$;
REVOKE ALL ON FUNCTION lfhe.is_credential_key(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION lfhe.is_credential_key(text) TO authenticated, lfhe_worker, lfhe_registrar;

-- Returns the JSON paths ($.a.b[0].c) of every credential-like key; '{}' if none.
CREATE OR REPLACE FUNCTION lfhe.credential_key_paths(p jsonb, p_path text DEFAULT '$')
RETURNS text[] LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_out text[] := '{}';
  v_key text;
  v_val jsonb;
  v_i   integer := 0;
BEGIN
  IF p IS NULL THEN
    RETURN v_out;
  END IF;
  IF pg_catalog.jsonb_typeof(p) = 'object' THEN
    FOR v_key, v_val IN SELECT e.key, e.value FROM pg_catalog.jsonb_each(p) e ORDER BY e.key COLLATE "C" LOOP
      IF lfhe.is_credential_key(v_key) THEN
        v_out := v_out || (p_path || '.' || v_key);
      END IF;
      v_out := v_out || lfhe.credential_key_paths(v_val, p_path || '.' || v_key);
    END LOOP;
  ELSIF pg_catalog.jsonb_typeof(p) = 'array' THEN
    FOR v_val IN SELECT e.value FROM pg_catalog.jsonb_array_elements(p) WITH ORDINALITY e(value, ord) ORDER BY e.ord LOOP
      v_out := v_out || lfhe.credential_key_paths(v_val, p_path || '[' || v_i || ']');
      v_i := v_i + 1;
    END LOOP;
  END IF;
  RETURN v_out;
END $$;
REVOKE ALL ON FUNCTION lfhe.credential_key_paths(jsonb, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION lfhe.credential_key_paths(jsonb, text) TO authenticated, lfhe_worker, lfhe_registrar;

-- Generic guard trigger: TG_ARGV[0] = jsonb column name.
CREATE OR REPLACE FUNCTION lfhe.reject_credential_keys()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_paths text[] := lfhe.credential_key_paths(pg_catalog.to_jsonb(NEW) -> TG_ARGV[0]);
BEGIN
  IF pg_catalog.cardinality(v_paths) > 0 THEN
    RAISE EXCEPTION 'CREDENTIAL_KEY_REJECTED: %.% must not contain credential-like keys (found at %)',
      TG_TABLE_NAME, TG_ARGV[0], pg_catalog.array_to_string(v_paths, ', ')
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION lfhe.reject_credential_keys() FROM PUBLIC;

-- sources.collection_config ----------------------------------------------------
ALTER TABLE lfhe.sources DROP CONSTRAINT sources_config_has_no_credentials;
ALTER TABLE lfhe.sources ADD CONSTRAINT sources_config_has_no_credentials
  CHECK (pg_catalog.cardinality(lfhe.credential_key_paths(collection_config)) = 0);
CREATE TRIGGER sources_reject_credential_keys BEFORE INSERT OR UPDATE OF collection_config ON lfhe.sources
  FOR EACH ROW EXECUTE FUNCTION lfhe.reject_credential_keys('collection_config');

-- model_configurations.settings -----------------------------------------------
ALTER TABLE lfhe.model_configurations DROP CONSTRAINT model_settings_have_no_credentials;
ALTER TABLE lfhe.model_configurations ADD CONSTRAINT model_settings_have_no_credentials
  CHECK (pg_catalog.cardinality(lfhe.credential_key_paths(settings)) = 0);
CREATE TRIGGER model_configurations_reject_credential_keys BEFORE INSERT ON lfhe.model_configurations
  FOR EACH ROW EXECUTE FUNCTION lfhe.reject_credential_keys('settings');

-- processing_jobs.payload -----------------------------------------------------
ALTER TABLE lfhe.processing_jobs ADD CONSTRAINT processing_jobs_payload_has_no_credentials
  CHECK (pg_catalog.cardinality(lfhe.credential_key_paths(payload)) = 0);
CREATE TRIGGER processing_jobs_reject_credential_keys BEFORE INSERT OR UPDATE OF payload ON lfhe.processing_jobs
  FOR EACH ROW EXECUTE FUNCTION lfhe.reject_credential_keys('payload');
