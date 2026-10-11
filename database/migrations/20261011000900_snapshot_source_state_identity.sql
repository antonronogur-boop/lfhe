-- ============================================================================
-- CG1-02  Snapshot identity = SOURCE STATE (not clean text alone)
--
-- Two identities are now distinct (docs/snapshot-identity.md):
--   A. SOURCE SNAPSHOT IDENTITY  source_state_sha256 = SHA-256 of the RFC 8785
--      canonical JSON of source_state ('lfhe-snapshot-state/1'): content hash,
--      final URL, media type, title, language, all source-STATED publication /
--      update timestamps with their fields and bases, discovery identifiers and
--      the retention mode. A new article_snapshot version is created whenever
--      any of these changes — even if the clean body text is unchanged.
--      Excluded on purpose (cosmetic / volatile): raw bytes when clean text was
--      extracted, response headers, redirect hops, system retrieval time.
--   B. CLEAN TEXT / TEXT REPRESENTATION IDENTITY  text_representations.text_sha256
--      (unchanged). content_identity_sha256 keeps its original meaning: the
--      content hash (clean text, or raw bytes when no text is extractable); it
--      is an input to A, no longer the duplicate criterion.
-- source_state is stored verbatim so A is independently verifiable
-- (lfhe_shared.canonical_json.canonical_sha256(source_state)).
-- Existing rows (pre-CG1) are not rewritten (snapshots are immutable); the
-- constraint applies to every new row (NOT VALID).
-- ============================================================================

ALTER TABLE lfhe.article_snapshots
  ADD COLUMN source_state jsonb,
  ADD COLUMN source_state_sha256 text CHECK (source_state_sha256 ~ '^[0-9a-f]{64}$');
ALTER TABLE lfhe.article_snapshots
  ADD CONSTRAINT snapshot_source_state_required CHECK (
    source_state IS NOT NULL AND source_state_sha256 IS NOT NULL
    AND source_state ->> 'format' = 'lfhe-snapshot-state/1') NOT VALID;
CREATE INDEX article_snapshots_state_idx ON lfhe.article_snapshots (article_id, source_state_sha256);
COMMENT ON COLUMN lfhe.article_snapshots.content_identity_sha256 IS
  'Content hash: clean-text SHA-256 when text was extracted, else raw SHA-256. Input to source_state; not the snapshot identity.';
COMMENT ON COLUMN lfhe.article_snapshots.source_state_sha256 IS
  'Snapshot identity: SHA-256 of RFC 8785 canonical JSON of source_state (lfhe-snapshot-state/1).';

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
BEGIN
  IF NOT EXISTS (SELECT 1 FROM lfhe.collection_runs r
                 WHERE r.id = v_run AND r.source_id = v_source AND r.status = 'RUNNING') THEN
    RAISE EXCEPTION 'collection run % is not a RUNNING run of source %', v_run, v_source
      USING ERRCODE = 'object_not_in_prerequisite_state';
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
    date_status, metadata, source_state, source_state_sha256)
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
    coalesce(p -> 'metadata', '{}'::jsonb), p -> 'source_state', p ->> 'source_state_sha256')
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

-- Read-only pre-check so the collector can skip writing raw bytes to the
-- object store for routine duplicates (no unreferenced objects). The
-- authoritative decision is still taken under the row lock in record_snapshot.
CREATE OR REPLACE FUNCTION lfhe.snapshot_state_is_current(p_source uuid, p_canonical_url text, p_state_sha256 text)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
  SELECT coalesce((
    SELECT s.source_state_sha256 = p_state_sha256
    FROM lfhe.articles a JOIN lfhe.article_snapshots s ON s.article_id = a.id
    WHERE a.source_id = p_source AND a.canonical_url = p_canonical_url
    ORDER BY s.snapshot_version DESC LIMIT 1), false)
$$;
REVOKE ALL ON FUNCTION lfhe.snapshot_state_is_current(uuid, text, text) FROM PUBLIC, anon, authenticated, service_role, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.snapshot_state_is_current(uuid, text, text) TO lfhe_worker;
