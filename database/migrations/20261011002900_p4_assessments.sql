-- LFHÉ Phase 4 (P4-03 / P4-04) — statement-centric assessments and M07 ingestion.
-- Baseline: Phase 4 Addendum §3, §7–§13, §18 (indicator proposals), §19, §21;
-- Prompt Pack v1.2 §16–§23 (statement types, schema, KNOWN_FACT rule, no structural
-- fact exception, derived summary, confidence), PG-01/04/06/07/17.
--
-- * Authoritative analytic content exists ONLY as assessment_statements of an
--   immutable, hash-bound assessment_version. A derived summary references statement
--   IDs and is non-authoritative.
-- * source_epistemic_status and attribution_required are derived deterministically
--   from the as-of claim workflow state (lfhe.claim_status_asof); the model's
--   attribution flag must agree or the whole output is rejected.
-- * Likelihood: the approved likelihood vocabulary is NOT present in the repository
--   → lfhe.likelihood_terms is created EMPTY (CHANGE REQUEST CR4-01). A likelihood can
--   only be recorded with a term from that table, on ANALYTIC_JUDGMENT / IMPLICATION,
--   with a rationale. Likelihood ≠ analytic confidence (separate columns / tables).
-- * ai_recommended_confidence + rationale come from M07; final_analytic_confidence is
--   HUMAN_ONLY (migration 3100) and is never a column of a model-written row.

INSERT INTO lfhe.audit_event_types (code, spec_source) VALUES
  ('ASSESSMENT_INGESTION_RECORDED', 'Phase 4 impl.'),
  ('ASSESSMENT_VERSION_CREATED', 'Phase 4 impl.'),
  ('ASSESSMENT_STATE_CHANGED', 'Phase 4 impl.'),
  ('ASSESSMENT_SUPERSEDED', 'Phase 4 impl.')
ON CONFLICT (code) DO NOTHING;

CREATE TYPE lfhe.assessment_statement_type AS ENUM (           -- Prompt Pack v1.2 §17 (closed)
  'KNOWN_FACT', 'ASSUMPTION', 'CHANGE_FROM_BASELINE', 'ANALYTIC_JUDGMENT', 'IMPLICATION',
  'ALTERNATIVE_EXPLANATION', 'INFORMATION_GAP', 'INDICATOR_SUPPORT', 'INDICATOR_WEAKEN', 'HU_NATO_RELEVANCE');
CREATE TYPE lfhe.statement_provenance_class AS ENUM (          -- Prompt Pack v1.2 §18 (closed)
  'CASE_EVIDENCE', 'APPROVED_REFERENCE_CONTEXT', 'MIXED', 'NONE_REQUIRED');
CREATE TYPE lfhe.epistemic_category AS ENUM ('FACT', 'ASSUMPTION', 'ASSESSMENT');   -- system-level distinction
CREATE TYPE lfhe.analytic_confidence AS ENUM ('HIGH', 'MODERATE', 'LOW');           -- Prompt Pack v1.2 §22
CREATE TYPE lfhe.statement_evidence_role AS ENUM ('SUPPORTS', 'CONTRADICTS');       -- supporting_* / contradicting_*
CREATE TYPE lfhe.assessment_state AS ENUM (                    -- Addendum §13 state machine
  'DRAFT', 'CHALLENGED', 'IN_REVIEW', 'APPROVED', 'REJECTED', 'ESCALATED', 'REPROCESSING_REQUESTED', 'SUPERSEDED');

-- Approved likelihood vocabulary: deliberately EMPTY (CR4-01). Owner/migration only.
CREATE TABLE lfhe.likelihood_terms (
  code         text PRIMARY KEY CHECK (code ~ '^[A-Z][A-Z0-9_]{1,60}$'),
  rank         integer NOT NULL UNIQUE,
  description  text NOT NULL,
  spec_source  text NOT NULL
);

CREATE OR REPLACE FUNCTION lfhe.statement_category(p lfhe.assessment_statement_type)
RETURNS lfhe.epistemic_category LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
  SELECT CASE WHEN p IN ('KNOWN_FACT', 'CHANGE_FROM_BASELINE', 'INDICATOR_SUPPORT', 'INDICATOR_WEAKEN') THEN 'FACT'
              WHEN p = 'ASSUMPTION' THEN 'ASSUMPTION' ELSE 'ASSESSMENT' END::lfhe.epistemic_category
$$;

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------
CREATE TABLE lfhe.assessments (
  id          uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  event_id    uuid NOT NULL REFERENCES lfhe.events(id),
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE lfhe.assessment_ingestion_results (
  model_run_id            uuid PRIMARY KEY REFERENCES lfhe.model_runs(id),
  model_run_status        lfhe.model_run_status NOT NULL,
  output_status           text,
  outcome                 text NOT NULL,
  report_mode             text NOT NULL,
  information_cutoff      timestamptz NOT NULL,
  rejection_reasons       text[] NOT NULL DEFAULT '{}',
  human_review_required   boolean NOT NULL,
  warnings                jsonb NOT NULL DEFAULT '[]',
  repair_of_model_run_id  uuid REFERENCES lfhe.model_runs(id),
  created_at              timestamptz NOT NULL DEFAULT now(),
  CHECK ((outcome = 'OUTPUT_REJECTED') = (cardinality(rejection_reasons) > 0))
);

CREATE TABLE lfhe.assessment_versions (
  id                              uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  assessment_id                   uuid NOT NULL REFERENCES lfhe.assessments(id),
  version_no                      integer NOT NULL CHECK (version_no >= 1),
  previous_version_id             uuid REFERENCES lfhe.assessment_versions(id),
  event_version_id                uuid NOT NULL,
  event_version_hash              text NOT NULL,
  baseline_version_id             uuid REFERENCES lfhe.baseline_versions(id),
  baseline_status                 text NOT NULL CHECK (baseline_status IN ('BASELINE_AVAILABLE', 'BASELINE_UNAVAILABLE')),
  context_previous_assessment_version_id uuid REFERENCES lfhe.assessment_versions(id),
  report_mode                     text NOT NULL CHECK (report_mode IN ('LIVE', 'REPLAY')),
  information_cutoff              timestamptz NOT NULL,
  origin                          text NOT NULL CHECK (origin IN ('AI', 'HUMAN')),
  created_by_model_run_id         uuid REFERENCES lfhe.model_runs(id),
  created_by_user                 uuid,
  ai_recommended_confidence       lfhe.analytic_confidence,
  ai_confidence_rationale         text,
  content                         jsonb NOT NULL,
  content_hash                    text NOT NULL,
  created_at                      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (assessment_id, version_no),
  UNIQUE (id, content_hash),
  FOREIGN KEY (event_version_id, event_version_hash) REFERENCES lfhe.event_versions (id, content_hash),
  CHECK ((version_no = 1) = (previous_version_id IS NULL)),
  CHECK ((origin = 'AI') = (created_by_model_run_id IS NOT NULL AND created_by_user IS NULL)),
  CHECK ((origin = 'HUMAN') = (created_by_user IS NOT NULL AND created_by_model_run_id IS NULL)),
  CHECK (origin = 'HUMAN' OR (ai_recommended_confidence IS NOT NULL AND length(btrim(ai_confidence_rationale)) >= 20)),
  CHECK ((baseline_status = 'BASELINE_AVAILABLE') = (baseline_version_id IS NOT NULL)),
  CHECK (content_hash = lfhe.p4_hash('lfhe-assessment-version/1', content))
);

CREATE TABLE lfhe.assessment_reference_contexts (
  assessment_version_id         uuid NOT NULL REFERENCES lfhe.assessment_versions(id),
  reference_context_version_id  uuid NOT NULL REFERENCES lfhe.reference_context_versions(id),
  PRIMARY KEY (assessment_version_id, reference_context_version_id)
);

CREATE TABLE lfhe.assessment_statements (
  id                      uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  assessment_version_id   uuid NOT NULL REFERENCES lfhe.assessment_versions(id),
  statement_local_id      text NOT NULL CHECK (statement_local_id ~ '^AS[0-9]{1,3}$'),
  statement_type          lfhe.assessment_statement_type NOT NULL,
  epistemic_category      lfhe.epistemic_category NOT NULL,
  statement_text          text NOT NULL CHECK (length(btrim(statement_text)) BETWEEN 3 AND 4000),
  provenance_class        lfhe.statement_provenance_class NOT NULL,
  evidence_required       boolean NOT NULL,
  uses_baseline           boolean NOT NULL,
  attribution_required    boolean NOT NULL,
  attribution_text        text,
  source_epistemic_status jsonb NOT NULL DEFAULT '[]',
  likelihood_term         text REFERENCES lfhe.likelihood_terms(code),
  likelihood_rationale    text,
  created_at              timestamptz NOT NULL DEFAULT now(),
  UNIQUE (assessment_version_id, statement_local_id),
  CHECK (epistemic_category = lfhe.statement_category(statement_type)),
  CHECK (NOT attribution_required OR length(btrim(attribution_text)) > 0),
  CHECK ((likelihood_term IS NULL) = (likelihood_rationale IS NULL)),
  CHECK (likelihood_term IS NULL OR statement_type IN ('ANALYTIC_JUDGMENT', 'IMPLICATION')),
  CHECK (statement_type NOT IN ('KNOWN_FACT', 'CHANGE_FROM_BASELINE', 'INDICATOR_SUPPORT', 'INDICATOR_WEAKEN')
         OR (provenance_class <> 'NONE_REQUIRED' AND evidence_required))
);

CREATE TABLE lfhe.assessment_statement_evidence (
  statement_id  uuid NOT NULL REFERENCES lfhe.assessment_statements(id),
  object_type   text NOT NULL CHECK (object_type IN ('claim', 'baseline_version', 'reference_context_version')),
  object_id     uuid NOT NULL,
  role          lfhe.statement_evidence_role NOT NULL,
  PRIMARY KEY (statement_id, object_type, object_id, role)
);

CREATE TABLE lfhe.assessment_statement_premises (
  statement_id          uuid NOT NULL REFERENCES lfhe.assessment_statements(id),
  premise_statement_id  uuid NOT NULL REFERENCES lfhe.assessment_statements(id),
  PRIMARY KEY (statement_id, premise_statement_id),
  CHECK (statement_id <> premise_statement_id)
);

-- convenience text, NOT authoritative: resolves only to statement IDs
CREATE TABLE lfhe.assessment_derived_summaries (
  assessment_version_id  uuid PRIMARY KEY REFERENCES lfhe.assessment_versions(id),
  summary_text           text NOT NULL,
  source_statement_ids   uuid[] NOT NULL CHECK (cardinality(source_statement_ids) >= 1),
  authoritative          boolean NOT NULL DEFAULT false CHECK (NOT authoritative)
);

-- M07 indicators_to_watch proposals (become authoritative indicators only via humans, P4-07)
CREATE TABLE lfhe.assessment_indicator_proposals (
  id                     uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  assessment_version_id  uuid NOT NULL REFERENCES lfhe.assessment_versions(id),
  indicator_local_id     text NOT NULL CHECK (indicator_local_id ~ '^IND[0-9]{1,3}$'),
  indicator_text         text NOT NULL CHECK (length(btrim(indicator_text)) BETWEEN 5 AND 1000),
  observable_condition   text NOT NULL CHECK (length(btrim(observable_condition)) BETWEEN 10 AND 1000),
  related_statement_ids  uuid[] NOT NULL CHECK (cardinality(related_statement_ids) >= 1),
  supporting_claim_ids   uuid[] NOT NULL DEFAULT '{}',
  UNIQUE (assessment_version_id, indicator_local_id)
);

CREATE TABLE lfhe.assessment_state_history (
  seq                    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id                     uuid NOT NULL UNIQUE DEFAULT pg_catalog.gen_random_uuid(),
  assessment_version_id  uuid NOT NULL REFERENCES lfhe.assessment_versions(id),
  old_state              lfhe.assessment_state,
  new_state              lfhe.assessment_state NOT NULL,
  actor_type             lfhe.actor_type NOT NULL,
  actor_user_id          uuid,
  decision_id            uuid,
  reason                 text NOT NULL,
  created_at             timestamptz NOT NULL DEFAULT now(),
  CHECK ((actor_user_id IS NOT NULL) = (actor_type = 'HUMAN')),
  -- non-humans may only create DRAFT and run the deterministic challenge transitions
  CHECK (actor_type = 'HUMAN' OR (old_state IS NULL AND new_state = 'DRAFT')
         OR (old_state = 'DRAFT' AND new_state = 'CHALLENGED') OR (old_state = 'CHALLENGED' AND new_state = 'IN_REVIEW')),
  CHECK (old_state IS DISTINCT FROM new_state)
);
CREATE UNIQUE INDEX assessment_state_initial ON lfhe.assessment_state_history (assessment_version_id) WHERE old_state IS NULL;

DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['likelihood_terms', 'assessments', 'assessment_ingestion_results', 'assessment_versions',
    'assessment_reference_contexts', 'assessment_statements', 'assessment_statement_evidence',
    'assessment_statement_premises', 'assessment_derived_summaries', 'assessment_indicator_proposals',
    'assessment_state_history'] LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON lfhe.%I FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation()',
                   t || '_immutable', t);
  END LOOP;
END $$;

ALTER TABLE lfhe.relevance_results ADD CONSTRAINT relevance_previous_assessment_fk
  FOREIGN KEY (previous_assessment_version_id) REFERENCES lfhe.assessment_versions(id);

-- ---------------------------------------------------------------------------
-- State helpers
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.assessment_version_state(p_version uuid)
RETURNS lfhe.assessment_state LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT new_state FROM lfhe.assessment_state_history WHERE assessment_version_id = p_version ORDER BY seq DESC LIMIT 1
$$;

CREATE OR REPLACE FUNCTION lfhe.set_assessment_state(p_version uuid, p_new lfhe.assessment_state, p_actor_type lfhe.actor_type,
                                                     p_actor uuid, p_decision uuid, p_reason text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  INSERT INTO lfhe.assessment_state_history (assessment_version_id, old_state, new_state, actor_type, actor_user_id,
    decision_id, reason)
  VALUES (p_version, lfhe.assessment_version_state(p_version), p_new, p_actor_type, p_actor, p_decision, p_reason);
END $$;

-- ---------------------------------------------------------------------------
-- Knowledge bound of an assessment version (§19: previous assessment context)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.p4_run_evidence_eligible(p_run uuid, p_mode text, p_cutoff timestamptz, p_depth integer DEFAULT 0)
RETURNS boolean LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  r record;
BEGIN
  IF p_depth > 30 OR p_run IS NULL OR NOT EXISTS (SELECT 1 FROM lfhe.model_runs WHERE id = p_run) THEN
    RETURN false;
  END IF;
  FOR r IN SELECT x ->> 'object_type' AS t, x ->> 'object_id' AS i
           FROM lfhe.model_runs m,
                pg_catalog.jsonb_array_elements(coalesce(m.input_manifest, '[]') || coalesce(m.context_manifest, '[]')) x
           WHERE m.id = p_run LOOP
    IF NOT (CASE r.t
        WHEN 'claim' THEN lfhe.claim_cutoff_eligible(r.i::uuid, p_mode, p_cutoff)
        WHEN 'article' THEN lfhe.article_cutoff_eligible(r.i::uuid, p_mode, p_cutoff)
        WHEN 'claim_lineage' THEN lfhe.lineage_usable(r.i::uuid, p_mode, p_cutoff, p_depth + 1)
        WHEN 'event_version' THEN lfhe.event_version_eligible(r.i::uuid, p_mode, p_cutoff, p_depth + 1)
        WHEN 'baseline_version' THEN lfhe.baseline_version_usable(r.i::uuid, p_mode, p_cutoff)
        WHEN 'reference_context_version' THEN lfhe.reference_context_version_usable(r.i::uuid, p_mode, p_cutoff, p_depth + 1)
        WHEN 'assessment_version' THEN lfhe.assessment_version_eligible(r.i::uuid, p_mode, p_cutoff, p_depth + 1)
        ELSE false END) THEN
      RETURN false;
    END IF;
  END LOOP;
  RETURN true;
END $$;

CREATE OR REPLACE FUNCTION lfhe.assessment_version_eligible(p_version uuid, p_mode text, p_cutoff timestamptz,
                                                            p_depth integer DEFAULT 0)
RETURNS boolean LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v lfhe.assessment_versions%ROWTYPE;
BEGIN
  IF p_depth > 30 THEN
    RETURN false;
  END IF;
  SELECT * INTO v FROM lfhe.assessment_versions WHERE id = p_version;
  IF NOT FOUND OR NOT lfhe.event_version_eligible(v.event_version_id, p_mode, p_cutoff, p_depth + 1) THEN
    RETURN false;
  END IF;
  IF v.origin = 'AI' AND NOT lfhe.p4_run_evidence_eligible(v.created_by_model_run_id, p_mode, p_cutoff, p_depth + 1) THEN
    RETURN false;
  END IF;
  IF EXISTS (SELECT 1 FROM lfhe.assessment_statements s JOIN lfhe.assessment_statement_evidence e ON e.statement_id = s.id
             WHERE s.assessment_version_id = v.id AND NOT (CASE e.object_type
               WHEN 'claim' THEN lfhe.claim_cutoff_eligible(e.object_id, p_mode, p_cutoff)
               WHEN 'baseline_version' THEN lfhe.baseline_version_usable(e.object_id, p_mode, p_cutoff)
               ELSE lfhe.reference_context_version_usable(e.object_id, p_mode, p_cutoff, p_depth + 1) END)) THEN
    RETURN false;
  END IF;
  RETURN v.previous_version_id IS NULL OR lfhe.assessment_version_eligible(v.previous_version_id, p_mode, p_cutoff, p_depth + 1);
END $$;

-- ---------------------------------------------------------------------------
-- Deterministic attribution (§10) and source epistemic status
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.p4_claim_corroborated_asof(p_claim uuid, p_mode text, p_cutoff timestamptz)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT coalesce((
    SELECT s.claim_status IN ('CORROBORATED', 'CONFIRMED_PRIMARY')
       AND c.source_statement_status IN ('FACT_REPORTED_BY_SOURCE', 'DIRECT_OBSERVATION_REPORTED')
       AND (NOT st.high_impact OR s.actor_type = 'HUMAN')          -- high-impact: human-confirmed status only
       AND NOT st.revalidation_pending
       AND st.review_state NOT IN ('REJECTED', 'REPROCESSING_REQUESTED')
    FROM lfhe.claims c JOIN lfhe.claim_state st ON st.claim_id = c.id
    JOIN LATERAL lfhe.claim_status_asof(c.id, p_mode, p_cutoff) s ON true
    WHERE c.id = p_claim), false)
$$;

CREATE OR REPLACE FUNCTION lfhe.p4_attribution_required(p_type lfhe.assessment_statement_type, p_claims uuid[],
                                                        p_rcs uuid[], p_mode text, p_cutoff timestamptz)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT CASE
    WHEN lfhe.statement_category(p_type) <> 'FACT' THEN false
    WHEN cardinality(coalesce(p_claims, '{}')) = 0 THEN cardinality(coalesce(p_rcs, '{}')) > 0   -- attribute to the context
    ELSE EXISTS (SELECT 1 FROM pg_catalog.unnest(p_claims) c WHERE NOT lfhe.p4_claim_corroborated_asof(c, p_mode, p_cutoff))
  END
$$;

CREATE OR REPLACE FUNCTION lfhe.p4_source_epistemic_status(p_claims uuid[], p_mode text, p_cutoff timestamptz)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT coalesce(pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
           'claim_id', c.id, 'claim_status', coalesce(s.claim_status::text, 'UNVERIFIED'),
           'source_statement_status', c.source_statement_status, 'high_impact', st.high_impact,
           'corroborated_for_attribution', lfhe.p4_claim_corroborated_asof(c.id, p_mode, p_cutoff)) ORDER BY c.id), '[]')
  FROM lfhe.claims c JOIN lfhe.claim_state st ON st.claim_id = c.id
  LEFT JOIN LATERAL lfhe.claim_status_asof(c.id, p_mode, p_cutoff) s ON true
  WHERE c.id = ANY (coalesce(p_claims, '{}'))
$$;

-- lexical guards (deterministic; a flag here rejects the output for human attention)
CREATE OR REPLACE FUNCTION lfhe.p4_text_has(p_kind text, p text)
RETURNS boolean LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
  SELECT CASE p_kind
    WHEN 'causal' THEN lower(p) ~ '\m(because|caused|causing|causes|led to|leads to|leading to|due to|as a result|resulted in|results in|in response to|owing to|therefore|consequently)\M'
    WHEN 'absence' THEN lower(p) ~ '(\mno evidence\M|\mno reports?\M|\mnot been (observed|reported|seen|detected)\M|\mhas not\M|\mhave not\M|\mdid not\M|\mabsence of\M|\mnever\M|\mthere (is|are|was|were) no\M|\mno\M[^.]{0,60}\m(has|have|had|was|were) been (reported|observed|seen|detected)\M|\mnone\M[^.]{0,40}\m(reported|observed|seen|detected)\M)'
    WHEN 'negation' THEN lower(p) ~ '\m(no|not|never|denied|denies|deny|without|none|nothing)\M'
    WHEN 'operational' THEN lower(p) ~ '\m(recommend(s|ed)?|should|must|advise[sd]?)\M[^.]{0,80}\m(strike|attack|destroy|neutrali[sz]e|target|engage|shoot down)\M'
                         OR lower(p) ~ '\m(strike|attack|destroy|neutrali[sz]e|target|engage)\M[^.]{0,40}\m(is|are) (recommended|advised)\M'
    ELSE false END
$$;

-- ---------------------------------------------------------------------------
-- Statement validation shared by M07 ingestion and human MODIFY_AND_APPROVE.
-- ctx: {event_version_id, claim_ids:[...], contradicts_claim_ids:[...], baseline_version_id, rc_version_ids:[...]}
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.assessment_statement_problems(ctx jsonb, p_statements jsonb, p_mode text,
                                                              p_cutoff timestamptz, p_check_attribution boolean)
RETURNS text[] LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_out    text[] := '{}';
  s        jsonb;
  v_local  text;
  v_type   lfhe.assessment_statement_type;
  v_cat    lfhe.epistemic_category;
  v_prov   text;
  v_claims uuid[];
  v_contra uuid[];
  v_rcs    uuid[];
  v_c      text;
  v_ctx_claims text[] := ARRAY(SELECT pg_catalog.jsonb_array_elements_text(coalesce(ctx -> 'claim_ids', '[]')));
  v_ctx_rcs    text[] := ARRAY(SELECT pg_catalog.jsonb_array_elements_text(coalesce(ctx -> 'rc_version_ids', '[]')));
  v_locals text[] := '{}';
  v_det    boolean;
  v_text   text;
  v_uuid   constant text := '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$';
BEGIN
  IF p_statements IS NULL OR pg_catalog.jsonb_typeof(p_statements) <> 'array' OR pg_catalog.jsonb_array_length(p_statements) = 0 THEN
    RETURN ARRAY['NO_ASSESSMENT_STATEMENTS'];
  END IF;
  FOR s IN SELECT * FROM pg_catalog.jsonb_array_elements(p_statements) LOOP
    v_local := s ->> 'statement_local_id';
    IF v_local IS NULL OR v_local !~ '^AS[0-9]{1,3}$' OR v_local = ANY (v_locals) THEN
      v_out := v_out || ('STATEMENT_LOCAL_ID_INVALID_OR_DUPLICATE:' || coalesce(left(v_local, 20), 'null'));
      CONTINUE;
    END IF;
    v_locals := v_locals || v_local;
  END LOOP;
  FOR s IN SELECT * FROM pg_catalog.jsonb_array_elements(p_statements) LOOP
    v_local := s ->> 'statement_local_id';
    BEGIN
      v_type := (s ->> 'statement_type')::lfhe.assessment_statement_type;
      v_prov := (s ->> 'provenance_class')::lfhe.statement_provenance_class::text;
    EXCEPTION WHEN invalid_text_representation THEN
      v_out := v_out || ('STATEMENT_ENUM_UNKNOWN:' || coalesce(left(v_local, 20), 'null'));
      CONTINUE;
    END;
    v_cat := lfhe.statement_category(v_type);
    v_text := coalesce(s ->> 'statement_text', '');
    -- evidence references must belong to the supplied, eligible context
    FOR v_c IN SELECT pg_catalog.jsonb_array_elements_text(coalesce(s -> 'supporting_claim_ids', '[]'))
               UNION ALL SELECT pg_catalog.jsonb_array_elements_text(coalesce(s -> 'contradicting_claim_ids', '[]')) LOOP
      IF v_c !~ v_uuid OR NOT (v_c = ANY (v_ctx_claims)) THEN
        v_out := v_out || ('EVIDENCE_NOT_SUPPLIED:' || v_local || ':' || left(v_c, 40));
      ELSIF NOT lfhe.claim_cutoff_eligible(v_c::uuid, p_mode, p_cutoff) THEN
        v_out := v_out || ('POST_CUTOFF_EVIDENCE:' || v_local || ':' || v_c);
      END IF;
    END LOOP;
    FOR v_c IN SELECT pg_catalog.jsonb_array_elements_text(coalesce(s -> 'supporting_reference_context_ids', '[]')) LOOP
      IF v_c !~ v_uuid OR NOT (v_c = ANY (v_ctx_rcs)) THEN
        v_out := v_out || ('REFERENCE_CONTEXT_NOT_SUPPLIED:' || v_local || ':' || left(v_c, 40));
      ELSIF NOT lfhe.reference_context_version_usable(v_c::uuid, p_mode, p_cutoff) THEN
        v_out := v_out || ('REFERENCE_CONTEXT_INELIGIBLE:' || v_local);
      END IF;
    END LOOP;
    v_claims := ARRAY(SELECT x::uuid FROM pg_catalog.jsonb_array_elements_text(coalesce(s -> 'supporting_claim_ids', '[]')) x
                      WHERE x ~ v_uuid);
    v_contra := ARRAY(SELECT x::uuid FROM pg_catalog.jsonb_array_elements_text(coalesce(s -> 'contradicting_claim_ids', '[]')) x
                      WHERE x ~ v_uuid);
    v_rcs := ARRAY(SELECT x::uuid FROM pg_catalog.jsonb_array_elements_text(coalesce(s -> 'supporting_reference_context_ids', '[]')) x
                   WHERE x ~ v_uuid);
    IF coalesce((s ->> 'uses_baseline')::boolean, false) AND (ctx ->> 'baseline_version_id') IS NULL THEN
      v_out := v_out || ('BASELINE_UNAVAILABLE:' || v_local);
    END IF;
    IF v_type = 'CHANGE_FROM_BASELINE' AND NOT coalesce((s ->> 'uses_baseline')::boolean, false) THEN
      v_out := v_out || ('CHANGE_WITHOUT_BASELINE:' || v_local);
    END IF;
    -- provenance class must match the evidence actually mapped
    IF v_prov = 'CASE_EVIDENCE' AND (cardinality(v_claims) = 0 AND NOT coalesce((s ->> 'uses_baseline')::boolean, false)
                                     OR cardinality(v_rcs) > 0)
       OR v_prov = 'APPROVED_REFERENCE_CONTEXT' AND (cardinality(v_rcs) = 0 OR cardinality(v_claims) > 0)
       OR v_prov = 'MIXED' AND (cardinality(v_rcs) = 0 OR cardinality(v_claims) = 0)
       OR v_prov = 'NONE_REQUIRED' AND (cardinality(v_claims) > 0 OR cardinality(v_rcs) > 0) THEN
      v_out := v_out || ('PROVENANCE_CLASS_MISMATCH:' || v_local);
    END IF;
    IF v_cat = 'FACT' THEN
      IF v_prov = 'NONE_REQUIRED' OR NOT coalesce((s ->> 'evidence_required')::boolean, false)
         OR (cardinality(v_claims) = 0 AND cardinality(v_rcs) = 0) THEN
        v_out := v_out || ('FACTUAL_STATEMENT_WITHOUT_EVIDENCE:' || v_local);
      END IF;
      IF lfhe.p4_text_has('causal', v_text) AND NOT EXISTS (
           SELECT 1 FROM lfhe.claims c WHERE c.id = ANY (v_claims)
           AND lfhe.p4_text_has('causal', c.claim_text_original || ' ' || c.claim_text_normalised || ' ' || c.span_exact_text)) THEN
        v_out := v_out || ('UNSUPPORTED_CAUSALITY_AS_FACT:' || v_local);
      END IF;
      IF lfhe.p4_text_has('absence', v_text) AND NOT EXISTS (
           SELECT 1 FROM lfhe.claims c WHERE c.id = ANY (v_claims)
           AND lfhe.p4_text_has('negation', c.claim_text_original || ' ' || c.claim_text_normalised || ' ' || c.span_exact_text)) THEN
        v_out := v_out || ('NEGATIVE_EVIDENCE_FROM_SILENCE:' || v_local);
      END IF;
    ELSIF v_type IN ('ANALYTIC_JUDGMENT', 'IMPLICATION', 'HU_NATO_RELEVANCE') THEN
      IF cardinality(v_claims) = 0 AND cardinality(v_rcs) = 0 AND NOT coalesce((s ->> 'uses_baseline')::boolean, false) THEN
        v_out := v_out || ('JUDGMENT_WITHOUT_PREMISES:' || v_local);
      END IF;
    ELSIF v_type = 'INFORMATION_GAP' AND v_prov <> 'NONE_REQUIRED' AND cardinality(v_claims) = 0 THEN
      v_out := v_out || ('PROVENANCE_CLASS_MISMATCH:' || v_local);
    END IF;
    FOR v_c IN SELECT pg_catalog.jsonb_array_elements_text(coalesce(s -> 'premise_statement_local_ids', '[]')) LOOP
      IF v_c = v_local OR NOT (v_c = ANY (v_locals)) THEN
        v_out := v_out || ('PREMISE_UNKNOWN:' || v_local || ':' || left(v_c, 20));
      END IF;
    END LOOP;
    -- likelihood: only prospective analytic statements, approved vocabulary, with rationale
    IF s -> 'likelihood' IS NOT NULL AND pg_catalog.jsonb_typeof(s -> 'likelihood') = 'object' THEN
      IF v_type NOT IN ('ANALYTIC_JUDGMENT', 'IMPLICATION') THEN
        v_out := v_out || ('LIKELIHOOD_NOT_APPLICABLE:' || v_local);
      ELSIF NOT EXISTS (SELECT 1 FROM lfhe.likelihood_terms t WHERE t.code = s -> 'likelihood' ->> 'term') THEN
        v_out := v_out || ('LIKELIHOOD_TERM_UNKNOWN:' || v_local);
      ELSIF coalesce(length(btrim(s -> 'likelihood' ->> 'rationale')), 0) < 10 THEN
        v_out := v_out || ('LIKELIHOOD_RATIONALE_REQUIRED:' || v_local);
      END IF;
    END IF;
    IF lfhe.p4_text_has('operational', v_text) THEN
      v_out := v_out || ('OPERATIONAL_RECOMMENDATION_PROHIBITED:' || v_local);
    END IF;
    -- attribution: deterministic, never model-authoritative (§10)
    v_det := lfhe.p4_attribution_required(v_type, v_claims, v_rcs, p_mode, p_cutoff);
    IF p_check_attribution AND coalesce((s ->> 'attribution_required')::boolean, NOT v_det) IS DISTINCT FROM v_det THEN
      v_out := v_out || ('ATTRIBUTION_CONTRADICTS_WORKFLOW_STATE:' || v_local);
    END IF;
    IF v_det AND (coalesce(length(btrim(s ->> 'attribution_text')), 0) = 0
                  OR pg_catalog.strpos(lower(v_text), lower(btrim(s ->> 'attribution_text'))) = 0) THEN
      v_out := v_out || ('ATTRIBUTION_MISSING:' || v_local);
    END IF;
  END LOOP;
  -- contradictions in the event version must stay visible (§2, test 23)
  FOR v_c IN SELECT pg_catalog.jsonb_array_elements_text(coalesce(ctx -> 'contradicts_claim_ids', '[]')) LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.jsonb_array_elements(p_statements) x
                   WHERE coalesce(x -> 'contradicting_claim_ids', '[]') ? v_c) THEN
      v_out := v_out || ('CONTRADICTION_OMITTED:' || v_c);
    END IF;
  END LOOP;
  RETURN v_out;
END $$;

-- one validated lineage repeated by several outlets does not justify HIGH confidence (§11, test 24)
CREATE OR REPLACE FUNCTION lfhe.p4_single_lineage(p_statements jsonb, p_mode text, p_cutoff timestamptz)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  WITH c AS (SELECT DISTINCT x::uuid AS claim_id
             FROM pg_catalog.jsonb_array_elements(p_statements) s,
                  pg_catalog.jsonb_array_elements_text(coalesce(s -> 'supporting_claim_ids', '[]')) x
             WHERE x ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
  SELECT (SELECT count(*) FROM c) > 1
     AND (SELECT count(DISTINCT g.independence_group)
          FROM c CROSS JOIN LATERAL lfhe.claim_independence_group_asof(c.claim_id, p_mode, p_cutoff) g) = 1
$$;

-- summary / indicators must resolve to statement IDs only
CREATE OR REPLACE FUNCTION lfhe.assessment_extra_problems(p_statements jsonb, p_summary jsonb, p_indicators jsonb,
                                                          ctx jsonb)
RETURNS text[] LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_out    text[] := '{}';
  v_locals text[] := ARRAY(SELECT x ->> 'statement_local_id' FROM pg_catalog.jsonb_array_elements(p_statements) x);
  v_i      jsonb;
  v_c      text;
  v_seen   text[] := '{}';
BEGIN
  IF p_summary IS NOT NULL AND pg_catalog.jsonb_typeof(p_summary) = 'object'
     AND coalesce(length(btrim(p_summary ->> 'text')), 0) > 0 THEN
    IF pg_catalog.jsonb_array_length(coalesce(p_summary -> 'source_statement_ids', '[]')) = 0 THEN
      v_out := v_out || 'SUMMARY_UNMAPPED'::text;
    END IF;
    FOR v_c IN SELECT pg_catalog.jsonb_array_elements_text(coalesce(p_summary -> 'source_statement_ids', '[]')) LOOP
      IF NOT (v_c = ANY (v_locals)) THEN
        v_out := v_out || ('SUMMARY_REFERENCES_UNKNOWN_STATEMENT:' || left(v_c, 20));
      END IF;
    END LOOP;
  END IF;
  FOR v_i IN SELECT * FROM pg_catalog.jsonb_array_elements(coalesce(p_indicators, '[]')) LOOP
    IF coalesce(v_i ->> 'indicator_local_id', '') !~ '^IND[0-9]{1,3}$' OR (v_i ->> 'indicator_local_id') = ANY (v_seen) THEN
      v_out := v_out || 'INDICATOR_LOCAL_ID_INVALID'::text;
    END IF;
    v_seen := v_seen || (v_i ->> 'indicator_local_id');
    IF coalesce(length(btrim(v_i ->> 'observable_condition')), 0) < 10 THEN
      v_out := v_out || ('INDICATOR_NOT_OBSERVABLE:' || coalesce(v_i ->> 'indicator_local_id', 'null'));
    END IF;
    IF pg_catalog.jsonb_array_length(coalesce(v_i -> 'related_statement_local_ids', '[]')) = 0 THEN
      v_out := v_out || ('INDICATOR_UNBOUND:' || coalesce(v_i ->> 'indicator_local_id', 'null'));
    END IF;
    FOR v_c IN SELECT pg_catalog.jsonb_array_elements_text(coalesce(v_i -> 'related_statement_local_ids', '[]')) LOOP
      IF NOT (v_c = ANY (v_locals)) THEN
        v_out := v_out || ('INDICATOR_REFERENCES_UNKNOWN_STATEMENT:' || left(v_c, 20));
      END IF;
    END LOOP;
    FOR v_c IN SELECT pg_catalog.jsonb_array_elements_text(coalesce(v_i -> 'supporting_claim_ids', '[]')) LOOP
      IF NOT (coalesce(ctx -> 'claim_ids', '[]') ? v_c) THEN
        v_out := v_out || ('EVIDENCE_NOT_SUPPLIED:' || coalesce(v_i ->> 'indicator_local_id', 'null'));
      END IF;
    END LOOP;
    IF lfhe.p4_text_has('operational', coalesce(v_i ->> 'indicator_text', '') || ' ' || coalesce(v_i ->> 'observable_condition', '')) THEN
      v_out := v_out || ('OPERATIONAL_RECOMMENDATION_PROHIBITED:' || coalesce(v_i ->> 'indicator_local_id', 'null'));
    END IF;
  END LOOP;
  RETURN v_out;
END $$;

-- ---------------------------------------------------------------------------
-- Writer (internal): canonical content → version + derived child rows
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.write_assessment_version(
  p_assessment uuid, ctx jsonb, p_statements jsonb, p_summary jsonb, p_indicators jsonb,
  p_ai_confidence text, p_ai_rationale text, p_origin text, p_run uuid, p_user uuid, p_previous uuid,
  p_mode text, p_cutoff timestamptz)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_no      integer;
  v_id      uuid;
  v_stmts   jsonb;
  v_content jsonb;
  v_ev      lfhe.event_versions%ROWTYPE;
  s         jsonb;
  v_sid     uuid;
  v_map     jsonb := '{}';
BEGIN
  SELECT * INTO v_ev FROM lfhe.event_versions WHERE id = (ctx ->> 'event_version_id')::uuid;
  SELECT coalesce(max(version_no), 0) + 1 INTO v_no FROM lfhe.assessment_versions WHERE assessment_id = p_assessment;
  SELECT coalesce(pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
      'statement_local_id', x ->> 'statement_local_id', 'statement_type', x ->> 'statement_type',
      'statement_text', x ->> 'statement_text', 'provenance_class', x ->> 'provenance_class',
      'evidence_required', coalesce((x ->> 'evidence_required')::boolean, false),
      'uses_baseline', coalesce((x ->> 'uses_baseline')::boolean, false),
      'attribution_required', lfhe.p4_attribution_required((x ->> 'statement_type')::lfhe.assessment_statement_type,
          ARRAY(SELECT y::uuid FROM pg_catalog.jsonb_array_elements_text(coalesce(x -> 'supporting_claim_ids', '[]')) y),
          ARRAY(SELECT y::uuid FROM pg_catalog.jsonb_array_elements_text(coalesce(x -> 'supporting_reference_context_ids', '[]')) y),
          p_mode, p_cutoff),
      'attribution_text', nullif(btrim(coalesce(x ->> 'attribution_text', '')), ''),
      'supporting_claim_ids', (SELECT coalesce(pg_catalog.jsonb_agg(DISTINCT y ORDER BY y), '[]')
                               FROM pg_catalog.jsonb_array_elements_text(coalesce(x -> 'supporting_claim_ids', '[]')) y),
      'contradicting_claim_ids', (SELECT coalesce(pg_catalog.jsonb_agg(DISTINCT y ORDER BY y), '[]')
                                  FROM pg_catalog.jsonb_array_elements_text(coalesce(x -> 'contradicting_claim_ids', '[]')) y),
      'supporting_reference_context_ids', (SELECT coalesce(pg_catalog.jsonb_agg(DISTINCT y ORDER BY y), '[]')
                               FROM pg_catalog.jsonb_array_elements_text(coalesce(x -> 'supporting_reference_context_ids', '[]')) y),
      'premise_statement_local_ids', (SELECT coalesce(pg_catalog.jsonb_agg(DISTINCT y ORDER BY y), '[]')
                               FROM pg_catalog.jsonb_array_elements_text(coalesce(x -> 'premise_statement_local_ids', '[]')) y),
      'likelihood', CASE WHEN pg_catalog.jsonb_typeof(x -> 'likelihood') = 'object'
                         THEN pg_catalog.jsonb_build_object('term', x -> 'likelihood' ->> 'term',
                                                            'rationale', x -> 'likelihood' ->> 'rationale') END)
      ORDER BY x ->> 'statement_local_id' COLLATE "C"), '[]')
  INTO v_stmts FROM pg_catalog.jsonb_array_elements(p_statements) x;
  v_content := pg_catalog.jsonb_build_object(
    'assessment_id', p_assessment, 'version_no', v_no, 'previous_version_id', p_previous,
    'event_version_id', v_ev.id, 'event_version_hash', v_ev.content_hash,
    'baseline_version_id', ctx ->> 'baseline_version_id',
    'context_previous_assessment_version_id', ctx ->> 'previous_assessment_version_id',
    'reference_context_version_ids', (SELECT coalesce(pg_catalog.jsonb_agg(DISTINCT y ORDER BY y), '[]')
                                      FROM pg_catalog.jsonb_array_elements_text(coalesce(ctx -> 'rc_version_ids', '[]')) y),
    'report_mode', p_mode, 'information_cutoff_epoch', extract(epoch FROM p_cutoff),
    'origin', p_origin, 'statements', v_stmts,
    'derived_summary', CASE WHEN coalesce(length(btrim(p_summary ->> 'text')), 0) > 0 THEN pg_catalog.jsonb_build_object(
        'text', p_summary ->> 'text', 'source_statement_ids',
        (SELECT pg_catalog.jsonb_agg(DISTINCT y ORDER BY y) FROM pg_catalog.jsonb_array_elements_text(p_summary -> 'source_statement_ids') y)) END,
    'indicators_to_watch', (SELECT coalesce(pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
        'indicator_local_id', i ->> 'indicator_local_id', 'indicator_text', i ->> 'indicator_text',
        'observable_condition', i ->> 'observable_condition',
        'related_statement_local_ids', (SELECT pg_catalog.jsonb_agg(DISTINCT y ORDER BY y)
                                        FROM pg_catalog.jsonb_array_elements_text(i -> 'related_statement_local_ids') y),
        'supporting_claim_ids', (SELECT coalesce(pg_catalog.jsonb_agg(DISTINCT y ORDER BY y), '[]')
                                 FROM pg_catalog.jsonb_array_elements_text(coalesce(i -> 'supporting_claim_ids', '[]')) y))
        ORDER BY i ->> 'indicator_local_id' COLLATE "C"), '[]') FROM pg_catalog.jsonb_array_elements(coalesce(p_indicators, '[]')) i),
    'ai_recommended_confidence', p_ai_confidence, 'ai_confidence_rationale', p_ai_rationale);
  INSERT INTO lfhe.assessment_versions (assessment_id, version_no, previous_version_id, event_version_id, event_version_hash,
    baseline_version_id, baseline_status, context_previous_assessment_version_id, report_mode, information_cutoff, origin,
    created_by_model_run_id, created_by_user, ai_recommended_confidence, ai_confidence_rationale, content, content_hash)
  VALUES (p_assessment, v_no, p_previous, v_ev.id, v_ev.content_hash, (ctx ->> 'baseline_version_id')::uuid,
    CASE WHEN ctx ->> 'baseline_version_id' IS NULL THEN 'BASELINE_UNAVAILABLE' ELSE 'BASELINE_AVAILABLE' END,
    (ctx ->> 'previous_assessment_version_id')::uuid, p_mode, p_cutoff, p_origin, p_run, p_user,
    p_ai_confidence::lfhe.analytic_confidence, p_ai_rationale, v_content, lfhe.p4_hash('lfhe-assessment-version/1', v_content))
  RETURNING id INTO v_id;
  INSERT INTO lfhe.assessment_reference_contexts (assessment_version_id, reference_context_version_id)
  SELECT v_id, y::uuid FROM pg_catalog.jsonb_array_elements_text(v_content -> 'reference_context_version_ids') y;
  FOR s IN SELECT * FROM pg_catalog.jsonb_array_elements(v_stmts) LOOP
    INSERT INTO lfhe.assessment_statements (assessment_version_id, statement_local_id, statement_type, epistemic_category,
      statement_text, provenance_class, evidence_required, uses_baseline, attribution_required, attribution_text,
      source_epistemic_status, likelihood_term, likelihood_rationale)
    VALUES (v_id, s ->> 'statement_local_id', (s ->> 'statement_type')::lfhe.assessment_statement_type,
      lfhe.statement_category((s ->> 'statement_type')::lfhe.assessment_statement_type), s ->> 'statement_text',
      (s ->> 'provenance_class')::lfhe.statement_provenance_class, (s ->> 'evidence_required')::boolean,
      (s ->> 'uses_baseline')::boolean, (s ->> 'attribution_required')::boolean, s ->> 'attribution_text',
      lfhe.p4_source_epistemic_status(ARRAY(SELECT y::uuid FROM pg_catalog.jsonb_array_elements_text(s -> 'supporting_claim_ids') y),
                                      p_mode, p_cutoff),
      s -> 'likelihood' ->> 'term', s -> 'likelihood' ->> 'rationale')
    RETURNING id INTO v_sid;
    v_map := v_map || pg_catalog.jsonb_build_object(s ->> 'statement_local_id', v_sid);
    INSERT INTO lfhe.assessment_statement_evidence (statement_id, object_type, object_id, role)
    SELECT v_sid, 'claim', y::uuid, 'SUPPORTS'::lfhe.statement_evidence_role
    FROM pg_catalog.jsonb_array_elements_text(s -> 'supporting_claim_ids') y
    UNION SELECT v_sid, 'claim', y::uuid, 'CONTRADICTS' FROM pg_catalog.jsonb_array_elements_text(s -> 'contradicting_claim_ids') y
    UNION SELECT v_sid, 'reference_context_version', y::uuid, 'SUPPORTS'
          FROM pg_catalog.jsonb_array_elements_text(s -> 'supporting_reference_context_ids') y
    UNION SELECT v_sid, 'baseline_version', (ctx ->> 'baseline_version_id')::uuid, 'SUPPORTS'
          WHERE (s ->> 'uses_baseline')::boolean;
  END LOOP;
  INSERT INTO lfhe.assessment_statement_premises (statement_id, premise_statement_id)
  SELECT (v_map ->> (st.v ->> 'statement_local_id'))::uuid, (v_map ->> pr.p)::uuid
  FROM pg_catalog.jsonb_array_elements(v_stmts) st(v),
       pg_catalog.jsonb_array_elements_text(st.v -> 'premise_statement_local_ids') pr(p);
  IF v_content -> 'derived_summary' IS NOT NULL AND pg_catalog.jsonb_typeof(v_content -> 'derived_summary') = 'object' THEN
    INSERT INTO lfhe.assessment_derived_summaries (assessment_version_id, summary_text, source_statement_ids)
    VALUES (v_id, v_content -> 'derived_summary' ->> 'text',
            ARRAY(SELECT (v_map ->> y)::uuid FROM pg_catalog.jsonb_array_elements_text(v_content -> 'derived_summary' -> 'source_statement_ids') y));
  END IF;
  INSERT INTO lfhe.assessment_indicator_proposals (assessment_version_id, indicator_local_id, indicator_text,
    observable_condition, related_statement_ids, supporting_claim_ids)
  SELECT v_id, i ->> 'indicator_local_id', i ->> 'indicator_text', i ->> 'observable_condition',
         ARRAY(SELECT (v_map ->> y)::uuid FROM pg_catalog.jsonb_array_elements_text(i -> 'related_statement_local_ids') y),
         ARRAY(SELECT y::uuid FROM pg_catalog.jsonb_array_elements_text(i -> 'supporting_claim_ids') y)
  FROM pg_catalog.jsonb_array_elements(v_content -> 'indicators_to_watch') i;
  RETURN v_id;
END $$;

-- ---------------------------------------------------------------------------
-- M07 ingestion (worker)
-- p: {model_run_id, output_status, human_review_required, warnings, repair_of_model_run_id, result}
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.m07_context(p_run uuid, p_mode text, p_cutoff timestamptz)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_ev   uuid;
  v_bl   uuid;
  v_prev uuid;
BEGIN
  SELECT (x ->> 'object_id')::uuid INTO v_ev FROM lfhe.model_runs m, pg_catalog.jsonb_array_elements(m.input_manifest) x
  WHERE m.id = p_run AND x ->> 'object_type' = 'event_version';
  SELECT (x ->> 'object_id')::uuid INTO v_bl FROM lfhe.model_runs m, pg_catalog.jsonb_array_elements(m.context_manifest) x
  WHERE m.id = p_run AND x ->> 'object_type' = 'baseline_version';
  SELECT (x ->> 'object_id')::uuid INTO v_prev FROM lfhe.model_runs m, pg_catalog.jsonb_array_elements(m.context_manifest) x
  WHERE m.id = p_run AND x ->> 'object_type' = 'assessment_version';
  RETURN pg_catalog.jsonb_build_object(
    'event_version_id', v_ev, 'baseline_version_id', v_bl, 'previous_assessment_version_id', v_prev,
    'claim_ids', (SELECT coalesce(pg_catalog.jsonb_agg(ec.claim_id ORDER BY ec.claim_id), '[]')
                  FROM lfhe.event_claims ec WHERE ec.event_version_id = v_ev),
    'contradicts_claim_ids', (SELECT coalesce(pg_catalog.jsonb_agg(ec.claim_id ORDER BY ec.claim_id), '[]')
                              FROM lfhe.event_claims ec WHERE ec.event_version_id = v_ev AND ec.role = 'CONTRADICTS'),
    'rc_version_ids', (SELECT coalesce(pg_catalog.jsonb_agg(x ->> 'object_id' ORDER BY x ->> 'object_id'), '[]')
                       FROM lfhe.model_runs m, pg_catalog.jsonb_array_elements(m.context_manifest) x
                       WHERE m.id = p_run AND x ->> 'object_type' = 'reference_context_version'));
END $$;

CREATE OR REPLACE FUNCTION lfhe.ingest_assessment(p jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_run     lfhe.model_runs%ROWTYPE;
  v_mode    text;
  v_cutoff  timestamptz;
  v_r       jsonb := p -> 'result';
  v_status  text := p ->> 'output_status';
  v_ctx     jsonb;
  v_reasons text[] := '{}';
  v_outcome text;
  v_ass     uuid;
  v_prev    uuid;
  v_id      uuid;
  v_ev      lfhe.event_versions%ROWTYPE;
BEGIN
  SELECT * INTO v_run FROM lfhe.model_runs WHERE id = (p ->> 'model_run_id')::uuid;
  IF NOT FOUND OR v_run.module_code <> 'M07_INTELLIGENCE_ASSESSOR' OR v_run.status = 'RUNNING' THEN
    RAISE EXCEPTION 'model run % is not a finished M07_INTELLIGENCE_ASSESSOR run', p ->> 'model_run_id'
      USING ERRCODE = 'object_not_in_prerequisite_state';
  END IF;
  SELECT * INTO v_mode, v_cutoff FROM lfhe.model_run_cutoff(v_run.id);
  IF v_run.status <> 'SUCCEEDED' THEN
    INSERT INTO lfhe.assessment_ingestion_results (model_run_id, model_run_status, outcome, report_mode, information_cutoff,
      human_review_required, repair_of_model_run_id)
    VALUES (v_run.id, v_run.status, v_run.status::text, v_mode, v_cutoff, false, (p ->> 'repair_of_model_run_id')::uuid);
    RETURN pg_catalog.jsonb_build_object('outcome', v_run.status::text);
  END IF;
  v_ctx := lfhe.m07_context(v_run.id, v_mode, v_cutoff);
  IF v_status IN ('INSUFFICIENT_INFORMATION', 'HUMAN_REVIEW_REQUIRED', 'AMBIGUOUS', 'FAILED') OR v_r IS NULL THEN
    v_outcome := CASE WHEN v_status = 'INSUFFICIENT_INFORMATION' THEN 'INSUFFICIENT_INFORMATION' ELSE 'HUMAN_REVIEW_REQUIRED' END;
  ELSE
    IF v_ctx ->> 'event_version_id' IS NULL OR v_r ->> 'event_version_id' IS DISTINCT FROM v_ctx ->> 'event_version_id' THEN
      v_reasons := v_reasons || 'EVENT_VERSION_NOT_SUPPLIED'::text;
    ELSIF NOT lfhe.event_version_eligible((v_ctx ->> 'event_version_id')::uuid, v_mode, v_cutoff) THEN
      v_reasons := v_reasons || 'EVENT_VERSION_NOT_CUTOFF_ELIGIBLE'::text;
    END IF;
    IF v_r ->> 'event_id' IS DISTINCT FROM (SELECT event_id::text FROM lfhe.event_versions
                                            WHERE id = (v_ctx ->> 'event_version_id')::uuid) THEN
      v_reasons := v_reasons || 'EVENT_ID_MISMATCH'::text;
    END IF;
    IF v_r ->> 'baseline_version_id' IS DISTINCT FROM v_ctx ->> 'baseline_version_id' THEN
      v_reasons := v_reasons || 'BASELINE_NOT_AS_SUPPLIED'::text;
    ELSIF v_ctx ->> 'baseline_version_id' IS NOT NULL
          AND NOT lfhe.baseline_version_usable((v_ctx ->> 'baseline_version_id')::uuid, v_mode, v_cutoff) THEN
      v_reasons := v_reasons || 'BASELINE_INELIGIBLE'::text;
    END IF;
    IF v_r ->> 'previous_assessment_version_id' IS DISTINCT FROM v_ctx ->> 'previous_assessment_version_id' THEN
      v_reasons := v_reasons || 'PREVIOUS_ASSESSMENT_NOT_AS_SUPPLIED'::text;
    ELSIF v_ctx ->> 'previous_assessment_version_id' IS NOT NULL
          AND NOT lfhe.assessment_version_eligible((v_ctx ->> 'previous_assessment_version_id')::uuid, v_mode, v_cutoff) THEN
      v_reasons := v_reasons || 'PREVIOUS_ASSESSMENT_INELIGIBLE'::text;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_catalog.jsonb_array_elements_text(v_ctx -> 'rc_version_ids') y
               WHERE NOT lfhe.reference_context_version_usable(y::uuid, v_mode, v_cutoff)) THEN
      v_reasons := v_reasons || 'REFERENCE_CONTEXT_INELIGIBLE'::text;
    END IF;
    IF v_r ? 'final_analytic_confidence' THEN
      v_reasons := v_reasons || 'FINAL_CONFIDENCE_IS_HUMAN_ONLY'::text;
    END IF;
    IF coalesce(length(btrim(v_r ->> 'ai_confidence_rationale')), 0) < 20 THEN
      v_reasons := v_reasons || 'CONFIDENCE_RATIONALE_REQUIRED'::text;
    END IF;
    IF cardinality(v_reasons) = 0 THEN
      v_reasons := v_reasons || lfhe.assessment_statement_problems(v_ctx, v_r -> 'assessment_statements', v_mode, v_cutoff, true)
                             || lfhe.assessment_extra_problems(v_r -> 'assessment_statements', v_r -> 'derived_summary',
                                                               v_r -> 'indicators_to_watch', v_ctx);
      IF v_r ->> 'ai_recommended_confidence' = 'HIGH'
         AND lfhe.p4_single_lineage(v_r -> 'assessment_statements', v_mode, v_cutoff) THEN
        v_reasons := v_reasons || 'CONFIDENCE_INFLATION_SINGLE_LINEAGE'::text;
      END IF;
    END IF;
    v_reasons := ARRAY(SELECT DISTINCT r FROM pg_catalog.unnest(v_reasons) r ORDER BY r);
    v_outcome := CASE WHEN cardinality(v_reasons) > 0 THEN 'OUTPUT_REJECTED' ELSE 'ASSESSMENT_RECORDED' END;
  END IF;
  INSERT INTO lfhe.assessment_ingestion_results (model_run_id, model_run_status, output_status, outcome, report_mode,
    information_cutoff, rejection_reasons, human_review_required, warnings, repair_of_model_run_id)
  VALUES (v_run.id, v_run.status, v_status, v_outcome, v_mode, v_cutoff, v_reasons, true,
    coalesce(p -> 'warnings', '[]'), (p ->> 'repair_of_model_run_id')::uuid);
  IF v_outcome <> 'ASSESSMENT_RECORDED' THEN
    RETURN pg_catalog.jsonb_build_object('outcome', v_outcome, 'rejection_reasons', pg_catalog.to_jsonb(v_reasons));
  END IF;
  SELECT * INTO v_ev FROM lfhe.event_versions WHERE id = (v_ctx ->> 'event_version_id')::uuid;
  IF v_ctx ->> 'previous_assessment_version_id' IS NOT NULL THEN
    SELECT assessment_id INTO v_ass FROM lfhe.assessment_versions WHERE id = (v_ctx ->> 'previous_assessment_version_id')::uuid;
    SELECT id INTO v_prev FROM lfhe.assessment_versions WHERE assessment_id = v_ass ORDER BY version_no DESC LIMIT 1;
  ELSE
    INSERT INTO lfhe.assessments (event_id) VALUES (v_ev.event_id) RETURNING id INTO v_ass;
  END IF;
  v_id := lfhe.write_assessment_version(v_ass, v_ctx, v_r -> 'assessment_statements', v_r -> 'derived_summary',
    v_r -> 'indicators_to_watch', v_r ->> 'ai_recommended_confidence', v_r ->> 'ai_confidence_rationale', 'AI', v_run.id,
    NULL, v_prev, v_mode, v_cutoff);
  PERFORM lfhe.set_assessment_state(v_id, 'DRAFT', 'WORKER', NULL, NULL, 'M07 draft (not validated)');
  RETURN pg_catalog.jsonb_build_object('outcome', v_outcome, 'assessment_id', v_ass, 'assessment_version_id', v_id);
END $$;

-- ---------------------------------------------------------------------------
-- Read view: current state per version (final confidence joins in migration 3100)
-- ---------------------------------------------------------------------------
CREATE VIEW lfhe.assessment_version_states WITH (security_invoker = true) AS
SELECT v.id AS assessment_version_id, v.assessment_id, v.version_no, v.content_hash, v.origin, v.event_version_id,
       v.ai_recommended_confidence,
       (SELECT h.new_state FROM lfhe.assessment_state_history h WHERE h.assessment_version_id = v.id ORDER BY h.seq DESC LIMIT 1)
         AS state
FROM lfhe.assessment_versions v;

-- ---------------------------------------------------------------------------
-- Audit
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.audit_assessment_objects()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_doc   jsonb := pg_catalog.to_jsonb(NEW);
  v_event text;
  v_obj   text;
  v_id    text;
BEGIN
  CASE TG_TABLE_NAME
    WHEN 'assessment_ingestion_results' THEN v_event := 'ASSESSMENT_INGESTION_RECORDED'; v_obj := 'assessment_ingestion_result'; v_id := v_doc ->> 'model_run_id';
    WHEN 'assessments' THEN v_event := 'ASSESSMENT_CREATED'; v_obj := 'assessment'; v_id := v_doc ->> 'id';
    WHEN 'assessment_versions' THEN
      v_event := CASE WHEN v_doc ->> 'origin' = 'HUMAN' THEN 'ASSESSMENT_MODIFIED' ELSE 'ASSESSMENT_VERSION_CREATED' END;
      v_obj := 'assessment_version'; v_id := v_doc ->> 'id'; v_doc := v_doc - 'content';
    WHEN 'assessment_state_history' THEN
      v_event := CASE v_doc ->> 'new_state' WHEN 'SUPERSEDED' THEN 'ASSESSMENT_SUPERSEDED' ELSE 'ASSESSMENT_STATE_CHANGED' END;
      v_obj := 'assessment_version'; v_id := v_doc ->> 'assessment_version_id';
  END CASE;
  PERFORM lfhe.write_audit(v_event, v_obj, v_id, NULL, v_doc, '{}'::jsonb);
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION lfhe.audit_assessment_objects() FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['assessment_ingestion_results', 'assessments', 'assessment_versions', 'assessment_state_history'] LOOP
    EXECUTE format('CREATE TRIGGER %I AFTER INSERT ON lfhe.%I FOR EACH ROW EXECUTE FUNCTION lfhe.audit_assessment_objects()',
                   t || '_audit', t);
  END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- Grants / RLS
-- ---------------------------------------------------------------------------
REVOKE ALL ON FUNCTION
  lfhe.assessment_version_state(uuid),
  lfhe.set_assessment_state(uuid, lfhe.assessment_state, lfhe.actor_type, uuid, uuid, text),
  lfhe.p4_run_evidence_eligible(uuid, text, timestamptz, integer),
  lfhe.assessment_version_eligible(uuid, text, timestamptz, integer),
  lfhe.p4_claim_corroborated_asof(uuid, text, timestamptz),
  lfhe.p4_attribution_required(lfhe.assessment_statement_type, uuid[], uuid[], text, timestamptz),
  lfhe.p4_source_epistemic_status(uuid[], text, timestamptz),
  lfhe.assessment_statement_problems(jsonb, jsonb, text, timestamptz, boolean),
  lfhe.p4_single_lineage(jsonb, text, timestamptz),
  lfhe.assessment_extra_problems(jsonb, jsonb, jsonb, jsonb),
  lfhe.write_assessment_version(uuid, jsonb, jsonb, jsonb, jsonb, text, text, text, uuid, uuid, uuid, text, timestamptz),
  lfhe.m07_context(uuid, text, timestamptz),
  lfhe.ingest_assessment(jsonb)
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.ingest_assessment(jsonb) TO lfhe_worker;
GRANT EXECUTE ON FUNCTION lfhe.assessment_version_eligible(uuid, text, timestamptz, integer),
  lfhe.p4_attribution_required(lfhe.assessment_statement_type, uuid[], uuid[], text, timestamptz),
  lfhe.p4_run_evidence_eligible(uuid, text, timestamptz, integer)
  TO lfhe_worker;
GRANT EXECUTE ON FUNCTION lfhe.assessment_version_state(uuid) TO authenticated, lfhe_worker;
REVOKE ALL ON FUNCTION lfhe.statement_category(lfhe.assessment_statement_type), lfhe.p4_text_has(text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION lfhe.statement_category(lfhe.assessment_statement_type), lfhe.p4_text_has(text, text)
  TO authenticated, lfhe_worker;

REVOKE ALL ON lfhe.likelihood_terms, lfhe.assessments, lfhe.assessment_ingestion_results, lfhe.assessment_versions,
  lfhe.assessment_reference_contexts, lfhe.assessment_statements, lfhe.assessment_statement_evidence,
  lfhe.assessment_statement_premises, lfhe.assessment_derived_summaries, lfhe.assessment_indicator_proposals,
  lfhe.assessment_state_history, lfhe.assessment_version_states
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT SELECT ON lfhe.likelihood_terms, lfhe.assessments, lfhe.assessment_ingestion_results, lfhe.assessment_versions,
  lfhe.assessment_reference_contexts, lfhe.assessment_statements, lfhe.assessment_statement_evidence,
  lfhe.assessment_statement_premises, lfhe.assessment_derived_summaries, lfhe.assessment_indicator_proposals,
  lfhe.assessment_state_history, lfhe.assessment_version_states
  TO authenticated, lfhe_worker;
DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['likelihood_terms', 'assessments', 'assessment_ingestion_results', 'assessment_versions',
    'assessment_reference_contexts', 'assessment_statements', 'assessment_statement_evidence',
    'assessment_statement_premises', 'assessment_derived_summaries', 'assessment_indicator_proposals',
    'assessment_state_history'] LOOP
    EXECUTE format('ALTER TABLE lfhe.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY %I ON lfhe.%I FOR SELECT TO authenticated USING (lfhe.has_permission(''CLAIM_READ''))',
                   t || '_read_human', t);
    EXECUTE format('CREATE POLICY %I ON lfhe.%I FOR SELECT TO lfhe_worker USING (true)', t || '_read_worker', t);
  END LOOP;
END $$;
