-- ============================================================================
-- CG1-08  Credentials hidden in URL VALUES (userinfo, credential query params)
--
-- CG1-03 rejects credential-like KEY NAMES. This migration additionally
-- inspects every JSON string value that is an absolute URL
-- (^scheme://), at any depth, and rejects:
--   * userinfo in the authority (user, user:password, '@', or '%40');
--   * query or fragment parameters whose (percent-decoded) NAME is
--     credential-like under the same rule as CG1-03 (lfhe.is_credential_key):
--     token, api_key, apikey, key, secret, password, auth, authorization,
--     credential(s), bearer, access_token, client_secret, X-Api-Key, …
-- This covers the URL-bearing fields of every Phase 1 collection method
-- (feed_url, sitemap_url, endpoint, urls[]) and any URL placed in model
-- settings or job payloads.
-- Enforcement is the same as CG1-03: the BEFORE trigger raises with the JSON
-- path and the offending parameter NAME only (never a value), so a rejected
-- configuration produces no row, no audit entry and no secret in the error;
-- CHECK constraints are the backstop.
-- ============================================================================

CREATE OR REPLACE FUNCTION lfhe.percent_decode(p text)
RETURNS text LANGUAGE plpgsql IMMUTABLE STRICT SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v bytea := '';
  i integer := 1;
  n integer := pg_catalog.length(p);
  c text;
BEGIN
  WHILE i <= n LOOP
    c := pg_catalog.substr(p, i, 1);
    IF c = '%' AND pg_catalog.substr(p, i + 1, 2) ~ '^[0-9A-Fa-f]{2}$' THEN
      v := v || pg_catalog.decode(pg_catalog.substr(p, i + 1, 2), 'hex');
      i := i + 3;
    ELSIF c = '+' THEN
      v := v || '\x20'::bytea;
      i := i + 1;
    ELSE
      v := v || pg_catalog.convert_to(c, 'UTF8');
      i := i + 1;
    END IF;
  END LOOP;
  RETURN pg_catalog.convert_from(v, 'UTF8');
EXCEPTION WHEN others THEN
  RETURN p;  -- undecodable: inspect the raw name
END $$;
REVOKE ALL ON FUNCTION lfhe.percent_decode(text) FROM PUBLIC;

-- Problems in one URL string: '{}' when clean or not an absolute URL.
CREATE OR REPLACE FUNCTION lfhe.url_credential_problems(p_url text)
RETURNS text[] LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_out       text[] := '{}';
  v_authority text;
  v_params    text;
  v_part      text;
  v_name      text;
BEGIN
  IF p_url IS NULL OR p_url !~ '^[A-Za-z][A-Za-z0-9+.-]*://' THEN
    RETURN v_out;
  END IF;
  v_authority := pg_catalog.substring(p_url, '^[A-Za-z][A-Za-z0-9+.-]*://([^/?#]*)');
  IF pg_catalog.strpos(coalesce(v_authority, ''), '@') > 0 OR coalesce(v_authority, '') ~* '%40' THEN
    v_out := v_out || 'USERINFO'::text;
  END IF;
  -- query and fragment parameters (fragment: e.g. #access_token=…)
  v_params := coalesce(pg_catalog.substring(p_url, '\?([^#]*)'), '') || '&'
              || coalesce(pg_catalog.substring(p_url, '#(.*)$'), '');
  FOREACH v_part IN ARRAY pg_catalog.string_to_array(v_params, '&') LOOP
    CONTINUE WHEN v_part = '';
    v_name := lfhe.percent_decode(pg_catalog.split_part(v_part, '=', 1));
    IF v_name <> '' AND lfhe.is_credential_key(v_name) THEN
      v_out := v_out || ('CREDENTIAL_PARAMETER:' || pg_catalog.lower(v_name));
    END IF;
  END LOOP;
  RETURN v_out;
END $$;
REVOKE ALL ON FUNCTION lfhe.url_credential_problems(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION lfhe.url_credential_problems(text) TO authenticated, lfhe_worker, lfhe_registrar;

-- Recursive: '$.path (PROBLEM)' for every offending URL string value.
CREATE OR REPLACE FUNCTION lfhe.credential_url_paths(p jsonb, p_path text DEFAULT '$')
RETURNS text[] LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_out text[] := '{}';
  v_key text;
  v_val jsonb;
  v_i   integer := 0;
  v_problem text;
BEGIN
  IF p IS NULL THEN
    RETURN v_out;
  END IF;
  CASE pg_catalog.jsonb_typeof(p)
    WHEN 'string' THEN
      FOREACH v_problem IN ARRAY lfhe.url_credential_problems(p #>> '{}') LOOP
        v_out := v_out || (p_path || ' (' || v_problem || ')');
      END LOOP;
    WHEN 'object' THEN
      FOR v_key, v_val IN SELECT e.key, e.value FROM pg_catalog.jsonb_each(p) e ORDER BY e.key COLLATE "C" LOOP
        v_out := v_out || lfhe.credential_url_paths(v_val, p_path || '.' || v_key);
      END LOOP;
    WHEN 'array' THEN
      FOR v_val IN SELECT e.value FROM pg_catalog.jsonb_array_elements(p) WITH ORDINALITY e(value, ord) ORDER BY e.ord LOOP
        v_out := v_out || lfhe.credential_url_paths(v_val, p_path || '[' || v_i || ']');
        v_i := v_i + 1;
      END LOOP;
    ELSE
      NULL;
  END CASE;
  RETURN v_out;
END $$;
REVOKE ALL ON FUNCTION lfhe.credential_url_paths(jsonb, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION lfhe.credential_url_paths(jsonb, text) TO authenticated, lfhe_worker, lfhe_registrar;

-- The CG1-03 guard trigger now checks key names AND URL values.
CREATE OR REPLACE FUNCTION lfhe.reject_credential_keys()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_doc   jsonb := pg_catalog.to_jsonb(NEW) -> TG_ARGV[0];
  v_paths text[] := lfhe.credential_key_paths(v_doc);
  v_urls  text[] := lfhe.credential_url_paths(v_doc);
BEGIN
  IF pg_catalog.cardinality(v_paths) > 0 THEN
    RAISE EXCEPTION 'CREDENTIAL_KEY_REJECTED: %.% must not contain credential-like keys (found at %)',
      TG_TABLE_NAME, TG_ARGV[0], pg_catalog.array_to_string(v_paths, ', ')
      USING ERRCODE = 'check_violation';
  END IF;
  IF pg_catalog.cardinality(v_urls) > 0 THEN
    RAISE EXCEPTION 'CREDENTIAL_URL_REJECTED: %.% must not contain URLs with userinfo or credential parameters (found at %)',
      TG_TABLE_NAME, TG_ARGV[0], pg_catalog.array_to_string(v_urls, ', ')
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION lfhe.reject_credential_keys() FROM PUBLIC;

ALTER TABLE lfhe.sources ADD CONSTRAINT sources_config_urls_have_no_credentials
  CHECK (pg_catalog.cardinality(lfhe.credential_url_paths(collection_config)) = 0);
ALTER TABLE lfhe.model_configurations ADD CONSTRAINT model_settings_urls_have_no_credentials
  CHECK (pg_catalog.cardinality(lfhe.credential_url_paths(settings)) = 0);
ALTER TABLE lfhe.processing_jobs ADD CONSTRAINT processing_jobs_payload_urls_have_no_credentials
  CHECK (pg_catalog.cardinality(lfhe.credential_url_paths(payload)) = 0);
