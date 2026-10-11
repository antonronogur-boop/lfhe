-- ============================================================================
-- P1-09  Articles and original-language snapshots
--        (DS §8–§10, Enforcement Addendum G-03, Prompt Pack v1.2.2, ADR-0006)
--
-- * articles: identity = (source, canonical URL). Immutable.
-- * article_snapshots: one immutable row per distinct content state of an
--   article. A content revision creates snapshot_version n+1; earlier
--   versions are never modified (later page edits cannot contaminate replay).
--   The three times are separate columns and are never collapsed:
--     publication_datetime          (as stated by the source, with field)
--     public_availability_datetime  (+ basis + confidence; NULL when unknown)
--     system_retrieval_datetime     (when LFHÉ fetched it)
--   Event time is NOT a snapshot attribute (claims, Phase 2).
-- * text_representations: deterministic canonical clean text of the
--   ORIGINAL-LANGUAGE snapshot, keyed by preprocessor name+version, with
--   database-verified SHA-256 and code-point length. Evidence-span offsets
--   (Phase 2) point into this immutable text. Translations are never stored
--   here (is_original_language must be true).
-- * Workers write only through lfhe.record_snapshot(), which also verifies
--   that the collection run is RUNNING and belongs to the article's source.
-- ============================================================================

CREATE TABLE lfhe.articles (
  id             uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  source_id      uuid NOT NULL REFERENCES lfhe.sources(id),
  canonical_url  text NOT NULL CHECK (canonical_url ~ '^https?://'),
  first_seen_url text NOT NULL,
  first_seen_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_id, canonical_url)
);

CREATE TABLE lfhe.article_snapshots (
  id                               uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  article_id                       uuid NOT NULL REFERENCES lfhe.articles(id),
  snapshot_version                 integer NOT NULL CHECK (snapshot_version >= 1),
  collection_run_id                uuid NOT NULL REFERENCES lfhe.collection_runs(id),
  requested_url                    text NOT NULL,
  final_url                        text NOT NULL,
  redirect_chain                   text[] NOT NULL DEFAULT '{}',
  http_status                      smallint NOT NULL CHECK (http_status BETWEEN 200 AND 299),
  content_type                     text NOT NULL,
  response_headers                 jsonb NOT NULL DEFAULT '{}'::jsonb,
  raw_content_sha256               text NOT NULL CHECK (raw_content_sha256 ~ '^[0-9a-f]{64}$'),
  raw_size_bytes                   integer NOT NULL CHECK (raw_size_bytes >= 0),
  raw_storage_key                  text,
  retention_mode_applied           lfhe.retention_mode NOT NULL,
  content_identity_sha256          text NOT NULL CHECK (content_identity_sha256 ~ '^[0-9a-f]{64}$'),
  title_original                   text,
  language                         text CHECK (language ~ '^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$'),
  language_method                  text CHECK (language_method IN
                                     ('html_lang', 'feed_language', 'detector', 'source_primary_language', 'none')),
  publication_datetime             timestamptz,
  publication_datetime_field       text,
  public_availability_datetime     timestamptz,
  public_availability_basis        lfhe.public_availability_basis NOT NULL,
  public_availability_confidence   lfhe.timestamp_confidence NOT NULL,
  source_updated_datetime          timestamptz,
  source_updated_datetime_field    text,
  system_retrieval_datetime        timestamptz NOT NULL,
  date_status                      lfhe.date_status NOT NULL,
  metadata                         jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at                       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (article_id, snapshot_version),
  CONSTRAINT snapshot_retention_storage_consistent CHECK (
    (retention_mode_applied = 'FULL') = (raw_storage_key IS NOT NULL)),
  CONSTRAINT snapshot_availability_not_after_retrieval CHECK (
    public_availability_datetime IS NULL OR public_availability_datetime <= system_retrieval_datetime),
  CONSTRAINT snapshot_availability_basis_consistent CHECK (
    (public_availability_datetime IS NULL) = (public_availability_basis IN ('UNKNOWN', 'LOW_CONFIDENCE_TIMESTAMP'))),
  CONSTRAINT snapshot_publication_field_present CHECK (
    (publication_datetime IS NULL) = (publication_datetime_field IS NULL)),
  CONSTRAINT snapshot_date_status_consistent CHECK (
    date_status = 'DATE_UNCERTAIN' OR (publication_datetime IS NOT NULL AND public_availability_datetime IS NOT NULL))
);
CREATE INDEX article_snapshots_article_idx ON lfhe.article_snapshots (article_id, snapshot_version DESC);
CREATE INDEX article_snapshots_retrieval_idx ON lfhe.article_snapshots (system_retrieval_datetime);
CREATE INDEX article_snapshots_availability_idx ON lfhe.article_snapshots (public_availability_datetime);

CREATE TABLE lfhe.text_representations (
  id                    uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  snapshot_id           uuid NOT NULL REFERENCES lfhe.article_snapshots(id),
  representation_type   text NOT NULL CHECK (representation_type IN ('CANONICAL_CLEAN_TEXT', 'PERMITTED_EXCERPT')),
  preprocessor_name     text NOT NULL,
  preprocessor_version  text NOT NULL CHECK (preprocessor_version ~ '^\d+\.\d+\.\d+$'),
  language              text CHECK (language ~ '^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$'),
  is_original_language  boolean NOT NULL DEFAULT true CHECK (is_original_language),
  unicode_normalization text NOT NULL DEFAULT 'NFC' CHECK (unicode_normalization = 'NFC'),
  offset_unit           text NOT NULL DEFAULT 'UNICODE_CODE_POINT' CHECK (offset_unit = 'UNICODE_CODE_POINT'),
  text_content          text NOT NULL,
  text_sha256           text NOT NULL,
  char_length           integer NOT NULL,
  created_at            timestamptz NOT NULL DEFAULT now(),
  UNIQUE (snapshot_id, representation_type, preprocessor_name, preprocessor_version),
  CONSTRAINT text_hash_matches CHECK (
    text_sha256 = encode(extensions.digest(convert_to(text_content, 'UTF8'), 'sha256'), 'hex')),
  CONSTRAINT text_length_matches CHECK (char_length = char_length(text_content))
);

-- ---------------------------------------------------------------------------
-- Immutability (no update/delete for anyone, including the owner)
-- ---------------------------------------------------------------------------
CREATE TRIGGER articles_immutable BEFORE UPDATE OR DELETE ON lfhe.articles
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();
CREATE TRIGGER article_snapshots_immutable BEFORE UPDATE OR DELETE ON lfhe.article_snapshots
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();
CREATE TRIGGER text_representations_immutable BEFORE UPDATE OR DELETE ON lfhe.text_representations
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();

-- ---------------------------------------------------------------------------
-- Audit
-- ---------------------------------------------------------------------------
CREATE TRIGGER articles_audit AFTER INSERT ON lfhe.articles
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_row_change('ARTICLE_CREATED', '-', '-', 'article');
CREATE TRIGGER article_snapshots_audit AFTER INSERT ON lfhe.article_snapshots
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_row_change('ARTICLE_SNAPSHOT_CREATED', '-', '-', 'article_snapshot');

CREATE OR REPLACE FUNCTION lfhe.audit_text_representation()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  -- The text itself is integrity-protected by text_sha256; the audit entry
  -- records the hash, not a second copy of the content.
  PERFORM lfhe.write_audit('TEXT_REPRESENTATION_CREATED', 'text_representation', NEW.id::text,
    NULL, to_jsonb(NEW) - 'text_content', '{}'::jsonb);
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION lfhe.audit_text_representation() FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator;
CREATE TRIGGER text_representations_audit AFTER INSERT ON lfhe.text_representations
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_text_representation();

-- ---------------------------------------------------------------------------
-- Worker write path
-- p: {source_id, collection_run_id, canonical_url, requested_url, final_url,
--     redirect_chain[], http_status, content_type, response_headers{},
--     raw_content_sha256, raw_size_bytes, raw_storage_key, retention_mode_applied,
--     content_identity_sha256, title_original, language, language_method,
--     publication_datetime, publication_datetime_field,
--     public_availability_datetime, public_availability_basis,
--     public_availability_confidence, source_updated_datetime,
--     source_updated_datetime_field, system_retrieval_datetime, date_status,
--     metadata{}, text: {representation_type, preprocessor_name,
--     preprocessor_version, language, text_content, text_sha256, char_length} | null}
-- Returns {outcome: NEW|REVISED|DUPLICATE, article_id, snapshot_id, snapshot_version}
-- ---------------------------------------------------------------------------
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

  SELECT s.id, s.snapshot_version, s.content_identity_sha256 INTO v_latest
  FROM lfhe.article_snapshots s WHERE s.article_id = v_article
  ORDER BY s.snapshot_version DESC LIMIT 1;

  IF FOUND AND v_latest.content_identity_sha256 = p ->> 'content_identity_sha256' THEN
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
    date_status, metadata)
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
    coalesce(p -> 'metadata', '{}'::jsonb))
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
REVOKE ALL ON FUNCTION lfhe.record_snapshot(jsonb) FROM PUBLIC, anon, authenticated, service_role, lfhe_evaluator;
GRANT EXECUTE ON FUNCTION lfhe.record_snapshot(jsonb) TO lfhe_worker;

-- ---------------------------------------------------------------------------
-- Read access
-- ---------------------------------------------------------------------------
REVOKE ALL ON lfhe.articles, lfhe.article_snapshots, lfhe.text_representations
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator;
GRANT SELECT ON lfhe.articles, lfhe.article_snapshots, lfhe.text_representations TO authenticated, lfhe_worker;
ALTER TABLE lfhe.articles ENABLE ROW LEVEL SECURITY;
ALTER TABLE lfhe.article_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE lfhe.text_representations ENABLE ROW LEVEL SECURITY;
CREATE POLICY articles_read_human ON lfhe.articles FOR SELECT TO authenticated USING (lfhe.has_permission('ARTICLE_READ'));
CREATE POLICY articles_read_worker ON lfhe.articles FOR SELECT TO lfhe_worker USING (true);
CREATE POLICY snapshots_read_human ON lfhe.article_snapshots FOR SELECT TO authenticated USING (lfhe.has_permission('ARTICLE_READ'));
CREATE POLICY snapshots_read_worker ON lfhe.article_snapshots FOR SELECT TO lfhe_worker USING (true);
CREATE POLICY texts_read_human ON lfhe.text_representations FOR SELECT TO authenticated USING (lfhe.has_permission('ARTICLE_READ'));
CREATE POLICY texts_read_worker ON lfhe.text_representations FOR SELECT TO lfhe_worker USING (true);
