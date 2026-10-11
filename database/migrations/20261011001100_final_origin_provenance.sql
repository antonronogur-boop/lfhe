-- ============================================================================
-- CG1-04  Final-origin provenance for redirects
--
-- * final_origin_host: host of final_url (generated, lower-case, no port /
--   userinfo) — the origin the content was actually served from.
-- * final_url_in_source_domain: computed by record_snapshot from the source's
--   approved canonical_domain (exact host or a subdomain).
-- * record_snapshot refuses a snapshot whose final origin is outside the
--   source domain unless the source config has allow_external_links = true
--   (defence in depth behind the collector's redirect guard, which rejects
--   such hops before requesting them: EXTERNAL_REDIRECT_REJECTED).
-- ============================================================================

CREATE OR REPLACE FUNCTION lfhe.url_host(p_url text)
RETURNS text LANGUAGE sql IMMUTABLE STRICT SET search_path = pg_catalog, pg_temp AS $$
  SELECT pg_catalog.lower(pg_catalog.substring(p_url, '^[A-Za-z][A-Za-z0-9+.-]*://(?:[^@/?#]*@)?([^/:?#\[\]]+)'))
$$;
REVOKE ALL ON FUNCTION lfhe.url_host(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION lfhe.url_host(text) TO authenticated, lfhe_worker;

ALTER TABLE lfhe.article_snapshots
  ADD COLUMN final_origin_host text GENERATED ALWAYS AS (lfhe.url_host(final_url)) STORED,
  ADD COLUMN final_url_in_source_domain boolean;
ALTER TABLE lfhe.article_snapshots
  ADD CONSTRAINT snapshot_final_origin_classified CHECK (final_url_in_source_domain IS NOT NULL) NOT VALID;
CREATE INDEX article_snapshots_external_origin_idx ON lfhe.article_snapshots (final_origin_host)
  WHERE final_url_in_source_domain = false;

CREATE OR REPLACE FUNCTION lfhe.record_snapshot(p jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_source   uuid := (p ->> 'source_id')::uuid;
  v_run      uuid := (p ->> 'collection_run_id')::uuid;
  v_article  uuid;
  v_new_article boolean := false;
  v_latest   record;
  v_version  integer;
  v_snapshot uuid;
  v_text     jsonb := p -> 'text';
  v_domain   text;
  v_allow    boolean;
  v_host     text := lfhe.url_host(p ->> 'final_url');
  v_in       boolean;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM lfhe.collection_runs r
                 WHERE r.id = v_run AND r.source_id = v_source AND r.status = 'RUNNING') THEN
    RAISE EXCEPTION 'collection run % is not a RUNNING run of source %', v_run, v_source
      USING ERRCODE = 'object_not_in_prerequisite_state';
  END IF;

  -- CG1-04: the database decides whether the document's final origin is
  -- inside the approved source domain; external origins are stored only when
  -- the source explicitly allows external links, and are always flagged.
  SELECT lower(s.canonical_domain), coalesce((s.collection_config ->> 'allow_external_links')::boolean, false)
    INTO v_domain, v_allow FROM lfhe.sources s WHERE s.id = v_source;
  v_in := v_host IS NOT NULL AND (v_host = v_domain OR right(v_host, length(v_domain) + 1) = '.' || v_domain);
  IF NOT v_in AND NOT v_allow THEN
    RAISE EXCEPTION 'EXTERNAL_ORIGIN_NOT_ALLOWED: final URL host % is outside source domain %', v_host, v_domain
      USING ERRCODE = 'check_violation';
  END IF;

  INSERT INTO lfhe.articles (source_id, canonical_url, first_seen_url)
  VALUES (v_source, p ->> 'canonical_url', p ->> 'requested_url')
  ON CONFLICT (source_id, canonical_url) DO NOTHING
  RETURNING id INTO v_article;
  IF v_article IS NULL THEN
    SELECT id INTO v_article FROM lfhe.articles
    WHERE source_id = v_source AND canonical_url = p ->> 'canonical_url';
  ELSE
    v_new_article := true;
  END IF;

  -- Serialise snapshot creation per article.
  PERFORM 1 FROM lfhe.articles WHERE id = v_article FOR UPDATE;

  IF p ->> 'source_state_sha256' IS NULL OR p -> 'source_state' IS NULL THEN
    RAISE EXCEPTION 'source_state and source_state_sha256 are required' USING ERRCODE = 'not_null_violation';
  END IF;

  SELECT s.id, s.snapshot_version, s.source_state_sha256 INTO v_latest
  FROM lfhe.article_snapshots s WHERE s.article_id = v_article
  ORDER BY s.snapshot_version DESC LIMIT 1;

  -- Snapshot identity = source state (CG1-02). A version is a DUPLICATE only
  -- when the latest version has the identical source-state hash.
  IF FOUND AND v_latest.source_state_sha256 = p ->> 'source_state_sha256' THEN
    RETURN jsonb_build_object('outcome', 'DUPLICATE', 'article_id', v_article,
                              'snapshot_id', v_latest.id, 'snapshot_version', v_latest.snapshot_version);
  END IF;
  v_version := coalesce(v_latest.snapshot_version, 0) + 1;

  INSERT INTO lfhe.article_snapshots (
    article_id, snapshot_version, collection_run_id, requested_url, final_url, redirect_chain,
    http_status, content_type, response_headers, raw_content_sha256, raw_size_bytes,
    raw_storage_key, retention_mode_applied, content_identity_sha256, title_original,
    language, language_method, publication_datetime, publication_datetime_field,
    public_availability_datetime, public_availability_basis, public_availability_confidence,
    source_updated_datetime, source_updated_datetime_field, system_retrieval_datetime,
    date_status, metadata, source_state, source_state_sha256, final_url_in_source_domain)
  VALUES (
    v_article, v_version, v_run, p ->> 'requested_url', p ->> 'final_url',
    coalesce(ARRAY(SELECT jsonb_array_elements_text(p -> 'redirect_chain')), '{}'),
    (p ->> 'http_status')::smallint, p ->> 'content_type', coalesce(p -> 'response_headers', '{}'::jsonb),
    p ->> 'raw_content_sha256', (p ->> 'raw_size_bytes')::integer, p ->> 'raw_storage_key',
    (p ->> 'retention_mode_applied')::lfhe.retention_mode, p ->> 'content_identity_sha256',
    p ->> 'title_original', p ->> 'language', p ->> 'language_method',
    (p ->> 'publication_datetime')::timestamptz, p ->> 'publication_datetime_field',
    (p ->> 'public_availability_datetime')::timestamptz,
    (p ->> 'public_availability_basis')::lfhe.public_availability_basis,
    (p ->> 'public_availability_confidence')::lfhe.timestamp_confidence,
    (p ->> 'source_updated_datetime')::timestamptz, p ->> 'source_updated_datetime_field',
    (p ->> 'system_retrieval_datetime')::timestamptz, (p ->> 'date_status')::lfhe.date_status,
    coalesce(p -> 'metadata', '{}'::jsonb), p -> 'source_state', p ->> 'source_state_sha256', v_in)
  RETURNING id INTO v_snapshot;

  IF v_text IS NOT NULL AND jsonb_typeof(v_text) = 'object' THEN
    INSERT INTO lfhe.text_representations (snapshot_id, representation_type, preprocessor_name,
      preprocessor_version, language, text_content, text_sha256, char_length)
    VALUES (v_snapshot, v_text ->> 'representation_type', v_text ->> 'preprocessor_name',
      v_text ->> 'preprocessor_version', v_text ->> 'language', v_text ->> 'text_content',
      v_text ->> 'text_sha256', (v_text ->> 'char_length')::integer);
  END IF;

  RETURN jsonb_build_object('outcome', CASE WHEN v_version = 1 THEN 'NEW' ELSE 'REVISED' END,
                            'article_id', v_article, 'snapshot_id', v_snapshot,
                            'snapshot_version', v_version, 'new_article', v_new_article);
END $$;
REVOKE ALL ON FUNCTION lfhe.record_snapshot(jsonb) FROM PUBLIC, anon, authenticated, service_role, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.record_snapshot(jsonb) TO lfhe_worker;
