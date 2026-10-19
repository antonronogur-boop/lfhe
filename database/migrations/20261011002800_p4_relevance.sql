-- LFHÉ Phase 4 (P4-02) — M06 Relevance Analyst: persistence, deterministic
-- ingestion, human validation / override / promotion / manual assessment request.
-- Baseline: Phase 4 Addendum §3, §4 (incl. 4.1 gatekeeper control, 4.2 PIR-07),
-- §19, §21, §22; Prompt Pack v1.2 §15 (scores, formula, safeguard), §56.
--
-- * The subject is an exact event_version (id + content_hash) eligible for the run's
--   (report_mode, information_cutoff) under the CLOSED Phase 3 as-of rules.
-- * priority_score (= relevance_score) is computed deterministically from the
--   Prompt Pack formula (0.25 MS + 0.20 NC + 0.25 HU/NATO + 0.20 SR + 0.10 TS);
--   the model supplies only the five 0–5 sub-scores.
-- * DS-38 recommendation threshold: not present in the repository → NO numeric
--   threshold is applied; automatic_assessment_recommended is advisory only (§4.1).
-- * M06 never hides, deletes or excludes: there is no write path that removes or
--   filters an event; lfhe.event_relevance_queue lists every event.
-- * PIR-07 (§4.2): whenever an assessment is recommended or PIR_07 is applied, the
--   output must either establish HU/NATO relevance concretely (≥1 dimension, ≥1
--   supporting claim of the event version, a non-generic rationale) or state that it
--   is not established (score 0).

INSERT INTO lfhe.audit_event_types (code, spec_source) VALUES
  ('RELEVANCE_INGESTION_RECORDED', 'Phase 4 impl.'),
  ('RELEVANCE_RESULT_RECORDED', 'Phase 4 impl.')
ON CONFLICT (code) DO NOTHING;

CREATE TYPE lfhe.hu_nato_dimension AS ENUM (           -- Phase 4 Addendum §4.2 list
  'CAPABILITY', 'READINESS', 'FORCE_PROTECTION', 'AIR_DEFENCE', 'DETERRENCE', 'INTEROPERABILITY',
  'PROCUREMENT_CAPABILITY_DEVELOPMENT', 'DOCTRINE_ADAPTATION', 'INDUSTRIAL_CAPACITY', 'SENSOR_TO_DECISION',
  'UAS_C_UAS', 'EASTERN_FLANK_POSTURE', 'WARNING_MONITORING');
CREATE TYPE lfhe.m06_recommendation AS ENUM ('BACKGROUND_ONLY', 'EXCLUDE_FROM_AUTOMATIC_ASSESSMENT');  -- Prompt Pack §15

CREATE OR REPLACE FUNCTION lfhe.m06_priority_score(p_ms integer, p_nc integer, p_hn integer, p_sr integer, p_ts integer)
RETURNS numeric LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
  SELECT round(0.25 * p_ms + 0.20 * p_nc + 0.25 * p_hn + 0.20 * p_sr + 0.10 * p_ts, 2)
$$;

CREATE OR REPLACE FUNCTION lfhe.text_is_generic_relevance(p text)
RETURNS boolean LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
  -- generic phrases with nothing evidence-specific around them (Addendum §4.2)
  SELECT p IS NULL OR length(btrim(p)) < 40
      OR pg_catalog.regexp_replace(lower(p), '[^a-z ]', '', 'g') ~
         '^\s*(this is |it is |the development is |)(very |highly |)(important for nato|strategically significant|relevant to european security|important for hungary|relevant for nato|significant for nato and hungary)\s*$'
$$;

CREATE TABLE lfhe.relevance_ingestion_results (
  model_run_id            uuid PRIMARY KEY REFERENCES lfhe.model_runs(id),
  model_run_status        lfhe.model_run_status NOT NULL,
  output_status           text,
  outcome                 text NOT NULL CHECK (outcome IN ('RELEVANCE_RECORDED', 'OUTPUT_REJECTED', 'INSUFFICIENT_INFORMATION',
                                                           'HUMAN_REVIEW_REQUIRED', 'SCHEMA_VALIDATION_FAILED', 'PROVIDER_ERROR',
                                                           'FAILED', 'RUNNING', 'SUCCEEDED')),
  report_mode             text NOT NULL,
  information_cutoff      timestamptz NOT NULL,
  rejection_reasons       text[] NOT NULL DEFAULT '{}',
  human_review_required   boolean NOT NULL,
  warnings                jsonb NOT NULL DEFAULT '[]',
  repair_of_model_run_id  uuid REFERENCES lfhe.model_runs(id),
  created_at              timestamptz NOT NULL DEFAULT now(),
  CHECK ((outcome = 'OUTPUT_REJECTED') = (cardinality(rejection_reasons) > 0))
);

CREATE TABLE lfhe.relevance_results (
  id                              uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  model_run_id                    uuid NOT NULL UNIQUE REFERENCES lfhe.relevance_ingestion_results(model_run_id),
  event_id                        uuid NOT NULL REFERENCES lfhe.events(id),
  event_version_id                uuid NOT NULL,
  event_version_hash              text NOT NULL,
  baseline_version_id             uuid REFERENCES lfhe.baseline_versions(id),
  previous_assessment_version_id  uuid,
  military_significance           smallint NOT NULL CHECK (military_significance BETWEEN 0 AND 5),
  novelty_change                  smallint NOT NULL CHECK (novelty_change BETWEEN 0 AND 5),
  hu_nato_relevance_score         smallint NOT NULL CHECK (hu_nato_relevance_score BETWEEN 0 AND 5),
  strategic_relevance             smallint NOT NULL CHECK (strategic_relevance BETWEEN 0 AND 5),
  time_sensitivity                smallint NOT NULL CHECK (time_sensitivity BETWEEN 0 AND 5),
  priority_score                  numeric(3, 2) NOT NULL CHECK (priority_score BETWEEN 0 AND 5),
  applicable_pir_ids              text[] NOT NULL,
  recommendation                  lfhe.m06_recommendation,
  automatic_assessment_recommended boolean NOT NULL,
  retain_for_manual_review        boolean NOT NULL,
  hu_nato_relevance_established   boolean NOT NULL,
  hu_nato_dimensions              lfhe.hu_nato_dimension[] NOT NULL DEFAULT '{}',
  hu_nato_evidence_claim_ids      uuid[] NOT NULL DEFAULT '{}',
  hu_nato_relevance_rationale     text NOT NULL,
  executive_relevance             text NOT NULL,
  reasoning_summary               text NOT NULL,
  relevance_uncertainty           text,
  human_review_required           boolean NOT NULL,
  created_at                      timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (event_version_id, event_version_hash) REFERENCES lfhe.event_versions (id, content_hash),
  CHECK (priority_score = lfhe.m06_priority_score(military_significance, novelty_change, hu_nato_relevance_score,
                                                  strategic_relevance, time_sensitivity)),
  CHECK (hu_nato_relevance_established = (hu_nato_relevance_score > 0)),
  CHECK (NOT hu_nato_relevance_established OR (cardinality(hu_nato_dimensions) > 0
                                               AND cardinality(hu_nato_evidence_claim_ids) > 0))
);
CREATE INDEX relevance_results_event_idx ON lfhe.relevance_results (event_id, created_at DESC);

-- Human decisions on a relevance result or an event version (permission ASSESSMENT_REVIEW)
CREATE TABLE lfhe.relevance_decisions (
  seq                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id                  uuid NOT NULL UNIQUE DEFAULT pg_catalog.gen_random_uuid(),
  action              text NOT NULL CHECK (action IN ('VALIDATE', 'OVERRIDE', 'PROMOTE', 'REQUEST_ASSESSMENT')),
  relevance_result_id uuid REFERENCES lfhe.relevance_results(id),
  event_id            uuid NOT NULL REFERENCES lfhe.events(id),
  event_version_id    uuid NOT NULL,
  event_version_hash  text NOT NULL,
  override            jsonb,
  actor_user_id       uuid NOT NULL,
  reason              text NOT NULL CHECK (length(btrim(reason)) >= 5),
  created_at          timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (event_version_id, event_version_hash) REFERENCES lfhe.event_versions (id, content_hash),
  CHECK ((action IN ('VALIDATE', 'OVERRIDE')) = (relevance_result_id IS NOT NULL)),
  CHECK ((action = 'OVERRIDE') = (override IS NOT NULL))
);

DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['relevance_ingestion_results', 'relevance_results', 'relevance_decisions'] LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON lfhe.%I FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation()',
                   t || '_immutable', t);
  END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- Worker ingestion
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.relevance_problems(p_run uuid, p_mode text, p_cutoff timestamptz, r jsonb)
RETURNS text[] LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_out   text[] := '{}';
  v_uuid  constant text := '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$';
  v_ver   lfhe.event_versions%ROWTYPE;
  v_pir   text;
  v_c     text;
  v_recommended boolean := coalesce((r ->> 'automatic_assessment_recommended')::boolean, false);
  v_pir07 boolean := coalesce(r -> 'applicable_pir_ids', '[]') ? 'PIR_07';
BEGIN
  IF (r ->> 'event_version_id') IS NULL OR (r ->> 'event_version_id') !~ v_uuid
     OR NOT lfhe.run_has_object(p_run, 'input', 'event_version', r ->> 'event_version_id') THEN
    RETURN ARRAY['EVENT_VERSION_NOT_IN_MODEL_RUN_INPUT'];
  END IF;
  SELECT * INTO v_ver FROM lfhe.event_versions WHERE id = (r ->> 'event_version_id')::uuid;
  IF NOT FOUND OR v_ver.event_id::text IS DISTINCT FROM r ->> 'event_id' THEN
    RETURN ARRAY['EVENT_ID_MISMATCH'];
  END IF;
  IF NOT lfhe.event_version_eligible(v_ver.id, p_mode, p_cutoff) THEN
    v_out := v_out || 'EVENT_VERSION_NOT_CUTOFF_ELIGIBLE'::text;
  END IF;
  IF (r ->> 'baseline_version_id') IS NOT NULL AND (
       (r ->> 'baseline_version_id') !~ v_uuid
       OR NOT lfhe.run_has_object(p_run, 'context', 'baseline_version', r ->> 'baseline_version_id')
       OR NOT lfhe.baseline_version_usable((r ->> 'baseline_version_id')::uuid, p_mode, p_cutoff)) THEN
    v_out := v_out || 'BASELINE_NOT_SUPPLIED_OR_INELIGIBLE'::text;
  END IF;
  IF (r ->> 'previous_assessment_version_id') IS NOT NULL
     AND NOT lfhe.run_has_object(p_run, 'context', 'assessment_version', r ->> 'previous_assessment_version_id') THEN
    v_out := v_out || 'PREVIOUS_ASSESSMENT_NOT_SUPPLIED'::text;
  END IF;
  FOR v_pir IN SELECT pg_catalog.jsonb_array_elements_text(coalesce(r -> 'applicable_pir_ids', '[]')) LOOP
    IF NOT EXISTS (SELECT 1 FROM lfhe.taxonomy_items t WHERE t.id = v_pir AND t.taxonomy_type = 'PIR') THEN
      v_out := v_out || ('PIR_ID_UNKNOWN:' || left(v_pir, 60));
    END IF;
  END LOOP;
  IF coalesce((r ->> 'hu_nato_relevance_score')::integer, -1) > 0 THEN
    -- relevance established: concrete dimension(s), evidence from the event version, non-generic rationale
    IF pg_catalog.jsonb_array_length(coalesce(r -> 'hu_nato_dimensions', '[]')) = 0 THEN
      v_out := v_out || 'HU_NATO_DIMENSION_REQUIRED'::text;
    END IF;
    IF pg_catalog.jsonb_array_length(coalesce(r -> 'hu_nato_evidence_claim_ids', '[]')) = 0 THEN
      v_out := v_out || 'HU_NATO_EVIDENCE_REQUIRED'::text;
    END IF;
    FOR v_c IN SELECT pg_catalog.jsonb_array_elements_text(coalesce(r -> 'hu_nato_evidence_claim_ids', '[]')) LOOP
      IF v_c !~ v_uuid OR NOT EXISTS (SELECT 1 FROM lfhe.event_claims ec WHERE ec.event_version_id = v_ver.id
                                      AND ec.claim_id = v_c::uuid) THEN
        v_out := v_out || ('HU_NATO_EVIDENCE_NOT_IN_EVENT_VERSION:' || left(v_c, 80));
      END IF;
    END LOOP;
    IF lfhe.text_is_generic_relevance(r ->> 'hu_nato_relevance_rationale') THEN
      v_out := v_out || 'HU_NATO_RATIONALE_GENERIC'::text;
    END IF;
  ELSIF v_recommended OR v_pir07 THEN
    -- recommended / PIR-07 without established relevance: an explicit "not established" statement is required
    IF coalesce(length(btrim(r ->> 'hu_nato_relevance_rationale')), 0) < 20 THEN
      v_out := v_out || 'HU_NATO_NOT_ESTABLISHED_STATEMENT_REQUIRED'::text;
    END IF;
    IF pg_catalog.jsonb_array_length(coalesce(r -> 'hu_nato_dimensions', '[]')) > 0 THEN
      v_out := v_out || 'HU_NATO_DIMENSIONS_WITHOUT_ESTABLISHED_RELEVANCE'::text;
    END IF;
  END IF;
  IF v_pir07 AND coalesce((r ->> 'hu_nato_relevance_score')::integer, 0) = 0
     AND lfhe.text_is_generic_relevance(r ->> 'hu_nato_relevance_rationale')
     AND coalesce(length(btrim(r ->> 'hu_nato_relevance_rationale')), 0) >= 40 THEN
    v_out := v_out || 'HU_NATO_RATIONALE_GENERIC'::text;
  END IF;
  RETURN v_out;
END $$;

-- p: {model_run_id, output_status, human_review_required, warnings, repair_of_model_run_id, result}
CREATE OR REPLACE FUNCTION lfhe.ingest_relevance(p jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_run      lfhe.model_runs%ROWTYPE;
  v_mode     text;
  v_cutoff   timestamptz;
  v_r        jsonb := p -> 'result';
  v_status   text := p ->> 'output_status';
  v_reasons  text[] := '{}';
  v_outcome  text;
  v_id       uuid;
  v_ver      lfhe.event_versions%ROWTYPE;
BEGIN
  SELECT * INTO v_run FROM lfhe.model_runs WHERE id = (p ->> 'model_run_id')::uuid;
  IF NOT FOUND OR v_run.module_code <> 'M06_RELEVANCE' OR v_run.status = 'RUNNING' THEN
    RAISE EXCEPTION 'model run % is not a finished M06_RELEVANCE run', p ->> 'model_run_id'
      USING ERRCODE = 'object_not_in_prerequisite_state';
  END IF;
  SELECT * INTO v_mode, v_cutoff FROM lfhe.model_run_cutoff(v_run.id);
  IF v_run.status <> 'SUCCEEDED' THEN
    INSERT INTO lfhe.relevance_ingestion_results (model_run_id, model_run_status, outcome, report_mode, information_cutoff,
      human_review_required, repair_of_model_run_id)
    VALUES (v_run.id, v_run.status, v_run.status::text, v_mode, v_cutoff, false, (p ->> 'repair_of_model_run_id')::uuid);
    RETURN pg_catalog.jsonb_build_object('outcome', v_run.status::text);
  END IF;
  IF v_status IN ('INSUFFICIENT_INFORMATION', 'HUMAN_REVIEW_REQUIRED', 'AMBIGUOUS', 'FAILED') OR v_r IS NULL
     OR pg_catalog.jsonb_typeof(v_r) <> 'object' THEN
    v_outcome := CASE WHEN v_status = 'INSUFFICIENT_INFORMATION' THEN 'INSUFFICIENT_INFORMATION' ELSE 'HUMAN_REVIEW_REQUIRED' END;
  ELSE
    v_reasons := lfhe.relevance_problems(v_run.id, v_mode, v_cutoff, v_r);
    v_outcome := CASE WHEN cardinality(v_reasons) > 0 THEN 'OUTPUT_REJECTED' ELSE 'RELEVANCE_RECORDED' END;
  END IF;
  INSERT INTO lfhe.relevance_ingestion_results (model_run_id, model_run_status, output_status, outcome, report_mode,
    information_cutoff, rejection_reasons, human_review_required, warnings, repair_of_model_run_id)
  VALUES (v_run.id, v_run.status, v_status, v_outcome, v_mode, v_cutoff, v_reasons,
    coalesce((p ->> 'human_review_required')::boolean, false) OR v_outcome <> 'RELEVANCE_RECORDED',
    coalesce(p -> 'warnings', '[]'), (p ->> 'repair_of_model_run_id')::uuid);
  IF v_outcome <> 'RELEVANCE_RECORDED' THEN
    RETURN pg_catalog.jsonb_build_object('outcome', v_outcome, 'rejection_reasons', pg_catalog.to_jsonb(v_reasons));
  END IF;
  SELECT * INTO v_ver FROM lfhe.event_versions WHERE id = (v_r ->> 'event_version_id')::uuid;
  INSERT INTO lfhe.relevance_results (model_run_id, event_id, event_version_id, event_version_hash, baseline_version_id,
    previous_assessment_version_id, military_significance, novelty_change, hu_nato_relevance_score, strategic_relevance,
    time_sensitivity, priority_score, applicable_pir_ids, recommendation, automatic_assessment_recommended,
    retain_for_manual_review, hu_nato_relevance_established, hu_nato_dimensions, hu_nato_evidence_claim_ids,
    hu_nato_relevance_rationale, executive_relevance, reasoning_summary, relevance_uncertainty, human_review_required)
  VALUES (v_run.id, v_ver.event_id, v_ver.id, v_ver.content_hash, (v_r ->> 'baseline_version_id')::uuid,
    (v_r ->> 'previous_assessment_version_id')::uuid,
    (v_r ->> 'military_significance')::smallint, (v_r ->> 'novelty_change')::smallint,
    (v_r ->> 'hu_nato_relevance_score')::smallint, (v_r ->> 'strategic_relevance')::smallint,
    (v_r ->> 'time_sensitivity')::smallint,
    lfhe.m06_priority_score((v_r ->> 'military_significance')::integer, (v_r ->> 'novelty_change')::integer,
      (v_r ->> 'hu_nato_relevance_score')::integer, (v_r ->> 'strategic_relevance')::integer,
      (v_r ->> 'time_sensitivity')::integer),
    ARRAY(SELECT pg_catalog.jsonb_array_elements_text(coalesce(v_r -> 'applicable_pir_ids', '[]')) ORDER BY 1),
    (v_r ->> 'recommendation')::lfhe.m06_recommendation,
    coalesce((v_r ->> 'automatic_assessment_recommended')::boolean, false),
    coalesce((v_r ->> 'retain_for_manual_review')::boolean, true),
    (v_r ->> 'hu_nato_relevance_score')::integer > 0,
    ARRAY(SELECT pg_catalog.jsonb_array_elements_text(coalesce(v_r -> 'hu_nato_dimensions', '[]'))::lfhe.hu_nato_dimension),
    ARRAY(SELECT pg_catalog.jsonb_array_elements_text(coalesce(v_r -> 'hu_nato_evidence_claim_ids', '[]'))::uuid),
    coalesce(v_r ->> 'hu_nato_relevance_rationale', ''), coalesce(v_r ->> 'executive_relevance', ''),
    coalesce(v_r ->> 'reasoning_summary', ''), v_r ->> 'relevance_uncertainty',
    coalesce((p ->> 'human_review_required')::boolean, false))
  RETURNING id INTO v_id;
  RETURN pg_catalog.jsonb_build_object('outcome', v_outcome, 'relevance_result_id', v_id);
END $$;

-- ---------------------------------------------------------------------------
-- HUMAN_ONLY (permission ASSESSMENT_REVIEW)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.p4_require_event_version(p_version uuid, p_hash text)
RETURNS lfhe.event_versions LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v lfhe.event_versions%ROWTYPE;
BEGIN
  SELECT * INTO v FROM lfhe.event_versions WHERE id = p_version;
  IF NOT FOUND OR v.content_hash IS DISTINCT FROM p_hash THEN
    RAISE EXCEPTION 'VERSION_HASH_MISMATCH: event version % / hash', p_version USING ERRCODE = 'serialization_failure';
  END IF;
  RETURN v;
END $$;

CREATE OR REPLACE FUNCTION lfhe.decide_relevance(p_result uuid, p_action text, p_override jsonb, p_reason text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('ASSESSMENT_REVIEW');
  v_r     lfhe.relevance_results%ROWTYPE;
  v_id    uuid;
BEGIN
  IF p_action NOT IN ('VALIDATE', 'OVERRIDE') THEN
    RAISE EXCEPTION 'action must be VALIDATE or OVERRIDE' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  SELECT * INTO v_r FROM lfhe.relevance_results WHERE id = p_result;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'unknown relevance result %', p_result USING ERRCODE = 'no_data_found';
  END IF;
  IF p_action = 'OVERRIDE' AND (p_override IS NULL OR pg_catalog.jsonb_typeof(p_override) <> 'object'
       OR NOT (p_override ?| ARRAY['priority_score', 'automatic_assessment_recommended', 'applicable_pir_ids',
                                   'hu_nato_relevance_rationale'])
       OR (p_override ? 'priority_score' AND NOT ((p_override ->> 'priority_score')::numeric BETWEEN 0 AND 5))) THEN
    RAISE EXCEPTION 'OVERRIDE_INVALID' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  INSERT INTO lfhe.relevance_decisions (action, relevance_result_id, event_id, event_version_id, event_version_hash,
    override, actor_user_id, reason)
  VALUES (p_action, v_r.id, v_r.event_id, v_r.event_version_id, v_r.event_version_hash,
    CASE WHEN p_action = 'OVERRIDE' THEN p_override END, v_actor, p_reason)
  RETURNING id INTO v_id;
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.decide_relevance(uuid, text, jsonb, text) IS 'HUMAN_ONLY';

-- manual promotion / manual assessment request — independent of any M06 score
CREATE OR REPLACE FUNCTION lfhe.promote_event_version(p_version uuid, p_hash text, p_action text, p_reason text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('ASSESSMENT_REVIEW');
  v       lfhe.event_versions := lfhe.p4_require_event_version(p_version, p_hash);
  v_id    uuid;
BEGIN
  IF p_action NOT IN ('PROMOTE', 'REQUEST_ASSESSMENT') THEN
    RAISE EXCEPTION 'action must be PROMOTE or REQUEST_ASSESSMENT' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  INSERT INTO lfhe.relevance_decisions (action, event_id, event_version_id, event_version_hash, actor_user_id, reason)
  VALUES (p_action, v.event_id, v.id, v.content_hash, v_actor, p_reason) RETURNING id INTO v_id;
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.promote_event_version(uuid, text, text, text) IS 'HUMAN_ONLY';

-- ---------------------------------------------------------------------------
-- Visibility: every event, with its latest relevance (if any) — nothing hidden
-- ---------------------------------------------------------------------------
CREATE VIEW lfhe.event_relevance_queue WITH (security_invoker = true) AS
SELECT h.event_id, h.head_version_id, h.state, h.is_current,
       r.id AS relevance_result_id, r.event_version_id AS scored_event_version_id, r.priority_score,
       r.automatic_assessment_recommended, r.recommendation, r.hu_nato_relevance_established,
       (SELECT d.override FROM lfhe.relevance_decisions d WHERE d.relevance_result_id = r.id AND d.action = 'OVERRIDE'
        ORDER BY d.seq DESC LIMIT 1) AS latest_override,
       EXISTS (SELECT 1 FROM lfhe.relevance_decisions d WHERE d.event_id = h.event_id
               AND d.action IN ('PROMOTE', 'REQUEST_ASSESSMENT')) AS manually_promoted_or_requested
FROM lfhe.event_heads h
LEFT JOIN LATERAL (SELECT * FROM lfhe.relevance_results x WHERE x.event_id = h.event_id
                   ORDER BY x.created_at DESC, x.id LIMIT 1) r ON true;

-- ---------------------------------------------------------------------------
-- Audit
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.audit_relevance_objects()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_event text;
  v_obj   text;
  v_id    text;
BEGIN
  CASE TG_TABLE_NAME
    WHEN 'relevance_ingestion_results' THEN v_event := 'RELEVANCE_INGESTION_RECORDED'; v_obj := 'relevance_ingestion_result'; v_id := NEW.model_run_id::text;
    WHEN 'relevance_results' THEN v_event := 'RELEVANCE_RESULT_RECORDED'; v_obj := 'relevance_result'; v_id := (pg_catalog.to_jsonb(NEW) ->> 'id');
    WHEN 'relevance_decisions' THEN
      v_event := CASE pg_catalog.to_jsonb(NEW) ->> 'action' WHEN 'VALIDATE' THEN 'EXECUTIVE_RELEVANCE_VALIDATED'
                   WHEN 'OVERRIDE' THEN 'RELEVANCE_SCORE_OVERRIDDEN' WHEN 'PROMOTE' THEN 'EVENT_MANUALLY_PROMOTED'
                   ELSE 'MANUAL_ASSESSMENT_REQUESTED' END;
      v_obj := 'event_version'; v_id := (pg_catalog.to_jsonb(NEW) ->> 'event_version_id');
  END CASE;
  PERFORM lfhe.write_audit(v_event, v_obj, v_id, NULL, pg_catalog.to_jsonb(NEW), '{}'::jsonb);
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION lfhe.audit_relevance_objects() FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['relevance_ingestion_results', 'relevance_results', 'relevance_decisions'] LOOP
    EXECUTE format('CREATE TRIGGER %I AFTER INSERT ON lfhe.%I FOR EACH ROW EXECUTE FUNCTION lfhe.audit_relevance_objects()',
                   t || '_audit', t);
  END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- Grants / RLS
-- ---------------------------------------------------------------------------
REVOKE ALL ON FUNCTION lfhe.relevance_problems(uuid, text, timestamptz, jsonb), lfhe.ingest_relevance(jsonb),
  lfhe.p4_require_event_version(uuid, text), lfhe.text_is_generic_relevance(text),
  lfhe.m06_priority_score(integer, integer, integer, integer, integer)
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.ingest_relevance(jsonb) TO lfhe_worker;
GRANT EXECUTE ON FUNCTION lfhe.m06_priority_score(integer, integer, integer, integer, integer) TO authenticated, lfhe_worker;
REVOKE ALL ON FUNCTION lfhe.decide_relevance(uuid, text, jsonb, text), lfhe.promote_event_version(uuid, text, text, text)
  FROM PUBLIC, anon, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.decide_relevance(uuid, text, jsonb, text), lfhe.promote_event_version(uuid, text, text, text)
  TO authenticated;

REVOKE ALL ON lfhe.relevance_ingestion_results, lfhe.relevance_results, lfhe.relevance_decisions, lfhe.event_relevance_queue
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT SELECT ON lfhe.relevance_ingestion_results, lfhe.relevance_results, lfhe.relevance_decisions, lfhe.event_relevance_queue
  TO authenticated, lfhe_worker;
DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['relevance_ingestion_results', 'relevance_results', 'relevance_decisions'] LOOP
    EXECUTE format('ALTER TABLE lfhe.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY %I ON lfhe.%I FOR SELECT TO authenticated USING (lfhe.has_permission(''CLAIM_READ''))',
                   t || '_read_human', t);
    EXECUTE format('CREATE POLICY %I ON lfhe.%I FOR SELECT TO lfhe_worker USING (true)', t || '_read_worker', t);
  END LOOP;
END $$;
