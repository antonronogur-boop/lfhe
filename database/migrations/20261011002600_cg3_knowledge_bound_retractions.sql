-- LFHÉ final CG3 correction — knowledge-bound lineage retractions (replaces SD3-13).
--
-- PO decision: docs/specs/PO_Decision_2026-10-19_CG3_Final_Correction.md.
-- Problem: migration 2300 treated EXISTS(claim_lineage_retractions) as "lineage
-- unusable" for every run, so a retraction based on evidence obtained after a
-- historical cutoff T removed a dependence from REPLAY(T) — hindsight leakage that
-- could increase the apparent number of independent groups.
--
-- Approved semantics: "Lineage retractions are themselves knowledge-bound. A
-- retraction affects a historical run only when its supporting evidence is
-- eligible for that run's cutoff."
--   * a lineage stays usable at T when its own bound is eligible at T, unless a
--     retraction is also usable at T;
--   * a retraction is usable for (mode, T) iff it has a declared evidence basis
--     (claim / article objects, append-only lfhe.claim_lineage_retraction_evidence)
--     and every object of that basis is cutoff-eligible for (mode, T) — regardless
--     of when the retraction was recorded;
--   * a retraction without a reproducible evidence basis never alters REPLAY; in
--     LIVE it applies when recorded at or before the cutoff (current knowledge);
--   * retraction created_at alone is never the historical criterion for REPLAY.
-- The current-state view lfhe.active_claim_lineage (human UI / duplicate guard) is
-- unchanged. Forward-only; migrations 1800–2500 are not edited.

CREATE TABLE lfhe.claim_lineage_retraction_evidence (
  lineage_id   uuid NOT NULL REFERENCES lfhe.claim_lineage_retractions(lineage_id),
  object_type  text NOT NULL CHECK (object_type IN ('claim', 'article')),
  object_id    uuid NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (lineage_id, object_type, object_id)
);
CREATE TRIGGER claim_lineage_retraction_evidence_immutable BEFORE UPDATE OR DELETE ON lfhe.claim_lineage_retraction_evidence
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();
REVOKE ALL ON lfhe.claim_lineage_retraction_evidence
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT SELECT ON lfhe.claim_lineage_retraction_evidence TO authenticated, lfhe_worker;
ALTER TABLE lfhe.claim_lineage_retraction_evidence ENABLE ROW LEVEL SECURITY;
CREATE POLICY claim_lineage_retraction_evidence_read_human ON lfhe.claim_lineage_retraction_evidence
  FOR SELECT TO authenticated USING (lfhe.has_permission('CLAIM_READ'));
CREATE POLICY claim_lineage_retraction_evidence_read_worker ON lfhe.claim_lineage_retraction_evidence
  FOR SELECT TO lfhe_worker USING (true);

CREATE OR REPLACE FUNCTION lfhe.lineage_retraction_usable(p_lineage uuid, p_mode text, p_cutoff timestamptz)
RETURNS boolean LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  r lfhe.claim_lineage_retractions%ROWTYPE;
BEGIN
  SELECT * INTO r FROM lfhe.claim_lineage_retractions WHERE lineage_id = p_lineage;
  IF NOT FOUND THEN
    RETURN false;
  END IF;
  IF EXISTS (SELECT 1 FROM lfhe.claim_lineage_retraction_evidence e WHERE e.lineage_id = p_lineage) THEN
    RETURN NOT EXISTS (SELECT 1 FROM lfhe.claim_lineage_retraction_evidence e WHERE e.lineage_id = p_lineage AND NOT CASE e.object_type
                         WHEN 'claim' THEN lfhe.claim_cutoff_eligible(e.object_id, p_mode, p_cutoff)
                         ELSE lfhe.article_cutoff_eligible(e.object_id, p_mode, p_cutoff) END);
  END IF;
  -- no reproducible evidence basis: never alters REPLAY; LIVE = current knowledge at the cutoff
  RETURN p_mode = 'LIVE' AND r.created_at <= p_cutoff;
END $$;
REVOKE ALL ON FUNCTION lfhe.lineage_retraction_usable(uuid, text, timestamptz)
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.lineage_retraction_usable(uuid, text, timestamptz) TO lfhe_worker;

CREATE OR REPLACE FUNCTION lfhe.lineage_usable(p_lineage uuid, p_mode text, p_cutoff timestamptz, p_depth integer DEFAULT 0)
RETURNS boolean LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  l lfhe.claim_lineage%ROWTYPE;
BEGIN
  IF p_depth > 50 OR p_mode NOT IN ('LIVE', 'REPLAY') OR p_cutoff IS NULL THEN
    RETURN false;
  END IF;
  SELECT * INTO l FROM lfhe.claim_lineage WHERE id = p_lineage;
  IF NOT FOUND THEN
    RETURN false;
  END IF;
  -- a retraction counts for this run only if it is itself knowledge-bound to the cutoff
  IF lfhe.lineage_retraction_usable(l.id, p_mode, p_cutoff) THEN
    RETURN false;
  END IF;
  IF NOT lfhe.claim_cutoff_eligible(l.child_claim_id, p_mode, p_cutoff)
     OR (l.parent_claim_id IS NOT NULL AND NOT lfhe.claim_cutoff_eligible(l.parent_claim_id, p_mode, p_cutoff))
     OR (l.parent_article_id IS NOT NULL AND NOT lfhe.article_cutoff_eligible(l.parent_article_id, p_mode, p_cutoff))
     OR (l.external_origin_id IS NOT NULL AND NOT lfhe.claim_cutoff_eligible(
           (SELECT o.evidence_claim_id FROM lfhe.external_origins o WHERE o.id = l.external_origin_id), p_mode, p_cutoff)) THEN
    RETURN false;
  END IF;
  IF l.basis = 'PROPOSAL_ACCEPTED' THEN
    RETURN lfhe.run_evidence_eligible((SELECT p.model_run_id FROM lfhe.lineage_proposals p WHERE p.id = l.proposal_id),
                                      p_mode, p_cutoff, p_depth + 1);
  END IF;
  IF EXISTS (SELECT 1 FROM lfhe.claim_lineage_evidence e WHERE e.lineage_id = l.id) THEN
    RETURN NOT EXISTS (SELECT 1 FROM lfhe.claim_lineage_evidence e WHERE e.lineage_id = l.id AND NOT CASE e.object_type
                         WHEN 'claim' THEN lfhe.claim_cutoff_eligible(e.object_id, p_mode, p_cutoff)
                         ELSE lfhe.article_cutoff_eligible(e.object_id, p_mode, p_cutoff) END);
  END IF;
  -- human-recorded lineage without a declared evidence basis: no provable bound
  RETURN p_mode = 'LIVE' AND l.created_at <= p_cutoff;
END $$;

-- Retraction with an optional declared evidence basis ([{object_type: claim|article, object_id}]).
DROP FUNCTION lfhe.retract_claim_lineage(uuid, text);
CREATE FUNCTION lfhe.retract_claim_lineage(p_lineage_id uuid, p_reason text, p_evidence_basis jsonb DEFAULT NULL)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('CLAIM_REVIEW');
  v_e     jsonb;
BEGIN
  IF p_reason IS NULL OR length(btrim(p_reason)) < 5 THEN
    RAISE EXCEPTION 'a reason is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  IF p_evidence_basis IS NOT NULL AND pg_catalog.jsonb_typeof(p_evidence_basis) <> 'array' THEN
    RAISE EXCEPTION 'EVIDENCE_BASIS_INVALID: must be an array' USING ERRCODE = 'check_violation';
  END IF;
  INSERT INTO lfhe.claim_lineage_retractions (lineage_id, actor_user_id, reason) VALUES (p_lineage_id, v_actor, p_reason);
  FOR v_e IN SELECT * FROM pg_catalog.jsonb_array_elements(coalesce(p_evidence_basis, '[]')) LOOP
    IF v_e ->> 'object_type' = 'claim' AND EXISTS (SELECT 1 FROM lfhe.claims WHERE id = (v_e ->> 'object_id')::uuid)
       OR v_e ->> 'object_type' = 'article' AND EXISTS (SELECT 1 FROM lfhe.articles WHERE id = (v_e ->> 'object_id')::uuid) THEN
      INSERT INTO lfhe.claim_lineage_retraction_evidence (lineage_id, object_type, object_id)
      VALUES (p_lineage_id, v_e ->> 'object_type', (v_e ->> 'object_id')::uuid) ON CONFLICT DO NOTHING;
    ELSE
      RAISE EXCEPTION 'EVIDENCE_BASIS_INVALID: %', left(v_e::text, 200) USING ERRCODE = 'check_violation';
    END IF;
  END LOOP;
END $$;
COMMENT ON FUNCTION lfhe.retract_claim_lineage(uuid, text, jsonb) IS 'HUMAN_ONLY';
REVOKE ALL ON FUNCTION lfhe.retract_claim_lineage(uuid, text, jsonb)
  FROM PUBLIC, anon, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.retract_claim_lineage(uuid, text, jsonb) TO authenticated;
