-- LFHÉ Phase 6 (P6-01, P6-02, P6-03 ingestion, P6-04) — M10 QA bound to an exact report version.
-- Baseline: Phase 6 Addendum §5–§16, §26–§28, §30 (docs/specs/LFHE_Phase6_Authoritative_Baseline_Addendum_v1.0.md);
-- Prompt Pack v1.2 §34–§48; CG0 E.16–E.17, H (QA architecture, run order).
--
-- * DC6-01: report_versions stay immutable and untouched. Every QA object is bound by composite
--   FK to (report_version_id, report_version_hash).
-- * qa_requests  — HUMAN request to run QA on the latest version (enqueues RUN_REPORT_QA).
-- * qa_runs      — kind D (M10-D, deterministic software, NO model_run) or S (M10-S, exactly one
--                  model_run + prompt version; the D run it received as context).
-- * qa_check_results — immutable findings in the Prompt Pack §44 schema; recommended_action is
--                  advisory text only (nothing executes it).
-- * qa_results   — the deterministic combined status (PASS / PASS_WITH_WARNINGS / FAIL) of one
--                  exact (D, S) pair, computed by the database, never by the model.
-- * warning_acknowledgements — HUMAN_ONLY (QA_WARNING_ACKNOWLEDGE), bound to one exact WARNING
--                  finding of one exact qa_result of one exact version/hash; never for FAIL/CRITICAL.
-- * Nothing here edits report content, confidence, likelihood, attribution or citations (§15).
-- * Reruns never delete: a new request → new runs → new qa_result; QA_RESULT_CHANGED_BY_RERUN is
--   audited when the authoritative status changes. A new report version starts QA from zero.

INSERT INTO lfhe.audit_event_types (code, spec_source) VALUES
  ('REPORT_QA_REQUESTED', 'Phase 6 impl.'),
  ('QA_RESULT_RECORDED', 'Phase 6 impl.')
ON CONFLICT (code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Vocabularies (closed)
-- ---------------------------------------------------------------------------
CREATE TABLE lfhe.qa_checks (
  check_id     text NOT NULL CHECK (check_id ~ '^(QA-[0-9]{2}|D[0-9]{2}|S[0-9]{2}|STRUCTURE)$'),
  layer        text NOT NULL CHECK (layer IN ('D', 'S')),
  description  text NOT NULL,
  spec_source  text NOT NULL,
  PRIMARY KEY (check_id, layer)
);
INSERT INTO lfhe.qa_checks (check_id, layer, description, spec_source) VALUES
  ('QA-01', 'D', 'Statement mappings exist, statement ids resolve, required evidence links resolve', 'P6 Addendum §8'),
  ('QA-02', 'D', 'Referenced sources / snapshots / evidence objects exist', 'P6 Addendum §8'),
  ('QA-03', 'D', 'Structured date relationships are valid', 'P6 Addendum §8'),
  ('QA-04', 'D', 'LIVE / REPLAY cutoff eligibility of all evidence (event time is not a criterion)', 'P6 Addendum §8'),
  ('QA-05', 'D', 'Known lineage / independence groups vs corroboration wording', 'P6 Addendum §8'),
  ('QA-06', 'D', 'Exact numerical support in the statement''s own approved sources', 'P6 Addendum §8'),
  ('QA-07', 'D', 'Authoritative status / epistemic state consistency', 'P6 Addendum §8'),
  ('QA-08', 'D', 'Confidence = approved final_analytic_confidence; likelihood = approved term', 'P6 Addendum §8'),
  ('QA-09', 'D', 'Selected caveats / contradictions are still covered', 'P6 Addendum §8; Phase 5 coverage rule'),
  ('QA-10', 'D', 'Every analytical source object is approved (as of the report cutoff)', 'P6 Addendum §8'),
  ('QA-11', 'D', 'Exact version / hash pins resolve; no floating reference', 'P6 Addendum §8'),
  ('QA-12', 'D', 'Model / prompt traceability of model-authored objects', 'P6 Addendum §8'),
  ('QA-13', 'D', 'Known event ids / relationships (merge, supersede) across report items', 'P6 Addendum §8'),
  ('QA-14', 'D', 'OSINT boundary: source / meta rules and prohibited markings', 'P6 Addendum §8'),
  ('QA-16', 'D', 'Release manifest prerequisites (structural readiness; DC6-03)', 'P6 Addendum §8, DC6-03'),
  ('QA-17', 'D', 'Hindsight: cutoff, baseline and reference-context eligibility; unsupported facts', 'P6 Addendum §8'),
  ('STRUCTURE', 'D', 'Canonical schema, sections, limits, mappings, confidence / likelihood fields, coverage, removals', 'P6 Addendum §8'),
  ('D18', 'D', 'Original-language claim grounding (exact span in the original-language snapshot)', 'P6 Addendum §8'),
  ('D19', 'D', 'Attribution omission rules', 'P6 Addendum §8'),
  ('D20', 'D', 'Required high-impact human validations exist', 'P6 Addendum §8'),
  ('D21', 'D', 'Baseline eligibility', 'P6 Addendum §8'),
  ('D22', 'D', 'Reference-context eligibility', 'P6 Addendum §8'),
  ('D23', 'D', 'QA is bound to the exact, current report_version_id + report_version_hash', 'P6 Addendum §8'),
  ('D24', 'D', 'Human approvals are bound to the exact version / hash', 'P6 Addendum §8'),
  ('D25', 'D', 'Manifest prerequisites (final completeness is checked in the release transaction)', 'P6 Addendum §8, DC6-03'),
  ('QA-01', 'S', 'Evidence entailment (actor, action, scope, quantity, time, location, causality, certainty, attribution)', 'P6 Addendum §10'),
  ('QA-05', 'S', 'Source-independence representation', 'P6 Addendum §10'),
  ('QA-06', 'S', 'Numerical scope / attribution / relationship', 'P6 Addendum §10'),
  ('QA-07', 'S', 'Epistemic class preservation', 'P6 Addendum §10'),
  ('QA-09', 'S', 'Contradiction / caveat / alternative / gap preservation', 'P6 Addendum §10'),
  ('QA-13', 'S', 'Misleading semantic duplication', 'P6 Addendum §10'),
  ('QA-17', 'S', 'Hindsight / unsupported knowledge', 'P6 Addendum §10'),
  ('S18', 'S', 'Claim normalisation fidelity against the original-language span', 'P6 Addendum §10'),
  ('S19', 'S', 'Attribution preservation', 'P6 Addendum §10'),
  ('S20', 'S', 'Reference-context semantic scope', 'P6 Addendum §10');

-- automatic fail conditions (Prompt Pack §47 / Addendum §12)
CREATE OR REPLACE FUNCTION lfhe.p6_autofail_codes()
RETURNS text[] LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
  SELECT ARRAY['UNSUPPORTED_FACT', 'FABRICATED_CITATION', 'MISSING_REQUIRED_PROVENANCE', 'POST_CUTOFF_EVIDENCE',
               'UNAPPROVED_ASSESSMENT', 'UNAUTHORISED_CONFIDENCE_CHANGE', 'PROHIBITED_INFORMATION',
               'UNPINNED_REQUIRED_VERSION', 'MATERIAL_EPISTEMIC_STRENGTH_INCREASE']
$$;

-- closed advisory vocabulary; never executed by anything
CREATE OR REPLACE FUNCTION lfhe.p6_recommended_actions()
RETURNS text[] LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
  SELECT ARRAY['NO_ACTION', 'RETURN_TO_ANALYST_FOR_REVISION', 'RESTORE_ATTRIBUTION', 'RESTORE_CAVEAT_OR_CONTRADICTION',
               'REMOVE_OR_SOURCE_UNSUPPORTED_CONTENT', 'CORRECT_CONFIDENCE_OR_LIKELIHOOD', 'REVIEW_DUPLICATION',
               'RE_RUN_QA', 'HUMAN_HANDLING_REVIEW', 'HUMAN_ANALYTICAL_REVIEW', 'RETURN_TO_ANALYTICAL_REVIEW']
$$;

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------
CREATE TABLE lfhe.qa_requests (
  id                   uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  report_id            uuid NOT NULL REFERENCES lfhe.reports(id),
  report_version_id    uuid NOT NULL,
  report_version_hash  text NOT NULL,
  requested_by         uuid NOT NULL,
  reason               text NOT NULL CHECK (length(btrim(reason)) >= 5),
  job_id               uuid REFERENCES lfhe.processing_jobs(id),
  created_at           timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (report_version_id, report_version_hash) REFERENCES lfhe.report_versions (id, report_version_hash)
);

CREATE TABLE lfhe.qa_runs (
  id                       uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  report_id                uuid NOT NULL REFERENCES lfhe.reports(id),
  report_version_id        uuid NOT NULL,
  report_version_hash      text NOT NULL,
  qa_request_id            uuid NOT NULL REFERENCES lfhe.qa_requests(id),
  kind                     text NOT NULL CHECK (kind IN ('D', 'S')),
  status                   text NOT NULL CHECK (status IN ('COMPLETED', 'INVALID')),
  engine_version           text,
  model_run_id             uuid UNIQUE REFERENCES lfhe.model_runs(id),
  prompt_version_id        uuid REFERENCES lfhe.prompt_versions(id),
  deterministic_qa_run_id  uuid REFERENCES lfhe.qa_runs(id),
  diagnostic_only          boolean NOT NULL DEFAULT false,
  invalid_reasons          text[] NOT NULL DEFAULT '{}',
  model_status             text,
  model_qa_status          text,          -- the model's own (advisory, non-authoritative) qa_status
  model_release_blocked    boolean,       -- the model's own (advisory, non-authoritative) flag
  repair_of_model_run_id   uuid REFERENCES lfhe.model_runs(id),
  created_at               timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id, report_version_id, report_version_hash),
  FOREIGN KEY (report_version_id, report_version_hash) REFERENCES lfhe.report_versions (id, report_version_hash),
  CHECK ((kind = 'D') = (model_run_id IS NULL AND prompt_version_id IS NULL AND deterministic_qa_run_id IS NULL)),
  CHECK (kind = 'D' OR (model_run_id IS NOT NULL AND prompt_version_id IS NOT NULL AND deterministic_qa_run_id IS NOT NULL)),
  CHECK ((kind = 'D') = (engine_version IS NOT NULL)),
  CHECK ((status = 'INVALID') = (cardinality(invalid_reasons) > 0))
);

CREATE TABLE lfhe.qa_check_results (
  id                     uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  qa_run_id              uuid NOT NULL REFERENCES lfhe.qa_runs(id),
  finding_no             integer NOT NULL CHECK (finding_no >= 1),
  check_id               text NOT NULL,
  layer                  text NOT NULL CHECK (layer IN ('D', 'S')),
  status                 text NOT NULL CHECK (status IN ('PASS', 'WARNING', 'FAIL')),
  severity               lfhe.challenge_severity NOT NULL,
  finding_code           text NOT NULL CHECK (finding_code ~ '^[A-Z][A-Z0-9_]{2,60}$'),
  affected_object_id     text,
  affected_statement_id  uuid REFERENCES lfhe.report_item_statements(id),
  details                text NOT NULL CHECK (length(btrim(details)) BETWEEN 1 AND 4000),
  evidence_refs          jsonb NOT NULL DEFAULT '[]' CHECK (pg_catalog.jsonb_typeof(evidence_refs) = 'array'),
  recommended_action     text NOT NULL CHECK (recommended_action = ANY (lfhe.p6_recommended_actions())),
  UNIQUE (qa_run_id, finding_no),
  FOREIGN KEY (check_id, layer) REFERENCES lfhe.qa_checks (check_id, layer),
  CHECK (severity <> 'CRITICAL' OR status = 'FAIL'),
  CHECK (status <> 'PASS' OR severity = 'INFO'),
  CHECK (status <> 'FAIL' OR severity IN ('MAJOR', 'CRITICAL')),
  CHECK (status <> 'WARNING' OR severity IN ('WARNING', 'MAJOR'))
);
CREATE INDEX qa_check_results_run_idx ON lfhe.qa_check_results (qa_run_id);

CREATE TABLE lfhe.qa_results (
  id                       uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  report_id                uuid NOT NULL REFERENCES lfhe.reports(id),
  report_version_id        uuid NOT NULL,
  report_version_hash      text NOT NULL,
  result_no                integer NOT NULL CHECK (result_no >= 1),
  qa_request_id            uuid NOT NULL REFERENCES lfhe.qa_requests(id),
  deterministic_qa_run_id  uuid NOT NULL,
  semantic_qa_run_id       uuid NOT NULL,
  status                   text NOT NULL CHECK (status IN ('PASS', 'PASS_WITH_WARNINGS', 'FAIL')),
  fail_reasons             text[] NOT NULL DEFAULT '{}',
  warning_finding_ids      uuid[] NOT NULL DEFAULT '{}',
  critical_count           integer NOT NULL,
  fail_count               integer NOT NULL,
  warning_count            integer NOT NULL,
  release_blocked          boolean NOT NULL,
  previous_qa_result_id    uuid REFERENCES lfhe.qa_results(id),
  changed_by_rerun         boolean NOT NULL,
  created_at               timestamptz NOT NULL DEFAULT now(),
  UNIQUE (report_version_id, result_no),
  UNIQUE (id, report_version_id, report_version_hash),
  UNIQUE (deterministic_qa_run_id, semantic_qa_run_id),
  FOREIGN KEY (report_version_id, report_version_hash) REFERENCES lfhe.report_versions (id, report_version_hash),
  FOREIGN KEY (deterministic_qa_run_id, report_version_id, report_version_hash)
    REFERENCES lfhe.qa_runs (id, report_version_id, report_version_hash),
  FOREIGN KEY (semantic_qa_run_id, report_version_id, report_version_hash)
    REFERENCES lfhe.qa_runs (id, report_version_id, report_version_hash),
  CHECK ((status = 'FAIL') = (cardinality(fail_reasons) > 0)),
  CHECK (release_blocked = (status = 'FAIL')),
  CHECK (status <> 'PASS' OR warning_count = 0),
  CHECK (status <> 'PASS_WITH_WARNINGS' OR (warning_count > 0 AND critical_count = 0 AND fail_count = 0))
);

CREATE TABLE lfhe.warning_acknowledgements (
  id                   uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  qa_result_id         uuid NOT NULL,
  qa_check_result_id   uuid NOT NULL REFERENCES lfhe.qa_check_results(id),
  report_version_id    uuid NOT NULL,
  report_version_hash  text NOT NULL,
  acknowledged_by      uuid NOT NULL,
  rationale            text NOT NULL CHECK (length(btrim(rationale)) >= 10),
  created_at           timestamptz NOT NULL DEFAULT now(),
  UNIQUE (qa_result_id, qa_check_result_id),
  FOREIGN KEY (qa_result_id, report_version_id, report_version_hash)
    REFERENCES lfhe.qa_results (id, report_version_id, report_version_hash)
);

DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['qa_checks', 'qa_requests', 'qa_runs', 'qa_check_results', 'qa_results', 'warning_acknowledgements'] LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON lfhe.%I FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation()',
                   t || '_immutable', t);
  END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------
-- the latest version of the report (stale versions are never QA'd, approved or released)
CREATE OR REPLACE FUNCTION lfhe.p6_is_latest_version(p_version uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT EXISTS (SELECT 1 FROM lfhe.report_versions v WHERE v.id = p_version
                 AND NOT EXISTS (SELECT 1 FROM lfhe.report_versions x WHERE x.report_id = v.report_id AND x.version_no > v.version_no))
$$;

-- the authoritative (current) combined QA result of a version: the latest one
CREATE OR REPLACE FUNCTION lfhe.p6_current_qa_result(p_version uuid)
RETURNS lfhe.qa_results LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT * FROM lfhe.qa_results WHERE report_version_id = p_version ORDER BY result_no DESC LIMIT 1
$$;

-- WARNING findings of a result that still need a human acknowledgement
CREATE OR REPLACE FUNCTION lfhe.p6_unacknowledged_warnings(p_result uuid)
RETURNS uuid[] LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT coalesce(ARRAY(SELECT x FROM lfhe.qa_results r, pg_catalog.unnest(r.warning_finding_ids) x
                        WHERE r.id = p_result
                          AND NOT EXISTS (SELECT 1 FROM lfhe.warning_acknowledgements a
                                          WHERE a.qa_result_id = r.id AND a.qa_check_result_id = x)
                        ORDER BY x), '{}')
$$;

-- classification / handling markings that must never appear in an OSINT-only product
CREATE OR REPLACE FUNCTION lfhe.p6_prohibited_marking(p text)
RETURNS boolean LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
  SELECT coalesce(p, '') ~ '(\mTOP SECRET\M|\mCOSMIC TOP SECRET\M|\mNATO (RESTRICTED|CONFIDENTIAL|SECRET|UNCLASSIFIED)\M|\mNOFORN\M|\mFOUO\M|\mREL TO\M|//[A-Z]|\m(SECRET|CONFIDENTIAL|RESTRICTED|CLASSIFIED)//|\(S\)|\(TS\)|\(C\)\s|\mNEMZETI MINŐSÍTETT\M|\mKORLÁTOZOTT TERJESZTÉSŰ\M|\mTITKOS!)'
$$;

CREATE OR REPLACE FUNCTION lfhe.p6_finding(p_check text, p_status text, p_severity text, p_code text, p_object text,
                                           p_statement uuid, p_details text, p_refs jsonb, p_action text)
RETURNS jsonb LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
  SELECT pg_catalog.jsonb_build_object('check_id', p_check, 'status', p_status, 'severity', p_severity, 'finding_code', p_code,
    'affected_object_id', p_object, 'affected_statement_id', p_statement, 'details', left(p_details, 4000),
    'evidence_refs', coalesce(p_refs, '[]'), 'recommended_action', p_action)
$$;

CREATE OR REPLACE FUNCTION lfhe.p6_ref(p_type text, p_id text)
RETURNS jsonb LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
  SELECT pg_catalog.jsonb_build_object('object_type', p_type, 'object_id', p_id)
$$;

-- map a Phase 5 validator problem onto the M10-D check / finding vocabulary (all FAIL CRITICAL)
CREATE OR REPLACE FUNCTION lfhe.p6_validator_finding(p_problem text)
RETURNS jsonb LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
  SELECT lfhe.p6_finding(m.c, 'FAIL', 'CRITICAL', m.code, NULL, NULL,
                         'Phase 5 content validator (re-run on the stored version): ' || p_problem, '[]', m.a)
  FROM (SELECT split_part(p_problem, ':', 1) AS k) x,
       LATERAL (SELECT CASE
         WHEN x.k IN ('CONFIDENCE_CHANGED', 'MERGE_ACROSS_CONFIDENCE_LEVELS', 'CONFIDENCE_MISSING_ON_KEY_JUDGMENT') THEN 'QA-08'
         WHEN x.k LIKE 'LIKELIHOOD_%' OR x.k = 'MERGE_ACROSS_LIKELIHOOD' THEN 'QA-08'
         WHEN x.k = 'ATTRIBUTION_REMOVED' THEN 'D19'
         WHEN x.k = 'UNSUPPORTED_NEW_FACT' THEN 'QA-17'
         WHEN x.k IN ('UNSUPPORTED_NEW_JUDGMENT', 'EPISTEMIC_STRENGTHENING') THEN 'QA-07'
         WHEN x.k IN ('REPORT_STATEMENT_WITHOUT_SOURCE', 'UNKNOWN_SOURCE_STATEMENT', 'SOURCE_STATEMENT_NOT_IN_SELECTED_CANDIDATE',
                      'SOURCE_CANDIDATE_NOT_SELECTED') THEN 'QA-01'
         WHEN x.k IN ('SELECTED_STATEMENT_OMITTED', 'CAVEAT_REMOVAL_PROHIBITED', 'CAVEAT_REMOVAL_FOR_LENGTH_PROHIBITED') THEN 'QA-09'
         ELSE 'STRUCTURE' END AS c,
       CASE
         WHEN x.k IN ('CONFIDENCE_CHANGED', 'MERGE_ACROSS_CONFIDENCE_LEVELS', 'CONFIDENCE_MISSING_ON_KEY_JUDGMENT') THEN 'UNAUTHORISED_CONFIDENCE_CHANGE'
         WHEN x.k LIKE 'LIKELIHOOD_%' OR x.k = 'MERGE_ACROSS_LIKELIHOOD' THEN 'UNAUTHORISED_LIKELIHOOD_CHANGE'
         WHEN x.k = 'ATTRIBUTION_REMOVED' THEN 'ATTRIBUTION_REMOVED'
         WHEN x.k = 'UNSUPPORTED_NEW_FACT' THEN 'UNSUPPORTED_FACT'
         WHEN x.k IN ('UNSUPPORTED_NEW_JUDGMENT', 'EPISTEMIC_STRENGTHENING') THEN 'MATERIAL_EPISTEMIC_STRENGTH_INCREASE'
         WHEN x.k = 'REPORT_STATEMENT_WITHOUT_SOURCE' THEN 'MISSING_REQUIRED_PROVENANCE'
         WHEN x.k IN ('UNKNOWN_SOURCE_STATEMENT', 'SOURCE_STATEMENT_NOT_IN_SELECTED_CANDIDATE', 'SOURCE_CANDIDATE_NOT_SELECTED') THEN 'FABRICATED_CITATION'
         WHEN x.k IN ('SELECTED_STATEMENT_OMITTED', 'CAVEAT_REMOVAL_PROHIBITED', 'CAVEAT_REMOVAL_FOR_LENGTH_PROHIBITED') THEN 'CONTRADICTION_OR_CAVEAT_REMOVED'
         ELSE 'REPORT_STRUCTURE_INVALID' END AS code,
       CASE
         WHEN x.k = 'ATTRIBUTION_REMOVED' THEN 'RESTORE_ATTRIBUTION'
         WHEN x.k LIKE '%CONFIDENCE%' OR x.k LIKE '%LIKELIHOOD%' THEN 'CORRECT_CONFIDENCE_OR_LIKELIHOOD'
         WHEN x.k IN ('SELECTED_STATEMENT_OMITTED', 'CAVEAT_REMOVAL_PROHIBITED', 'CAVEAT_REMOVAL_FOR_LENGTH_PROHIBITED') THEN 'RESTORE_CAVEAT_OR_CONTRADICTION'
         WHEN x.k IN ('UNSUPPORTED_NEW_FACT', 'UNSUPPORTED_NEW_JUDGMENT', 'EPISTEMIC_STRENGTHENING') THEN 'REMOVE_OR_SOURCE_UNSUPPORTED_CONTENT'
         ELSE 'RETURN_TO_ANALYST_FOR_REVISION' END AS a) m
$$;

-- ---------------------------------------------------------------------------
-- HUMAN_ONLY: request QA for the latest version (REPORT_EDIT or REPORT_CONTENT_APPROVE)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.request_report_qa(p_version uuid, p_hash text, p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.current_human_user();
  v       lfhe.report_versions;
  v_id    uuid;
  v_job   uuid;
BEGIN
  IF v_actor IS NULL THEN
    RAISE EXCEPTION 'human authentication required' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF NOT (lfhe.user_has_permission(v_actor, 'REPORT_EDIT') OR lfhe.user_has_permission(v_actor, 'REPORT_CONTENT_APPROVE')) THEN
    RAISE EXCEPTION 'permission REPORT_EDIT or REPORT_CONTENT_APPROVE required' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF p_reason IS NULL OR length(btrim(p_reason)) < 5 THEN
    RAISE EXCEPTION 'a reason is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  v := lfhe.p5_require_latest_version(p_version, p_hash);
  IF EXISTS (SELECT 1 FROM lfhe.report_version_states s WHERE s.report_version_id = v.id AND s.length_review_pending) THEN
    RAISE EXCEPTION 'LENGTH_REVIEW_PENDING: decide the removal proposals of version % first', v.id USING ERRCODE = 'check_violation';
  END IF;
  IF EXISTS (SELECT 1 FROM lfhe.report_releases x WHERE x.report_version_id = v.id) THEN
    RAISE EXCEPTION 'REPORT_VERSION_RELEASED: a released version is immutable; correct it with a new version'
      USING ERRCODE = 'check_violation';
  END IF;
  INSERT INTO lfhe.qa_requests (report_id, report_version_id, report_version_hash, requested_by, reason)
  VALUES (v.report_id, v.id, v.report_version_hash, v_actor, p_reason) RETURNING id INTO v_id;
  v_job := lfhe.enqueue_job('RUN_REPORT_QA', 'report_version', v.id::text, 'RUN_REPORT_QA:' || v_id,
    pg_catalog.jsonb_build_object('report_version_hash', v.report_version_hash, 'qa_request_id', v_id), 90::smallint, 3);
  PERFORM lfhe.write_audit('REPORT_QA_REQUESTED', 'report_version', v.id::text, NULL,
    pg_catalog.jsonb_build_object('qa_request_id', v_id, 'report_version_hash', v.report_version_hash, 'job_id', v_job,
                                  'reason', p_reason), '{}');
  RETURN pg_catalog.jsonb_build_object('qa_request_id', v_id, 'job_id', v_job);
END $$;
COMMENT ON FUNCTION lfhe.request_report_qa(uuid, text, text) IS 'HUMAN_ONLY';

-- ---------------------------------------------------------------------------
-- M10-D — deterministic QA engine (worker). Ordinary software: no model, no model_run.
-- Raises (and records nothing) on an unknown version, a hash mismatch or a foreign request.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.run_m10d(p_version uuid, p_hash text, p_request uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_engine  constant text := 'lfhe-m10d/1.0.0';
  v         lfhe.report_versions;
  r         lfhe.reports;
  q         lfhe.qa_requests;
  v_mode    text;
  v_cut     timestamptz;
  v_f       jsonb := '[]';
  v_run     uuid;
  v_n       integer := 0;
  v_x       jsonb;
  v_p       text;
  s         record;
  e         record;
  c         record;
  v_srcs    uuid[];
  v_csrcs   uuid[];
  v_cst     jsonb;
  v_cit     jsonb;
  v_confs   text[];
  v_terms   text[];
  v_txt     text;
  v_corpus  text;
  v_claims  uuid[];
  v_rcs     uuid[];
  v_avs     uuid[];
  v_ind     jsonb;
  v_probs   text[];
  v_cnt     integer;
  v_check   text;
BEGIN
  SELECT * INTO v FROM lfhe.report_versions WHERE id = p_version;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'REPORT_VERSION_NOT_FOUND: %', p_version USING ERRCODE = 'no_data_found';
  END IF;
  IF v.report_version_hash IS DISTINCT FROM p_hash THEN
    RAISE EXCEPTION 'VERSION_HASH_MISMATCH: report version %', p_version USING ERRCODE = 'serialization_failure';
  END IF;
  SELECT * INTO q FROM lfhe.qa_requests WHERE id = p_request;
  IF NOT FOUND OR q.report_version_id <> v.id OR q.report_version_hash <> v.report_version_hash THEN
    RAISE EXCEPTION 'QA_REQUEST_NOT_FOR_VERSION: %', p_request USING ERRCODE = 'check_violation';
  END IF;
  r := lfhe.p5_require_report(v.report_id);
  v_mode := v.report_mode::text;
  v_cut := v.information_cutoff;

  -- D23: exact binding; the version must still be the current one
  IF lfhe.jcs_sha256(v.canonical_json) IS DISTINCT FROM v.report_version_hash THEN
    v_f := v_f || lfhe.p6_finding('D23', 'FAIL', 'CRITICAL', 'VERSION_BINDING_INVALID', v.id::text, NULL,
                                  'stored canonical JSON does not hash to report_version_hash', '[]', 'RE_RUN_QA');
  END IF;
  IF NOT lfhe.p6_is_latest_version(v.id) THEN
    v_f := v_f || lfhe.p6_finding('D23', 'FAIL', 'CRITICAL', 'VERSION_NOT_CURRENT', v.id::text, NULL,
                                  'a newer version of the report exists; QA of a stale version cannot support release', '[]',
                                  'RE_RUN_QA');
  END IF;
  IF (v.canonical_json -> 'report' ->> 'report_id') IS DISTINCT FROM r.id::text
     OR (v.canonical_json -> 'report' ->> 'report_mode') IS DISTINCT FROM r.report_mode::text
     OR (v.canonical_json -> 'report' ->> 'information_cutoff') IS DISTINCT FROM lfhe.p5_ts(r.information_cutoff)
     OR v.report_mode <> r.report_mode OR v.information_cutoff <> r.information_cutoff THEN
    v_f := v_f || lfhe.p6_finding('D23', 'FAIL', 'CRITICAL', 'VERSION_BINDING_INVALID', v.id::text, NULL,
                                  'canonical report header does not match the report (id / mode / cutoff)', '[]', 'RE_RUN_QA');
  END IF;
  SELECT count(*) INTO v_cnt FROM lfhe.report_item_statements st JOIN lfhe.report_items i ON i.id = st.report_item_id
  WHERE i.report_version_id = v.id;
  IF v_cnt IS DISTINCT FROM (SELECT count(*) FROM pg_catalog.jsonb_array_elements(v.canonical_json -> 'sections') sec,
                                    pg_catalog.jsonb_array_elements(sec -> 'items') it, pg_catalog.jsonb_array_elements(it -> 'statements') st)::integer THEN
    v_f := v_f || lfhe.p6_finding('STRUCTURE', 'FAIL', 'CRITICAL', 'CANONICAL_TABLE_MISMATCH', v.id::text, NULL,
                                  'canonical JSON and report statement rows disagree', '[]', 'RE_RUN_QA');
  END IF;

  -- STRUCTURE / QA-08 / D19 / QA-17 / QA-07 / QA-01 / QA-09: the Phase 5 validator re-run on the stored content
  FOREACH v_p IN ARRAY lfhe.report_content_problems(v.selection_set_id, lfhe.report_version_content(v.id),
       ARRAY(SELECT x::uuid FROM pg_catalog.jsonb_array_elements_text(coalesce(v.canonical_json -> 'human_removals', '[]')) x),
       'HUMAN') LOOP
    v_f := v_f || lfhe.p6_validator_finding(v_p);
  END LOOP;
  IF (SELECT count(*) FROM lfhe.report_items i WHERE i.report_version_id = v.id AND i.section = 'KEY_JUDGMENT') > 3 THEN
    v_f := v_f || lfhe.p6_finding('STRUCTURE', 'FAIL', 'CRITICAL', 'REPORT_STRUCTURE_INVALID', v.id::text, NULL,
                                  'more than 3 Key Judgments', '[]', 'RETURN_TO_ANALYST_FOR_REVISION');
  END IF;
  IF EXISTS (SELECT 1 FROM pg_catalog.jsonb_array_elements(v.canonical_json -> 'sections') sec
             WHERE NOT ((sec ->> 'section') = ANY (enum_range(NULL::lfhe.report_section)::text[]))) THEN
    v_f := v_f || lfhe.p6_finding('STRUCTURE', 'FAIL', 'CRITICAL', 'REPORT_STRUCTURE_INVALID', v.id::text, NULL,
                                  'unknown section in canonical JSON', '[]', 'RETURN_TO_ANALYST_FOR_REVISION');
  END IF;
  IF v.length_review_required AND NOT EXISTS (SELECT 1 FROM lfhe.report_removal_decisions d WHERE d.report_version_id = v.id) THEN
    v_f := v_f || lfhe.p6_finding('STRUCTURE', 'FAIL', 'MAJOR', 'LENGTH_REVIEW_PENDING', v.id::text, NULL,
                                  'REPORT_LENGTH_REVIEW_REQUIRED has not been decided by a human', '[]',
                                  'RETURN_TO_ANALYST_FOR_REVISION');
  END IF;

  -- QA-11 / QA-16: pins and manifest prerequisites
  IF NOT EXISTS (SELECT 1 FROM lfhe.report_selection_sets ss WHERE ss.id = v.selection_set_id AND ss.content_hash = v.selection_set_hash) THEN
    v_f := v_f || lfhe.p6_finding('QA-11', 'FAIL', 'CRITICAL', 'UNPINNED_REQUIRED_VERSION', v.selection_set_id::text, NULL,
                                  'selection set id / hash does not resolve', '[]', 'RETURN_TO_ANALYST_FOR_REVISION');
  END IF;
  FOR s IN SELECT i.*, si.candidate_type, si.object_id, si.object_hash,
                  (SELECT it FROM pg_catalog.jsonb_array_elements(v.canonical_json -> 'sections') sec,
                          pg_catalog.jsonb_array_elements(sec -> 'items') it
                   WHERE it ->> 'item_local_id' = i.item_local_id LIMIT 1) AS citem
           FROM lfhe.report_items i
           LEFT JOIN lfhe.report_selection_set_items si ON si.selection_set_id = v.selection_set_id AND si.candidate_id = i.source_candidate_id
           WHERE i.report_version_id = v.id ORDER BY i.section, i.item_no LOOP
    IF s.candidate_type IS NULL THEN
      v_f := v_f || lfhe.p6_finding('QA-11', 'FAIL', 'CRITICAL', 'UNPINNED_REQUIRED_VERSION', s.id::text, NULL,
                                    'item candidate ' || s.source_candidate_id || ' is not in the pinned selection set', '[]',
                                    'RETURN_TO_ANALYST_FOR_REVISION');
      CONTINUE;
    END IF;
    IF lfhe.report_object_hash(s.candidate_type, s.object_id) IS DISTINCT FROM s.object_hash THEN
      v_f := v_f || lfhe.p6_finding('QA-11', 'FAIL', 'CRITICAL', 'UNPINNED_REQUIRED_VERSION', s.object_id::text, NULL,
                                    'selected object hash no longer resolves', '[]', 'RETURN_TO_ANALYST_FOR_REVISION');
    END IF;
    v_ind := lfhe.p5_candidate_pins(s.candidate_type, s.object_id);
    IF s.citem IS NULL OR (s.citem -> 'pins') IS DISTINCT FROM v_ind
       OR (v_ind -> 'assessment_version' ->> 'id') IS DISTINCT FROM s.pinned_assessment_version_id::text
       OR (v_ind -> 'assessment_version' ->> 'hash') IS DISTINCT FROM s.pinned_assessment_version_hash
       OR (v_ind -> 'event_version' ->> 'id') IS DISTINCT FROM s.pinned_event_version_id::text
       OR (v_ind -> 'event_version' ->> 'hash') IS DISTINCT FROM s.pinned_event_version_hash
       OR (v_ind -> 'indicator_version' ->> 'id') IS DISTINCT FROM s.pinned_indicator_version_id::text
       OR (v_ind -> 'trend_version' ->> 'id') IS DISTINCT FROM s.pinned_trend_version_id::text THEN
      v_f := v_f || lfhe.p6_finding('QA-11', 'FAIL', 'CRITICAL', 'UNPINNED_REQUIRED_VERSION', s.item_local_id, NULL,
                                    'item pins (canonical / stored / resolved) disagree', '[]', 'RETURN_TO_ANALYST_FOR_REVISION');
    END IF;
    IF s.pinned_event_version_id IS NOT NULL AND lfhe.event_version_stored_hash(s.pinned_event_version_id)
         IS DISTINCT FROM s.pinned_event_version_hash THEN
      v_f := v_f || lfhe.p6_finding('QA-11', 'FAIL', 'CRITICAL', 'UNPINNED_REQUIRED_VERSION', s.pinned_event_version_id::text, NULL,
                                    'pinned event version hash does not verify', '[]', 'RETURN_TO_ANALYST_FOR_REVISION');
    END IF;
    -- QA-10 for indicator / trend candidates (assessment versions are checked per source below)
    IF s.candidate_type <> 'ASSESSMENT_VERSION' AND NOT lfhe.report_candidate_eligible(s.candidate_type, s.object_id, v_mode, v_cut) THEN
      v_f := v_f || lfhe.p6_finding('QA-10', 'FAIL', 'CRITICAL', 'UNAPPROVED_ASSESSMENT', s.object_id::text, NULL,
                                    s.candidate_type || ' is not eligible / current as of the report cutoff', '[]',
                                    'RETURN_TO_ANALYTICAL_REVIEW');
    END IF;
    -- QA-08: item-level confidence
    IF s.pinned_assessment_version_id IS NOT NULL
       AND (s.citem ->> 'final_analytic_confidence') IS DISTINCT FROM lfhe.p5_final_confidence(s.pinned_assessment_version_id)::text THEN
      v_f := v_f || lfhe.p6_finding('QA-08', 'FAIL', 'CRITICAL', 'UNAUTHORISED_CONFIDENCE_CHANGE', s.item_local_id, NULL,
                                    'item confidence differs from the approved final_analytic_confidence', '[]',
                                    'CORRECT_CONFIDENCE_OR_LIKELIHOOD');
    END IF;
  END LOOP;

  -- QA-13 (deterministic portion): one event represented by several developments / merged or superseded events
  FOR c IN SELECT ev.event_id, array_agg(DISTINCT i.item_local_id ORDER BY i.item_local_id) AS items, count(DISTINCT i.id) AS n
           FROM lfhe.report_items i JOIN lfhe.event_versions ev ON ev.id = i.pinned_event_version_id
           WHERE i.report_version_id = v.id AND i.section IN ('KEY_JUDGMENT', 'SIGNIFICANT_DEVELOPMENT', 'INDICATOR_WARNING')
           GROUP BY ev.event_id HAVING count(DISTINCT i.id) > 1 LOOP
    v_f := v_f || lfhe.p6_finding('QA-13', 'WARNING', 'WARNING', 'DUPLICATE_EVENT_REPRESENTATION', c.event_id::text, NULL,
                                  'event appears in ' || c.n || ' report items: ' || array_to_string(c.items, ', '),
                                  pg_catalog.jsonb_build_array(lfhe.p6_ref('event', c.event_id::text)), 'REVIEW_DUPLICATION');
  END LOOP;
  FOR c IN SELECT rel.relationship_type::text AS t, rel.from_event_id, rel.to_event_id
           FROM lfhe.event_relationships rel
           WHERE rel.relationship_type IN ('MERGED_INTO', 'SUPERSEDED_BY')
             AND rel.from_event_id IN (SELECT ev.event_id FROM lfhe.report_items i JOIN lfhe.event_versions ev ON ev.id = i.pinned_event_version_id
                                       WHERE i.report_version_id = v.id)
             AND rel.to_event_id IN (SELECT ev.event_id FROM lfhe.report_items i JOIN lfhe.event_versions ev ON ev.id = i.pinned_event_version_id
                                     WHERE i.report_version_id = v.id) LOOP
    v_f := v_f || lfhe.p6_finding('QA-13', 'FAIL', 'MAJOR', 'MERGED_EVENT_DOUBLE_COUNTED', c.from_event_id::text, NULL,
                                  'event ' || c.from_event_id || ' ' || c.t || ' ' || c.to_event_id || ' and both are reported',
                                  pg_catalog.jsonb_build_array(lfhe.p6_ref('event', c.from_event_id::text), lfhe.p6_ref('event', c.to_event_id::text)),
                                  'REVIEW_DUPLICATION');
  END LOOP;

  -- QA-12: model-authored objects
  IF v.origin = 'MODEL' AND NOT EXISTS (
       SELECT 1 FROM lfhe.model_runs m JOIN lfhe.prompt_versions pv ON pv.id = m.prompt_version_id
       JOIN lfhe.model_configurations mc ON mc.id = m.model_configuration_id
       WHERE m.id = v.created_by_model_run_id AND m.status = 'SUCCEEDED' AND m.module_code = 'M09_EXECUTIVE_EDITOR'
         AND pv.content_hash = m.prompt_content_hash AND mc.config_hash = m.model_config_hash) THEN
    v_f := v_f || lfhe.p6_finding('QA-12', 'FAIL', 'CRITICAL', 'MISSING_REQUIRED_PROVENANCE', v.created_by_model_run_id::text, NULL,
                                  'M09 model run / prompt / model configuration does not resolve', '[]', 'RE_RUN_QA');
  END IF;
  FOR c IN SELECT DISTINCT st.model_run_id FROM lfhe.report_item_statements st JOIN lfhe.report_items i ON i.id = st.report_item_id
           WHERE i.report_version_id = v.id AND st.author_type = 'MODEL'
             AND NOT EXISTS (SELECT 1 FROM lfhe.model_runs m WHERE m.id = st.model_run_id AND m.status = 'SUCCEEDED'
                             AND m.module_code = 'M09_EXECUTIVE_EDITOR') LOOP
    v_f := v_f || lfhe.p6_finding('QA-12', 'FAIL', 'CRITICAL', 'MISSING_REQUIRED_PROVENANCE', c.model_run_id::text, NULL,
                                  'model-authored report statement without a succeeded M09 run', '[]', 'RE_RUN_QA');
  END LOOP;

  -- statement-level checks
  FOR s IN SELECT st.*, i.section, i.item_local_id, i.source_candidate_id, i.pinned_assessment_version_id AS pav
           FROM lfhe.report_item_statements st JOIN lfhe.report_items i ON i.id = st.report_item_id
           WHERE i.report_version_id = v.id ORDER BY i.section, i.item_no, st.statement_no LOOP
    v_srcs := ARRAY(SELECT x.assessment_statement_id FROM lfhe.report_statement_sources x
                    WHERE x.report_item_statement_id = s.id ORDER BY 1);
    SELECT st2 INTO v_cst FROM pg_catalog.jsonb_array_elements(v.canonical_json -> 'sections') sec,
           pg_catalog.jsonb_array_elements(sec -> 'items') it, pg_catalog.jsonb_array_elements(it -> 'statements') st2
    WHERE it ->> 'item_local_id' = s.item_local_id AND st2 ->> 'report_statement_local_id' = s.report_statement_local_id LIMIT 1;
    v_csrcs := ARRAY(SELECT y::uuid FROM pg_catalog.jsonb_array_elements_text(coalesce(v_cst -> 'sources', '[]')) y ORDER BY 1);
    v_txt := s.statement_text;
    -- QA-01 deterministic
    IF cardinality(v_srcs) = 0 THEN
      v_f := v_f || lfhe.p6_finding('QA-01', 'FAIL', 'CRITICAL', 'MISSING_REQUIRED_PROVENANCE', s.report_statement_local_id, s.id,
                                    'report statement without an approved assessment-statement mapping', '[]',
                                    'RETURN_TO_ANALYST_FOR_REVISION');
      CONTINUE;
    END IF;
    IF v_cst IS NULL OR v_csrcs IS DISTINCT FROM v_srcs OR (v_cst ->> 'text') IS DISTINCT FROM v_txt
       OR (v_cst ->> 'statement_role') IS DISTINCT FROM s.statement_role::text
       OR (v_cst ->> 'likelihood_term') IS DISTINCT FROM s.likelihood_term THEN
      v_f := v_f || lfhe.p6_finding('QA-01', 'FAIL', 'CRITICAL', 'FABRICATED_CITATION', s.report_statement_local_id, s.id,
                                    'canonical statement and stored mapping disagree', '[]', 'RETURN_TO_ANALYST_FOR_REVISION');
    END IF;
    FOR c IN SELECT x.*, a.id AS aid, a.assessment_version_id AS av, a.statement_type, a.statement_text, a.attribution_required,
                    a.attribution_text, a.evidence_required, a.likelihood_term AS lt, a.epistemic_category
             FROM lfhe.report_statement_sources x LEFT JOIN lfhe.assessment_statements a ON a.id = x.assessment_statement_id
             WHERE x.report_item_statement_id = s.id LOOP
      IF c.aid IS NULL OR c.av IS DISTINCT FROM c.assessment_version_id THEN
        v_f := v_f || lfhe.p6_finding('QA-02', 'FAIL', 'CRITICAL', 'MISSING_REQUIRED_PROVENANCE', c.assessment_statement_id::text, s.id,
                                      'cited assessment statement does not resolve to its assessment version', '[]',
                                      'RETURN_TO_ANALYST_FOR_REVISION');
        CONTINUE;
      END IF;
      IF NOT EXISTS (SELECT 1 FROM lfhe.report_selection_set_items si
                     JOIN LATERAL lfhe.report_candidate_statements(si.candidate_type, si.object_id) cs ON cs.statement_id = c.aid
                     WHERE si.selection_set_id = v.selection_set_id AND si.candidate_id = s.source_candidate_id) THEN
        v_f := v_f || lfhe.p6_finding('QA-01', 'FAIL', 'CRITICAL', 'FABRICATED_CITATION', c.aid::text, s.id,
                                      'cited statement does not belong to the item''s selected candidate',
                                      pg_catalog.jsonb_build_array(lfhe.p6_ref('assessment_statement', c.aid::text)),
                                      'RETURN_TO_ANALYST_FOR_REVISION');
      END IF;
      IF c.evidence_required AND NOT EXISTS (SELECT 1 FROM lfhe.assessment_statement_evidence ev
                                             WHERE ev.statement_id = c.aid AND ev.role = 'SUPPORTS') THEN
        v_f := v_f || lfhe.p6_finding('QA-01', 'FAIL', 'CRITICAL', 'MISSING_REQUIRED_PROVENANCE', c.aid::text, s.id,
                                      'evidence-required assessment statement without supporting evidence',
                                      pg_catalog.jsonb_build_array(lfhe.p6_ref('assessment_statement', c.aid::text)),
                                      'RETURN_TO_ANALYTICAL_REVIEW');
      END IF;
      -- QA-10 / QA-04 / D21 / D22 per source assessment version
      IF NOT lfhe.assessment_version_approved_asof(c.av, v_mode, v_cut) THEN
        v_f := v_f || lfhe.p6_finding('QA-10', 'FAIL', 'CRITICAL', 'UNAPPROVED_ASSESSMENT', c.av::text, s.id,
                                      'source assessment version is not the approved, current version as of the report cutoff',
                                      pg_catalog.jsonb_build_array(lfhe.p6_ref('assessment_version', c.av::text)),
                                      'RETURN_TO_ANALYTICAL_REVIEW');
      END IF;
      IF NOT lfhe.assessment_version_eligible(c.av, v_mode, v_cut) THEN
        v_f := v_f || lfhe.p6_finding('QA-04', 'FAIL', 'CRITICAL', 'POST_CUTOFF_EVIDENCE', c.av::text, s.id,
                                      'source assessment version (or its inputs) is not eligible for ' || v_mode || ' cutoff '
                                      || lfhe.p5_ts(v_cut), pg_catalog.jsonb_build_array(lfhe.p6_ref('assessment_version', c.av::text)),
                                      'RETURN_TO_ANALYTICAL_REVIEW');
      END IF;
      -- QA-07: authoritative state of the source assessment version
      IF lfhe.assessment_version_state(c.av)::text IS DISTINCT FROM 'APPROVED' THEN
        v_f := v_f || lfhe.p6_finding('QA-07', 'FAIL', 'MAJOR', 'EPISTEMIC_STATE_INCONSISTENT', c.av::text, s.id,
                                      'source assessment version state is ' || coalesce(lfhe.assessment_version_state(c.av)::text, 'none'),
                                      pg_catalog.jsonb_build_array(lfhe.p6_ref('assessment_version', c.av::text)),
                                      'RETURN_TO_ANALYTICAL_REVIEW');
      END IF;
      IF c.epistemic_category IS DISTINCT FROM lfhe.statement_category(c.statement_type) THEN
        v_f := v_f || lfhe.p6_finding('QA-07', 'FAIL', 'MAJOR', 'EPISTEMIC_STATE_INCONSISTENT', c.aid::text, s.id,
                                      'assessment statement category does not match its type', '[]', 'RETURN_TO_ANALYTICAL_REVIEW');
      END IF;
      -- D19: attribution required upstream must survive; omission must be deterministically justified
      IF c.attribution_required AND pg_catalog.strpos(lower(v_txt), lower(coalesce(c.attribution_text, chr(1)))) = 0 THEN
        v_f := v_f || lfhe.p6_finding('D19', 'FAIL', 'CRITICAL', 'ATTRIBUTION_REMOVED', c.aid::text, s.id,
                                      'required attribution "' || coalesce(c.attribution_text, '') || '" is missing',
                                      pg_catalog.jsonb_build_array(lfhe.p6_ref('assessment_statement', c.aid::text)), 'RESTORE_ATTRIBUTION');
      END IF;
      v_claims := ARRAY(SELECT ev.object_id FROM lfhe.assessment_statement_evidence ev
                        WHERE ev.statement_id = c.aid AND ev.object_type = 'claim' AND ev.role = 'SUPPORTS');
      v_rcs := ARRAY(SELECT ev.object_id FROM lfhe.assessment_statement_evidence ev
                     WHERE ev.statement_id = c.aid AND ev.object_type = 'reference_context_version' AND ev.role = 'SUPPORTS');
      IF NOT c.attribution_required AND lfhe.p4_attribution_required(c.statement_type, v_claims, v_rcs, v_mode, v_cut) THEN
        v_f := v_f || lfhe.p6_finding('D19', 'FAIL', 'CRITICAL', 'ATTRIBUTION_OMISSION_UNSUPPORTED', c.aid::text, s.id,
                                      'attribution was omitted but the supporting claims are not corroborated as of the cutoff',
                                      pg_catalog.jsonb_build_array(lfhe.p6_ref('assessment_statement', c.aid::text)), 'RESTORE_ATTRIBUTION');
      END IF;
    END LOOP;
    -- QA-08: confidence / likelihood values (statement level)
    v_confs := ARRAY(SELECT DISTINCT lfhe.p5_final_confidence(x.assessment_version_id)::text FROM lfhe.report_statement_sources x
                     WHERE x.report_item_statement_id = s.id);
    IF cardinality(v_confs) <> 1 OR v_confs[1] IS NULL
       OR ((v_cst ->> 'final_analytic_confidence') IS NOT NULL AND (v_cst ->> 'final_analytic_confidence') <> v_confs[1])
       OR (s.statement_role = 'KEY_JUDGMENT' AND (v_cst ->> 'final_analytic_confidence') IS NULL) THEN
      v_f := v_f || lfhe.p6_finding('QA-08', 'FAIL', 'CRITICAL', 'UNAUTHORISED_CONFIDENCE_CHANGE', s.report_statement_local_id, s.id,
                                    'statement confidence is not the single approved final_analytic_confidence of its sources', '[]',
                                    'CORRECT_CONFIDENCE_OR_LIKELIHOOD');
    END IF;
    v_terms := ARRAY(SELECT DISTINCT a.likelihood_term FROM lfhe.report_statement_sources x
                     JOIN lfhe.assessment_statements a ON a.id = x.assessment_statement_id
                     WHERE x.report_item_statement_id = s.id AND a.likelihood_term IS NOT NULL);
    IF cardinality(v_terms) > 1 OR s.likelihood_term IS DISTINCT FROM v_terms[1] THEN
      v_f := v_f || lfhe.p6_finding('QA-08', 'FAIL', 'CRITICAL', 'UNAUTHORISED_LIKELIHOOD_CHANGE', s.report_statement_local_id, s.id,
                                    'statement likelihood ' || coalesce(s.likelihood_term, 'none') || ' differs from the approved term '
                                    || coalesce(array_to_string(v_terms, '/'), 'none'), '[]', 'CORRECT_CONFIDENCE_OR_LIKELIHOOD');
    END IF;
    -- QA-07: contested flag consistent with the current evidence state
    IF s.contested IS DISTINCT FROM EXISTS (SELECT 1 FROM pg_catalog.unnest(v_srcs) z WHERE lfhe.p5_statement_contested(z)) THEN
      v_f := v_f || lfhe.p6_finding('QA-07', 'FAIL', 'MAJOR', 'EPISTEMIC_STATE_INCONSISTENT', s.report_statement_local_id, s.id,
                                    'contested flag does not match the contradicting-evidence state', '[]', 'RE_RUN_QA');
    END IF;
    -- QA-06: every number must occur in the statement's own approved sources or their supporting claims
    SELECT lower(coalesce(string_agg(a.statement_text || ' ' || coalesce(a.attribution_text, ''), ' '), '')) INTO v_corpus
    FROM lfhe.assessment_statements a WHERE a.id = ANY (v_srcs);
    SELECT v_corpus || ' ' || lower(coalesce(string_agg(cl.claim_text_normalised || ' ' || cl.claim_text_original || ' '
                                                        || coalesce(cl.quantity::text, ''), ' '), '')) INTO v_corpus
    FROM lfhe.assessment_statement_evidence ev JOIN lfhe.claims cl ON cl.id = ev.object_id
    WHERE ev.statement_id = ANY (v_srcs) AND ev.object_type = 'claim';
    FOR c IN SELECT DISTINCT (pg_catalog.regexp_matches(v_txt, '\d+(?:[.,]\d+)?', 'g'))[1] AS w LOOP
      IF pg_catalog.strpos(v_corpus, c.w) = 0 THEN
        v_f := v_f || lfhe.p6_finding('QA-06', 'FAIL', 'CRITICAL', 'UNSUPPORTED_FACT', s.report_statement_local_id, s.id,
                                      'number "' || c.w || '" is not in the statement''s approved sources or their evidence', '[]',
                                      'REMOVE_OR_SOURCE_UNSUPPORTED_CONTENT');
      END IF;
    END LOOP;
    -- QA-05: corroboration / independence wording must match the approved lineage state
    IF lower(v_txt) ~ '\m(independent(ly)?|corroborat\w*|confirmed by|multiple sources|several sources|separately confirmed)' THEN
      v_claims := ARRAY(SELECT DISTINCT ev.object_id FROM lfhe.assessment_statement_evidence ev
                        WHERE ev.statement_id = ANY (v_srcs) AND ev.object_type = 'claim' AND ev.role = 'SUPPORTS');
      v_ind := lfhe.independence_summary_asof(v_claims, v_mode, v_cut);
      IF NOT EXISTS (SELECT 1 FROM lfhe.assessment_statements a WHERE a.id = ANY (v_srcs)
                     AND lower(a.statement_text) ~ '\m(independent(ly)?|corroborat\w*|confirmed by|multiple sources|several sources|separately confirmed)') THEN
        v_f := v_f || lfhe.p6_finding('QA-05', 'FAIL', 'CRITICAL', 'FALSE_INDEPENDENT_CONFIRMATION', s.report_statement_local_id, s.id,
                                      'corroboration / independence wording not present in the approved sources; lineage: ' || v_ind::text,
                                      '[]', 'REMOVE_OR_SOURCE_UNSUPPORTED_CONTENT');
      ELSIF (v_ind ->> 'claims_with_unknown_lineage')::integer > 0 OR (v_ind ->> 'distinct_groups_upper_bound')::integer < 2 THEN
        v_f := v_f || lfhe.p6_finding('QA-05', 'WARNING', 'WARNING', 'INDEPENDENCE_REPRESENTATION_UNVERIFIED', s.report_statement_local_id,
                                      s.id, 'approved corroboration wording; validated lineage does not establish two independent groups: '
                                      || v_ind::text, '[]', 'HUMAN_ANALYTICAL_REVIEW');
      END IF;
    END IF;
    -- QA-14: prohibited markings in report text
    IF lfhe.p6_prohibited_marking(v_txt) THEN
      v_f := v_f || lfhe.p6_finding('QA-14', 'FAIL', 'CRITICAL', 'PROHIBITED_INFORMATION', s.report_statement_local_id, s.id,
                                    'classification / handling marking in report text (OSINT-only product)', '[]', 'HUMAN_HANDLING_REVIEW');
    END IF;
  END LOOP;

  -- evidence-level checks over every claim / baseline / reference context behind the cited statements
  v_avs := ARRAY(SELECT DISTINCT x.assessment_version_id FROM lfhe.report_statement_sources x
                 JOIN lfhe.report_item_statements st ON st.id = x.report_item_statement_id
                 JOIN lfhe.report_items i ON i.id = st.report_item_id WHERE i.report_version_id = v.id);
  FOR e IN SELECT DISTINCT ev.object_type, ev.object_id, ev.statement_id
           FROM lfhe.report_statement_sources x JOIN lfhe.report_item_statements st ON st.id = x.report_item_statement_id
           JOIN lfhe.report_items i ON i.id = st.report_item_id
           JOIN lfhe.assessment_statement_evidence ev ON ev.statement_id = x.assessment_statement_id
           WHERE i.report_version_id = v.id ORDER BY 1, 2, 3 LOOP
    IF e.object_type = 'claim' THEN
      SELECT cl.*, src.id AS src_id, src.access_restrictions, src.source_type, snap.id AS snap_id, art.id AS art_id,
             st.high_impact, st.status_human_confirmed, st.revalidation_pending, st.review_state
      INTO c FROM lfhe.claims cl
      LEFT JOIN lfhe.article_snapshots snap ON snap.id = cl.article_snapshot_id
      LEFT JOIN lfhe.articles art ON art.id = cl.article_id
      LEFT JOIN lfhe.sources src ON src.id = cl.source_id
      LEFT JOIN lfhe.claim_state st ON st.claim_id = cl.id
      WHERE cl.id = e.object_id;
      IF c.id IS NULL OR c.snap_id IS NULL OR c.art_id IS NULL OR c.src_id IS NULL THEN
        v_f := v_f || lfhe.p6_finding('QA-02', 'FAIL', 'CRITICAL', 'MISSING_REQUIRED_PROVENANCE', e.object_id::text, NULL,
                                      'evidence claim / snapshot / article / source does not resolve',
                                      pg_catalog.jsonb_build_array(lfhe.p6_ref('claim', e.object_id::text)), 'RETURN_TO_ANALYTICAL_REVIEW');
        CONTINUE;
      END IF;
      IF NOT lfhe.claim_cutoff_eligible(c.id, v_mode, v_cut) THEN
        v_f := v_f || lfhe.p6_finding('QA-04', 'FAIL', 'CRITICAL', 'POST_CUTOFF_EVIDENCE', c.id::text, NULL,
                                      'evidence snapshot is not eligible for ' || v_mode || ' cutoff ' || lfhe.p5_ts(v_cut),
                                      pg_catalog.jsonb_build_array(lfhe.p6_ref('claim', c.id::text), lfhe.p6_ref('article_snapshot', c.snap_id::text)),
                                      'RETURN_TO_ANALYTICAL_REVIEW');
      END IF;
      v_probs := lfhe.claim_grounding_problems(c.text_representation_id, c.article_snapshot_id, c.article_id, c.source_id,
                   c.language_original, c.span_locator_type, c.span_start, c.span_end, c.span_exact_text, c.claim_text_original);
      IF cardinality(v_probs) > 0 THEN
        v_f := v_f || lfhe.p6_finding('D18', 'FAIL', 'CRITICAL', 'MISSING_REQUIRED_PROVENANCE', c.id::text, NULL,
                                      'original-language grounding no longer verifies: ' || array_to_string(v_probs, ', '),
                                      pg_catalog.jsonb_build_array(lfhe.p6_ref('claim', c.id::text)), 'RETURN_TO_ANALYTICAL_REVIEW');
      END IF;
      IF c.high_impact AND (c.revalidation_pending OR NOT c.status_human_confirmed
                            OR c.review_state NOT IN ('VALIDATED', 'MODIFIED')) THEN
        v_f := v_f || lfhe.p6_finding('D20', 'FAIL', 'CRITICAL', 'HIGH_IMPACT_VALIDATION_MISSING', c.id::text, NULL,
                                      'high-impact evidence claim without completed human validation (review '
                                      || coalesce(c.review_state, 'PENDING') || ', revalidation pending ' || c.revalidation_pending || ')',
                                      pg_catalog.jsonb_build_array(lfhe.p6_ref('claim', c.id::text)), 'RETURN_TO_ANALYTICAL_REVIEW');
      END IF;
      IF coalesce(btrim(c.access_restrictions), '') <> '' THEN
        v_f := v_f || lfhe.p6_finding('QA-14', 'WARNING', 'MAJOR', 'OSINT_HANDLING_REVIEW_REQUIRED', c.src_id::text, NULL,
                                      'evidence source declares access restrictions; human handling review required',
                                      pg_catalog.jsonb_build_array(lfhe.p6_ref('claim', c.id::text)), 'HUMAN_HANDLING_REVIEW');
      END IF;
      IF lfhe.p6_prohibited_marking(c.claim_text_original) OR lfhe.p6_prohibited_marking(c.span_exact_text) THEN
        v_f := v_f || lfhe.p6_finding('QA-14', 'FAIL', 'CRITICAL', 'PROHIBITED_INFORMATION', c.id::text, NULL,
                                      'classification / handling marking in evidence text', pg_catalog.jsonb_build_array(lfhe.p6_ref('claim', c.id::text)),
                                      'HUMAN_HANDLING_REVIEW');
      END IF;
      -- QA-03: evidence must have been retrieved before this report version was written
      IF EXISTS (SELECT 1 FROM lfhe.article_snapshots sn WHERE sn.id = c.article_snapshot_id
                 AND sn.system_retrieval_datetime > v.created_at) THEN
        v_f := v_f || lfhe.p6_finding('QA-03', 'FAIL', 'MAJOR', 'DATE_INCONSISTENT', c.id::text, NULL,
                                      'evidence retrieved after the report version was created',
                                      pg_catalog.jsonb_build_array(lfhe.p6_ref('article_snapshot', c.article_snapshot_id::text)), 'RE_RUN_QA');
      END IF;
    ELSIF e.object_type = 'baseline_version' THEN
      IF NOT EXISTS (SELECT 1 FROM lfhe.baseline_versions b WHERE b.id = e.object_id) THEN
        v_f := v_f || lfhe.p6_finding('QA-02', 'FAIL', 'CRITICAL', 'MISSING_REQUIRED_PROVENANCE', e.object_id::text, NULL,
                                      'baseline version does not resolve', '[]', 'RETURN_TO_ANALYTICAL_REVIEW');
      ELSIF NOT lfhe.baseline_version_usable(e.object_id, v_mode, v_cut) THEN
        v_f := v_f || lfhe.p6_finding('D21', 'FAIL', 'CRITICAL', 'POST_CUTOFF_EVIDENCE', e.object_id::text, NULL,
                                      'baseline version is not eligible as of the report cutoff',
                                      pg_catalog.jsonb_build_array(lfhe.p6_ref('baseline_version', e.object_id::text)), 'RETURN_TO_ANALYTICAL_REVIEW');
      END IF;
    ELSE
      IF NOT EXISTS (SELECT 1 FROM lfhe.reference_context_versions rc WHERE rc.id = e.object_id) THEN
        v_f := v_f || lfhe.p6_finding('QA-02', 'FAIL', 'CRITICAL', 'MISSING_REQUIRED_PROVENANCE', e.object_id::text, NULL,
                                      'reference context version does not resolve', '[]', 'RETURN_TO_ANALYTICAL_REVIEW');
      ELSIF NOT lfhe.reference_context_version_usable(e.object_id, v_mode, v_cut) THEN
        v_f := v_f || lfhe.p6_finding('D22', 'FAIL', 'CRITICAL', 'POST_CUTOFF_EVIDENCE', e.object_id::text, NULL,
                                      'reference context version is not eligible (knowledge_as_of / approval) as of the report cutoff',
                                      pg_catalog.jsonb_build_array(lfhe.p6_ref('reference_context_version', e.object_id::text)),
                                      'RETURN_TO_ANALYTICAL_REVIEW');
      END IF;
    END IF;
  END LOOP;
  -- baselines / reference contexts / model runs of the cited assessment versions
  FOR c IN SELECT av.id, av.baseline_version_id, av.origin, av.created_by_model_run_id, av.created_at,
                  (SELECT a.created_at FROM lfhe.analytical_approvals a WHERE a.assessment_version_id = av.id
                   AND a.decision IN ('APPROVE', 'MODIFY_AND_APPROVE')) AS approved_at
           FROM lfhe.assessment_versions av WHERE av.id = ANY (v_avs) LOOP
    IF c.baseline_version_id IS NOT NULL AND NOT lfhe.baseline_version_usable(c.baseline_version_id, v_mode, v_cut) THEN
      v_f := v_f || lfhe.p6_finding('D21', 'FAIL', 'CRITICAL', 'POST_CUTOFF_EVIDENCE', c.baseline_version_id::text, NULL,
                                    'assessment baseline version is not eligible as of the report cutoff',
                                    pg_catalog.jsonb_build_array(lfhe.p6_ref('baseline_version', c.baseline_version_id::text)),
                                    'RETURN_TO_ANALYTICAL_REVIEW');
    END IF;
    FOR e IN SELECT arc.reference_context_version_id AS id FROM lfhe.assessment_reference_contexts arc
             WHERE arc.assessment_version_id = c.id LOOP
      IF NOT lfhe.reference_context_version_usable(e.id, v_mode, v_cut) THEN
        v_f := v_f || lfhe.p6_finding('D22', 'FAIL', 'CRITICAL', 'POST_CUTOFF_EVIDENCE', e.id::text, NULL,
                                      'reference context version supplied to the assessment is not eligible as of the report cutoff',
                                      pg_catalog.jsonb_build_array(lfhe.p6_ref('reference_context_version', e.id::text)),
                                      'RETURN_TO_ANALYTICAL_REVIEW');
      END IF;
    END LOOP;
    IF c.origin = 'AI' AND NOT EXISTS (
         SELECT 1 FROM lfhe.model_runs m JOIN lfhe.prompt_versions pv ON pv.id = m.prompt_version_id
         WHERE m.id = c.created_by_model_run_id AND m.status = 'SUCCEEDED' AND m.module_code = 'M07_INTELLIGENCE_ASSESSOR'
           AND pv.content_hash = m.prompt_content_hash) THEN
      v_f := v_f || lfhe.p6_finding('QA-12', 'FAIL', 'CRITICAL', 'MISSING_REQUIRED_PROVENANCE', c.id::text, NULL,
                                    'AI assessment version without a succeeded, traceable M07 run',
                                    pg_catalog.jsonb_build_array(lfhe.p6_ref('assessment_version', c.id::text)), 'RE_RUN_QA');
    END IF;
    IF c.approved_at IS NULL OR c.approved_at < c.created_at OR c.approved_at > v.created_at THEN
      v_f := v_f || lfhe.p6_finding('QA-03', 'FAIL', 'MAJOR', 'DATE_INCONSISTENT', c.id::text, NULL,
                                    'analytical approval time is inconsistent with the assessment / report version times',
                                    pg_catalog.jsonb_build_array(lfhe.p6_ref('assessment_version', c.id::text)), 'RE_RUN_QA');
    END IF;
  END LOOP;
  -- QA-14: markings in cited assessment statements
  FOR c IN SELECT a.id FROM lfhe.assessment_statements a WHERE a.assessment_version_id = ANY (v_avs)
           AND (lfhe.p6_prohibited_marking(a.statement_text) OR lfhe.p6_prohibited_marking(a.attribution_text)) LOOP
    v_f := v_f || lfhe.p6_finding('QA-14', 'FAIL', 'CRITICAL', 'PROHIBITED_INFORMATION', c.id::text, NULL,
                                  'classification / handling marking in an approved assessment statement',
                                  pg_catalog.jsonb_build_array(lfhe.p6_ref('assessment_statement', c.id::text)), 'HUMAN_HANDLING_REVIEW');
  END LOOP;

  -- QA-17 aggregate (hindsight): any cutoff / baseline / reference-context / unsupported-fact failure
  IF EXISTS (SELECT 1 FROM pg_catalog.jsonb_array_elements(v_f) x
             WHERE x ->> 'finding_code' = 'POST_CUTOFF_EVIDENCE' AND x ->> 'check_id' IN ('QA-04', 'D21', 'D22')) THEN
    v_f := v_f || lfhe.p6_finding('QA-17', 'FAIL', 'CRITICAL', 'POST_CUTOFF_EVIDENCE', v.id::text, NULL,
                                  'report depends on evidence / baseline / reference context not eligible at the cutoff', '[]',
                                  'RETURN_TO_ANALYTICAL_REVIEW');
  END IF;

  -- D24 / D25 / QA-16: prerequisites only (approvals and the manifest do not exist yet — DC6-03)
  IF EXISTS (SELECT 1 FROM lfhe.report_renders rr WHERE rr.report_version_id = v.id AND rr.report_version_hash <> v.report_version_hash) THEN
    v_f := v_f || lfhe.p6_finding('QA-16', 'FAIL', 'CRITICAL', 'MANIFEST_PREREQUISITE_MISSING', v.id::text, NULL,
                                  'a render is bound to a different hash', '[]', 'RE_RUN_QA');
  END IF;
  IF v.selection_set_id IS NULL OR r.information_cutoff IS NULL OR (v.origin = 'MODEL' AND v.created_by_model_run_id IS NULL) THEN
    v_f := v_f || lfhe.p6_finding('D25', 'FAIL', 'CRITICAL', 'MANIFEST_PREREQUISITE_MISSING', v.id::text, NULL,
                                  'manifest inputs (selection set, cutoff, authoring run) are incomplete', '[]', 'RE_RUN_QA');
  END IF;

  -- PASS rows for every deterministic check without a finding (coverage is visible)
  FOR v_check IN SELECT check_id FROM lfhe.qa_checks WHERE layer = 'D' ORDER BY check_id LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.jsonb_array_elements(v_f) x WHERE x ->> 'check_id' = v_check) THEN
      v_f := v_f || lfhe.p6_finding(v_check, 'PASS', 'INFO', 'CHECK_PASSED', NULL, NULL,
                                    CASE v_check WHEN 'D24' THEN 'no human approval exists yet for this version (bound at decision time)'
                                                 WHEN 'D25' THEN 'manifest prerequisites present; completeness is re-checked at release'
                                                 WHEN 'QA-16' THEN 'manifest structure is validated in the release transaction (DC6-03)'
                                                 ELSE 'no deterministic finding' END, '[]', 'NO_ACTION');
    END IF;
  END LOOP;

  INSERT INTO lfhe.qa_runs (report_id, report_version_id, report_version_hash, qa_request_id, kind, status, engine_version)
  VALUES (v.report_id, v.id, v.report_version_hash, q.id, 'D', 'COMPLETED', v_engine) RETURNING id INTO v_run;
  FOR v_x IN SELECT x FROM pg_catalog.jsonb_array_elements(v_f) WITH ORDINALITY t(x, o)
             ORDER BY CASE x ->> 'status' WHEN 'FAIL' THEN 0 WHEN 'WARNING' THEN 1 ELSE 2 END, x ->> 'check_id', o LOOP
    v_n := v_n + 1;
    INSERT INTO lfhe.qa_check_results (qa_run_id, finding_no, check_id, layer, status, severity, finding_code,
      affected_object_id, affected_statement_id, details, evidence_refs, recommended_action)
    VALUES (v_run, v_n, v_x ->> 'check_id', 'D', v_x ->> 'status', (v_x ->> 'severity')::lfhe.challenge_severity,
      v_x ->> 'finding_code', v_x ->> 'affected_object_id', (v_x ->> 'affected_statement_id')::uuid, v_x ->> 'details',
      v_x -> 'evidence_refs', v_x ->> 'recommended_action');
  END LOOP;
  RETURN pg_catalog.jsonb_build_object('qa_run_id', v_run, 'findings', v_n,
    'critical', (SELECT count(*) FROM lfhe.qa_check_results WHERE qa_run_id = v_run AND severity = 'CRITICAL'),
    'fail', (SELECT count(*) FROM lfhe.qa_check_results WHERE qa_run_id = v_run AND status = 'FAIL'),
    'warning', (SELECT count(*) FROM lfhe.qa_check_results WHERE qa_run_id = v_run AND status = 'WARNING'));
END $$;

-- ---------------------------------------------------------------------------
-- M10-S ingestion (worker). p: {model_run_id, output_status, human_review_required, warnings,
-- repair_of_model_run_id, qa_request_id, deterministic_qa_run_id, result}
-- An output that is malformed in content (unknown evidence ref, foreign statement, wrong version,
-- inconsistent severity, repair attempt, ...) is rejected as a whole: the S run is INVALID and its
-- findings are not stored. An INVALID run makes the combined result FAIL.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.ingest_qa_semantic(p jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_run     lfhe.model_runs%ROWTYPE;
  d         lfhe.qa_runs;
  v         lfhe.report_versions;
  v_r       jsonb := p -> 'result';
  v_reasons text[] := '{}';
  v_f       jsonb;
  v_ref     jsonb;
  v_id      uuid;
  v_n       integer := 0;
  v_diag    boolean;
BEGIN
  SELECT * INTO v_run FROM lfhe.model_runs WHERE id = (p ->> 'model_run_id')::uuid;
  IF NOT FOUND OR v_run.module_code <> 'M10_QA_AUDITOR' OR v_run.status = 'RUNNING' THEN
    RAISE EXCEPTION 'model run % is not a finished M10_QA_AUDITOR run', p ->> 'model_run_id'
      USING ERRCODE = 'object_not_in_prerequisite_state';
  END IF;
  SELECT * INTO d FROM lfhe.qa_runs WHERE id = (p ->> 'deterministic_qa_run_id')::uuid AND kind = 'D';
  IF NOT FOUND OR d.qa_request_id IS DISTINCT FROM (p ->> 'qa_request_id')::uuid THEN
    RAISE EXCEPTION 'QA_RUN_PAIRING_INVALID: deterministic run % / request %', p ->> 'deterministic_qa_run_id', p ->> 'qa_request_id'
      USING ERRCODE = 'check_violation';
  END IF;
  SELECT * INTO v FROM lfhe.report_versions WHERE id = d.report_version_id;
  v_diag := EXISTS (SELECT 1 FROM lfhe.qa_check_results x WHERE x.qa_run_id = d.id AND x.severity = 'CRITICAL');
  IF NOT lfhe.run_has_object(v_run.id, 'input', 'report_version', v.id::text) THEN
    v_reasons := v_reasons || 'REPORT_VERSION_NOT_SUPPLIED'::text;
  END IF;
  IF v_run.status <> 'SUCCEEDED' THEN
    v_reasons := v_reasons || ('MODEL_RUN_' || v_run.status::text);
  ELSIF (p ->> 'output_status') IS DISTINCT FROM 'SUCCESS' OR v_r IS NULL THEN
    v_reasons := v_reasons || ('MODEL_OUTPUT_STATUS_' || coalesce(p ->> 'output_status', 'NULL'));
  ELSE
    IF v_r ?| ARRAY['revised_text', 'corrected_statements', 'repaired_report', 'report_content', 'final_analytic_confidence',
                    'likelihood_term', 'approve', 'content_approved', 'security_review', 'release', 'released',
                    'acknowledge', 'acknowledgements'] THEN
      v_reasons := v_reasons || 'M10_HUMAN_ONLY_OR_REPAIR_ACTION'::text;
    END IF;
    IF (v_r ->> 'report_id') IS DISTINCT FROM v.report_id::text OR (v_r ->> 'report_version_id') IS DISTINCT FROM v.id::text
       OR (v_r ->> 'report_version_hash') IS DISTINCT FROM v.report_version_hash THEN
      v_reasons := v_reasons || 'REPORT_VERSION_BINDING_MISMATCH'::text;
    END IF;
    IF (v_r ->> 'deterministic_qa_run_id') IS DISTINCT FROM d.id::text THEN
      v_reasons := v_reasons || 'DETERMINISTIC_RUN_MISMATCH'::text;
    END IF;
    FOR v_f IN SELECT * FROM pg_catalog.jsonb_array_elements(coalesce(v_r -> 'findings', '[]')) LOOP
      IF NOT EXISTS (SELECT 1 FROM lfhe.qa_checks k WHERE k.layer = 'S' AND k.check_id = v_f ->> 'check_id') THEN
        v_reasons := v_reasons || ('CHECK_NOT_SEMANTIC:' || coalesce(v_f ->> 'check_id', 'null'));
      END IF;
      IF (v_f ->> 'severity') = 'CRITICAL' AND (v_f ->> 'status') <> 'FAIL'
         OR (v_f ->> 'status') = 'PASS' AND (v_f ->> 'severity') <> 'INFO'
         OR (v_f ->> 'status') = 'FAIL' AND (v_f ->> 'severity') NOT IN ('MAJOR', 'CRITICAL')
         OR (v_f ->> 'status') = 'WARNING' AND (v_f ->> 'severity') NOT IN ('WARNING', 'MAJOR') THEN
        v_reasons := v_reasons || ('FINDING_STATUS_SEVERITY_INCONSISTENT:' || coalesce(v_f ->> 'check_id', 'null'));
      END IF;
      IF (v_f ->> 'affected_statement_id') IS NOT NULL AND NOT EXISTS (
           SELECT 1 FROM lfhe.report_item_statements st JOIN lfhe.report_items i ON i.id = st.report_item_id
           WHERE i.report_version_id = v.id AND st.id::text = v_f ->> 'affected_statement_id') THEN
        v_reasons := v_reasons || ('AFFECTED_STATEMENT_NOT_IN_VERSION:' || left(v_f ->> 'affected_statement_id', 40));
      END IF;
      FOR v_ref IN SELECT * FROM pg_catalog.jsonb_array_elements(coalesce(v_f -> 'evidence_refs', '[]')) LOOP
        IF NOT (lfhe.run_has_object(v_run.id, 'input', v_ref ->> 'object_type', v_ref ->> 'object_id')
                OR lfhe.run_has_object(v_run.id, 'context', v_ref ->> 'object_type', v_ref ->> 'object_id')
                OR (v_ref ->> 'object_type') = 'report_item_statement' AND EXISTS (
                     SELECT 1 FROM lfhe.report_item_statements st JOIN lfhe.report_items i ON i.id = st.report_item_id
                     WHERE i.report_version_id = v.id AND st.id::text = v_ref ->> 'object_id')) THEN
          v_reasons := v_reasons || ('UNKNOWN_EVIDENCE_REF:' || coalesce(v_ref ->> 'object_type', 'null') || ':'
                                     || left(coalesce(v_ref ->> 'object_id', 'null'), 40));
        END IF;
      END LOOP;
    END LOOP;
  END IF;
  v_reasons := ARRAY(SELECT DISTINCT x FROM pg_catalog.unnest(v_reasons) x ORDER BY x);
  INSERT INTO lfhe.qa_runs (report_id, report_version_id, report_version_hash, qa_request_id, kind, status, model_run_id,
    prompt_version_id, deterministic_qa_run_id, diagnostic_only, invalid_reasons, model_status, model_qa_status,
    model_release_blocked, repair_of_model_run_id)
  VALUES (v.report_id, v.id, v.report_version_hash, d.qa_request_id, 'S',
    CASE WHEN cardinality(v_reasons) > 0 THEN 'INVALID' ELSE 'COMPLETED' END, v_run.id, v_run.prompt_version_id, d.id, v_diag,
    v_reasons, p ->> 'output_status', v_r ->> 'qa_status', (v_r ->> 'release_blocked')::boolean,
    (p ->> 'repair_of_model_run_id')::uuid)
  RETURNING id INTO v_id;
  IF cardinality(v_reasons) = 0 THEN
    FOR v_f IN SELECT x FROM pg_catalog.jsonb_array_elements(coalesce(v_r -> 'findings', '[]')) WITH ORDINALITY t(x, o)
               ORDER BY CASE x ->> 'status' WHEN 'FAIL' THEN 0 WHEN 'WARNING' THEN 1 ELSE 2 END, x ->> 'check_id', o LOOP
      v_n := v_n + 1;
      INSERT INTO lfhe.qa_check_results (qa_run_id, finding_no, check_id, layer, status, severity, finding_code,
        affected_object_id, affected_statement_id, details, evidence_refs, recommended_action)
      VALUES (v_id, v_n, v_f ->> 'check_id', 'S', v_f ->> 'status', (v_f ->> 'severity')::lfhe.challenge_severity,
        v_f ->> 'finding_code', v_f ->> 'affected_object_id', (v_f ->> 'affected_statement_id')::uuid, v_f ->> 'details',
        coalesce(v_f -> 'evidence_refs', '[]'), v_f ->> 'recommended_action');
    END LOOP;
  END IF;
  RETURN pg_catalog.jsonb_build_object('outcome', CASE WHEN cardinality(v_reasons) > 0 THEN 'OUTPUT_REJECTED' ELSE 'QA_RUN_RECORDED' END,
    'qa_run_id', v_id, 'rejection_reasons', pg_catalog.to_jsonb(v_reasons), 'findings', v_n, 'diagnostic_only', v_diag);
END $$;

-- ---------------------------------------------------------------------------
-- Combined QA result (worker) — deterministic; the model never decides it (§13)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.record_qa_result(p_deterministic_run uuid, p_semantic_run uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  d        lfhe.qa_runs;
  s        lfhe.qa_runs;
  v        lfhe.report_versions;
  v_prev   lfhe.qa_results;
  v_fail   text[] := '{}';
  v_warn   uuid[];
  v_crit   integer;
  v_fails  integer;
  v_status text;
  v_id     uuid;
BEGIN
  SELECT * INTO d FROM lfhe.qa_runs WHERE id = p_deterministic_run AND kind = 'D';
  SELECT * INTO s FROM lfhe.qa_runs WHERE id = p_semantic_run AND kind = 'S';
  IF d.id IS NULL OR s.id IS NULL OR s.deterministic_qa_run_id IS DISTINCT FROM d.id OR s.qa_request_id <> d.qa_request_id
     OR s.report_version_id <> d.report_version_id OR s.report_version_hash <> d.report_version_hash THEN
    RAISE EXCEPTION 'QA_RUN_PAIRING_INVALID: % / %', p_deterministic_run, p_semantic_run USING ERRCODE = 'check_violation';
  END IF;
  SELECT * INTO v FROM lfhe.report_versions WHERE id = d.report_version_id;
  PERFORM 1 FROM lfhe.reports WHERE id = v.report_id FOR UPDATE;
  v_prev := lfhe.p6_current_qa_result(v.id);
  IF d.status <> 'COMPLETED' THEN
    v_fail := v_fail || 'DETERMINISTIC_QA_INVALID'::text;
  END IF;
  IF s.status <> 'COMPLETED' THEN
    v_fail := v_fail || ('SEMANTIC_QA_INVALID:' || array_to_string(s.invalid_reasons, ','));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM lfhe.model_runs m JOIN lfhe.prompt_versions pv ON pv.id = m.prompt_version_id
                 WHERE m.id = s.model_run_id AND m.status = 'SUCCEEDED' AND m.module_code = 'M10_QA_AUDITOR'
                   AND pv.id = s.prompt_version_id AND pv.content_hash = m.prompt_content_hash) THEN
    v_fail := v_fail || 'SEMANTIC_QA_PROVENANCE_MISSING'::text;
  END IF;
  IF v.report_version_hash IS DISTINCT FROM d.report_version_hash OR lfhe.jcs_sha256(v.canonical_json) <> v.report_version_hash THEN
    v_fail := v_fail || 'VERSION_HASH_BINDING_FAILED'::text;
  END IF;
  SELECT count(*) FILTER (WHERE x.severity = 'CRITICAL'), count(*) FILTER (WHERE x.status = 'FAIL')
  INTO v_crit, v_fails FROM lfhe.qa_check_results x WHERE x.qa_run_id IN (d.id, s.id);
  IF v_crit > 0 THEN
    v_fail := v_fail || ('CRITICAL_FINDINGS:' || v_crit);
  END IF;
  IF v_fails > 0 THEN
    v_fail := v_fail || ('FAILED_FINDINGS:' || v_fails);
  END IF;
  v_fail := v_fail || ARRAY(SELECT DISTINCT 'AUTOMATIC_FAIL:' || x.finding_code FROM lfhe.qa_check_results x
                            WHERE x.qa_run_id IN (d.id, s.id) AND x.status <> 'PASS'
                              AND x.finding_code = ANY (lfhe.p6_autofail_codes()) ORDER BY 1);
  v_warn := ARRAY(SELECT x.id FROM lfhe.qa_check_results x WHERE x.qa_run_id IN (d.id, s.id) AND x.status = 'WARNING'
                  ORDER BY x.qa_run_id = s.id, x.finding_no);
  v_status := CASE WHEN cardinality(v_fail) > 0 THEN 'FAIL' WHEN cardinality(v_warn) > 0 THEN 'PASS_WITH_WARNINGS' ELSE 'PASS' END;
  INSERT INTO lfhe.qa_results (report_id, report_version_id, report_version_hash, result_no, qa_request_id,
    deterministic_qa_run_id, semantic_qa_run_id, status, fail_reasons, warning_finding_ids, critical_count, fail_count,
    warning_count, release_blocked, previous_qa_result_id, changed_by_rerun)
  VALUES (v.report_id, v.id, v.report_version_hash, coalesce(v_prev.result_no, 0) + 1, d.qa_request_id, d.id, s.id, v_status,
    v_fail, CASE WHEN v_status = 'FAIL' THEN '{}' ELSE v_warn END, v_crit, v_fails, cardinality(v_warn), v_status = 'FAIL', v_prev.id,
    v_prev.id IS NOT NULL AND v_prev.status <> v_status)
  RETURNING id INTO v_id;
  IF v_prev.id IS NOT NULL AND v_prev.status <> v_status THEN
    PERFORM lfhe.write_audit('QA_RESULT_CHANGED_BY_RERUN', 'report_version', v.id::text,
      pg_catalog.jsonb_build_object('qa_result_id', v_prev.id, 'status', v_prev.status),
      pg_catalog.jsonb_build_object('qa_result_id', v_id, 'status', v_status), '{}');
  END IF;
  RETURN pg_catalog.jsonb_build_object('qa_result_id', v_id, 'status', v_status, 'fail_reasons', pg_catalog.to_jsonb(v_fail),
    'warnings', cardinality(v_warn), 'previous_qa_result_id', v_prev.id);
END $$;

-- ---------------------------------------------------------------------------
-- HUMAN_ONLY (QA_WARNING_ACKNOWLEDGE): acknowledge one exact WARNING of the current result
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.acknowledge_qa_warning(p_version uuid, p_hash text, p_qa_result uuid, p_finding uuid,
                                                       p_rationale text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('QA_WARNING_ACKNOWLEDGE');
  v       lfhe.report_versions;
  q       lfhe.qa_results;
  f       lfhe.qa_check_results;
  v_id    uuid;
BEGIN
  IF p_rationale IS NULL OR length(btrim(p_rationale)) < 10 THEN
    RAISE EXCEPTION 'a rationale (>= 10 characters) is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  v := lfhe.p5_require_latest_version(p_version, p_hash);
  q := lfhe.p6_current_qa_result(v.id);
  IF q.id IS NULL OR q.id <> p_qa_result THEN
    RAISE EXCEPTION 'QA_RESULT_STALE: % is not the current QA result of version %', p_qa_result, v.id
      USING ERRCODE = 'serialization_failure';
  END IF;
  SELECT * INTO f FROM lfhe.qa_check_results WHERE id = p_finding;
  IF NOT FOUND OR f.qa_run_id NOT IN (q.deterministic_qa_run_id, q.semantic_qa_run_id) THEN
    RAISE EXCEPTION 'FINDING_NOT_IN_QA_RESULT: %', p_finding USING ERRCODE = 'check_violation';
  END IF;
  IF f.status <> 'WARNING' OR f.severity = 'CRITICAL' OR q.status <> 'PASS_WITH_WARNINGS' THEN
    RAISE EXCEPTION 'NOT_ACKNOWLEDGEABLE: only WARNING findings of a PASS_WITH_WARNINGS result can be acknowledged (finding %, result %)',
      f.status || '/' || f.severity, q.status USING ERRCODE = 'check_violation';
  END IF;
  IF EXISTS (SELECT 1 FROM lfhe.warning_acknowledgements a WHERE a.qa_result_id = q.id AND a.qa_check_result_id = f.id) THEN
    RAISE EXCEPTION 'WARNING_ALREADY_ACKNOWLEDGED' USING ERRCODE = 'unique_violation';
  END IF;
  INSERT INTO lfhe.warning_acknowledgements (qa_result_id, qa_check_result_id, report_version_id, report_version_hash,
    acknowledged_by, rationale)
  VALUES (q.id, f.id, v.id, v.report_version_hash, v_actor, p_rationale) RETURNING id INTO v_id;
  PERFORM lfhe.write_audit('QA_WARNING_ACKNOWLEDGED', 'report_version', v.id::text, NULL,
    pg_catalog.jsonb_build_object('warning_acknowledgement_id', v_id, 'qa_result_id', q.id, 'qa_check_result_id', f.id,
                                  'check_id', f.check_id, 'finding_code', f.finding_code, 'report_version_hash', v.report_version_hash,
                                  'rationale', p_rationale), '{}');
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.acknowledge_qa_warning(uuid, text, uuid, uuid, text) IS 'HUMAN_ONLY';

-- ---------------------------------------------------------------------------
-- Audit
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.audit_p6_objects()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_doc jsonb := pg_catalog.to_jsonb(NEW);
BEGIN
  PERFORM lfhe.write_audit(TG_ARGV[0], TG_ARGV[1], v_doc ->> TG_ARGV[2], NULL,
    v_doc - 'pdf_bytes' - 'source_html' - 'manifest_json',
    pg_catalog.jsonb_build_object('report_version_hash', v_doc ->> 'report_version_hash'));
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION lfhe.audit_p6_objects() FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;

CREATE TRIGGER qa_runs_audit AFTER INSERT ON lfhe.qa_runs
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_p6_objects('QA_RUN_CREATED', 'report_version', 'report_version_id');
CREATE TRIGGER qa_results_audit AFTER INSERT ON lfhe.qa_results
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_p6_objects('QA_RESULT_RECORDED', 'report_version', 'report_version_id');

-- ---------------------------------------------------------------------------
-- Jobs
-- ---------------------------------------------------------------------------
ALTER TABLE lfhe.processing_jobs DROP CONSTRAINT processing_jobs_job_type_check;
ALTER TABLE lfhe.processing_jobs ADD CONSTRAINT processing_jobs_job_type_check
  CHECK (job_type IN ('COLLECT_SOURCE', 'EXTRACT_CLAIMS', 'CLASSIFY_CLAIMS', 'ANALYSE_LINEAGE', 'BUILD_EVENTS',
                      'ASSESS_RELEVANCE', 'ASSESS_EVENT', 'CHALLENGE_ASSESSMENT', 'EDIT_REPORT', 'RENDER_REPORT',
                      'RUN_REPORT_QA', 'RENDER_RELEASE_PDF'));

-- ---------------------------------------------------------------------------
-- Grants / RLS
-- ---------------------------------------------------------------------------
REVOKE ALL ON FUNCTION lfhe.request_report_qa(uuid, text, text), lfhe.acknowledge_qa_warning(uuid, text, uuid, uuid, text)
  FROM PUBLIC, anon, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.request_report_qa(uuid, text, text), lfhe.acknowledge_qa_warning(uuid, text, uuid, uuid, text)
  TO authenticated;
REVOKE ALL ON FUNCTION lfhe.run_m10d(uuid, text, uuid), lfhe.ingest_qa_semantic(jsonb), lfhe.record_qa_result(uuid, uuid)
  FROM PUBLIC, anon, authenticated, service_role, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.run_m10d(uuid, text, uuid), lfhe.ingest_qa_semantic(jsonb), lfhe.record_qa_result(uuid, uuid)
  TO lfhe_worker;
REVOKE ALL ON FUNCTION lfhe.p6_autofail_codes(), lfhe.p6_recommended_actions(), lfhe.p6_is_latest_version(uuid),
  lfhe.p6_current_qa_result(uuid), lfhe.p6_unacknowledged_warnings(uuid), lfhe.p6_prohibited_marking(text),
  lfhe.p6_finding(text, text, text, text, text, uuid, text, jsonb, text), lfhe.p6_ref(text, text), lfhe.p6_validator_finding(text)
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.p6_autofail_codes(), lfhe.p6_recommended_actions(), lfhe.p6_prohibited_marking(text)
  TO authenticated, lfhe_worker;
GRANT EXECUTE ON FUNCTION lfhe.p6_is_latest_version(uuid), lfhe.p6_current_qa_result(uuid), lfhe.p6_unacknowledged_warnings(uuid)
  TO lfhe_worker;
GRANT EXECUTE ON FUNCTION lfhe.p6_unacknowledged_warnings(uuid) TO authenticated;    -- used by the security-invoker workflow view
-- a few report-reading helpers the M10-S input builder (worker) needs
GRANT EXECUTE ON FUNCTION lfhe.independence_summary_asof(uuid[], text, timestamptz), lfhe.claim_cutoff_eligible(uuid, text, timestamptz)
  TO lfhe_worker;

REVOKE ALL ON lfhe.qa_checks, lfhe.qa_requests, lfhe.qa_runs, lfhe.qa_check_results, lfhe.qa_results, lfhe.warning_acknowledgements
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT SELECT ON lfhe.qa_checks, lfhe.qa_requests, lfhe.qa_runs, lfhe.qa_check_results, lfhe.qa_results, lfhe.warning_acknowledgements
  TO authenticated, lfhe_worker;
DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['qa_checks', 'qa_requests', 'qa_runs', 'qa_check_results', 'qa_results', 'warning_acknowledgements'] LOOP
    EXECUTE format('ALTER TABLE lfhe.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY %I ON lfhe.%I FOR SELECT TO authenticated USING (lfhe.has_permission(''CLAIM_READ''))',
                   t || '_read_human', t);
    EXECUTE format('CREATE POLICY %I ON lfhe.%I FOR SELECT TO lfhe_worker USING (true)', t || '_read_worker', t);
  END LOOP;
END $$;
