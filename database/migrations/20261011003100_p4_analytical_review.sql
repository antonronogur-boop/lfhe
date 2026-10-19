-- LFHÉ Phase 4 (P4-06) — human analytical review, final analytic confidence (G-08),
-- immutable MODIFY_AND_APPROVE. Baseline: Phase 4 Addendum §12, §13, §16, §19, §22;
-- Prompt Pack v1.2 §25–§26; DC-01 (single canonical owner of final confidence).
--
-- * Decisions (closed lfhe.review_decision: APPROVE, MODIFY_AND_APPROVE, REJECT, ESCALATE,
--   REQUEST_REPROCESSING) are HUMAN_ONLY (ASSESSMENT_REVIEW; approval additionally
--   FINAL_CONFIDENCE_SET), bound to the exact assessment_version_id + content_hash of the
--   assessment's CURRENT version in IN_REVIEW / ESCALATED (stale → REVIEW_STALE).
-- * final_analytic_confidence exists in exactly one place: the immutable
--   lfhe.analytical_approvals row that approves a version (DC-01). It is never a column of a
--   model-written row and is never the same field as ai_recommended_confidence.
-- * MODIFY_AND_APPROVE writes a NEW human-authored version (statements re-validated with
--   the same provenance rules; unresolved provenance cannot be approved) and approves that
--   new version/hash; the old version becomes SUPERSEDED, never edited.
-- * Approving a later version supersedes the previously approved version of the same
--   assessment (history kept).

INSERT INTO lfhe.audit_event_types (code, spec_source) VALUES
  ('ASSESSMENT_REVIEW_RECORDED', 'Phase 4 impl.')
ON CONFLICT (code) DO NOTHING;

CREATE TABLE lfhe.analytical_approvals (
  seq                        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id                         uuid NOT NULL UNIQUE DEFAULT pg_catalog.gen_random_uuid(),
  assessment_version_id      uuid NOT NULL,
  content_hash               text NOT NULL,
  decision                   lfhe.review_decision NOT NULL,
  modified_from_version_id   uuid REFERENCES lfhe.assessment_versions(id),
  final_analytic_confidence  lfhe.analytic_confidence,
  final_confidence_rationale text,
  reviewer_user_id           uuid NOT NULL,
  reason                     text NOT NULL CHECK (length(btrim(reason)) >= 5),
  created_at                 timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (assessment_version_id, content_hash) REFERENCES lfhe.assessment_versions (id, content_hash),
  CHECK ((decision IN ('APPROVE', 'MODIFY_AND_APPROVE'))
         = (final_analytic_confidence IS NOT NULL AND length(btrim(final_confidence_rationale)) >= 20)),
  CHECK (decision IN ('APPROVE', 'MODIFY_AND_APPROVE') OR final_confidence_rationale IS NULL),
  CHECK ((decision = 'MODIFY_AND_APPROVE') = (modified_from_version_id IS NOT NULL))
);
-- at most one approval per version (the canonical final confidence)
CREATE UNIQUE INDEX analytical_approvals_one_approval ON lfhe.analytical_approvals (assessment_version_id)
  WHERE decision IN ('APPROVE', 'MODIFY_AND_APPROVE');
CREATE TRIGGER analytical_approvals_immutable BEFORE UPDATE OR DELETE ON lfhe.analytical_approvals
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();

-- ---------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.require_reviewable_version(p_version uuid, p_hash text)
RETURNS lfhe.assessment_versions LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v lfhe.assessment_versions%ROWTYPE;
  v_state lfhe.assessment_state;
BEGIN
  SELECT * INTO v FROM lfhe.assessment_versions WHERE id = p_version;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'unknown assessment version %', p_version USING ERRCODE = 'no_data_found';
  END IF;
  PERFORM 1 FROM lfhe.assessments WHERE id = v.assessment_id FOR UPDATE;
  IF v.content_hash IS DISTINCT FROM p_hash THEN
    RAISE EXCEPTION 'VERSION_HASH_MISMATCH: assessment version %', p_version USING ERRCODE = 'serialization_failure';
  END IF;
  IF EXISTS (SELECT 1 FROM lfhe.assessment_versions x WHERE x.assessment_id = v.assessment_id AND x.version_no > v.version_no) THEN
    RAISE EXCEPTION 'REVIEW_STALE: a later version of assessment % exists', v.assessment_id USING ERRCODE = 'serialization_failure';
  END IF;
  v_state := lfhe.assessment_version_state(v.id);
  IF v_state IN ('DRAFT', 'CHALLENGED') THEN
    RAISE EXCEPTION 'ASSESSMENT_NOT_CHALLENGED: M08 challenge must precede human review (state %)', v_state
      USING ERRCODE = 'object_not_in_prerequisite_state';
  END IF;
  IF v_state NOT IN ('IN_REVIEW', 'ESCALATED') THEN
    RAISE EXCEPTION 'ASSESSMENT_NOT_IN_REVIEW: state %', v_state USING ERRCODE = 'object_not_in_prerequisite_state';
  END IF;
  RETURN v;
END $$;

CREATE OR REPLACE FUNCTION lfhe.supersede_previous_approvals(p_assessment uuid, p_except uuid, p_actor uuid, p_decision uuid)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v uuid;
BEGIN
  FOR v IN SELECT x.id FROM lfhe.assessment_versions x WHERE x.assessment_id = p_assessment AND x.id <> p_except
           AND lfhe.assessment_version_state(x.id) = 'APPROVED' LOOP
    PERFORM lfhe.set_assessment_state(v, 'SUPERSEDED', 'HUMAN', p_actor, p_decision, 'superseded by a later approved version');
  END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- HUMAN_ONLY decisions
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.review_assessment(p_version uuid, p_hash text, p_decision lfhe.review_decision,
                                                  p_final_confidence lfhe.analytic_confidence,
                                                  p_confidence_rationale text, p_reason text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('ASSESSMENT_REVIEW');
  v       lfhe.assessment_versions;
  v_id    uuid;
BEGIN
  IF p_decision = 'MODIFY_AND_APPROVE' THEN
    RAISE EXCEPTION 'use lfhe.modify_and_approve_assessment' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  IF p_decision = 'APPROVE' THEN
    PERFORM lfhe.require_human_permission('FINAL_CONFIDENCE_SET');
    IF p_final_confidence IS NULL OR coalesce(length(btrim(p_confidence_rationale)), 0) < 20 THEN
      RAISE EXCEPTION 'FINAL_CONFIDENCE_AND_RATIONALE_REQUIRED' USING ERRCODE = 'check_violation';
    END IF;
  ELSIF p_final_confidence IS NOT NULL THEN
    RAISE EXCEPTION 'final confidence is set only by an approval' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  v := lfhe.require_reviewable_version(p_version, p_hash);
  INSERT INTO lfhe.analytical_approvals (assessment_version_id, content_hash, decision, final_analytic_confidence,
    final_confidence_rationale, reviewer_user_id, reason)
  VALUES (v.id, v.content_hash, p_decision, p_final_confidence,
    CASE WHEN p_decision = 'APPROVE' THEN p_confidence_rationale END, v_actor, p_reason)
  RETURNING id INTO v_id;
  PERFORM lfhe.set_assessment_state(v.id, CASE p_decision WHEN 'APPROVE' THEN 'APPROVED' WHEN 'REJECT' THEN 'REJECTED'
      WHEN 'ESCALATE' THEN 'ESCALATED' ELSE 'REPROCESSING_REQUESTED' END::lfhe.assessment_state,
    'HUMAN', v_actor, v_id, p_reason);
  IF p_decision = 'APPROVE' THEN
    PERFORM lfhe.supersede_previous_approvals(v.assessment_id, v.id, v_actor, v_id);
  END IF;
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.review_assessment(uuid, text, lfhe.review_decision, lfhe.analytic_confidence, text, text) IS 'HUMAN_ONLY';

-- p: {assessment_statements, derived_summary?, indicators_to_watch?}
CREATE OR REPLACE FUNCTION lfhe.modify_and_approve_assessment(p_version uuid, p_hash text, p jsonb,
                                                              p_final_confidence lfhe.analytic_confidence,
                                                              p_confidence_rationale text, p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor   uuid := lfhe.require_human_permission('ASSESSMENT_REVIEW');
  v         lfhe.assessment_versions;
  v_ctx     jsonb;
  v_reasons text[];
  v_new     uuid;
  v_hash    text;
  v_id      uuid;
BEGIN
  PERFORM lfhe.require_human_permission('FINAL_CONFIDENCE_SET');
  IF p_final_confidence IS NULL OR coalesce(length(btrim(p_confidence_rationale)), 0) < 20 THEN
    RAISE EXCEPTION 'FINAL_CONFIDENCE_AND_RATIONALE_REQUIRED' USING ERRCODE = 'check_violation';
  END IF;
  v := lfhe.require_reviewable_version(p_version, p_hash);
  -- same evidence context as the reviewed version: its event version claims, baseline, reference contexts
  v_ctx := pg_catalog.jsonb_build_object(
    'event_version_id', v.event_version_id, 'baseline_version_id', v.baseline_version_id,
    'previous_assessment_version_id', v.context_previous_assessment_version_id,
    'claim_ids', (SELECT coalesce(pg_catalog.jsonb_agg(ec.claim_id ORDER BY ec.claim_id), '[]')
                  FROM lfhe.event_claims ec WHERE ec.event_version_id = v.event_version_id),
    'contradicts_claim_ids', (SELECT coalesce(pg_catalog.jsonb_agg(ec.claim_id ORDER BY ec.claim_id), '[]')
                              FROM lfhe.event_claims ec WHERE ec.event_version_id = v.event_version_id AND ec.role = 'CONTRADICTS'),
    'rc_version_ids', (SELECT coalesce(pg_catalog.jsonb_agg(r.reference_context_version_id ORDER BY r.reference_context_version_id), '[]')
                       FROM lfhe.assessment_reference_contexts r WHERE r.assessment_version_id = v.id));
  v_reasons := lfhe.assessment_statement_problems(v_ctx, p -> 'assessment_statements', v.report_mode, v.information_cutoff, false)
            || lfhe.assessment_extra_problems(p -> 'assessment_statements', p -> 'derived_summary', p -> 'indicators_to_watch', v_ctx);
  IF cardinality(v_reasons) > 0 THEN
    RAISE EXCEPTION 'STATEMENT_PROVENANCE_INVALID: %', pg_catalog.array_to_string(v_reasons, ', ')
      USING ERRCODE = 'check_violation';
  END IF;
  v_new := lfhe.write_assessment_version(v.assessment_id, v_ctx, p -> 'assessment_statements', p -> 'derived_summary',
    p -> 'indicators_to_watch', v.ai_recommended_confidence::text, v.ai_confidence_rationale, 'HUMAN', NULL, v_actor, v.id,
    v.report_mode, v.information_cutoff);
  SELECT content_hash INTO v_hash FROM lfhe.assessment_versions WHERE id = v_new;
  INSERT INTO lfhe.analytical_approvals (assessment_version_id, content_hash, decision, modified_from_version_id,
    final_analytic_confidence, final_confidence_rationale, reviewer_user_id, reason)
  VALUES (v_new, v_hash, 'MODIFY_AND_APPROVE', v.id, p_final_confidence, p_confidence_rationale, v_actor, p_reason)
  RETURNING id INTO v_id;
  PERFORM lfhe.set_assessment_state(v_new, 'APPROVED', 'HUMAN', v_actor, v_id, p_reason);
  PERFORM lfhe.set_assessment_state(v.id, 'SUPERSEDED', 'HUMAN', v_actor, v_id, 'modified by a human reviewer');
  PERFORM lfhe.supersede_previous_approvals(v.assessment_id, v_new, v_actor, v_id);
  RETURN pg_catalog.jsonb_build_object('approval_id', v_id, 'assessment_version_id', v_new, 'content_hash', v_hash);
END $$;
COMMENT ON FUNCTION lfhe.modify_and_approve_assessment(uuid, text, jsonb, lfhe.analytic_confidence, text, text) IS 'HUMAN_ONLY';

-- As-of approval (§19): approved, and not superseded by a later approved version that is
-- itself knowable at the cutoff. Approval may be recorded after the cutoff (rule 7).
CREATE OR REPLACE FUNCTION lfhe.assessment_version_approved_asof(p_version uuid, p_mode text, p_cutoff timestamptz)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT EXISTS (SELECT 1 FROM lfhe.analytical_approvals a WHERE a.assessment_version_id = p_version
                 AND a.decision IN ('APPROVE', 'MODIFY_AND_APPROVE'))
     AND lfhe.assessment_version_eligible(p_version, p_mode, p_cutoff)
     AND NOT EXISTS (SELECT 1 FROM lfhe.assessment_versions v JOIN lfhe.assessment_versions x
                       ON x.assessment_id = v.assessment_id AND x.version_no > v.version_no
                     JOIN lfhe.analytical_approvals a ON a.assessment_version_id = x.id
                       AND a.decision IN ('APPROVE', 'MODIFY_AND_APPROVE')
                     WHERE v.id = p_version AND lfhe.assessment_version_eligible(x.id, p_mode, p_cutoff))
$$;

-- assessment_version_states: same columns + approval (appended)
CREATE OR REPLACE VIEW lfhe.assessment_version_states WITH (security_invoker = true) AS
SELECT v.id AS assessment_version_id, v.assessment_id, v.version_no, v.content_hash, v.origin, v.event_version_id,
       v.ai_recommended_confidence,
       (SELECT h.new_state FROM lfhe.assessment_state_history h WHERE h.assessment_version_id = v.id ORDER BY h.seq DESC LIMIT 1)
         AS state,
       a.final_analytic_confidence, a.final_confidence_rationale, a.reviewer_user_id AS approved_by, a.created_at AS approved_at
FROM lfhe.assessment_versions v
LEFT JOIN lfhe.analytical_approvals a ON a.assessment_version_id = v.id AND a.decision IN ('APPROVE', 'MODIFY_AND_APPROVE');

-- ---------------------------------------------------------------------------
-- Audit
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.audit_analytical_approvals()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_doc jsonb := pg_catalog.to_jsonb(NEW);
BEGIN
  PERFORM lfhe.write_audit(CASE NEW.decision WHEN 'APPROVE' THEN 'ASSESSMENT_APPROVED' WHEN 'MODIFY_AND_APPROVE' THEN 'ASSESSMENT_APPROVED'
      WHEN 'REJECT' THEN 'ASSESSMENT_REJECTED' WHEN 'ESCALATE' THEN 'REVIEW_ESCALATED' ELSE 'REPROCESSING_REQUESTED' END,
    'assessment_version', NEW.assessment_version_id::text, NULL, v_doc, '{}');
  IF NEW.final_analytic_confidence IS NOT NULL THEN
    PERFORM lfhe.write_audit('FINAL_CONFIDENCE_SET', 'assessment_version', NEW.assessment_version_id::text, NULL,
      pg_catalog.jsonb_build_object('final_analytic_confidence', NEW.final_analytic_confidence,
                                    'final_confidence_rationale', NEW.final_confidence_rationale,
                                    'content_hash', NEW.content_hash), '{}');
  END IF;
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION lfhe.audit_analytical_approvals() FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
CREATE TRIGGER analytical_approvals_audit AFTER INSERT ON lfhe.analytical_approvals
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_analytical_approvals();

-- ---------------------------------------------------------------------------
-- Grants / RLS
-- ---------------------------------------------------------------------------
REVOKE ALL ON FUNCTION lfhe.require_reviewable_version(uuid, text),
  lfhe.supersede_previous_approvals(uuid, uuid, uuid, uuid)
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
REVOKE ALL ON FUNCTION lfhe.assessment_version_approved_asof(uuid, text, timestamptz)
  FROM PUBLIC, anon, authenticated, service_role, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.assessment_version_approved_asof(uuid, text, timestamptz) TO lfhe_worker;
REVOKE ALL ON FUNCTION
  lfhe.review_assessment(uuid, text, lfhe.review_decision, lfhe.analytic_confidence, text, text),
  lfhe.modify_and_approve_assessment(uuid, text, jsonb, lfhe.analytic_confidence, text, text)
  FROM PUBLIC, anon, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION
  lfhe.review_assessment(uuid, text, lfhe.review_decision, lfhe.analytic_confidence, text, text),
  lfhe.modify_and_approve_assessment(uuid, text, jsonb, lfhe.analytic_confidence, text, text)
  TO authenticated;

REVOKE ALL ON lfhe.analytical_approvals, lfhe.assessment_version_states
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT SELECT ON lfhe.analytical_approvals, lfhe.assessment_version_states TO authenticated, lfhe_worker;
ALTER TABLE lfhe.analytical_approvals ENABLE ROW LEVEL SECURITY;
CREATE POLICY analytical_approvals_read_human ON lfhe.analytical_approvals FOR SELECT TO authenticated
  USING (lfhe.has_permission('CLAIM_READ'));
CREATE POLICY analytical_approvals_read_worker ON lfhe.analytical_approvals FOR SELECT TO lfhe_worker USING (true);
