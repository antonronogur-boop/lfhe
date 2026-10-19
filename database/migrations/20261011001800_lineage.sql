-- ============================================================================
-- P3-01  Claim-level lineage and independence (Phase 3 Addendum v1.0 §2–§4,
--        §12, §14; Prompt Pack v1.2 §13 M04; CG0 data model 6)
--
-- * M04 output is stored as immutable PROPOSALS (lineage_proposals,
--   corroboration_recommendations); nothing M04 returns changes a claim or the
--   authoritative lineage by itself.
-- * Authoritative lineage = lfhe.claim_lineage, written ONLY by humans
--   (CLAIM_REVIEW): accepting a proposal or recording / correcting lineage.
--   Lineage is never deleted; a correction is an append-only retraction.
-- * Relationship types (Addendum §3, closed): COMMON_ORIGINAL_SOURCE,
--   DERIVED_REPORTING. No independence relationship exists: independence is
--   never inferred; unknown stays unknown.
-- * Independence groups are DERIVED (never edited directly): connected
--   components of active, validated lineage (claim–claim, claim–article,
--   claim–external origin). Claims without validated lineage are singleton
--   groups with lineage_known = false. Republication / derived reporting
--   therefore can only REDUCE the count of distinct groups, never add to it.
-- * external_origins only when the claim's own evidence span names the origin
--   verbatim; a URL only if it appears verbatim in the original text.
-- * Cutoff (§12): every claim an M04/M05 run refers to must be eligible under
--   the run's declared report_mode / information_cutoff
--   (lfhe.claim_cutoff_eligible).
-- ============================================================================

CREATE TYPE lfhe.lineage_relationship_type AS ENUM ('COMMON_ORIGINAL_SOURCE', 'DERIVED_REPORTING');
CREATE TYPE lfhe.corroboration_recommendation AS ENUM (
  'NO_CHANGE', 'POTENTIAL_PARTIAL_CORROBORATION', 'POTENTIAL_CORROBORATION',
  'POTENTIAL_SOURCE_DEPENDENCE', 'POTENTIAL_CONTESTED');

INSERT INTO lfhe.audit_event_types (code, spec_source) VALUES
  ('LINEAGE_INGESTION_RECORDED', 'Phase 3 impl.'),
  ('LINEAGE_PROPOSAL_DECIDED', 'Phase 3 impl.'),
  ('CLAIM_LINEAGE_RETRACTED', 'Phase 3 impl.'),
  ('EXTERNAL_ORIGIN_CREATED', 'Phase 3 impl.'),
  ('CORROBORATION_RECOMMENDATION_DECIDED', 'Phase 3 impl.');

-- ---------------------------------------------------------------------------
-- Cutoff eligibility (CG0 §7 / Prompt Pack v1.2 §7; event time never used)
--   LIVE:   retrieved ≤ cutoff AND (availability unknown OR availability ≤ cutoff)
--           (a LIVE retrieval is itself proof of public availability at that time)
--   REPLAY: stated public availability known AND ≤ cutoff
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.claim_cutoff_eligible(p_claim uuid, p_mode text, p_cutoff timestamptz)
RETURNS boolean LANGUAGE sql STABLE SET search_path = pg_catalog, pg_temp AS $$
  SELECT coalesce((
    SELECT CASE p_mode
      WHEN 'LIVE' THEN s.system_retrieval_datetime <= p_cutoff
                       AND (s.public_availability_datetime IS NULL OR s.public_availability_datetime <= p_cutoff)
      WHEN 'REPLAY' THEN s.public_availability_datetime IS NOT NULL AND s.public_availability_datetime <= p_cutoff
      ELSE false END
    FROM lfhe.claims c JOIN lfhe.article_snapshots s ON s.id = c.article_snapshot_id
    WHERE c.id = p_claim), false)
$$;
REVOKE ALL ON FUNCTION lfhe.claim_cutoff_eligible(uuid, text, timestamptz) FROM PUBLIC, anon, service_role, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.claim_cutoff_eligible(uuid, text, timestamptz) TO authenticated, lfhe_worker;

-- The run's declared cutoff (task parameters), validated.
CREATE OR REPLACE FUNCTION lfhe.model_run_cutoff(p_run uuid, OUT report_mode text, OUT information_cutoff timestamptz)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  SELECT r.task_parameters ->> 'report_mode', (r.task_parameters ->> 'information_cutoff')::timestamptz
  INTO report_mode, information_cutoff FROM lfhe.model_runs r WHERE r.id = p_run;
  IF report_mode IS NULL OR report_mode NOT IN ('LIVE', 'REPLAY') OR information_cutoff IS NULL THEN
    RAISE EXCEPTION 'CUTOFF_NOT_DECLARED: model run % must declare report_mode and information_cutoff', p_run
      USING ERRCODE = 'check_violation';
  END IF;
END $$;
REVOKE ALL ON FUNCTION lfhe.model_run_cutoff(uuid) FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;

-- object reference present in a run's input / context manifest
CREATE OR REPLACE FUNCTION lfhe.run_has_object(p_run uuid, p_kind text, p_type text, p_id text)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT coalesce((SELECT CASE p_kind WHEN 'input' THEN r.input_manifest ELSE r.context_manifest END
                   @> pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object('object_type', p_type, 'object_id', p_id))
                   FROM lfhe.model_runs r WHERE r.id = p_run), false)
$$;
REVOKE ALL ON FUNCTION lfhe.run_has_object(uuid, text, text, text) FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;

-- ---------------------------------------------------------------------------
-- External origins (human-created; evidence-bound)
-- ---------------------------------------------------------------------------
CREATE TABLE lfhe.external_origins (
  id                 uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  name               text NOT NULL CHECK (length(btrim(name)) BETWEEN 2 AND 300),
  url                text,
  evidence_claim_id  uuid NOT NULL REFERENCES lfhe.claims(id),
  created_by         uuid NOT NULL,
  reason             text NOT NULL CHECK (length(btrim(reason)) >= 5),
  created_at         timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT external_origin_url_canonical CHECK (url IS NULL OR (lfhe.is_canonical_http_url(url)
                                                  AND cardinality(lfhe.url_credential_problems(url)) = 0))
);

CREATE OR REPLACE FUNCTION lfhe.external_origin_evidence_problems(p_claim uuid, p_name text, p_url text)
RETURNS text[] LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_span text;
  v_text text;
  v_out  text[] := '{}';
BEGIN
  SELECT c.span_exact_text, t.text_content INTO v_span, v_text
  FROM lfhe.claims c JOIN lfhe.text_representations t ON t.id = c.text_representation_id WHERE c.id = p_claim;
  IF v_span IS NULL THEN
    RETURN ARRAY['EVIDENCE_CLAIM_NOT_FOUND'];
  END IF;
  IF p_name IS NULL OR pg_catalog.strpos(v_span, p_name) = 0 THEN
    v_out := v_out || 'EXTERNAL_ORIGIN_NOT_EVIDENCED'::text;
  END IF;
  IF p_url IS NOT NULL AND pg_catalog.strpos(v_text, p_url) = 0 THEN
    v_out := v_out || 'EXTERNAL_ORIGIN_URL_NOT_IN_SOURCE'::text;
  END IF;
  RETURN v_out;
END $$;
REVOKE ALL ON FUNCTION lfhe.external_origin_evidence_problems(uuid, text, text) FROM PUBLIC, anon, authenticated, service_role, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.external_origin_evidence_problems(uuid, text, text) TO lfhe_worker;

CREATE OR REPLACE FUNCTION lfhe.external_origins_guard()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_problems text[] := lfhe.external_origin_evidence_problems(NEW.evidence_claim_id, NEW.name, NEW.url);
BEGIN
  IF cardinality(v_problems) > 0 THEN
    RAISE EXCEPTION 'EXTERNAL_ORIGIN_INVALID: %', pg_catalog.array_to_string(v_problems, ', ')
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION lfhe.external_origins_guard() FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
CREATE TRIGGER external_origins_guard BEFORE INSERT ON lfhe.external_origins
  FOR EACH ROW EXECUTE FUNCTION lfhe.external_origins_guard();
CREATE TRIGGER external_origins_immutable BEFORE UPDATE OR DELETE ON lfhe.external_origins
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();
CREATE TRIGGER external_origins_audit AFTER INSERT ON lfhe.external_origins
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_row_change('EXTERNAL_ORIGIN_CREATED', '-', '-', 'external_origin');

-- ---------------------------------------------------------------------------
-- M04 ingestion results, proposals, recommendations (immutable)
-- ---------------------------------------------------------------------------
CREATE TABLE lfhe.lineage_ingestion_results (
  model_run_id           uuid PRIMARY KEY REFERENCES lfhe.model_runs(id),
  id                     uuid NOT NULL UNIQUE DEFAULT pg_catalog.gen_random_uuid(),
  model_run_status       lfhe.model_run_status NOT NULL,
  output_status          text,
  outcome                text NOT NULL CHECK (outcome IN ('PROPOSALS_RECORDED', 'NO_PROPOSALS',
                           'INSUFFICIENT_INFORMATION', 'HUMAN_REVIEW_REQUIRED', 'OUTPUT_REJECTED',
                           'SCHEMA_VALIDATION_FAILED', 'PROVIDER_ERROR')),
  report_mode            text,
  information_cutoff     timestamptz,
  proposals_recorded     integer NOT NULL DEFAULT 0,
  recommendations_recorded integer NOT NULL DEFAULT 0,
  rejection_reasons      text[] NOT NULL DEFAULT '{}',
  human_review_required  boolean NOT NULL,
  warnings               jsonb NOT NULL DEFAULT '[]'::jsonb,
  repair_of_model_run_id uuid REFERENCES lfhe.model_runs(id),
  created_at             timestamptz NOT NULL DEFAULT now(),
  CHECK ((outcome = 'OUTPUT_REJECTED') = (cardinality(rejection_reasons) > 0)),
  CHECK (outcome <> 'OUTPUT_REJECTED' OR (proposals_recorded = 0 AND recommendations_recorded = 0))
);

CREATE TABLE lfhe.lineage_proposals (
  id                     uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  model_run_id           uuid NOT NULL REFERENCES lfhe.lineage_ingestion_results(model_run_id),
  proposal_index         integer NOT NULL,
  child_claim_id         uuid NOT NULL REFERENCES lfhe.claims(id),
  relationship_type      lfhe.lineage_relationship_type NOT NULL,
  parent_claim_id        uuid REFERENCES lfhe.claims(id),
  parent_article_id      uuid REFERENCES lfhe.articles(id),
  external_origin_name   text,
  external_origin_url    text,
  -- M04 output field "confidence" (proposal confidence; NOT analytic confidence)
  proposal_confidence    lfhe.assignment_confidence NOT NULL,
  explanation            text NOT NULL CHECK (length(explanation) BETWEEN 1 AND 2000),
  human_review_required  boolean NOT NULL DEFAULT true,
  created_at             timestamptz NOT NULL DEFAULT now(),
  UNIQUE (model_run_id, proposal_index),
  CHECK (num_nonnulls(parent_claim_id, parent_article_id, external_origin_name) = 1),
  CHECK (external_origin_url IS NULL OR external_origin_name IS NOT NULL),
  CHECK (parent_claim_id IS DISTINCT FROM child_claim_id),
  CHECK (human_review_required)
);

CREATE TABLE lfhe.corroboration_recommendations (
  id                     uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  model_run_id           uuid NOT NULL REFERENCES lfhe.lineage_ingestion_results(model_run_id),
  claim_id               uuid NOT NULL REFERENCES lfhe.claims(id),
  recommendation         lfhe.corroboration_recommendation NOT NULL,
  recommended_status     lfhe.claim_status,
  supporting_claim_ids   uuid[] NOT NULL DEFAULT '{}',
  explanation            text NOT NULL CHECK (length(explanation) BETWEEN 1 AND 2000),
  high_impact_at_recommendation boolean NOT NULL,
  human_review_required  boolean NOT NULL,
  created_at             timestamptz NOT NULL DEFAULT now(),
  UNIQUE (model_run_id, claim_id),
  CHECK (NOT high_impact_at_recommendation OR human_review_required)
);

CREATE TRIGGER lineage_ingestion_results_immutable BEFORE UPDATE OR DELETE ON lfhe.lineage_ingestion_results
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();
CREATE TRIGGER lineage_proposals_immutable BEFORE UPDATE OR DELETE ON lfhe.lineage_proposals
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();
CREATE TRIGGER corroboration_recommendations_immutable BEFORE UPDATE OR DELETE ON lfhe.corroboration_recommendations
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();
CREATE TRIGGER lineage_ingestion_results_audit AFTER INSERT ON lfhe.lineage_ingestion_results
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_row_change('LINEAGE_INGESTION_RECORDED', '-', '-', 'lineage_ingestion_result');
CREATE TRIGGER lineage_proposals_audit AFTER INSERT ON lfhe.lineage_proposals
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_row_change('LINEAGE_RECOMMENDATION_CREATED', '-', '-', 'lineage_proposal');
CREATE TRIGGER corroboration_recommendations_audit AFTER INSERT ON lfhe.corroboration_recommendations
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_row_change('LINEAGE_RECOMMENDATION_CREATED', '-', '-', 'corroboration_recommendation');

-- ---------------------------------------------------------------------------
-- Authoritative lineage (human only, append-only)
-- ---------------------------------------------------------------------------
CREATE TABLE lfhe.claim_lineage (
  seq                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id                  uuid NOT NULL UNIQUE DEFAULT pg_catalog.gen_random_uuid(),
  child_claim_id      uuid NOT NULL REFERENCES lfhe.claims(id),
  relationship_type   lfhe.lineage_relationship_type NOT NULL,
  parent_claim_id     uuid REFERENCES lfhe.claims(id),
  parent_article_id   uuid REFERENCES lfhe.articles(id),
  external_origin_id  uuid REFERENCES lfhe.external_origins(id),
  basis               text NOT NULL CHECK (basis IN ('PROPOSAL_ACCEPTED', 'HUMAN_RECORDED')),
  proposal_id         uuid REFERENCES lfhe.lineage_proposals(id),
  actor_user_id       uuid NOT NULL,
  reason              text NOT NULL CHECK (length(btrim(reason)) >= 5),
  created_at          timestamptz NOT NULL DEFAULT now(),
  CHECK (num_nonnulls(parent_claim_id, parent_article_id, external_origin_id) = 1),
  CHECK (parent_claim_id IS DISTINCT FROM child_claim_id),
  CHECK ((basis = 'PROPOSAL_ACCEPTED') = (proposal_id IS NOT NULL))
);
CREATE INDEX claim_lineage_child_idx ON lfhe.claim_lineage (child_claim_id);

CREATE TABLE lfhe.claim_lineage_retractions (
  lineage_id     uuid PRIMARY KEY REFERENCES lfhe.claim_lineage(id),
  id             uuid NOT NULL UNIQUE DEFAULT pg_catalog.gen_random_uuid(),
  actor_user_id  uuid NOT NULL,
  reason         text NOT NULL CHECK (length(btrim(reason)) >= 5),
  created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE lfhe.lineage_proposal_decisions (
  proposal_id    uuid PRIMARY KEY REFERENCES lfhe.lineage_proposals(id),
  id             uuid NOT NULL UNIQUE DEFAULT pg_catalog.gen_random_uuid(),
  decision       text NOT NULL CHECK (decision IN ('ACCEPTED', 'REJECTED')),
  lineage_id     uuid REFERENCES lfhe.claim_lineage(id),
  actor_user_id  uuid NOT NULL,
  reason         text NOT NULL CHECK (length(btrim(reason)) >= 5),
  created_at     timestamptz NOT NULL DEFAULT now(),
  CHECK ((decision = 'ACCEPTED') = (lineage_id IS NOT NULL))
);

CREATE TABLE lfhe.corroboration_recommendation_decisions (
  recommendation_id uuid PRIMARY KEY REFERENCES lfhe.corroboration_recommendations(id),
  id                uuid NOT NULL UNIQUE DEFAULT pg_catalog.gen_random_uuid(),
  decision          text NOT NULL CHECK (decision IN ('ACCEPTED', 'DECLINED')),
  status_history_id uuid REFERENCES lfhe.claim_status_history(id),
  actor_user_id     uuid NOT NULL,
  reason            text NOT NULL CHECK (length(btrim(reason)) >= 5),
  created_at        timestamptz NOT NULL DEFAULT now(),
  CHECK ((decision = 'ACCEPTED') = (status_history_id IS NOT NULL))
);

CREATE TRIGGER claim_lineage_append_only BEFORE UPDATE OR DELETE ON lfhe.claim_lineage
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();
CREATE TRIGGER claim_lineage_retractions_append_only BEFORE UPDATE OR DELETE ON lfhe.claim_lineage_retractions
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();
CREATE TRIGGER lineage_proposal_decisions_append_only BEFORE UPDATE OR DELETE ON lfhe.lineage_proposal_decisions
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();
CREATE TRIGGER corroboration_recommendation_decisions_append_only BEFORE UPDATE OR DELETE ON lfhe.corroboration_recommendation_decisions
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();

CREATE OR REPLACE FUNCTION lfhe.audit_claim_lineage()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  IF TG_TABLE_NAME = 'claim_lineage' THEN
    PERFORM lfhe.write_audit('LINEAGE_VALIDATED', 'claim_lineage', NEW.id::text, NULL, pg_catalog.to_jsonb(NEW), '{}'::jsonb);
    PERFORM lfhe.write_audit('INDEPENDENCE_GROUP_CHANGED', 'claim', NEW.child_claim_id::text, NULL, NULL,
      pg_catalog.jsonb_build_object('cause', 'LINEAGE_ADDED', 'claim_lineage_id', NEW.id));
  ELSE
    PERFORM lfhe.write_audit('CLAIM_LINEAGE_RETRACTED', 'claim_lineage', NEW.lineage_id::text, NULL, pg_catalog.to_jsonb(NEW), '{}'::jsonb);
    PERFORM lfhe.write_audit('INDEPENDENCE_GROUP_CHANGED', 'claim_lineage', NEW.lineage_id::text, NULL, NULL,
      pg_catalog.jsonb_build_object('cause', 'LINEAGE_RETRACTED'));
  END IF;
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION lfhe.audit_claim_lineage() FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
CREATE TRIGGER claim_lineage_audit AFTER INSERT ON lfhe.claim_lineage
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_claim_lineage();
CREATE TRIGGER claim_lineage_retractions_audit AFTER INSERT ON lfhe.claim_lineage_retractions
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_claim_lineage();
CREATE TRIGGER lineage_proposal_decisions_audit AFTER INSERT ON lfhe.lineage_proposal_decisions
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_row_change('LINEAGE_PROPOSAL_DECIDED', '-', '-', 'lineage_proposal_decision');
CREATE TRIGGER corroboration_recommendation_decisions_audit AFTER INSERT ON lfhe.corroboration_recommendation_decisions
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_row_change('CORROBORATION_RECOMMENDATION_DECIDED', '-', '-', 'corroboration_recommendation_decision');

-- ---------------------------------------------------------------------------
-- Derived independence (never edited directly)
-- ---------------------------------------------------------------------------
CREATE VIEW lfhe.active_claim_lineage WITH (security_invoker = true) AS
SELECT l.* FROM lfhe.claim_lineage l
WHERE NOT EXISTS (SELECT 1 FROM lfhe.claim_lineage_retractions r WHERE r.lineage_id = l.id);

-- Graph nodes: 'c:'||claim, 'a:'||article, 'o:'||origin. Edges from active lineage.
-- Component label = least node key reachable (deterministic).
CREATE OR REPLACE FUNCTION lfhe.claim_independence_group(p_claim uuid)
RETURNS TABLE (claim_id uuid, independence_group text, lineage_known boolean)
LANGUAGE sql STABLE SET search_path = pg_catalog, pg_temp AS $$
  WITH RECURSIVE edges AS (
    SELECT 'c:' || l.child_claim_id AS a,
           CASE WHEN l.parent_claim_id IS NOT NULL THEN 'c:' || l.parent_claim_id
                WHEN l.parent_article_id IS NOT NULL THEN 'a:' || l.parent_article_id
                ELSE 'o:' || l.external_origin_id END AS b
    FROM lfhe.claim_lineage l
    WHERE NOT EXISTS (SELECT 1 FROM lfhe.claim_lineage_retractions r WHERE r.lineage_id = l.id)
  ), undirected AS (
    SELECT a, b FROM edges UNION SELECT b, a FROM edges
  ), reach(node) AS (
    SELECT 'c:' || p_claim
    UNION
    SELECT u.b FROM reach JOIN undirected u ON u.a = reach.node
  )
  SELECT p_claim, (SELECT min(node COLLATE "C") FROM reach),
         EXISTS (SELECT 1 FROM edges e WHERE e.a = 'c:' || p_claim OR e.b = 'c:' || p_claim)
$$;
REVOKE ALL ON FUNCTION lfhe.claim_independence_group(uuid) FROM PUBLIC, anon, service_role, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.claim_independence_group(uuid) TO authenticated, lfhe_worker;

-- Summary for a set of claims that report the same assertion/event.
-- distinct_groups_upper_bound: claims sharing validated lineage collapse to one
-- group; claims with no validated lineage are counted separately but their
-- independence is UNKNOWN (never established by AI or by surface differences).
CREATE OR REPLACE FUNCTION lfhe.independence_summary(p_claims uuid[])
RETURNS jsonb LANGUAGE sql STABLE SET search_path = pg_catalog, pg_temp AS $$
  WITH g AS (SELECT (lfhe.claim_independence_group(c)).* FROM pg_catalog.unnest(p_claims) c)
  SELECT pg_catalog.jsonb_build_object(
    'claims', (SELECT count(*) FROM g),
    'distinct_groups_upper_bound', (SELECT count(DISTINCT independence_group) FROM g),
    'claims_with_validated_lineage', (SELECT count(*) FROM g WHERE lineage_known),
    'claims_with_unknown_lineage', (SELECT count(*) FROM g WHERE NOT lineage_known),
    'independence_established', false,
    'basis', 'VALIDATED_LINEAGE_DEPENDENCE_ONLY')
$$;
REVOKE ALL ON FUNCTION lfhe.independence_summary(uuid[]) FROM PUBLIC, anon, service_role, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.independence_summary(uuid[]) TO authenticated, lfhe_worker;

-- ---------------------------------------------------------------------------
-- Worker: M04 ingestion (fail closed: any invalid item rejects the output)
-- p: {model_run_id, output_status, human_review_required, warnings[], repair_of_model_run_id,
--     claim_relationships:[{child_claim_id, relationship_type, parent_claim_id, parent_article_id,
--        external_origin_name, external_origin_url, confidence, explanation}],
--     corroboration_recommendations:[{claim_id, recommendation, recommended_status,
--        supporting_claim_ids[], explanation}]}
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.ingest_lineage(p jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_run     lfhe.model_runs%ROWTYPE;
  v_mode    text;
  v_cutoff  timestamptz;
  v_reasons text[] := '{}';
  v_x       jsonb;
  v_c       text;
  v_i       integer := 0;
  v_np      integer;
  v_nr      integer;
  v_outcome text;
  v_status  text := p ->> 'output_status';
  v_uuid    constant text := '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$';
BEGIN
  SELECT * INTO v_run FROM lfhe.model_runs WHERE id = (p ->> 'model_run_id')::uuid;
  IF NOT FOUND OR v_run.module_code <> 'M04_LINEAGE' OR v_run.status = 'RUNNING' THEN
    RAISE EXCEPTION 'model run % is not a finished M04_LINEAGE run', p ->> 'model_run_id'
      USING ERRCODE = 'object_not_in_prerequisite_state';
  END IF;
  SELECT * INTO v_mode, v_cutoff FROM lfhe.model_run_cutoff(v_run.id);
  IF v_run.status <> 'SUCCEEDED' THEN
    INSERT INTO lfhe.lineage_ingestion_results (model_run_id, model_run_status, outcome, report_mode,
      information_cutoff, human_review_required, repair_of_model_run_id)
    VALUES (v_run.id, v_run.status, v_run.status::text, v_mode, v_cutoff, false, (p ->> 'repair_of_model_run_id')::uuid);
    RETURN pg_catalog.jsonb_build_object('outcome', v_run.status::text);
  END IF;

  -- validate every referenced object
  FOR v_x IN SELECT * FROM pg_catalog.jsonb_array_elements(coalesce(p -> 'claim_relationships', '[]')) LOOP
    FOREACH v_c IN ARRAY ARRAY[v_x ->> 'child_claim_id', v_x ->> 'parent_claim_id'] LOOP
      CONTINUE WHEN v_c IS NULL;
      IF v_c !~ v_uuid OR NOT lfhe.run_has_object(v_run.id, 'input', 'claim', v_c) THEN
        v_reasons := v_reasons || ('CLAIM_NOT_IN_MODEL_RUN_INPUT:' || left(v_c, 80));
      ELSIF NOT lfhe.claim_cutoff_eligible(v_c::uuid, v_mode, v_cutoff) THEN
        v_reasons := v_reasons || ('CLAIM_NOT_CUTOFF_ELIGIBLE:' || v_c);
      END IF;
    END LOOP;
    IF num_nonnulls(v_x ->> 'parent_claim_id', v_x ->> 'parent_article_id', v_x ->> 'external_origin_name') <> 1 THEN
      v_reasons := v_reasons || 'EXACTLY_ONE_PARENT_REQUIRED'::text;
    END IF;
    IF v_x ->> 'parent_claim_id' = v_x ->> 'child_claim_id' THEN
      v_reasons := v_reasons || 'SELF_LINEAGE'::text;
    END IF;
    IF v_x ->> 'relationship_type' IS NULL
       OR v_x ->> 'relationship_type' NOT IN ('COMMON_ORIGINAL_SOURCE', 'DERIVED_REPORTING') THEN
      v_reasons := v_reasons || ('RELATIONSHIP_TYPE_NOT_ALLOWED:' || left(coalesce(v_x ->> 'relationship_type', 'null'), 60));
    END IF;
    IF v_x ->> 'parent_article_id' IS NOT NULL AND (v_x ->> 'parent_article_id' !~ v_uuid
       OR NOT lfhe.run_has_object(v_run.id, 'input', 'article', v_x ->> 'parent_article_id')) THEN
      v_reasons := v_reasons || ('ARTICLE_NOT_IN_MODEL_RUN_INPUT:' || left(v_x ->> 'parent_article_id', 80));
    END IF;
    IF v_x ->> 'external_origin_name' IS NOT NULL AND (v_x ->> 'child_claim_id') ~ v_uuid THEN
      v_reasons := v_reasons || lfhe.external_origin_evidence_problems((v_x ->> 'child_claim_id')::uuid,
                                  v_x ->> 'external_origin_name', v_x ->> 'external_origin_url');
    ELSIF v_x ->> 'external_origin_url' IS NOT NULL THEN
      v_reasons := v_reasons || 'EXTERNAL_ORIGIN_URL_WITHOUT_NAME'::text;
    END IF;
  END LOOP;
  FOR v_x IN SELECT * FROM pg_catalog.jsonb_array_elements(coalesce(p -> 'corroboration_recommendations', '[]')) LOOP
    FOR v_c IN SELECT coalesce(v_x ->> 'claim_id', 'null') UNION ALL
               SELECT pg_catalog.jsonb_array_elements_text(coalesce(v_x -> 'supporting_claim_ids', '[]')) LOOP
      IF v_c !~ v_uuid OR NOT lfhe.run_has_object(v_run.id, 'input', 'claim', v_c) THEN
        v_reasons := v_reasons || ('CLAIM_NOT_IN_MODEL_RUN_INPUT:' || left(v_c, 80));
      ELSIF NOT lfhe.claim_cutoff_eligible(v_c::uuid, v_mode, v_cutoff) THEN
        v_reasons := v_reasons || ('CLAIM_NOT_CUTOFF_ELIGIBLE:' || v_c);
      END IF;
    END LOOP;
  END LOOP;

  v_np := pg_catalog.jsonb_array_length(coalesce(p -> 'claim_relationships', '[]'));
  v_nr := pg_catalog.jsonb_array_length(coalesce(p -> 'corroboration_recommendations', '[]'));
  v_reasons := ARRAY(SELECT DISTINCT r FROM pg_catalog.unnest(v_reasons) r ORDER BY r);
  v_outcome := CASE
    WHEN cardinality(v_reasons) > 0 THEN 'OUTPUT_REJECTED'
    WHEN v_np + v_nr > 0 THEN 'PROPOSALS_RECORDED'
    WHEN v_status = 'INSUFFICIENT_INFORMATION' THEN 'INSUFFICIENT_INFORMATION'
    WHEN v_status = 'HUMAN_REVIEW_REQUIRED' THEN 'HUMAN_REVIEW_REQUIRED'
    ELSE 'NO_PROPOSALS' END;

  INSERT INTO lfhe.lineage_ingestion_results (model_run_id, model_run_status, output_status, outcome, report_mode,
    information_cutoff, proposals_recorded, recommendations_recorded, rejection_reasons, human_review_required,
    warnings, repair_of_model_run_id)
  VALUES (v_run.id, v_run.status, v_status, v_outcome, v_mode, v_cutoff,
    CASE WHEN v_outcome = 'PROPOSALS_RECORDED' THEN v_np ELSE 0 END,
    CASE WHEN v_outcome = 'PROPOSALS_RECORDED' THEN v_nr ELSE 0 END, v_reasons,
    coalesce((p ->> 'human_review_required')::boolean, false) OR v_outcome IN ('OUTPUT_REJECTED', 'HUMAN_REVIEW_REQUIRED'),
    coalesce(p -> 'warnings', '[]'), (p ->> 'repair_of_model_run_id')::uuid);
  IF v_outcome <> 'PROPOSALS_RECORDED' THEN
    RETURN pg_catalog.jsonb_build_object('outcome', v_outcome, 'rejection_reasons', pg_catalog.to_jsonb(v_reasons));
  END IF;

  FOR v_x IN SELECT * FROM pg_catalog.jsonb_array_elements(coalesce(p -> 'claim_relationships', '[]')) LOOP
    INSERT INTO lfhe.lineage_proposals (model_run_id, proposal_index, child_claim_id, relationship_type,
      parent_claim_id, parent_article_id, external_origin_name, external_origin_url, proposal_confidence, explanation)
    VALUES (v_run.id, v_i, (v_x ->> 'child_claim_id')::uuid, (v_x ->> 'relationship_type')::lfhe.lineage_relationship_type,
      (v_x ->> 'parent_claim_id')::uuid, (v_x ->> 'parent_article_id')::uuid, v_x ->> 'external_origin_name',
      v_x ->> 'external_origin_url', (v_x ->> 'confidence')::lfhe.assignment_confidence,
      coalesce(nullif(v_x ->> 'explanation', ''), 'no explanation given'));
    v_i := v_i + 1;
  END LOOP;
  FOR v_x IN SELECT * FROM pg_catalog.jsonb_array_elements(coalesce(p -> 'corroboration_recommendations', '[]')) LOOP
    INSERT INTO lfhe.corroboration_recommendations (model_run_id, claim_id, recommendation, recommended_status,
      supporting_claim_ids, explanation, high_impact_at_recommendation, human_review_required)
    VALUES (v_run.id, (v_x ->> 'claim_id')::uuid, (v_x ->> 'recommendation')::lfhe.corroboration_recommendation,
      (v_x ->> 'recommended_status')::lfhe.claim_status,
      ARRAY(SELECT pg_catalog.jsonb_array_elements_text(coalesce(v_x -> 'supporting_claim_ids', '[]'))::uuid),
      coalesce(nullif(v_x ->> 'explanation', ''), 'no explanation given'),
      lfhe.claim_is_high_impact((v_x ->> 'claim_id')::uuid), true);
  END LOOP;
  RETURN pg_catalog.jsonb_build_object('outcome', v_outcome, 'proposals', v_np, 'recommendations', v_nr);
END $$;
REVOKE ALL ON FUNCTION lfhe.ingest_lineage(jsonb) FROM PUBLIC, anon, authenticated, service_role, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.ingest_lineage(jsonb) TO lfhe_worker;

-- ---------------------------------------------------------------------------
-- HUMAN_ONLY (CLAIM_REVIEW)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.insert_claim_lineage(
  p_child uuid, p_type lfhe.lineage_relationship_type, p_parent_claim uuid, p_parent_article uuid,
  p_origin uuid, p_basis text, p_proposal uuid, p_actor uuid, p_reason text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_id uuid;
BEGIN
  IF EXISTS (SELECT 1 FROM lfhe.active_claim_lineage l WHERE l.child_claim_id = p_child AND l.relationship_type = p_type
             AND l.parent_claim_id IS NOT DISTINCT FROM p_parent_claim
             AND l.parent_article_id IS NOT DISTINCT FROM p_parent_article
             AND l.external_origin_id IS NOT DISTINCT FROM p_origin) THEN
    RAISE EXCEPTION 'LINEAGE_ALREADY_RECORDED' USING ERRCODE = 'unique_violation';
  END IF;
  INSERT INTO lfhe.claim_lineage (child_claim_id, relationship_type, parent_claim_id, parent_article_id,
    external_origin_id, basis, proposal_id, actor_user_id, reason)
  VALUES (p_child, p_type, p_parent_claim, p_parent_article, p_origin, p_basis, p_proposal, p_actor, p_reason)
  RETURNING id INTO v_id;
  RETURN v_id;
END $$;
REVOKE ALL ON FUNCTION lfhe.insert_claim_lineage(uuid, lfhe.lineage_relationship_type, uuid, uuid, uuid, text, uuid, uuid, text)
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;

CREATE OR REPLACE FUNCTION lfhe.decide_lineage_proposal(p_proposal_id uuid, p_accept boolean, p_reason text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor  uuid := lfhe.require_human_permission('CLAIM_REVIEW');
  v_p      lfhe.lineage_proposals%ROWTYPE;
  v_origin uuid;
  v_lin    uuid;
BEGIN
  IF p_reason IS NULL OR length(btrim(p_reason)) < 5 THEN
    RAISE EXCEPTION 'a reason is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  SELECT * INTO v_p FROM lfhe.lineage_proposals WHERE id = p_proposal_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'unknown lineage proposal %', p_proposal_id USING ERRCODE = 'no_data_found';
  END IF;
  IF p_accept THEN
    IF v_p.external_origin_name IS NOT NULL THEN
      INSERT INTO lfhe.external_origins (name, url, evidence_claim_id, created_by, reason)
      VALUES (v_p.external_origin_name, v_p.external_origin_url, v_p.child_claim_id, v_actor, p_reason)
      RETURNING id INTO v_origin;
    END IF;
    v_lin := lfhe.insert_claim_lineage(v_p.child_claim_id, v_p.relationship_type, v_p.parent_claim_id,
      v_p.parent_article_id, v_origin, 'PROPOSAL_ACCEPTED', v_p.id, v_actor, p_reason);
  END IF;
  INSERT INTO lfhe.lineage_proposal_decisions (proposal_id, decision, lineage_id, actor_user_id, reason)
  VALUES (p_proposal_id, CASE WHEN p_accept THEN 'ACCEPTED' ELSE 'REJECTED' END, v_lin, v_actor, p_reason);
  RETURN v_lin;
END $$;
COMMENT ON FUNCTION lfhe.decide_lineage_proposal(uuid, boolean, text) IS 'HUMAN_ONLY';

-- Human recording / correction. p: {child_claim_id, relationship_type, parent_claim_id |
-- parent_article_id | external_origin_id | external_origin:{name, url, evidence_claim_id}}
CREATE OR REPLACE FUNCTION lfhe.record_claim_lineage(p jsonb, p_reason text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor  uuid := lfhe.require_human_permission('CLAIM_REVIEW');
  v_origin uuid := (p ->> 'external_origin_id')::uuid;
BEGIN
  IF p_reason IS NULL OR length(btrim(p_reason)) < 5 THEN
    RAISE EXCEPTION 'a reason is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  IF p ? 'external_origin' THEN
    INSERT INTO lfhe.external_origins (name, url, evidence_claim_id, created_by, reason)
    VALUES (p -> 'external_origin' ->> 'name', p -> 'external_origin' ->> 'url',
            coalesce((p -> 'external_origin' ->> 'evidence_claim_id')::uuid, (p ->> 'child_claim_id')::uuid),
            v_actor, p_reason)
    RETURNING id INTO v_origin;
  END IF;
  RETURN lfhe.insert_claim_lineage((p ->> 'child_claim_id')::uuid,
    (p ->> 'relationship_type')::lfhe.lineage_relationship_type, (p ->> 'parent_claim_id')::uuid,
    (p ->> 'parent_article_id')::uuid, v_origin, 'HUMAN_RECORDED', NULL, v_actor, p_reason);
END $$;
COMMENT ON FUNCTION lfhe.record_claim_lineage(jsonb, text) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.retract_claim_lineage(p_lineage_id uuid, p_reason text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('CLAIM_REVIEW');
BEGIN
  IF p_reason IS NULL OR length(btrim(p_reason)) < 5 THEN
    RAISE EXCEPTION 'a reason is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  INSERT INTO lfhe.claim_lineage_retractions (lineage_id, actor_user_id, reason) VALUES (p_lineage_id, v_actor, p_reason);
END $$;
COMMENT ON FUNCTION lfhe.retract_claim_lineage(uuid, text) IS 'HUMAN_ONLY';

-- Accepting a recommendation = a human status decision (bound to the expected
-- current status and to the recommending model run). Declining changes nothing.
CREATE OR REPLACE FUNCTION lfhe.decide_corroboration_recommendation(
  p_recommendation_id uuid, p_accept boolean, p_expected_current_status lfhe.claim_status,
  p_new_status lfhe.claim_status, p_reason text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('CLAIM_REVIEW');
  v_rec   lfhe.corroboration_recommendations%ROWTYPE;
  v_cur   lfhe.claim_status_history;
  v_hist  uuid;
BEGIN
  IF p_reason IS NULL OR length(btrim(p_reason)) < 5 THEN
    RAISE EXCEPTION 'a reason is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  SELECT * INTO v_rec FROM lfhe.corroboration_recommendations WHERE id = p_recommendation_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'unknown recommendation %', p_recommendation_id USING ERRCODE = 'no_data_found';
  END IF;
  IF p_accept THEN
    PERFORM 1 FROM lfhe.claims WHERE id = v_rec.claim_id FOR UPDATE;
    v_cur := lfhe.claim_current_status(v_rec.claim_id);
    IF v_cur.new_status IS DISTINCT FROM p_expected_current_status THEN
      RAISE EXCEPTION 'STATUS_STALE: claim status is %, not %', v_cur.new_status, p_expected_current_status
        USING ERRCODE = 'serialization_failure';
    END IF;
    IF p_new_status IS NULL OR p_new_status = v_cur.new_status THEN
      RAISE EXCEPTION 'accepting a recommendation requires a different new status' USING ERRCODE = 'invalid_parameter_value';
    END IF;
    INSERT INTO lfhe.claim_status_history (claim_id, old_status, new_status, basis, actor_type, actor_user_id,
      recommending_model_run_id, high_impact_at_change, reason)
    VALUES (v_rec.claim_id, v_cur.new_status, p_new_status, 'HUMAN_DECISION', 'HUMAN', v_actor, v_rec.model_run_id,
      lfhe.claim_is_high_impact(v_rec.claim_id), p_reason)
    RETURNING id INTO v_hist;
  END IF;
  INSERT INTO lfhe.corroboration_recommendation_decisions (recommendation_id, decision, status_history_id,
    actor_user_id, reason)
  VALUES (p_recommendation_id, CASE WHEN p_accept THEN 'ACCEPTED' ELSE 'DECLINED' END, v_hist, v_actor, p_reason);
  RETURN v_hist;
END $$;
COMMENT ON FUNCTION lfhe.decide_corroboration_recommendation(uuid, boolean, lfhe.claim_status, lfhe.claim_status, text) IS 'HUMAN_ONLY';

REVOKE ALL ON FUNCTION
  lfhe.decide_lineage_proposal(uuid, boolean, text),
  lfhe.record_claim_lineage(jsonb, text),
  lfhe.retract_claim_lineage(uuid, text),
  lfhe.decide_corroboration_recommendation(uuid, boolean, lfhe.claim_status, lfhe.claim_status, text)
  FROM PUBLIC, anon, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION
  lfhe.decide_lineage_proposal(uuid, boolean, text),
  lfhe.record_claim_lineage(jsonb, text),
  lfhe.retract_claim_lineage(uuid, text),
  lfhe.decide_corroboration_recommendation(uuid, boolean, lfhe.claim_status, lfhe.claim_status, text)
  TO authenticated;

-- ---------------------------------------------------------------------------
-- Read access
-- ---------------------------------------------------------------------------
REVOKE ALL ON lfhe.external_origins, lfhe.lineage_ingestion_results, lfhe.lineage_proposals,
  lfhe.corroboration_recommendations, lfhe.claim_lineage, lfhe.claim_lineage_retractions,
  lfhe.lineage_proposal_decisions, lfhe.corroboration_recommendation_decisions, lfhe.active_claim_lineage
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT SELECT ON lfhe.external_origins, lfhe.lineage_ingestion_results, lfhe.lineage_proposals,
  lfhe.corroboration_recommendations, lfhe.claim_lineage, lfhe.claim_lineage_retractions,
  lfhe.lineage_proposal_decisions, lfhe.corroboration_recommendation_decisions, lfhe.active_claim_lineage
  TO authenticated, lfhe_worker;
DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['external_origins', 'lineage_ingestion_results', 'lineage_proposals',
    'corroboration_recommendations', 'claim_lineage', 'claim_lineage_retractions',
    'lineage_proposal_decisions', 'corroboration_recommendation_decisions'] LOOP
    EXECUTE format('ALTER TABLE lfhe.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY %I ON lfhe.%I FOR SELECT TO authenticated USING (lfhe.has_permission(''CLAIM_READ''))',
                   t || '_read_human', t);
    EXECUTE format('CREATE POLICY %I ON lfhe.%I FOR SELECT TO lfhe_worker USING (true)', t || '_read_worker', t);
  END LOOP;
END $$;
