-- ============================================================================
-- CG1-08A  Canonicalise before credential inspection; database-authoritative
--          validation of the known source URL fields
--
-- 1. lfhe.url_inspection_form(): the form in which a URL-ish string is
--    inspected, mirroring how URL parsers (WHATWG / Pydantic HttpUrl) read it:
--      * ASCII tab, LF and CR are removed everywhere;
--      * leading/trailing C0 controls and spaces (U+0001–U+0020) are trimmed;
--      * '\' is read as '/'.
--    lfhe.url_credential_problems() now inspects this form, and
--      * authority/userinfo is checked for '<scheme>://…', for the special
--        schemes http/https/ws/wss/ftp/file with any number of slashes
--        ('https:user:pw@host' parses as a URL), and for '//authority';
--      * query/fragment parameter NAMES are checked in EVERY string that has
--        '?' or '#', absolute or relative ('/feed?api_key=…' is rejected).
--    Python (lfhe_shared.credentials) and TypeScript (apps/web/lib/credentials.ts)
--    implement the identical algorithm (parity-tested).
-- 2. lfhe.source_config_problems(method, config): the known URL-bearing fields
--      RSS_ATOM feed_url | STRUCTURED_FEED sitemap_url | OFFICIAL_API endpoint |
--      HTTP_FETCH urls[] (non-empty array)
--    must be present, JSON strings, canonical absolute http(s) URLs (no
--    whitespace or control characters, no backslash, no userinfo) and free of
--    credential parameters. Enforced by a BEFORE trigger (codes and paths only,
--    never values) before INSERT/UPDATE and therefore before any audit entry;
--    CHECK constraint as backstop.
-- ============================================================================

CREATE OR REPLACE FUNCTION lfhe.url_inspection_form(p text)
RETURNS text LANGUAGE sql IMMUTABLE STRICT SET search_path = pg_catalog, pg_temp AS $$
  SELECT pg_catalog.replace(
           pg_catalog.regexp_replace(
             pg_catalog.regexp_replace(p, '[\t\n\r]', '', 'g'),
             '^[\x01-\x20]+|[\x01-\x20]+$', '', 'g'),
           '\', '/')
$$;
REVOKE ALL ON FUNCTION lfhe.url_inspection_form(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION lfhe.url_inspection_form(text) TO authenticated, lfhe_worker, lfhe_registrar;

CREATE OR REPLACE FUNCTION lfhe.url_credential_problems(p_url text)
RETURNS text[] LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_out       text[] := '{}';
  v           text;
  v_authority text;
  v_params    text;
  v_part      text;
  v_name      text;
BEGIN
  IF p_url IS NULL THEN
    RETURN v_out;
  END IF;
  v := lfhe.url_inspection_form(p_url);
  IF v ~ '^[A-Za-z][A-Za-z0-9+.-]*://' THEN
    v_authority := pg_catalog.substring(v, '^[A-Za-z][A-Za-z0-9+.-]*://([^/?#]*)');
  ELSIF v ~* '^(https?|wss?|ftp|file):' THEN
    v_authority := pg_catalog.substring(v, '^[A-Za-z]+:/*([^/?#]*)');
  ELSIF v ~ '^//' THEN
    v_authority := pg_catalog.substring(v, '^//([^/?#]*)');
  END IF;
  IF pg_catalog.strpos(coalesce(v_authority, ''), '@') > 0 OR coalesce(v_authority, '') ~* '%40' THEN
    v_out := v_out || 'USERINFO'::text;
  END IF;
  IF pg_catalog.strpos(v, '?') > 0 OR pg_catalog.strpos(v, '#') > 0 THEN
    v_params := coalesce(pg_catalog.substring(v, '\?([^#]*)'), '') || '&'
                || coalesce(pg_catalog.substring(v, '#(.*)$'), '');
    FOREACH v_part IN ARRAY pg_catalog.string_to_array(v_params, '&') LOOP
      CONTINUE WHEN v_part = '';
      v_name := lfhe.percent_decode(pg_catalog.split_part(v_part, '=', 1));
      IF v_name <> '' AND lfhe.is_credential_key(v_name) THEN
        v_out := v_out || ('CREDENTIAL_PARAMETER:' || pg_catalog.lower(v_name));
      END IF;
    END LOOP;
  END IF;
  RETURN v_out;
END $$;
REVOKE ALL ON FUNCTION lfhe.url_credential_problems(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION lfhe.url_credential_problems(text) TO authenticated, lfhe_worker, lfhe_registrar;

-- Canonical absolute http(s) URL: lower/upper-case scheme, authority without
-- userinfo, no whitespace/control characters or backslash anywhere.
CREATE OR REPLACE FUNCTION lfhe.is_canonical_http_url(p text)
RETURNS boolean LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
  SELECT p IS NOT NULL
     AND p ~* '^https?://[a-z0-9._~%:\[\]-]+([/?#].*)?$'
     AND p !~ '[\x01-\x20\x7f\\]'
$$;
REVOKE ALL ON FUNCTION lfhe.is_canonical_http_url(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION lfhe.is_canonical_http_url(text) TO authenticated, lfhe_worker, lfhe_registrar;

CREATE OR REPLACE FUNCTION lfhe.source_url_field_problems(p_value jsonb, p_path text)
RETURNS text[] LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_out text[] := '{}';
  v_problem text;
BEGIN
  IF p_value IS NULL THEN
    RETURN ARRAY[p_path || ' (MISSING)'];
  END IF;
  IF pg_catalog.jsonb_typeof(p_value) <> 'string' THEN
    RETURN ARRAY[p_path || ' (NOT_A_STRING)'];
  END IF;
  IF NOT lfhe.is_canonical_http_url(p_value #>> '{}') THEN
    v_out := v_out || (p_path || ' (NOT_CANONICAL_ABSOLUTE_HTTP_URL)');
  END IF;
  FOREACH v_problem IN ARRAY lfhe.url_credential_problems(p_value #>> '{}') LOOP
    v_out := v_out || (p_path || ' (' || v_problem || ')');
  END LOOP;
  RETURN v_out;
END $$;
REVOKE ALL ON FUNCTION lfhe.source_url_field_problems(jsonb, text) FROM PUBLIC;

CREATE OR REPLACE FUNCTION lfhe.source_config_problems(p_method text, p_config jsonb)
RETURNS text[] LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_out  text[] := '{}';
  v_urls jsonb;
  v_i    integer := 0;
  v_elem jsonb;
BEGIN
  IF p_config IS NULL OR pg_catalog.jsonb_typeof(p_config) <> 'object' THEN
    RETURN ARRAY['$ (NOT_AN_OBJECT)'];
  END IF;
  CASE p_method
    WHEN 'RSS_ATOM' THEN
      v_out := lfhe.source_url_field_problems(p_config -> 'feed_url', '$.feed_url');
    WHEN 'STRUCTURED_FEED' THEN
      v_out := lfhe.source_url_field_problems(p_config -> 'sitemap_url', '$.sitemap_url');
    WHEN 'OFFICIAL_API' THEN
      v_out := lfhe.source_url_field_problems(p_config -> 'endpoint', '$.endpoint');
    WHEN 'HTTP_FETCH' THEN
      v_urls := p_config -> 'urls';
      IF v_urls IS NULL THEN
        v_out := ARRAY['$.urls (MISSING)'];
      ELSIF pg_catalog.jsonb_typeof(v_urls) <> 'array' OR pg_catalog.jsonb_array_length(v_urls) = 0 THEN
        v_out := ARRAY['$.urls (NOT_A_NON_EMPTY_ARRAY)'];
      ELSE
        FOR v_elem IN SELECT e.value FROM pg_catalog.jsonb_array_elements(v_urls) WITH ORDINALITY e(value, ord)
                      ORDER BY e.ord LOOP
          v_out := v_out || lfhe.source_url_field_problems(v_elem, '$.urls[' || v_i || ']');
          v_i := v_i + 1;
        END LOOP;
      END IF;
    ELSE
      NULL;  -- BROWSER_AUTOMATION: no adapter in Phase 1 and cannot be approved
  END CASE;
  RETURN v_out;
END $$;
REVOKE ALL ON FUNCTION lfhe.source_config_problems(text, jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION lfhe.source_config_problems(text, jsonb) TO authenticated, lfhe_worker;

CREATE OR REPLACE FUNCTION lfhe.validate_source_config()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_problems text[] := lfhe.source_config_problems(NEW.collection_method::text, NEW.collection_config);
BEGIN
  IF pg_catalog.cardinality(v_problems) > 0 THEN
    RAISE EXCEPTION 'SOURCE_CONFIG_INVALID: % configuration rejected (found at %)',
      NEW.collection_method, pg_catalog.array_to_string(v_problems, ', ')
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION lfhe.validate_source_config() FROM PUBLIC;
-- Fires after sources_reject_credential_keys (triggers run in name order).
CREATE TRIGGER sources_validate_config BEFORE INSERT OR UPDATE OF collection_config, collection_method
  ON lfhe.sources FOR EACH ROW EXECUTE FUNCTION lfhe.validate_source_config();

ALTER TABLE lfhe.sources ADD CONSTRAINT sources_config_urls_valid
  CHECK (pg_catalog.cardinality(lfhe.source_config_problems(collection_method::text, collection_config)) = 0);

-- Re-validate existing rows against the strengthened URL credential rule.
ALTER TABLE lfhe.sources DROP CONSTRAINT sources_config_urls_have_no_credentials;
ALTER TABLE lfhe.sources ADD CONSTRAINT sources_config_urls_have_no_credentials
  CHECK (pg_catalog.cardinality(lfhe.credential_url_paths(collection_config)) = 0);
ALTER TABLE lfhe.model_configurations DROP CONSTRAINT model_settings_urls_have_no_credentials;
ALTER TABLE lfhe.model_configurations ADD CONSTRAINT model_settings_urls_have_no_credentials
  CHECK (pg_catalog.cardinality(lfhe.credential_url_paths(settings)) = 0);
ALTER TABLE lfhe.processing_jobs DROP CONSTRAINT processing_jobs_payload_urls_have_no_credentials;
ALTER TABLE lfhe.processing_jobs ADD CONSTRAINT processing_jobs_payload_urls_have_no_credentials
  CHECK (pg_catalog.cardinality(lfhe.credential_url_paths(payload)) = 0);
