-- LFHÉ Phase 3 (P3-05) — one external origin per evidenced name.
--
-- Found by the acceptance corpus (L3_COMMON_EXTERNAL_ORIGIN): accepting two
-- COMMON_ORIGINAL_SOURCE proposals that name the same external origin created two
-- external_origins rows, so the two claims stayed in two independence groups —
-- republication via a common origin was NOT collapsed (inflation of 1).
--
-- Now an accepted / human-recorded external origin reuses the earliest existing
-- origin with the same normalised name (lfhe.normalise_entity_name). Collapsing is
-- the conservative direction (it can only reduce the independence upper bound).
-- Evidence rules are unchanged (the name must appear in the claim's evidence span,
-- a URL must appear in the source text; checked at ingestion / insert).
-- A human who needs two distinct origins with the same name records lineage with an
-- explicit external_origin_id. Forward-only; 20261011001800 is not edited.

CREATE OR REPLACE FUNCTION lfhe.resolve_external_origin(p_name text, p_url text, p_evidence_claim uuid,
                                                        p_actor uuid, p_reason text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_id uuid;
BEGIN
  -- serialise concurrent creation of the same origin
  PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(
    'lfhe.external_origin:' || coalesce(lfhe.normalise_entity_name(p_name), ''), 0));
  SELECT id INTO v_id FROM lfhe.external_origins
  WHERE lfhe.normalise_entity_name(name) = lfhe.normalise_entity_name(p_name)
  ORDER BY created_at, id LIMIT 1;
  IF v_id IS NULL THEN
    INSERT INTO lfhe.external_origins (name, url, evidence_claim_id, created_by, reason)
    VALUES (p_name, p_url, p_evidence_claim, p_actor, p_reason) RETURNING id INTO v_id;
  END IF;
  RETURN v_id;
END $$;
REVOKE ALL ON FUNCTION lfhe.resolve_external_origin(text, text, uuid, uuid, text)
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
      v_origin := lfhe.resolve_external_origin(v_p.external_origin_name, v_p.external_origin_url,
                                               v_p.child_claim_id, v_actor, p_reason);
    END IF;
    v_lin := lfhe.insert_claim_lineage(v_p.child_claim_id, v_p.relationship_type, v_p.parent_claim_id,
      v_p.parent_article_id, v_origin, 'PROPOSAL_ACCEPTED', v_p.id, v_actor, p_reason);
  END IF;
  INSERT INTO lfhe.lineage_proposal_decisions (proposal_id, decision, lineage_id, actor_user_id, reason)
  VALUES (p_proposal_id, CASE WHEN p_accept THEN 'ACCEPTED' ELSE 'REJECTED' END, v_lin, v_actor, p_reason);
  RETURN v_lin;
END $$;

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
    v_origin := lfhe.resolve_external_origin(p -> 'external_origin' ->> 'name', p -> 'external_origin' ->> 'url',
      coalesce((p -> 'external_origin' ->> 'evidence_claim_id')::uuid, (p ->> 'child_claim_id')::uuid), v_actor, p_reason);
  END IF;
  RETURN lfhe.insert_claim_lineage((p ->> 'child_claim_id')::uuid,
    (p ->> 'relationship_type')::lfhe.lineage_relationship_type, (p ->> 'parent_claim_id')::uuid,
    (p ->> 'parent_article_id')::uuid, v_origin, 'HUMAN_RECORDED', NULL, v_actor, p_reason);
END $$;
