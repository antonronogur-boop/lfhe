-- LFHÉ Phase 4 (P4-05) — M08 Challenger: structured, immutable challenge output (G-07)
-- and separate, audited human dispositions. Baseline: Phase 4 Addendum §13–§15, §21, §22;
-- Prompt Pack v1.2 §24 (closed flag type / severity / recommended-action enums).
--
-- * M08 challenges one exact assessment_version (id + content_hash) in DRAFT. It cannot
--   rewrite M07: the output has no field that edits statements, evidence or confidence,
--   and all assessment tables are immutable.
-- * A recorded challenge moves the version DRAFT → CHALLENGED → IN_REVIEW
--   (deterministic, worker; the only non-human transitions allowed by CHECK).
-- * A flag targets an exact statement (by local id of that version) and/or a named
--   assessment field; evidence refs must be claims of the supplied event version.
-- * Dispositions (ACCEPTED / REJECTED / ACKNOWLEDGED / REPROCESSING_REQUESTED /
--   ESCALATED — Addendum §15) are HUMAN_ONLY (ASSESSMENT_REVIEW), append-only, audited
--   as CHALLENGER_FLAG_DISPOSITIONED. The model never writes a disposition.

INSERT INTO lfhe.audit_event_types (code, spec_source) VALUES
  ('CHALLENGE_INGESTION_RECORDED', 'Phase 4 impl.'),
  ('CHALLENGE_RECORDED', 'Phase 4 impl.')
ON CONFLICT (code) DO NOTHING;

CREATE TYPE lfhe.challenge_flag_type AS ENUM (           -- Prompt Pack v1.2 §24 (closed)
  'CONFIRMATION_BIAS', 'ANCHORING', 'MIRROR_IMAGING', 'PREMATURE_CLOSURE', 'CIRCULAR_REPORTING', 'SOURCE_DEPENDENCE',
  'UNSUPPORTED_CAUSALITY', 'OVERCONFIDENCE', 'MISSING_ALTERNATIVE', 'CONTRADICTORY_EVIDENCE', 'DATE_ERROR',
  'BASELINE_ERROR', 'SCOPE_ERROR', 'HINDSIGHT_CONTAMINATION', 'UNSUPPORTED_STATEMENT', 'EPISTEMIC_STRENGTH_MISMATCH');
CREATE TYPE lfhe.challenge_severity AS ENUM ('INFO', 'WARNING', 'MAJOR', 'CRITICAL');   -- common QA scale
CREATE TYPE lfhe.challenge_recommended_action AS ENUM (  -- Prompt Pack v1.2 §24 (closed)
  'NO_ACTION', 'ANALYST_REVIEW', 'REVISE_STATEMENT', 'ADD_CAVEAT', 'LOWER_CONFIDENCE', 'RECHECK_LINEAGE', 'RECHECK_DATE',
  'RECHECK_BASELINE', 'REQUEST_MORE_EVIDENCE', 'REMOVE_UNSUPPORTED_STATEMENT', 'REPROCESS');
-- assessment fields a flag may target when it is not about one statement
CREATE TYPE lfhe.challenge_affected_field AS ENUM (
  'AI_RECOMMENDED_CONFIDENCE', 'AI_CONFIDENCE_RATIONALE', 'DERIVED_SUMMARY', 'INDICATORS_TO_WATCH', 'BASELINE',
  'REFERENCE_CONTEXT', 'STATEMENT_SET');

CREATE TABLE lfhe.challenge_ingestion_results (
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

CREATE TABLE lfhe.challenge_runs (
  id                          uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  model_run_id                uuid NOT NULL UNIQUE REFERENCES lfhe.challenge_ingestion_results(model_run_id),
  assessment_version_id       uuid NOT NULL,
  assessment_version_hash     text NOT NULL,
  challenge_result            text NOT NULL CHECK (length(btrim(challenge_result)) BETWEEN 1 AND 200),
  strongest_counterargument   text NOT NULL CHECK (length(btrim(strongest_counterargument)) >= 10),
  confidence_challenge        text NOT NULL,
  recommended_overall_action  lfhe.challenge_recommended_action NOT NULL,
  created_at                  timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (assessment_version_id, assessment_version_hash) REFERENCES lfhe.assessment_versions (id, content_hash)
);

CREATE TABLE lfhe.challenge_flags (
  id                     uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  challenge_run_id       uuid NOT NULL REFERENCES lfhe.challenge_runs(id),
  flag_no                integer NOT NULL CHECK (flag_no >= 1),
  flag_type              lfhe.challenge_flag_type NOT NULL,
  severity               lfhe.challenge_severity NOT NULL,
  affected_statement_id  uuid REFERENCES lfhe.assessment_statements(id),
  affected_field         lfhe.challenge_affected_field,
  explanation            text NOT NULL CHECK (length(btrim(explanation)) >= 10),
  evidence_claim_ids     uuid[] NOT NULL DEFAULT '{}',
  recommended_action     lfhe.challenge_recommended_action NOT NULL,
  UNIQUE (challenge_run_id, flag_no),
  CHECK (affected_statement_id IS NOT NULL OR affected_field IS NOT NULL)
);

CREATE TABLE lfhe.challenge_flag_dispositions (
  seq            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id             uuid NOT NULL UNIQUE DEFAULT pg_catalog.gen_random_uuid(),
  flag_id        uuid NOT NULL REFERENCES lfhe.challenge_flags(id),
  disposition    text NOT NULL CHECK (disposition IN ('ACCEPTED', 'REJECTED', 'ACKNOWLEDGED', 'REPROCESSING_REQUESTED', 'ESCALATED')),
  actor_user_id  uuid NOT NULL,
  reason         text NOT NULL CHECK (length(btrim(reason)) >= 5),
  created_at     timestamptz NOT NULL DEFAULT now()
);

DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['challenge_ingestion_results', 'challenge_runs', 'challenge_flags', 'challenge_flag_dispositions'] LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON lfhe.%I FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation()',
                   t || '_immutable', t);
  END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- M08 ingestion (worker)
-- p: {model_run_id, output_status, human_review_required, warnings, repair_of_model_run_id, result}
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.ingest_challenge(p jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_run     lfhe.model_runs%ROWTYPE;
  v_r       jsonb := p -> 'result';
  v_status  text := p ->> 'output_status';
  v_reasons text[] := '{}';
  v_outcome text;
  v_ver     lfhe.assessment_versions%ROWTYPE;
  v_f       jsonb;
  v_c       text;
  v_n       integer := 0;
  v_cr      uuid;
  v_sid     uuid;
  v_claims  uuid[];
  v_uuid    constant text := '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$';
BEGIN
  SELECT * INTO v_run FROM lfhe.model_runs WHERE id = (p ->> 'model_run_id')::uuid;
  IF NOT FOUND OR v_run.module_code <> 'M08_CHALLENGER' OR v_run.status = 'RUNNING' THEN
    RAISE EXCEPTION 'model run % is not a finished M08_CHALLENGER run', p ->> 'model_run_id'
      USING ERRCODE = 'object_not_in_prerequisite_state';
  END IF;
  PERFORM lfhe.model_run_cutoff(v_run.id);
  IF v_run.status <> 'SUCCEEDED' THEN
    INSERT INTO lfhe.challenge_ingestion_results (model_run_id, model_run_status, outcome, human_review_required,
      repair_of_model_run_id)
    VALUES (v_run.id, v_run.status, v_run.status::text, false, (p ->> 'repair_of_model_run_id')::uuid);
    RETURN pg_catalog.jsonb_build_object('outcome', v_run.status::text);
  END IF;
  IF v_status IN ('INSUFFICIENT_INFORMATION', 'HUMAN_REVIEW_REQUIRED', 'AMBIGUOUS', 'FAILED') OR v_r IS NULL THEN
    v_outcome := CASE WHEN v_status = 'INSUFFICIENT_INFORMATION' THEN 'INSUFFICIENT_INFORMATION' ELSE 'HUMAN_REVIEW_REQUIRED' END;
  ELSE
    IF coalesce(v_r ->> 'assessment_version_id', '') !~ v_uuid
       OR NOT lfhe.run_has_object(v_run.id, 'input', 'assessment_version', v_r ->> 'assessment_version_id') THEN
      v_reasons := v_reasons || 'ASSESSMENT_VERSION_NOT_SUPPLIED'::text;
    ELSE
      SELECT * INTO v_ver FROM lfhe.assessment_versions WHERE id = (v_r ->> 'assessment_version_id')::uuid;
      IF v_ver.content_hash IS DISTINCT FROM v_r ->> 'assessment_version_hash' THEN
        v_reasons := v_reasons || 'ASSESSMENT_VERSION_HASH_MISMATCH'::text;
      END IF;
      IF lfhe.assessment_version_state(v_ver.id) IS DISTINCT FROM 'DRAFT' THEN
        v_reasons := v_reasons || 'ASSESSMENT_NOT_IN_DRAFT'::text;
      END IF;
      v_claims := ARRAY(SELECT claim_id FROM lfhe.event_claims WHERE event_version_id = v_ver.event_version_id);
    END IF;
    IF v_r ?| ARRAY['final_analytic_confidence', 'assessment_statements', 'revised_statements', 'ai_recommended_confidence'] THEN
      v_reasons := v_reasons || 'M08_MAY_NOT_MODIFY_ASSESSMENT'::text;
    END IF;
    IF coalesce(length(btrim(v_r ->> 'strongest_counterargument')), 0) < 10 THEN
      v_reasons := v_reasons || 'STRONGEST_COUNTERARGUMENT_REQUIRED'::text;
    END IF;
    IF cardinality(v_reasons) = 0 THEN
      FOR v_f IN SELECT * FROM pg_catalog.jsonb_array_elements(coalesce(v_r -> 'flags', '[]')) LOOP
        IF v_f ->> 'affected_statement_local_id' IS NULL AND v_f ->> 'affected_field' IS NULL THEN
          v_reasons := v_reasons || 'FLAG_TARGET_REQUIRED'::text;
        END IF;
        IF v_f ->> 'affected_statement_local_id' IS NOT NULL AND NOT EXISTS (
             SELECT 1 FROM lfhe.assessment_statements s WHERE s.assessment_version_id = v_ver.id
             AND s.statement_local_id = v_f ->> 'affected_statement_local_id') THEN
          v_reasons := v_reasons || ('FLAG_TARGET_UNKNOWN:' || left(v_f ->> 'affected_statement_local_id', 20));
        END IF;
        FOR v_c IN SELECT pg_catalog.jsonb_array_elements_text(coalesce(v_f -> 'evidence_claim_ids', '[]')) LOOP
          IF v_c !~ v_uuid OR NOT (v_c::uuid = ANY (v_claims)) THEN
            v_reasons := v_reasons || ('EVIDENCE_NOT_SUPPLIED:' || left(v_c, 40));
          END IF;
        END LOOP;
      END LOOP;
    END IF;
    v_reasons := ARRAY(SELECT DISTINCT r FROM pg_catalog.unnest(v_reasons) r ORDER BY r);
    v_outcome := CASE WHEN cardinality(v_reasons) > 0 THEN 'OUTPUT_REJECTED' ELSE 'CHALLENGE_RECORDED' END;
  END IF;
  INSERT INTO lfhe.challenge_ingestion_results (model_run_id, model_run_status, output_status, outcome, rejection_reasons,
    human_review_required, warnings, repair_of_model_run_id)
  VALUES (v_run.id, v_run.status, v_status, v_outcome, v_reasons, true, coalesce(p -> 'warnings', '[]'),
    (p ->> 'repair_of_model_run_id')::uuid);
  IF v_outcome <> 'CHALLENGE_RECORDED' THEN
    RETURN pg_catalog.jsonb_build_object('outcome', v_outcome, 'rejection_reasons', pg_catalog.to_jsonb(v_reasons));
  END IF;
  INSERT INTO lfhe.challenge_runs (model_run_id, assessment_version_id, assessment_version_hash, challenge_result,
    strongest_counterargument, confidence_challenge, recommended_overall_action)
  VALUES (v_run.id, v_ver.id, v_ver.content_hash, v_r ->> 'challenge_result', v_r ->> 'strongest_counterargument',
    coalesce(v_r ->> 'confidence_challenge', ''), (v_r ->> 'recommended_overall_action')::lfhe.challenge_recommended_action)
  RETURNING id INTO v_cr;
  FOR v_f IN SELECT * FROM pg_catalog.jsonb_array_elements(coalesce(v_r -> 'flags', '[]')) LOOP
    v_n := v_n + 1;
    SELECT s.id INTO v_sid FROM lfhe.assessment_statements s WHERE s.assessment_version_id = v_ver.id
      AND s.statement_local_id = v_f ->> 'affected_statement_local_id';
    INSERT INTO lfhe.challenge_flags (challenge_run_id, flag_no, flag_type, severity, affected_statement_id, affected_field,
      explanation, evidence_claim_ids, recommended_action)
    VALUES (v_cr, v_n, (v_f ->> 'flag_type')::lfhe.challenge_flag_type, (v_f ->> 'severity')::lfhe.challenge_severity,
      CASE WHEN v_f ->> 'affected_statement_local_id' IS NOT NULL THEN v_sid END,
      (v_f ->> 'affected_field')::lfhe.challenge_affected_field, v_f ->> 'explanation',
      ARRAY(SELECT pg_catalog.jsonb_array_elements_text(coalesce(v_f -> 'evidence_claim_ids', '[]'))::uuid),
      (v_f ->> 'recommended_action')::lfhe.challenge_recommended_action);
  END LOOP;
  PERFORM lfhe.set_assessment_state(v_ver.id, 'CHALLENGED', 'WORKER', NULL, NULL, 'M08 challenge recorded');
  PERFORM lfhe.set_assessment_state(v_ver.id, 'IN_REVIEW', 'WORKER', NULL, NULL, 'deterministic transition to human review');
  RETURN pg_catalog.jsonb_build_object('outcome', v_outcome, 'challenge_run_id', v_cr, 'flags', v_n);
END $$;

-- ---------------------------------------------------------------------------
-- HUMAN_ONLY disposition (ASSESSMENT_REVIEW)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.dispose_challenge_flag(p_flag uuid, p_disposition text, p_reason text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('ASSESSMENT_REVIEW');
  v_id    uuid;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM lfhe.challenge_flags WHERE id = p_flag) THEN
    RAISE EXCEPTION 'unknown challenge flag %', p_flag USING ERRCODE = 'no_data_found';
  END IF;
  INSERT INTO lfhe.challenge_flag_dispositions (flag_id, disposition, actor_user_id, reason)
  VALUES (p_flag, p_disposition, v_actor, p_reason) RETURNING id INTO v_id;
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.dispose_challenge_flag(uuid, text, text) IS 'HUMAN_ONLY';

-- ---------------------------------------------------------------------------
-- Audit
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.audit_challenge_objects()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_doc   jsonb := pg_catalog.to_jsonb(NEW);
BEGIN
  CASE TG_TABLE_NAME
    WHEN 'challenge_ingestion_results' THEN
      PERFORM lfhe.write_audit('CHALLENGE_INGESTION_RECORDED', 'challenge_ingestion_result', v_doc ->> 'model_run_id', NULL, v_doc, '{}');
    WHEN 'challenge_runs' THEN
      PERFORM lfhe.write_audit('CHALLENGE_RECORDED', 'assessment_version', v_doc ->> 'assessment_version_id', NULL, v_doc, '{}');
    WHEN 'challenge_flag_dispositions' THEN
      PERFORM lfhe.write_audit('CHALLENGER_FLAG_DISPOSITIONED', 'challenge_flag', v_doc ->> 'flag_id', NULL, v_doc, '{}');
  END CASE;
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION lfhe.audit_challenge_objects() FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['challenge_ingestion_results', 'challenge_runs', 'challenge_flag_dispositions'] LOOP
    EXECUTE format('CREATE TRIGGER %I AFTER INSERT ON lfhe.%I FOR EACH ROW EXECUTE FUNCTION lfhe.audit_challenge_objects()',
                   t || '_audit', t);
  END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- Grants / RLS
-- ---------------------------------------------------------------------------
REVOKE ALL ON FUNCTION lfhe.ingest_challenge(jsonb) FROM PUBLIC, anon, authenticated, service_role, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.ingest_challenge(jsonb) TO lfhe_worker;
REVOKE ALL ON FUNCTION lfhe.dispose_challenge_flag(uuid, text, text) FROM PUBLIC, anon, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.dispose_challenge_flag(uuid, text, text) TO authenticated;

REVOKE ALL ON lfhe.challenge_ingestion_results, lfhe.challenge_runs, lfhe.challenge_flags, lfhe.challenge_flag_dispositions
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT SELECT ON lfhe.challenge_ingestion_results, lfhe.challenge_runs, lfhe.challenge_flags, lfhe.challenge_flag_dispositions
  TO authenticated, lfhe_worker;
DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['challenge_ingestion_results', 'challenge_runs', 'challenge_flags', 'challenge_flag_dispositions'] LOOP
    EXECUTE format('ALTER TABLE lfhe.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY %I ON lfhe.%I FOR SELECT TO authenticated USING (lfhe.has_permission(''CLAIM_READ''))',
                   t || '_read_human', t);
    EXECUTE format('CREATE POLICY %I ON lfhe.%I FOR SELECT TO lfhe_worker USING (true)', t || '_read_worker', t);
  END LOOP;
END $$;
