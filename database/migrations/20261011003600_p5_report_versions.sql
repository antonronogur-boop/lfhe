-- LFHÉ Phase 5 (P5-02 … P5-06) — immutable, hash-bound report versions; report items,
-- statements and statement sources; one deterministic validator for M09 and human content;
-- M09 ingestion; length / removal review; provenance-preserving human edits.
-- Baseline: Phase 5 Addendum §6–§19, §24, §25; Prompt Pack v1.2 §27–§33; CG0 (table names).
--
-- Content model (M09 output shape, Prompt Pack §31, plus `source_candidate_id` per item and
-- `likelihood_term` per statement — SD5-03/SD5-04):
--   {key_judgments|significant_developments|indicators_warning|trend_watch|what_to_watch|caveats:
--      [{item_local_id, source_candidate_id, statements: [{report_statement_local_id, text,
--        statement_role, source_assessment_statement_ids[], final_analytic_confidence,
--        likelihood_term, editorial_transform}]}]}
-- * An item derives from exactly ONE selected candidate; its statements may cite only that
--   candidate's approved assessment statements (SD5-05). KJ / SIGNIFICANT_DEVELOPMENT /
--   INDICATOR_WARNING / TREND_WATCH items require the candidate's HUMAN-assigned section;
--   WHAT_TO_WATCH and CAVEAT items may derive from any selected candidate.
-- * Coverage: every approved statement of every selected candidate is mapped by >= 1 report
--   statement unless a HUMAN removal decision removed it — M09 cannot silently delete; it may
--   only propose removal. Caveat-class statements (INFORMATION_GAP, ALTERNATIVE_EXPLANATION,
--   ASSUMPTION, or any statement with contradicting evidence) cannot be removed while other
--   statements of the same assessment remain in the report.
-- * Confidence = the approved final_analytic_confidence only; likelihood = the approved source
--   term only; required attribution text must survive; lexical guards against new numbers /
--   names, new causality, strengthening words and operational wording (heuristics, SD5-06).
-- * DC-01: no report table has a confidence column. The report carries the approved
--   final_analytic_confidence only inside the immutable canonical_json, validated equal to the
--   single canonical owner (lfhe.analytical_approvals) at write time (SD5-08).
-- * canonical_json is JCS-serialised; report_version_hash = SHA-256(JCS(canonical_json)) (CHECK).
--   Phase 5 state is DRAFT_VERSION only (no QA / approval / release state exists).

INSERT INTO lfhe.audit_event_types (code, spec_source) VALUES
  ('REPORT_EDIT_INGESTION_RECORDED', 'Phase 5 impl.'),
  ('REPORT_REMOVAL_PROPOSED', 'Phase 5 impl.'),
  ('REPORT_REMOVAL_DECIDED', 'Phase 5 impl.')
ON CONFLICT (code) DO NOTHING;

CREATE TYPE lfhe.editorial_transform AS ENUM (                  -- Prompt Pack v1.2 §30 (closed)
  'VERBATIM_APPROVED', 'PARAPHRASE', 'COMPRESSION', 'NON_ANALYTIC_FORMATTING');

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------
CREATE TABLE lfhe.report_edit_ingestion_results (
  model_run_id            uuid PRIMARY KEY REFERENCES lfhe.model_runs(id),
  model_run_status        lfhe.model_run_status NOT NULL,
  output_status           text,
  outcome                 text NOT NULL,
  rejection_reasons       text[] NOT NULL DEFAULT '{}',
  human_review_required   boolean NOT NULL,
  warnings                jsonb NOT NULL DEFAULT '[]',
  repair_of_model_run_id  uuid REFERENCES lfhe.model_runs(id),
  created_at              timestamptz NOT NULL DEFAULT now(),
  CHECK ((outcome = 'OUTPUT_REJECTED') = (cardinality(rejection_reasons) > 0))
);

CREATE TABLE lfhe.report_versions (
  id                          uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  report_id                   uuid NOT NULL REFERENCES lfhe.reports(id),
  version_no                  integer NOT NULL CHECK (version_no >= 1),
  previous_report_version_id  uuid REFERENCES lfhe.report_versions(id),
  selection_set_id            uuid NOT NULL,
  selection_set_hash          text NOT NULL,
  report_mode                 lfhe.report_mode NOT NULL,
  information_cutoff          timestamptz NOT NULL,
  origin                      text NOT NULL CHECK (origin IN ('MODEL', 'HUMAN')),
  created_by_model_run_id     uuid REFERENCES lfhe.report_edit_ingestion_results(model_run_id),
  created_by_user             uuid,
  state                       text NOT NULL DEFAULT 'DRAFT_VERSION' CHECK (state = 'DRAFT_VERSION'),
  length_status               text NOT NULL CHECK (length_status IN ('WITHIN_LIMIT', 'NEAR_LIMIT', 'EXCEEDS_LIMIT')),
  length_review_required      boolean NOT NULL,
  canonical_json              jsonb NOT NULL,
  report_version_hash         text NOT NULL,
  created_at                  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (report_id, version_no),
  UNIQUE (id, report_version_hash),
  FOREIGN KEY (selection_set_id, selection_set_hash) REFERENCES lfhe.report_selection_sets (id, content_hash),
  CHECK (report_version_hash = lfhe.jcs_sha256(canonical_json)),
  CHECK ((origin = 'MODEL') = (created_by_model_run_id IS NOT NULL AND created_by_user IS NULL)),
  CHECK ((origin = 'HUMAN') = (created_by_user IS NOT NULL AND created_by_model_run_id IS NULL)),
  CHECK (origin = 'MODEL' OR NOT length_review_required)
);

CREATE TABLE lfhe.report_items (
  id                               uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  report_version_id                uuid NOT NULL REFERENCES lfhe.report_versions(id),
  section                          lfhe.report_section NOT NULL,
  item_no                          integer NOT NULL CHECK (item_no >= 1),
  item_local_id                    text NOT NULL,
  source_candidate_id              uuid NOT NULL REFERENCES lfhe.report_candidate_pool(id),
  pinned_assessment_version_id     uuid,
  pinned_assessment_version_hash   text,
  pinned_event_version_id          uuid,
  pinned_event_version_hash        text,
  pinned_indicator_version_id      uuid,
  pinned_indicator_version_hash    text,
  pinned_trend_version_id          uuid,
  pinned_trend_version_hash        text,
  UNIQUE (report_version_id, section, item_no),
  UNIQUE (report_version_id, item_local_id),
  FOREIGN KEY (pinned_assessment_version_id, pinned_assessment_version_hash) REFERENCES lfhe.assessment_versions (id, content_hash),
  FOREIGN KEY (pinned_event_version_id, pinned_event_version_hash) REFERENCES lfhe.event_versions (id, content_hash),
  FOREIGN KEY (pinned_indicator_version_id, pinned_indicator_version_hash) REFERENCES lfhe.indicator_versions (id, content_hash),
  FOREIGN KEY (pinned_trend_version_id, pinned_trend_version_hash) REFERENCES lfhe.trend_versions (id, content_hash),
  CHECK (pinned_assessment_version_id IS NOT NULL OR pinned_trend_version_id IS NOT NULL)
);

CREATE TABLE lfhe.report_item_statements (
  id                         uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  report_item_id             uuid NOT NULL REFERENCES lfhe.report_items(id),
  statement_no               integer NOT NULL CHECK (statement_no >= 1),
  report_statement_local_id  text NOT NULL,
  statement_role             lfhe.report_section NOT NULL,
  statement_text             text NOT NULL CHECK (length(btrim(statement_text)) BETWEEN 1 AND 1500),
  likelihood_term            text REFERENCES lfhe.likelihood_terms(code),
  editorial_transform        lfhe.editorial_transform NOT NULL,
  contested                  boolean NOT NULL,
  author_type                text NOT NULL CHECK (author_type IN ('MODEL', 'HUMAN')),
  model_run_id               uuid REFERENCES lfhe.model_runs(id),
  user_id                    uuid,
  UNIQUE (report_item_id, statement_no),
  CHECK ((author_type = 'MODEL') = (model_run_id IS NOT NULL AND user_id IS NULL)),
  CHECK ((author_type = 'HUMAN') = (user_id IS NOT NULL AND model_run_id IS NULL))
);

CREATE TABLE lfhe.report_statement_sources (
  report_item_statement_id  uuid NOT NULL REFERENCES lfhe.report_item_statements(id),
  assessment_statement_id   uuid NOT NULL REFERENCES lfhe.assessment_statements(id),
  assessment_version_id     uuid NOT NULL REFERENCES lfhe.assessment_versions(id),
  PRIMARY KEY (report_item_statement_id, assessment_statement_id)
);

CREATE TABLE lfhe.report_removal_proposals (
  id                         uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  report_version_id          uuid NOT NULL REFERENCES lfhe.report_versions(id),
  proposal_no                integer NOT NULL CHECK (proposal_no >= 1),
  removal_local_id           text NOT NULL,
  target_item_local_id       text,
  target_statement_local_id  text,
  source_assessment_statement_ids uuid[] NOT NULL,
  reason                     text NOT NULL CHECK (length(btrim(reason)) >= 5),
  UNIQUE (report_version_id, proposal_no),
  CHECK ((target_item_local_id IS NULL) <> (target_statement_local_id IS NULL))
);

CREATE TABLE lfhe.report_removal_decisions (
  seq                    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id                     uuid NOT NULL UNIQUE DEFAULT pg_catalog.gen_random_uuid(),
  report_version_id      uuid NOT NULL,
  report_version_hash    text NOT NULL,
  proposal_id            uuid REFERENCES lfhe.report_removal_proposals(id),
  decision               text NOT NULL CHECK (decision IN ('ACCEPT', 'REJECT', 'KEEP_LENGTH')),
  resulting_version_id   uuid REFERENCES lfhe.report_versions(id),
  actor_user_id          uuid NOT NULL,
  reason                 text NOT NULL CHECK (length(btrim(reason)) >= 5),
  created_at             timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (report_version_id, report_version_hash) REFERENCES lfhe.report_versions (id, report_version_hash),
  CHECK ((decision = 'KEEP_LENGTH') = (proposal_id IS NULL))
);
CREATE UNIQUE INDEX report_removal_decisions_once ON lfhe.report_removal_decisions (report_version_id, coalesce(proposal_id::text, ''));

DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['report_edit_ingestion_results', 'report_versions', 'report_items', 'report_item_statements',
                           'report_statement_sources', 'report_removal_proposals', 'report_removal_decisions'] LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON lfhe.%I FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation()',
                   t || '_immutable', t);
  END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- Statement facts used by the validator
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.p5_section_key(p lfhe.report_section)
RETURNS text LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
  SELECT CASE p WHEN 'KEY_JUDGMENT' THEN 'key_judgments' WHEN 'SIGNIFICANT_DEVELOPMENT' THEN 'significant_developments'
    WHEN 'INDICATOR_WARNING' THEN 'indicators_warning' WHEN 'TREND_WATCH' THEN 'trend_watch'
    WHEN 'WHAT_TO_WATCH' THEN 'what_to_watch' ELSE 'caveats' END
$$;

CREATE OR REPLACE FUNCTION lfhe.p5_statement_contested(p_statement uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT EXISTS (SELECT 1 FROM lfhe.assessment_statement_evidence e WHERE e.statement_id = p_statement AND e.role = 'CONTRADICTS')
$$;

CREATE OR REPLACE FUNCTION lfhe.p5_caveat_class(p_statement uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT EXISTS (SELECT 1 FROM lfhe.assessment_statements s WHERE s.id = p_statement
                 AND s.statement_type IN ('INFORMATION_GAP', 'ALTERNATIVE_EXPLANATION', 'ASSUMPTION'))
      OR lfhe.p5_statement_contested(p_statement)
$$;

CREATE OR REPLACE FUNCTION lfhe.p5_final_confidence(p_assessment_version uuid)
RETURNS lfhe.analytic_confidence LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT final_analytic_confidence FROM lfhe.analytical_approvals
  WHERE assessment_version_id = p_assessment_version AND decision IN ('APPROVE', 'MODIFY_AND_APPROVE')
$$;

-- canonical likelihood phrases found in a text (longest phrases consumed first)
CREATE OR REPLACE FUNCTION lfhe.p5_likelihood_phrases(p text)
RETURNS text[] LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v text := ' ' || lower(coalesce(p, '')) || ' ';
  v_out text[] := '{}';
  t record;
BEGIN
  FOR t IN SELECT * FROM (VALUES ('ROUGHLY_EVEN_CHANCE', 'roughly even chance'), ('HIGHLY_UNLIKELY', 'highly unlikely'),
                                 ('HIGHLY_LIKELY', 'highly likely'), ('ALMOST_CERTAIN', 'almost certain'),
                                 ('REMOTE_CHANCE', 'remote chance'), ('UNLIKELY', 'unlikely'), ('LIKELY', 'likely')) x(code, phrase) LOOP
    IF v ~ ('\m' || t.phrase || '\M') THEN
      v_out := v_out || t.code;
      v := pg_catalog.regexp_replace(v, '\m' || t.phrase || '\M', ' ', 'g');
    END IF;
  END LOOP;
  RETURN v_out;
END $$;

CREATE OR REPLACE FUNCTION lfhe.p5_likelihood_phrase(p_code text)
RETURNS text LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
  SELECT lower(replace(p_code, '_', ' '))
$$;

-- ---------------------------------------------------------------------------
-- The deterministic validator (M09 output and human content)
-- p_content: section-keyed object (shape above) + removal_recommendations (M09 only)
-- p_removed: approved assessment statement ids removed by HUMAN decisions (cumulative)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.report_content_problems(p_set uuid, p_content jsonb, p_removed uuid[], p_origin text)
RETURNS text[] LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_uuid    constant text := '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$';
  v_out     text[] := '{}';
  v_sec     lfhe.report_section;
  v_item    jsonb;
  v_st      jsonb;
  v_cand    lfhe.report_selection_set_items;
  v_items   text[] := '{}';
  v_locals  text[] := '{}';
  v_srcs    uuid[];
  v_mapped  uuid[] := '{}';
  v_src     text;
  v_corpus  text;
  v_confs   lfhe.analytic_confidence[];
  v_terms   text[];
  v_found   text[];
  v_text    text;
  v_role    text;
  v_word    text;
  v_kj      integer := 0;
  v_rem     jsonb;
  v_sim     uuid[];
  v_srcphr  text[];
  v_item_ok boolean;
  r         record;
BEGIN
  IF p_content IS NULL OR pg_catalog.jsonb_typeof(p_content) <> 'object' THEN
    RETURN ARRAY['REPORT_CONTENT_INVALID'];
  END IF;
  IF p_origin = 'MODEL' AND p_content ?| ARRAY['selection_decisions', 'include', 'exclude', 'approved', 'content_approved',
       'release', 'released', 'remove_source_statement_ids', 'removed_statements', 'ai_recommended_confidence'] THEN
    v_out := v_out || 'M09_HUMAN_ONLY_ACTION'::text;
  END IF;
  FOREACH v_sec IN ARRAY enum_range(NULL::lfhe.report_section) LOOP
    IF p_content ? lfhe.p5_section_key(v_sec) AND pg_catalog.jsonb_typeof(p_content -> lfhe.p5_section_key(v_sec)) <> 'array' THEN
      v_out := v_out || ('REPORT_SECTION_INVALID:' || lfhe.p5_section_key(v_sec));
      CONTINUE;
    END IF;
    FOR v_item IN SELECT * FROM pg_catalog.jsonb_array_elements(coalesce(p_content -> lfhe.p5_section_key(v_sec), '[]')) LOOP
      IF v_sec = 'KEY_JUDGMENT' THEN
        v_kj := v_kj + 1;
      END IF;
      IF coalesce(v_item ->> 'item_local_id', '') !~ '^[A-Za-z0-9_-]{1,20}$' OR (v_item ->> 'item_local_id') = ANY (v_items) THEN
        v_out := v_out || 'ITEM_LOCAL_ID_INVALID_OR_DUPLICATE'::text;
      END IF;
      v_items := v_items || (v_item ->> 'item_local_id');
      v_cand := NULL;
      IF coalesce(v_item ->> 'source_candidate_id', '') ~ v_uuid THEN
        SELECT * INTO v_cand FROM lfhe.report_selection_set_items i
        WHERE i.selection_set_id = p_set AND i.candidate_id = (v_item ->> 'source_candidate_id')::uuid;
      END IF;
      IF v_cand.candidate_id IS NULL THEN
        v_out := v_out || ('SOURCE_CANDIDATE_NOT_SELECTED:' || coalesce(left(v_item ->> 'item_local_id', 20), 'null'));
        CONTINUE;
      END IF;
      IF v_sec IN ('KEY_JUDGMENT', 'SIGNIFICANT_DEVELOPMENT', 'INDICATOR_WARNING', 'TREND_WATCH') AND v_cand.section <> v_sec THEN
        v_out := v_out || ('SECTION_NOT_AUTHORISED:' || (v_item ->> 'item_local_id') || ':' || v_cand.section || '->' || v_sec);
      END IF;
      IF pg_catalog.jsonb_typeof(v_item -> 'statements') IS DISTINCT FROM 'array' OR pg_catalog.jsonb_array_length(v_item -> 'statements') = 0 THEN
        v_out := v_out || ('ITEM_WITHOUT_STATEMENTS:' || (v_item ->> 'item_local_id'));
        CONTINUE;
      END IF;
      -- source corpus of the candidate (statements + attribution + indicator / trend texts)
      SELECT lower(coalesce(pg_catalog.string_agg(s.statement_text || ' ' || coalesce(s.attribution_text, ''), ' '), '')) INTO v_corpus
      FROM lfhe.report_candidate_statements(v_cand.candidate_type, v_cand.object_id) cs
      JOIN lfhe.assessment_statements s ON s.id = cs.statement_id;
      IF v_cand.candidate_type = 'INDICATOR_VERSION' THEN
        SELECT v_corpus || ' ' || lower((content ->> 'indicator_text') || ' ' || (content ->> 'observable_condition')) INTO v_corpus
        FROM lfhe.indicator_versions WHERE id = v_cand.object_id;
      ELSIF v_cand.candidate_type = 'TREND_VERSION' THEN
        SELECT v_corpus || ' ' || lower((content ->> 'title') || ' ' || (content ->> 'direction') || ' ' || (content ->> 'velocity')
                                        || ' ' || (content ->> 'uncertainty')) INTO v_corpus
        FROM lfhe.trend_versions WHERE id = v_cand.object_id;
      END IF;
      v_item_ok := false;
      FOR v_st IN SELECT * FROM pg_catalog.jsonb_array_elements(v_item -> 'statements') LOOP
        v_text := coalesce(v_st ->> 'text', '');
        v_role := v_st ->> 'statement_role';
        IF coalesce(v_st ->> 'report_statement_local_id', '') !~ '^RS[0-9]{1,3}$' OR (v_st ->> 'report_statement_local_id') = ANY (v_locals) THEN
          v_out := v_out || 'STATEMENT_LOCAL_ID_INVALID_OR_DUPLICATE'::text;
        END IF;
        v_locals := v_locals || (v_st ->> 'report_statement_local_id');
        IF length(btrim(v_text)) = 0 OR length(v_text) > 1500 THEN
          v_out := v_out || ('STATEMENT_TEXT_INVALID:' || coalesce(v_st ->> 'report_statement_local_id', 'null'));
        END IF;
        IF v_role IS NULL OR NOT (v_role = ANY (enum_range(NULL::lfhe.report_section)::text[])) OR v_role NOT IN (v_sec::text, 'CAVEAT') THEN
          v_out := v_out || ('STATEMENT_ROLE_INVALID:' || coalesce(v_st ->> 'report_statement_local_id', 'null'));
        END IF;
        IF coalesce(v_st ->> 'editorial_transform', '') NOT IN ('VERBATIM_APPROVED', 'PARAPHRASE', 'COMPRESSION', 'NON_ANALYTIC_FORMATTING') THEN
          v_out := v_out || ('EDITORIAL_TRANSFORM_UNKNOWN:' || coalesce(v_st ->> 'report_statement_local_id', 'null'));
        END IF;
        -- sources
        v_srcs := '{}';
        IF pg_catalog.jsonb_typeof(v_st -> 'source_assessment_statement_ids') IS DISTINCT FROM 'array'
           OR pg_catalog.jsonb_array_length(v_st -> 'source_assessment_statement_ids') = 0 THEN
          v_out := v_out || ('REPORT_STATEMENT_WITHOUT_SOURCE:' || coalesce(v_st ->> 'report_statement_local_id', 'null'));
          CONTINUE;
        END IF;
        FOR v_src IN SELECT pg_catalog.jsonb_array_elements_text(v_st -> 'source_assessment_statement_ids') LOOP
          IF v_src !~ v_uuid OR NOT EXISTS (SELECT 1 FROM lfhe.assessment_statements WHERE id = v_src::uuid) THEN
            v_out := v_out || ('UNKNOWN_SOURCE_STATEMENT:' || left(v_src, 40));
          ELSIF NOT EXISTS (SELECT 1 FROM lfhe.report_candidate_statements(v_cand.candidate_type, v_cand.object_id) cs
                            WHERE cs.statement_id = v_src::uuid) THEN
            v_out := v_out || ('SOURCE_STATEMENT_NOT_IN_SELECTED_CANDIDATE:' || left(v_src, 40));
          ELSE
            v_srcs := v_srcs || v_src::uuid;
          END IF;
        END LOOP;
        IF cardinality(v_srcs) = 0 THEN
          CONTINUE;
        END IF;
        v_mapped := v_mapped || v_srcs;
        IF (v_st ->> 'editorial_transform') = 'VERBATIM_APPROVED' AND NOT EXISTS (
             SELECT 1 FROM lfhe.assessment_statements s WHERE s.id = ANY (v_srcs) AND s.statement_text = v_text) THEN
          v_out := v_out || ('VERBATIM_MISMATCH:' || (v_st ->> 'report_statement_local_id'));
        END IF;
        -- confidence: the approved final analytic confidence only
        v_confs := ARRAY(SELECT DISTINCT lfhe.p5_final_confidence(s.assessment_version_id)
                         FROM lfhe.assessment_statements s WHERE s.id = ANY (v_srcs));
        IF cardinality(v_confs) > 1 THEN
          v_out := v_out || ('MERGE_ACROSS_CONFIDENCE_LEVELS:' || (v_st ->> 'report_statement_local_id'));
        ELSIF (v_st ->> 'final_analytic_confidence') IS NULL AND v_role = 'KEY_JUDGMENT' THEN
          v_out := v_out || ('CONFIDENCE_MISSING_ON_KEY_JUDGMENT:' || (v_st ->> 'report_statement_local_id'));
        ELSIF (v_st ->> 'final_analytic_confidence') IS NOT NULL AND (v_st ->> 'final_analytic_confidence') IS DISTINCT FROM v_confs[1]::text THEN
          v_out := v_out || ('CONFIDENCE_CHANGED:' || (v_st ->> 'report_statement_local_id'));
        END IF;
        FOR r IN SELECT (pg_catalog.regexp_matches(lower(v_text), '\m(high|moderate|low) confidence\M', 'g'))[1] AS w LOOP
          IF upper(r.w) IS DISTINCT FROM v_confs[1]::text AND NOT EXISTS (
               SELECT 1 FROM lfhe.assessment_statements s WHERE s.id = ANY (v_srcs)
               AND lower(s.statement_text) ~ ('\m' || r.w || ' confidence\M')) THEN
            v_out := v_out || ('CONFIDENCE_CHANGED:' || (v_st ->> 'report_statement_local_id'));
          END IF;
        END LOOP;
        -- likelihood: the approved source term only
        v_terms := ARRAY(SELECT DISTINCT s.likelihood_term FROM lfhe.assessment_statements s
                         WHERE s.id = ANY (v_srcs) AND s.likelihood_term IS NOT NULL);
        v_srcphr := ARRAY(SELECT DISTINCT x FROM lfhe.assessment_statements s, pg_catalog.unnest(lfhe.p5_likelihood_phrases(s.statement_text)) x
                          WHERE s.id = ANY (v_srcs));
        v_found := ARRAY(SELECT x FROM pg_catalog.unnest(lfhe.p5_likelihood_phrases(v_text)) x
                         WHERE NOT (x = ANY (v_srcphr)) OR x = ANY (v_terms));
        IF cardinality(v_terms) > 1 THEN
          v_out := v_out || ('MERGE_ACROSS_LIKELIHOOD:' || (v_st ->> 'report_statement_local_id'));
        ELSIF cardinality(v_terms) = 0 AND ((v_st ->> 'likelihood_term') IS NOT NULL OR cardinality(v_found) > 0) THEN
          v_out := v_out || ('LIKELIHOOD_ADDED:' || (v_st ->> 'report_statement_local_id'));
        ELSIF cardinality(v_terms) = 1 THEN
          IF (v_st ->> 'likelihood_term') IS NULL THEN
            v_out := v_out || ('LIKELIHOOD_REMOVED:' || (v_st ->> 'report_statement_local_id'));
          ELSIF (v_st ->> 'likelihood_term') <> v_terms[1] OR NOT (v_found <@ v_terms) THEN
            v_out := v_out || ('LIKELIHOOD_CHANGED:' || (v_st ->> 'report_statement_local_id'));
          ELSIF NOT (v_terms[1] = ANY (lfhe.p5_likelihood_phrases(v_text))) THEN
            v_out := v_out || ('LIKELIHOOD_REMOVED:' || (v_st ->> 'report_statement_local_id'));
          END IF;
        END IF;
        -- attribution: required upstream attribution text survives
        IF EXISTS (SELECT 1 FROM lfhe.assessment_statements s WHERE s.id = ANY (v_srcs) AND s.attribution_required
                   AND pg_catalog.strpos(lower(v_text), lower(coalesce(s.attribution_text, chr(1)))) = 0) THEN
          v_out := v_out || ('ATTRIBUTION_REMOVED:' || (v_st ->> 'report_statement_local_id'));
        END IF;
        -- new facts (heuristic): numbers and capitalised names must occur in the candidate's approved material
        FOR r IN SELECT (pg_catalog.regexp_matches(v_text, '\d+(?:[.,]\d+)?', 'g'))[1] AS w LOOP
          IF pg_catalog.strpos(v_corpus, r.w) = 0 THEN
            v_out := v_out || ('UNSUPPORTED_NEW_FACT:' || (v_st ->> 'report_statement_local_id') || ':' || left(r.w, 20));
          END IF;
        END LOOP;
        FOR r IN SELECT (pg_catalog.regexp_matches(v_text, '[^.!?:;\s]\s+([A-Z][A-Za-z]{2,})', 'g'))[1] AS w LOOP
          IF v_corpus !~ ('\m' || lower(r.w) || '\M') THEN
            v_out := v_out || ('UNSUPPORTED_NEW_FACT:' || (v_st ->> 'report_statement_local_id') || ':' || left(r.w, 30));
          END IF;
        END LOOP;
        -- new judgment / strengthening / operational (heuristic)
        IF lfhe.p4_text_has('causal', v_text) AND NOT lfhe.p4_text_has('causal', v_corpus) THEN
          v_out := v_out || ('UNSUPPORTED_NEW_JUDGMENT:' || (v_st ->> 'report_statement_local_id'));
        END IF;
        FOR r IN SELECT (pg_catalog.regexp_matches(lower(v_text),
                   '\m(confirmed|definitely|certainly|undoubtedly|clearly|proves|proven|independently|corroborated|will)\M', 'g'))[1] AS w LOOP
          IF v_corpus !~ ('\m' || r.w || '\M') THEN
            v_out := v_out || ('EPISTEMIC_STRENGTHENING:' || (v_st ->> 'report_statement_local_id') || ':' || r.w);
          END IF;
        END LOOP;
        IF lfhe.p4_text_has('operational', v_text) THEN
          v_out := v_out || ('OPERATIONAL_RECOMMENDATION_PROHIBITED:' || (v_st ->> 'report_statement_local_id'));
        END IF;
        -- role / source-type consistency (item-level for KJ / WTW / INDICATOR_WARNING)
        IF v_sec = 'KEY_JUDGMENT' AND v_role = 'KEY_JUDGMENT' AND EXISTS (SELECT 1 FROM lfhe.assessment_statements s
             WHERE s.id = ANY (v_srcs) AND s.statement_type IN ('ANALYTIC_JUDGMENT', 'IMPLICATION', 'HU_NATO_RELEVANCE')) THEN
          v_item_ok := true;
        ELSIF v_sec = 'WHAT_TO_WATCH' AND v_role = 'WHAT_TO_WATCH' AND (v_cand.candidate_type = 'INDICATOR_VERSION' OR EXISTS (
             SELECT 1 FROM lfhe.assessment_statements s WHERE s.id = ANY (v_srcs)
             AND (s.statement_type IN ('IMPLICATION', 'INDICATOR_SUPPORT', 'INDICATOR_WEAKEN') OR s.likelihood_term IS NOT NULL))) THEN
          v_item_ok := true;
        ELSIF v_sec = 'INDICATOR_WARNING' AND v_role = 'INDICATOR_WARNING' AND (v_cand.candidate_type = 'INDICATOR_VERSION' OR EXISTS (
             SELECT 1 FROM lfhe.assessment_statements s WHERE s.id = ANY (v_srcs) AND s.statement_type IN ('INDICATOR_SUPPORT', 'INDICATOR_WEAKEN'))) THEN
          v_item_ok := true;
        ELSIF v_sec NOT IN ('KEY_JUDGMENT', 'WHAT_TO_WATCH', 'INDICATOR_WARNING') THEN
          v_item_ok := true;
        END IF;
        IF v_role = 'CAVEAT' AND NOT EXISTS (SELECT 1 FROM pg_catalog.unnest(v_srcs) x WHERE lfhe.p5_caveat_class(x)) THEN
          v_out := v_out || ('CAVEAT_WITHOUT_CAVEAT_SOURCE:' || (v_st ->> 'report_statement_local_id'));
        END IF;
        IF v_sec = 'TREND_WATCH' AND v_cand.candidate_type <> 'TREND_VERSION' THEN
          v_out := v_out || ('TREND_NOT_FROM_ELIGIBLE_TREND:' || (v_st ->> 'report_statement_local_id'));
        END IF;
      END LOOP;
      IF NOT v_item_ok THEN
        v_out := v_out || (CASE v_sec WHEN 'KEY_JUDGMENT' THEN 'KEY_JUDGMENT_WITHOUT_APPROVED_JUDGMENT:'
                             WHEN 'WHAT_TO_WATCH' THEN 'WHAT_TO_WATCH_NOT_FORWARD_LOOKING:'
                             ELSE 'INDICATOR_NOT_FROM_APPROVED_INDICATOR:' END || (v_item ->> 'item_local_id'));
      END IF;
    END LOOP;
  END LOOP;
  IF v_kj > 3 THEN
    v_out := v_out || 'MAX_KEY_JUDGMENTS_EXCEEDED'::text;
  END IF;
  -- human removals: only selected statements; caveats stay while their assessment is reported
  IF EXISTS (SELECT 1 FROM pg_catalog.unnest(coalesce(p_removed, '{}')) x
             WHERE NOT EXISTS (SELECT 1 FROM lfhe.report_selection_statements(p_set) s WHERE s.statement_id = x)) THEN
    v_out := v_out || 'REMOVED_STATEMENT_NOT_SELECTED'::text;
  END IF;
  -- coverage: nothing selected disappears without a HUMAN removal decision
  FOR r IN SELECT DISTINCT s.statement_id, a.statement_local_id FROM lfhe.report_selection_statements(p_set) s
           JOIN lfhe.assessment_statements a ON a.id = s.statement_id
           WHERE NOT (s.statement_id = ANY (v_mapped)) AND NOT (s.statement_id = ANY (coalesce(p_removed, '{}'))) LOOP
    v_out := v_out || ('SELECTED_STATEMENT_OMITTED:' || r.statement_local_id || ':' || left(r.statement_id::text, 8));
  END LOOP;
  IF EXISTS (SELECT 1 FROM pg_catalog.unnest(coalesce(p_removed, '{}')) x JOIN lfhe.assessment_statements a ON a.id = x
             WHERE lfhe.p5_caveat_class(x) AND EXISTS (
               SELECT 1 FROM lfhe.assessment_statements o WHERE o.assessment_version_id = a.assessment_version_id
               AND o.id = ANY (v_mapped) AND NOT lfhe.p5_caveat_class(o.id))) THEN
    v_out := v_out || 'CAVEAT_REMOVAL_PROHIBITED'::text;
  END IF;
  -- M09 removal proposals: targets exist; simulated removal never drops a needed caveat
  IF p_content ? 'removal_recommendations' THEN
    FOR v_rem IN SELECT * FROM pg_catalog.jsonb_array_elements(coalesce(p_content -> 'removal_recommendations', '[]')) LOOP
      IF NOT ((v_rem ->> 'target_item_local_id') = ANY (v_items) AND (v_rem ->> 'target_report_statement_local_id') IS NULL
              OR (v_rem ->> 'target_report_statement_local_id') = ANY (v_locals) AND (v_rem ->> 'target_item_local_id') IS NULL) THEN
        v_out := v_out || ('REMOVAL_TARGET_UNKNOWN:' || coalesce(left(v_rem ->> 'removal_local_id', 20), 'null'));
        CONTINUE;
      END IF;
      v_sim := lfhe.p5_sources_after_removal(p_content, v_rem);
      IF EXISTS (SELECT 1 FROM lfhe.report_selection_statements(p_set) s JOIN lfhe.assessment_statements a ON a.id = s.statement_id
                 WHERE lfhe.p5_caveat_class(s.statement_id) AND NOT (s.statement_id = ANY (v_sim))
                   AND s.statement_id = ANY (v_mapped)
                   AND EXISTS (SELECT 1 FROM lfhe.assessment_statements o WHERE o.assessment_version_id = a.assessment_version_id
                               AND o.id = ANY (v_sim) AND NOT lfhe.p5_caveat_class(o.id))) THEN
        v_out := v_out || ('CAVEAT_REMOVAL_FOR_LENGTH_PROHIBITED:' || coalesce(left(v_rem ->> 'removal_local_id', 20), 'null'));
      END IF;
    END LOOP;
  END IF;
  RETURN ARRAY(SELECT DISTINCT x FROM pg_catalog.unnest(v_out) x ORDER BY x);
END $$;

-- source statements still mapped after removing one target (item or statement)
CREATE OR REPLACE FUNCTION lfhe.p5_sources_after_removal(p_content jsonb, p_removal jsonb)
RETURNS uuid[] LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
  SELECT coalesce(ARRAY(
    SELECT DISTINCT x::uuid
    FROM pg_catalog.jsonb_each(p_content) sec,
         LATERAL pg_catalog.jsonb_array_elements(CASE WHEN pg_catalog.jsonb_typeof(sec.value) = 'array'
                                                      AND sec.key <> 'removal_recommendations' THEN sec.value ELSE '[]' END) it,
         LATERAL pg_catalog.jsonb_array_elements(coalesce(it -> 'statements', '[]')) st,
         LATERAL pg_catalog.jsonb_array_elements_text(coalesce(st -> 'source_assessment_statement_ids', '[]')) x
    WHERE (it ->> 'item_local_id') IS DISTINCT FROM (p_removal ->> 'target_item_local_id')
      AND (st ->> 'report_statement_local_id') IS DISTINCT FROM (p_removal ->> 'target_report_statement_local_id')
      AND x ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'), '{}')
$$;

-- deterministic length status (counts against §10 targets), combined with the model's own status
CREATE OR REPLACE FUNCTION lfhe.p5_length_status(p_content jsonb, p_model_status text)
RETURNS text LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT CASE
    WHEN p_model_status = 'EXCEEDS_LIMIT' OR EXISTS (
      SELECT 1 FROM lfhe.report_section_targets t
      WHERE t.target_max IS NOT NULL
        AND pg_catalog.jsonb_array_length(coalesce(p_content -> lfhe.p5_section_key(t.section), '[]')) > t.target_max)
    THEN 'EXCEEDS_LIMIT'
    WHEN p_model_status = 'NEAR_LIMIT' THEN 'NEAR_LIMIT'
    ELSE 'WITHIN_LIMIT' END
$$;

-- ---------------------------------------------------------------------------
-- Canonical JSON + writer (internal)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.p5_candidate_pins(p_type lfhe.report_candidate_type, p_id uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_av uuid;
  v_out jsonb := pg_catalog.jsonb_build_object('assessment_version', NULL, 'event_version', NULL,
                                               'indicator_version', NULL, 'trend_version', NULL);
BEGIN
  IF p_type = 'INDICATOR_VERSION' THEN
    SELECT assessment_version_id INTO v_av FROM lfhe.indicator_versions WHERE id = p_id;
    v_out := v_out || pg_catalog.jsonb_build_object('indicator_version', pg_catalog.jsonb_build_object(
      'id', p_id, 'hash', (SELECT content_hash FROM lfhe.indicator_versions WHERE id = p_id)));
  ELSIF p_type = 'ASSESSMENT_VERSION' THEN
    v_av := p_id;
  ELSE
    RETURN v_out || pg_catalog.jsonb_build_object('trend_version', pg_catalog.jsonb_build_object(
      'id', p_id, 'hash', (SELECT content_hash FROM lfhe.trend_versions WHERE id = p_id)));
  END IF;
  SELECT v_out || pg_catalog.jsonb_build_object(
           'assessment_version', pg_catalog.jsonb_build_object('id', v.id, 'hash', v.content_hash),
           'event_version', pg_catalog.jsonb_build_object('id', v.event_version_id, 'hash', v.event_version_hash))
  INTO v_out FROM lfhe.assessment_versions v WHERE v.id = v_av;
  RETURN v_out;
END $$;

-- normalised sections (canonical order: section enum order; MODEL items by human priority, HUMAN
-- items in the given order; statements in the given order; sources sorted)
CREATE OR REPLACE FUNCTION lfhe.p5_canonical_sections(p_set uuid, p_content jsonb, p_origin text)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_out jsonb := '[]';
  v_sec lfhe.report_section;
  v_items jsonb;
BEGIN
  FOREACH v_sec IN ARRAY enum_range(NULL::lfhe.report_section) LOOP
    SELECT coalesce(pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
             'item_no', x.n, 'item_local_id', x.item ->> 'item_local_id', 'source_candidate_id', x.cand,
             'pins', lfhe.p5_candidate_pins(x.ctype, x.obj),
             'final_analytic_confidence', (SELECT lfhe.p5_final_confidence((lfhe.p5_candidate_pins(x.ctype, x.obj) -> 'assessment_version' ->> 'id')::uuid))::text,
             'statements', (SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
                 'statement_no', s.n, 'report_statement_local_id', s.st ->> 'report_statement_local_id',
                 'statement_role', s.st ->> 'statement_role', 'text', s.st ->> 'text',
                 'sources', (SELECT pg_catalog.jsonb_agg(DISTINCT y ORDER BY y)
                             FROM pg_catalog.jsonb_array_elements_text(s.st -> 'source_assessment_statement_ids') y),
                 'final_analytic_confidence', s.st ->> 'final_analytic_confidence',
                 'likelihood_term', s.st ->> 'likelihood_term',
                 'editorial_transform', s.st ->> 'editorial_transform',
                 'contested', EXISTS (SELECT 1 FROM pg_catalog.jsonb_array_elements_text(s.st -> 'source_assessment_statement_ids') z
                                      WHERE lfhe.p5_statement_contested(z::uuid)))
               ORDER BY s.n)
               FROM pg_catalog.jsonb_array_elements(x.item -> 'statements') WITH ORDINALITY s(st, n)))
           ORDER BY x.n), '[]')
    INTO v_items
    FROM (SELECT e.item, (e.item ->> 'source_candidate_id')::uuid AS cand, i.candidate_type AS ctype, i.object_id AS obj,
                 row_number() OVER (ORDER BY CASE WHEN p_origin = 'MODEL' THEN i.priority ELSE 0 END,
                                             CASE WHEN p_origin = 'MODEL' THEN i.candidate_id::text ELSE '' END, e.pos)::integer AS n
          FROM pg_catalog.jsonb_array_elements(coalesce(p_content -> lfhe.p5_section_key(v_sec), '[]')) WITH ORDINALITY e(item, pos)
          JOIN lfhe.report_selection_set_items i ON i.selection_set_id = p_set AND i.candidate_id = (e.item ->> 'source_candidate_id')::uuid) x;
    v_out := v_out || pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object('section', v_sec, 'items', v_items));
  END LOOP;
  RETURN v_out;
END $$;

CREATE OR REPLACE FUNCTION lfhe.p5_coverage(p_sections jsonb)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
           'section', t.section, 'count', pg_catalog.jsonb_array_length(s -> 'items'),
           'target_min', t.target_min, 'target_max', t.target_max,
           'below_target', t.target_min IS NOT NULL AND pg_catalog.jsonb_array_length(s -> 'items') < t.target_min,
           'above_target', t.target_max IS NOT NULL AND pg_catalog.jsonb_array_length(s -> 'items') > t.target_max)
         ORDER BY t.section)
  FROM pg_catalog.jsonb_array_elements(p_sections) s JOIN lfhe.report_section_targets t ON t.section::text = s ->> 'section'
$$;

CREATE OR REPLACE FUNCTION lfhe.p5_write_report_version(p_report uuid, p_set uuid, p_content jsonb, p_removed uuid[],
  p_length_status text, p_origin text, p_run uuid, p_user uuid, p_removals jsonb)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  r        lfhe.reports := lfhe.p5_require_report(p_report);
  v_set    lfhe.report_selection_sets;
  v_prev   lfhe.report_versions;
  v_no     integer;
  v_secs   jsonb := lfhe.p5_canonical_sections(p_set, p_content, p_origin);
  v_canon  jsonb;
  v_id     uuid;
  v_item   uuid;
  v_stid   uuid;
  v_sec    jsonb;
  v_it     jsonb;
  v_st     jsonb;
  v_oa     text;
  v_or     uuid;
  v_ou     uuid;
  v_review boolean;
  v_n      integer := 0;
  v_rem    jsonb;
BEGIN
  SELECT * INTO v_set FROM lfhe.report_selection_sets WHERE id = p_set;
  SELECT * INTO v_prev FROM lfhe.report_versions WHERE report_id = r.id ORDER BY version_no DESC LIMIT 1;
  v_no := coalesce(v_prev.version_no, 0) + 1;
  v_canon := pg_catalog.jsonb_build_object(
    'format', 'lfhe-report/1',
    'report', pg_catalog.jsonb_build_object('report_id', r.id, 'code', r.code, 'title', r.title, 'cycle_label', r.cycle_label,
                                            'report_mode', r.report_mode, 'information_cutoff', lfhe.p5_ts(r.information_cutoff)),
    'version_no', v_no, 'previous_report_version_id', v_prev.id,
    'selection_set', pg_catalog.jsonb_build_object('id', v_set.id, 'hash', v_set.content_hash),
    'sections', v_secs, 'coverage', lfhe.p5_coverage(v_secs),
    'human_removals', coalesce((SELECT pg_catalog.jsonb_agg(DISTINCT x ORDER BY x) FROM pg_catalog.unnest(p_removed) x), '[]'),
    'length_status', p_length_status);
  v_review := p_origin = 'MODEL' AND (p_length_status = 'EXCEEDS_LIMIT' OR pg_catalog.jsonb_array_length(coalesce(p_removals, '[]')) > 0);
  INSERT INTO lfhe.report_versions (report_id, version_no, previous_report_version_id, selection_set_id, selection_set_hash,
    report_mode, information_cutoff, origin, created_by_model_run_id, created_by_user, length_status, length_review_required,
    canonical_json, report_version_hash)
  VALUES (r.id, v_no, v_prev.id, v_set.id, v_set.content_hash, r.report_mode, r.information_cutoff, p_origin, p_run, p_user,
    p_length_status, v_review, v_canon, lfhe.jcs_sha256(v_canon))
  RETURNING id INTO v_id;
  FOR v_sec IN SELECT * FROM pg_catalog.jsonb_array_elements(v_secs) LOOP
    FOR v_it IN SELECT * FROM pg_catalog.jsonb_array_elements(v_sec -> 'items') LOOP
      INSERT INTO lfhe.report_items (report_version_id, section, item_no, item_local_id, source_candidate_id,
        pinned_assessment_version_id, pinned_assessment_version_hash, pinned_event_version_id, pinned_event_version_hash,
        pinned_indicator_version_id, pinned_indicator_version_hash, pinned_trend_version_id, pinned_trend_version_hash)
      VALUES (v_id, (v_sec ->> 'section')::lfhe.report_section, (v_it ->> 'item_no')::integer, v_it ->> 'item_local_id',
        (v_it ->> 'source_candidate_id')::uuid,
        (v_it -> 'pins' -> 'assessment_version' ->> 'id')::uuid, v_it -> 'pins' -> 'assessment_version' ->> 'hash',
        (v_it -> 'pins' -> 'event_version' ->> 'id')::uuid, v_it -> 'pins' -> 'event_version' ->> 'hash',
        (v_it -> 'pins' -> 'indicator_version' ->> 'id')::uuid, v_it -> 'pins' -> 'indicator_version' ->> 'hash',
        (v_it -> 'pins' -> 'trend_version' ->> 'id')::uuid, v_it -> 'pins' -> 'trend_version' ->> 'hash')
      RETURNING id INTO v_item;
      FOR v_st IN SELECT * FROM pg_catalog.jsonb_array_elements(v_it -> 'statements') LOOP
        -- authorship: an unchanged statement keeps its previous author; anything else is this author
        v_oa := NULL; v_or := NULL; v_ou := NULL;
        IF p_origin = 'HUMAN' AND v_prev.id IS NOT NULL THEN
          SELECT s.author_type, s.model_run_id, s.user_id INTO v_oa, v_or, v_ou
          FROM lfhe.report_item_statements s JOIN lfhe.report_items i ON i.id = s.report_item_id
          WHERE i.report_version_id = v_prev.id AND s.statement_text = v_st ->> 'text'
            AND s.statement_role::text = v_st ->> 'statement_role'
            AND s.editorial_transform::text = v_st ->> 'editorial_transform'
            AND ARRAY(SELECT x.assessment_statement_id::text FROM lfhe.report_statement_sources x
                      WHERE x.report_item_statement_id = s.id ORDER BY 1)
                = ARRAY(SELECT y FROM pg_catalog.jsonb_array_elements_text(v_st -> 'sources') y ORDER BY 1)
          LIMIT 1;
        END IF;
        INSERT INTO lfhe.report_item_statements (report_item_id, statement_no, report_statement_local_id, statement_role,
          statement_text, likelihood_term, editorial_transform, contested, author_type, model_run_id, user_id)
        VALUES (v_item, (v_st ->> 'statement_no')::integer, v_st ->> 'report_statement_local_id',
          (v_st ->> 'statement_role')::lfhe.report_section, v_st ->> 'text', v_st ->> 'likelihood_term',
          (v_st ->> 'editorial_transform')::lfhe.editorial_transform, (v_st ->> 'contested')::boolean,
          coalesce(v_oa, p_origin),
          CASE WHEN coalesce(v_oa, p_origin) = 'MODEL' THEN coalesce(v_or, p_run) END,
          CASE WHEN coalesce(v_oa, p_origin) = 'HUMAN' THEN coalesce(v_ou, p_user) END)
        RETURNING id INTO v_stid;
        INSERT INTO lfhe.report_statement_sources (report_item_statement_id, assessment_statement_id, assessment_version_id)
        SELECT v_stid, a.id, a.assessment_version_id FROM lfhe.assessment_statements a
        WHERE a.id IN (SELECT y::uuid FROM pg_catalog.jsonb_array_elements_text(v_st -> 'sources') y);
      END LOOP;
    END LOOP;
  END LOOP;
  FOR v_rem IN SELECT * FROM pg_catalog.jsonb_array_elements(coalesce(p_removals, '[]')) LOOP
    v_n := v_n + 1;
    INSERT INTO lfhe.report_removal_proposals (report_version_id, proposal_no, removal_local_id, target_item_local_id,
      target_statement_local_id, source_assessment_statement_ids, reason)
    VALUES (v_id, v_n, coalesce(v_rem ->> 'removal_local_id', 'RM' || v_n), v_rem ->> 'target_item_local_id',
      v_rem ->> 'target_report_statement_local_id',
      ARRAY(SELECT DISTINCT x FROM pg_catalog.unnest(lfhe.p5_removal_sources(p_content, v_rem)) x ORDER BY 1),
      coalesce(nullif(btrim(v_rem ->> 'reason'), ''), 'length (no reason given)'));
  END LOOP;
  PERFORM lfhe.enqueue_job('RENDER_REPORT', 'report_version', v_id::text, 'RENDER_REPORT:' || v_id,
    pg_catalog.jsonb_build_object('report_version_hash', lfhe.jcs_sha256(v_canon)), 100::smallint, 3);
  RETURN v_id;
END $$;

CREATE OR REPLACE FUNCTION lfhe.p5_removal_sources(p_content jsonb, p_removal jsonb)
RETURNS uuid[] LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
  SELECT coalesce(ARRAY(
    SELECT DISTINCT x::uuid
    FROM pg_catalog.jsonb_each(p_content) sec,
         LATERAL pg_catalog.jsonb_array_elements(CASE WHEN pg_catalog.jsonb_typeof(sec.value) = 'array'
                                                      AND sec.key <> 'removal_recommendations' THEN sec.value ELSE '[]' END) it,
         LATERAL pg_catalog.jsonb_array_elements(coalesce(it -> 'statements', '[]')) st,
         LATERAL pg_catalog.jsonb_array_elements_text(coalesce(st -> 'source_assessment_statement_ids', '[]')) x
    WHERE ((it ->> 'item_local_id') = (p_removal ->> 'target_item_local_id')
           OR (st ->> 'report_statement_local_id') = (p_removal ->> 'target_report_statement_local_id'))
      AND x ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'), '{}')
$$;

-- section-keyed content of an existing version (input shape), for human edits / removals
CREATE OR REPLACE FUNCTION lfhe.report_version_content(p_version uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT pg_catalog.jsonb_object_agg(lfhe.p5_section_key((s ->> 'section')::lfhe.report_section),
           (SELECT coalesce(pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
                     'item_local_id', it ->> 'item_local_id', 'source_candidate_id', it ->> 'source_candidate_id',
                     'statements', (SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
                         'report_statement_local_id', st ->> 'report_statement_local_id', 'text', st ->> 'text',
                         'statement_role', st ->> 'statement_role', 'source_assessment_statement_ids', st -> 'sources',
                         'final_analytic_confidence', st ->> 'final_analytic_confidence',
                         'likelihood_term', st ->> 'likelihood_term', 'editorial_transform', st ->> 'editorial_transform')
                       ORDER BY (st ->> 'statement_no')::integer)
                       FROM pg_catalog.jsonb_array_elements(it -> 'statements') st))
                   ORDER BY (it ->> 'item_no')::integer), '[]')
            FROM pg_catalog.jsonb_array_elements(s -> 'items') it))
  FROM lfhe.report_versions v, pg_catalog.jsonb_array_elements(v.canonical_json -> 'sections') s
  WHERE v.id = p_version
$$;

-- ---------------------------------------------------------------------------
-- M09 ingestion (worker)
-- p: {model_run_id, output_status, human_review_required, warnings, repair_of_model_run_id, result}
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.ingest_report_edit(p jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_run     lfhe.model_runs%ROWTYPE;
  v_r       jsonb := p -> 'result';
  v_status  text := p ->> 'output_status';
  v_reasons text[] := '{}';
  v_outcome text;
  v_set     lfhe.report_selection_sets;
  r         lfhe.reports;
  v_len     text;
  v_id      uuid;
  v_bad     text;
BEGIN
  SELECT * INTO v_run FROM lfhe.model_runs WHERE id = (p ->> 'model_run_id')::uuid;
  IF NOT FOUND OR v_run.module_code <> 'M09_EXECUTIVE_EDITOR' OR v_run.status = 'RUNNING' THEN
    RAISE EXCEPTION 'model run % is not a finished M09_EXECUTIVE_EDITOR run', p ->> 'model_run_id'
      USING ERRCODE = 'object_not_in_prerequisite_state';
  END IF;
  IF v_run.status <> 'SUCCEEDED' THEN
    INSERT INTO lfhe.report_edit_ingestion_results (model_run_id, model_run_status, outcome, human_review_required,
      repair_of_model_run_id)
    VALUES (v_run.id, v_run.status, v_run.status::text, false, (p ->> 'repair_of_model_run_id')::uuid);
    RETURN pg_catalog.jsonb_build_object('outcome', v_run.status::text);
  END IF;
  IF v_status IN ('INSUFFICIENT_INFORMATION', 'HUMAN_REVIEW_REQUIRED', 'AMBIGUOUS', 'FAILED') OR v_r IS NULL THEN
    v_outcome := CASE WHEN v_status = 'INSUFFICIENT_INFORMATION' THEN 'INSUFFICIENT_INFORMATION' ELSE 'HUMAN_REVIEW_REQUIRED' END;
  ELSE
    IF coalesce(v_r ->> 'selection_set_id', '') !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
       OR NOT lfhe.run_has_object(v_run.id, 'input', 'report_selection_set', v_r ->> 'selection_set_id') THEN
      v_reasons := v_reasons || 'REPORT_SELECTION_NOT_SUPPLIED'::text;
    ELSE
      SELECT * INTO v_set FROM lfhe.report_selection_sets WHERE id = (v_r ->> 'selection_set_id')::uuid;
      r := lfhe.p5_require_report(v_set.report_id);
      IF v_set.content_hash IS DISTINCT FROM v_r ->> 'selection_set_hash' THEN
        v_reasons := v_reasons || 'SELECTION_HASH_MISMATCH'::text;
      END IF;
      SELECT pg_catalog.string_agg(i.candidate_type::text || ':' || i.object_id::text, ',') INTO v_bad
      FROM lfhe.report_selection_set_items i
      WHERE i.selection_set_id = v_set.id
        AND (NOT lfhe.report_candidate_eligible(i.candidate_type, i.object_id, r.report_mode::text, r.information_cutoff)
             OR lfhe.report_object_hash(i.candidate_type, i.object_id) IS DISTINCT FROM i.object_hash);
      IF v_bad IS NOT NULL THEN
        v_reasons := v_reasons || ('SOURCE_NOT_APPROVED_OR_INELIGIBLE:' || left(v_bad, 200));
      END IF;
      IF (v_r -> 'header') IS NOT NULL AND v_r -> 'header' <> '{}'::jsonb THEN
        v_reasons := v_reasons || 'REPORT_HEADER_NOT_EDITABLE'::text;
      END IF;
      v_reasons := v_reasons || lfhe.report_content_problems(v_set.id, v_r, '{}', 'MODEL');
    END IF;
    v_reasons := ARRAY(SELECT DISTINCT x FROM pg_catalog.unnest(v_reasons) x ORDER BY x);
    v_outcome := CASE WHEN cardinality(v_reasons) > 0 THEN 'OUTPUT_REJECTED' ELSE 'REPORT_VERSION_RECORDED' END;
  END IF;
  INSERT INTO lfhe.report_edit_ingestion_results (model_run_id, model_run_status, output_status, outcome, rejection_reasons,
    human_review_required, warnings, repair_of_model_run_id)
  VALUES (v_run.id, v_run.status, v_status, v_outcome, v_reasons, true, coalesce(p -> 'warnings', '[]'),
    (p ->> 'repair_of_model_run_id')::uuid);
  IF v_outcome <> 'REPORT_VERSION_RECORDED' THEN
    RETURN pg_catalog.jsonb_build_object('outcome', v_outcome, 'rejection_reasons', pg_catalog.to_jsonb(v_reasons));
  END IF;
  PERFORM 1 FROM lfhe.reports WHERE id = r.id FOR UPDATE;
  v_len := lfhe.p5_length_status(v_r, v_r ->> 'length_status');
  v_id := lfhe.p5_write_report_version(r.id, v_set.id, v_r, '{}', v_len, 'MODEL', v_run.id, NULL,
                                       coalesce(v_r -> 'removal_recommendations', '[]'));
  RETURN pg_catalog.jsonb_build_object('outcome', v_outcome, 'report_version_id', v_id, 'length_status', v_len,
    'length_review_required', (SELECT length_review_required FROM lfhe.report_versions WHERE id = v_id));
END $$;

-- ---------------------------------------------------------------------------
-- HUMAN_ONLY (REPORT_EDIT): edits and removal decisions — always a NEW version
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.p5_require_latest_version(p_version uuid, p_hash text)
RETURNS lfhe.report_versions LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v lfhe.report_versions;
BEGIN
  SELECT * INTO v FROM lfhe.report_versions WHERE id = p_version;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'unknown report version %', p_version USING ERRCODE = 'no_data_found';
  END IF;
  PERFORM 1 FROM lfhe.reports WHERE id = v.report_id FOR UPDATE;
  IF v.report_version_hash IS DISTINCT FROM p_hash THEN
    RAISE EXCEPTION 'VERSION_HASH_MISMATCH: report version %', p_version USING ERRCODE = 'serialization_failure';
  END IF;
  IF EXISTS (SELECT 1 FROM lfhe.report_versions x WHERE x.report_id = v.report_id AND x.version_no > v.version_no) THEN
    RAISE EXCEPTION 'REPORT_VERSION_STALE: a later version of report % exists', v.report_id USING ERRCODE = 'serialization_failure';
  END IF;
  RETURN v;
END $$;

-- p: {sections in M09 shape (key_judgments, …, caveats), remove_source_statement_ids?: [ids]}
CREATE OR REPLACE FUNCTION lfhe.edit_report_version(p_version uuid, p_hash text, p jsonb, p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor   uuid := lfhe.require_human_permission('REPORT_EDIT');
  v         lfhe.report_versions;
  v_removed uuid[];
  v_reasons text[];
  v_content jsonb;
  v_id      uuid;
  v_new     lfhe.report_versions;
BEGIN
  IF p_reason IS NULL OR length(btrim(p_reason)) < 5 THEN
    RAISE EXCEPTION 'a reason is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  v := lfhe.p5_require_latest_version(p_version, p_hash);
  IF EXISTS (SELECT 1 FROM pg_catalog.jsonb_array_elements_text(coalesce(p -> 'remove_source_statement_ids', '[]')) x
             WHERE x !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') THEN
    RAISE EXCEPTION 'REMOVED_STATEMENT_NOT_SELECTED' USING ERRCODE = 'check_violation';
  END IF;
  v_removed := ARRAY(SELECT DISTINCT x FROM (
      SELECT y::uuid AS x FROM pg_catalog.jsonb_array_elements_text(v.canonical_json -> 'human_removals') y
      UNION SELECT y::uuid FROM pg_catalog.jsonb_array_elements_text(coalesce(p -> 'remove_source_statement_ids', '[]')) y) q ORDER BY 1);
  v_content := p - 'remove_source_statement_ids' - 'removal_recommendations';
  v_reasons := lfhe.report_content_problems(v.selection_set_id, v_content, v_removed, 'HUMAN');
  IF cardinality(v_reasons) > 0 THEN
    RAISE EXCEPTION 'REPORT_CONTENT_INVALID: %', pg_catalog.array_to_string(v_reasons, ', ') USING ERRCODE = 'check_violation';
  END IF;
  IF lfhe.p5_canonical_sections(v.selection_set_id, v_content, 'HUMAN') = v.canonical_json -> 'sections'
     AND pg_catalog.to_jsonb(v_removed) = v.canonical_json -> 'human_removals' THEN
    RAISE EXCEPTION 'REPORT_EDIT_NO_CHANGE' USING ERRCODE = 'check_violation';
  END IF;
  v_id := lfhe.p5_write_report_version(v.report_id, v.selection_set_id, v_content, v_removed,
                                       lfhe.p5_length_status(v_content, NULL), 'HUMAN', NULL, v_actor, '[]');
  SELECT * INTO v_new FROM lfhe.report_versions WHERE id = v_id;
  PERFORM lfhe.write_audit(
    CASE WHEN lfhe.p5_sections_same_multiset(v.canonical_json -> 'sections', v_new.canonical_json -> 'sections')
              AND pg_catalog.to_jsonb(v_removed) = v.canonical_json -> 'human_removals'
         THEN 'REPORT_CONTENT_REORDERED' ELSE 'REPORT_TEXT_EDITED' END,
    'report_version', v_id::text, NULL,
    pg_catalog.jsonb_build_object('previous_report_version_id', v.id, 'previous_hash', v.report_version_hash,
                                  'report_version_hash', v_new.report_version_hash, 'reason', p_reason,
                                  'removed_source_statement_ids', pg_catalog.to_jsonb(v_removed)), '{}');
  RETURN pg_catalog.jsonb_build_object('report_version_id', v_id, 'report_version_hash', v_new.report_version_hash);
END $$;
COMMENT ON FUNCTION lfhe.edit_report_version(uuid, text, jsonb, text) IS 'HUMAN_ONLY';

-- same statements (text, role, sources) regardless of order → a pure reorder
CREATE OR REPLACE FUNCTION lfhe.p5_sections_same_multiset(a jsonb, b jsonb)
RETURNS boolean LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
  SELECT ARRAY(SELECT (s ->> 'section') || '|' || (st ->> 'statement_role') || '|' || (st ->> 'text') || '|' || (st ->> 'sources')
               FROM pg_catalog.jsonb_array_elements(a) s, pg_catalog.jsonb_array_elements(s -> 'items') it,
                    pg_catalog.jsonb_array_elements(it -> 'statements') st ORDER BY 1)
       = ARRAY(SELECT (s ->> 'section') || '|' || (st ->> 'statement_role') || '|' || (st ->> 'text') || '|' || (st ->> 'sources')
               FROM pg_catalog.jsonb_array_elements(b) s, pg_catalog.jsonb_array_elements(s -> 'items') it,
                    pg_catalog.jsonb_array_elements(it -> 'statements') st ORDER BY 1)
$$;

-- p_decisions: [{proposal_id, decision: ACCEPT | REJECT}] — every proposal of the version, once.
-- A version that needs length review but has no proposals takes [] (recorded as KEEP_LENGTH).
CREATE OR REPLACE FUNCTION lfhe.decide_report_removals(p_version uuid, p_hash text, p_decisions jsonb, p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor   uuid := lfhe.require_human_permission('REPORT_EDIT');
  v         lfhe.report_versions;
  v_content jsonb;
  v_rem     record;
  v_removed uuid[];
  v_mapped  uuid[];
  v_reasons text[];
  v_new     uuid;
  v_accept  integer := 0;
  d         jsonb;
BEGIN
  v := lfhe.p5_require_latest_version(p_version, p_hash);
  IF NOT v.length_review_required THEN
    RAISE EXCEPTION 'REPORT_LENGTH_REVIEW_NOT_REQUIRED: version % has no pending length / removal review', v.id
      USING ERRCODE = 'object_not_in_prerequisite_state';
  END IF;
  IF EXISTS (SELECT 1 FROM lfhe.report_removal_decisions WHERE report_version_id = v.id) THEN
    RAISE EXCEPTION 'REMOVAL_ALREADY_DECIDED' USING ERRCODE = 'unique_violation';
  END IF;
  IF (SELECT count(*) FROM lfhe.report_removal_proposals WHERE report_version_id = v.id)
       <> pg_catalog.jsonb_array_length(coalesce(p_decisions, '[]'))
     OR EXISTS (SELECT 1 FROM pg_catalog.jsonb_array_elements(coalesce(p_decisions, '[]')) x
                WHERE (x ->> 'decision') NOT IN ('ACCEPT', 'REJECT')
                   OR NOT EXISTS (SELECT 1 FROM lfhe.report_removal_proposals rp WHERE rp.report_version_id = v.id
                                  AND rp.id::text = x ->> 'proposal_id'))
     OR (SELECT count(DISTINCT x ->> 'proposal_id') FROM pg_catalog.jsonb_array_elements(coalesce(p_decisions, '[]')) x)
        <> pg_catalog.jsonb_array_length(coalesce(p_decisions, '[]')) THEN
    RAISE EXCEPTION 'REMOVAL_DECISIONS_INCOMPLETE: decide every proposal of the version exactly once' USING ERRCODE = 'check_violation';
  END IF;
  v_content := lfhe.report_version_content(v.id);
  FOR v_rem IN SELECT rp.*, x ->> 'decision' AS decision FROM pg_catalog.jsonb_array_elements(coalesce(p_decisions, '[]')) x
               JOIN lfhe.report_removal_proposals rp ON rp.id::text = x ->> 'proposal_id' ORDER BY rp.proposal_no LOOP
    IF v_rem.decision = 'ACCEPT' THEN
      v_accept := v_accept + 1;
      v_content := lfhe.p5_apply_removal(v_content, v_rem.target_item_local_id, v_rem.target_statement_local_id);
    END IF;
  END LOOP;
  IF v_accept > 0 THEN
    v_mapped := lfhe.p5_sources_after_removal(v_content, '{}'::jsonb);
    v_removed := ARRAY(SELECT DISTINCT x FROM (
        SELECT y::uuid AS x FROM pg_catalog.jsonb_array_elements_text(v.canonical_json -> 'human_removals') y
        UNION
        SELECT s FROM lfhe.report_removal_proposals rp, pg_catalog.unnest(rp.source_assessment_statement_ids) s
        WHERE rp.report_version_id = v.id
          AND rp.id::text IN (SELECT x ->> 'proposal_id' FROM pg_catalog.jsonb_array_elements(p_decisions) x WHERE x ->> 'decision' = 'ACCEPT')
          AND NOT (s = ANY (v_mapped))) q ORDER BY 1);
    v_reasons := lfhe.report_content_problems(v.selection_set_id, v_content, v_removed, 'HUMAN');
    IF cardinality(v_reasons) > 0 THEN
      RAISE EXCEPTION 'REPORT_CONTENT_INVALID: %', pg_catalog.array_to_string(v_reasons, ', ') USING ERRCODE = 'check_violation';
    END IF;
    v_new := lfhe.p5_write_report_version(v.report_id, v.selection_set_id, v_content, v_removed,
                                          lfhe.p5_length_status(v_content, NULL), 'HUMAN', NULL, v_actor, '[]');
  END IF;
  IF pg_catalog.jsonb_array_length(coalesce(p_decisions, '[]')) = 0 THEN
    INSERT INTO lfhe.report_removal_decisions (report_version_id, report_version_hash, proposal_id, decision, resulting_version_id,
      actor_user_id, reason)
    VALUES (v.id, v.report_version_hash, NULL, 'KEEP_LENGTH', NULL, v_actor, p_reason);
  END IF;
  FOR d IN SELECT * FROM pg_catalog.jsonb_array_elements(coalesce(p_decisions, '[]')) LOOP
    INSERT INTO lfhe.report_removal_decisions (report_version_id, report_version_hash, proposal_id, decision, resulting_version_id,
      actor_user_id, reason)
    VALUES (v.id, v.report_version_hash, (d ->> 'proposal_id')::uuid, d ->> 'decision', v_new, v_actor, p_reason);
  END LOOP;
  RETURN pg_catalog.jsonb_build_object('accepted', v_accept, 'report_version_id', v_new,
    'report_version_hash', (SELECT report_version_hash FROM lfhe.report_versions WHERE id = v_new));
END $$;
COMMENT ON FUNCTION lfhe.decide_report_removals(uuid, text, jsonb, text) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.p5_apply_removal(p_content jsonb, p_item text, p_statement text)
RETURNS jsonb LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
  SELECT pg_catalog.jsonb_object_agg(sec.key,
    (SELECT coalesce(pg_catalog.jsonb_agg(it2 ORDER BY n), '[]') FROM (
       SELECT it || pg_catalog.jsonb_build_object('statements',
                (SELECT coalesce(pg_catalog.jsonb_agg(st ORDER BY m), '[]')
                 FROM pg_catalog.jsonb_array_elements(it -> 'statements') WITH ORDINALITY q(st, m)
                 WHERE (st ->> 'report_statement_local_id') IS DISTINCT FROM p_statement)) AS it2, n
       FROM pg_catalog.jsonb_array_elements(sec.value) WITH ORDINALITY e(it, n)
       WHERE (it ->> 'item_local_id') IS DISTINCT FROM p_item) z
     WHERE pg_catalog.jsonb_array_length(it2 -> 'statements') > 0))
  FROM pg_catalog.jsonb_each(p_content) sec
$$;

-- ---------------------------------------------------------------------------
-- Views
-- ---------------------------------------------------------------------------
CREATE VIEW lfhe.report_version_states WITH (security_invoker = true) AS
SELECT v.id AS report_version_id, v.report_id, v.version_no, v.report_version_hash, v.state, v.origin, v.selection_set_id,
       v.length_status, v.length_review_required,
       (SELECT count(*) FROM lfhe.report_removal_proposals p WHERE p.report_version_id = v.id) AS removal_proposals,
       v.length_review_required AND NOT EXISTS (SELECT 1 FROM lfhe.report_removal_decisions d WHERE d.report_version_id = v.id)
         AS length_review_pending,
       NOT EXISTS (SELECT 1 FROM lfhe.report_versions x WHERE x.report_id = v.report_id AND x.version_no > v.version_no) AS is_latest,
       v.created_by_model_run_id, v.created_by_user, v.created_at
FROM lfhe.report_versions v;

-- ---------------------------------------------------------------------------
-- Audit
-- ---------------------------------------------------------------------------
CREATE TRIGGER report_edit_ingestion_results_audit AFTER INSERT ON lfhe.report_edit_ingestion_results
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_p5_objects('REPORT_EDIT_INGESTION_RECORDED', 'report_edit_ingestion_result', 'model_run_id');
CREATE TRIGGER report_versions_audit AFTER INSERT ON lfhe.report_versions
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_p5_objects('REPORT_VERSION_CREATED', 'report_version', 'id');
CREATE TRIGGER report_removal_proposals_audit AFTER INSERT ON lfhe.report_removal_proposals
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_p5_objects('REPORT_REMOVAL_PROPOSED', 'report_version', 'report_version_id');
CREATE TRIGGER report_removal_decisions_audit AFTER INSERT ON lfhe.report_removal_decisions
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_p5_objects('REPORT_REMOVAL_DECIDED', 'report_version', 'report_version_id');

-- ---------------------------------------------------------------------------
-- Grants / RLS
-- ---------------------------------------------------------------------------
REVOKE ALL ON FUNCTION lfhe.edit_report_version(uuid, text, jsonb, text), lfhe.decide_report_removals(uuid, text, jsonb, text)
  FROM PUBLIC, anon, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.edit_report_version(uuid, text, jsonb, text), lfhe.decide_report_removals(uuid, text, jsonb, text)
  TO authenticated;
REVOKE ALL ON FUNCTION lfhe.ingest_report_edit(jsonb) FROM PUBLIC, anon, authenticated, service_role, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.ingest_report_edit(jsonb) TO lfhe_worker;
REVOKE ALL ON FUNCTION lfhe.p5_section_key(lfhe.report_section), lfhe.p5_statement_contested(uuid), lfhe.p5_caveat_class(uuid),
  lfhe.p5_final_confidence(uuid), lfhe.p5_likelihood_phrases(text), lfhe.p5_likelihood_phrase(text),
  lfhe.report_content_problems(uuid, jsonb, uuid[], text), lfhe.p5_sources_after_removal(jsonb, jsonb),
  lfhe.p5_length_status(jsonb, text), lfhe.p5_candidate_pins(lfhe.report_candidate_type, uuid),
  lfhe.p5_canonical_sections(uuid, jsonb, text), lfhe.p5_coverage(jsonb),
  lfhe.p5_write_report_version(uuid, uuid, jsonb, uuid[], text, text, uuid, uuid, jsonb), lfhe.p5_removal_sources(jsonb, jsonb),
  lfhe.report_version_content(uuid), lfhe.p5_require_latest_version(uuid, text), lfhe.p5_sections_same_multiset(jsonb, jsonb),
  lfhe.p5_apply_removal(jsonb, text, text)
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.report_content_problems(uuid, jsonb, uuid[], text), lfhe.p5_likelihood_phrases(text),
  lfhe.report_version_content(uuid), lfhe.p5_candidate_pins(lfhe.report_candidate_type, uuid),
  lfhe.p5_statement_contested(uuid), lfhe.p5_caveat_class(uuid), lfhe.p5_final_confidence(uuid) TO lfhe_worker;

REVOKE ALL ON lfhe.report_edit_ingestion_results, lfhe.report_versions, lfhe.report_items, lfhe.report_item_statements,
  lfhe.report_statement_sources, lfhe.report_removal_proposals, lfhe.report_removal_decisions, lfhe.report_version_states
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT SELECT ON lfhe.report_edit_ingestion_results, lfhe.report_versions, lfhe.report_items, lfhe.report_item_statements,
  lfhe.report_statement_sources, lfhe.report_removal_proposals, lfhe.report_removal_decisions, lfhe.report_version_states
  TO authenticated, lfhe_worker;
DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['report_edit_ingestion_results', 'report_versions', 'report_items', 'report_item_statements',
                           'report_statement_sources', 'report_removal_proposals', 'report_removal_decisions'] LOOP
    EXECUTE format('ALTER TABLE lfhe.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY %I ON lfhe.%I FOR SELECT TO authenticated USING (lfhe.has_permission(''CLAIM_READ''))',
                   t || '_read_human', t);
    EXECUTE format('CREATE POLICY %I ON lfhe.%I FOR SELECT TO lfhe_worker USING (true)', t || '_read_worker', t);
  END LOOP;
END $$;
