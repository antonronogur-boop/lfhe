-- LFHÉ CG3 corrective pass — CG3-03: no name-only external-origin identity collapse.
--
-- Problem: migration 2200 reused the earliest external_origin whose normalised
-- name matched, silently making claims citing two genuinely different origins of
-- the same name dependent (one independence group) — dependence inferred without
-- identity evidence.
--
-- Now:
--   * explicit human selection — decide_lineage_proposal(..., p_external_origin_id)
--     or record_claim_lineage({external_origin_id}) — reuses exactly that origin;
--     the selected origin's name must be evidenced in the child claim's span and a
--     proposal URL must not contradict the origin's URL
--     (EXTERNAL_ORIGIN_IDENTITY_CONFLICT);
--   * automatic reuse only on unambiguous identity evidence: the same canonical
--     URL AND the same normalised name, exactly one existing origin;
--   * otherwise (same name only, different URLs, no URL, several candidates) a NEW
--     origin is created — the distinction is preserved and a human may later
--     record the common identity explicitly.
-- Forward-only. decide_lineage_proposal(uuid, boolean, text) is replaced by the
-- 4-argument form (the 4th argument defaults to NULL, so 3-argument calls keep working).

CREATE OR REPLACE FUNCTION lfhe.resolve_external_origin(p_name text, p_url text, p_evidence_claim uuid,
                                                        p_actor uuid, p_reason text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_ids uuid[];
  v_id  uuid;
BEGIN
  IF p_url IS NOT NULL THEN
    PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('lfhe.external_origin_url:' || p_url, 0));
    v_ids := ARRAY(SELECT id FROM lfhe.external_origins
                   WHERE url = p_url AND lfhe.normalise_entity_name(name) = lfhe.normalise_entity_name(p_name)
                   ORDER BY created_at, id);
    IF cardinality(v_ids) = 1 THEN
      RETURN v_ids[1];                    -- unambiguous identity evidence: same canonical URL and name
    END IF;
  END IF;
  INSERT INTO lfhe.external_origins (name, url, evidence_claim_id, created_by, reason)
  VALUES (p_name, p_url, p_evidence_claim, p_actor, p_reason) RETURNING id INTO v_id;
  RETURN v_id;
END $$;

CREATE OR REPLACE FUNCTION lfhe.check_selected_external_origin(p_origin uuid, p_child_claim uuid, p_proposal_url text)
RETURNS void LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  o lfhe.external_origins%ROWTYPE;
  v_problems text[];
BEGIN
  SELECT * INTO o FROM lfhe.external_origins WHERE id = p_origin;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'unknown external origin %', p_origin USING ERRCODE = 'no_data_found';
  END IF;
  v_problems := lfhe.external_origin_evidence_problems(p_child_claim, o.name, NULL);
  IF cardinality(v_problems) > 0 THEN
    RAISE EXCEPTION 'EXTERNAL_ORIGIN_INVALID: selected origin "%" is not evidenced for claim %: %', o.name, p_child_claim,
      pg_catalog.array_to_string(v_problems, ', ') USING ERRCODE = 'check_violation';
  END IF;
  IF p_proposal_url IS NOT NULL AND o.url IS NOT NULL AND p_proposal_url <> o.url THEN
    RAISE EXCEPTION 'EXTERNAL_ORIGIN_IDENTITY_CONFLICT: proposal URL differs from the selected origin''s URL'
      USING ERRCODE = 'check_violation';
  END IF;
END $$;
REVOKE ALL ON FUNCTION lfhe.check_selected_external_origin(uuid, uuid, text)
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;

DROP FUNCTION lfhe.decide_lineage_proposal(uuid, boolean, text);
CREATE FUNCTION lfhe.decide_lineage_proposal(p_proposal_id uuid, p_accept boolean, p_reason text,
                                             p_external_origin_id uuid DEFAULT NULL)
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
  IF p_external_origin_id IS NOT NULL AND (NOT p_accept OR v_p.external_origin_name IS NULL) THEN
    RAISE EXCEPTION 'an external origin can only be selected when accepting an external-origin proposal'
      USING ERRCODE = 'invalid_parameter_value';
  END IF;
  IF p_accept THEN
    IF p_external_origin_id IS NOT NULL THEN
      PERFORM lfhe.check_selected_external_origin(p_external_origin_id, v_p.child_claim_id, v_p.external_origin_url);
      v_origin := p_external_origin_id;           -- explicit human identity decision
    ELSIF v_p.external_origin_name IS NOT NULL THEN
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
COMMENT ON FUNCTION lfhe.decide_lineage_proposal(uuid, boolean, text, uuid) IS 'HUMAN_ONLY';
REVOKE ALL ON FUNCTION lfhe.decide_lineage_proposal(uuid, boolean, text, uuid)
  FROM PUBLIC, anon, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.decide_lineage_proposal(uuid, boolean, text, uuid) TO authenticated;

CREATE OR REPLACE FUNCTION lfhe.record_claim_lineage(p jsonb, p_reason text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor  uuid := lfhe.require_human_permission('CLAIM_REVIEW');
  v_origin uuid := (p ->> 'external_origin_id')::uuid;
  v_id     uuid;
  v_e      jsonb;
BEGIN
  IF p_reason IS NULL OR length(btrim(p_reason)) < 5 THEN
    RAISE EXCEPTION 'a reason is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  IF v_origin IS NOT NULL THEN
    -- explicit human selection of an existing origin: it must exist and be evidenced for this claim
    PERFORM lfhe.check_selected_external_origin(v_origin, (p ->> 'child_claim_id')::uuid, NULL);
  ELSIF p ? 'external_origin' THEN
    v_origin := lfhe.resolve_external_origin(p -> 'external_origin' ->> 'name', p -> 'external_origin' ->> 'url',
      coalesce((p -> 'external_origin' ->> 'evidence_claim_id')::uuid, (p ->> 'child_claim_id')::uuid), v_actor, p_reason);
  END IF;
  v_id := lfhe.insert_claim_lineage((p ->> 'child_claim_id')::uuid,
    (p ->> 'relationship_type')::lfhe.lineage_relationship_type, (p ->> 'parent_claim_id')::uuid,
    (p ->> 'parent_article_id')::uuid, v_origin, 'HUMAN_RECORDED', NULL, v_actor, p_reason);
  -- CG3-01: the evidence the human relied on (claims / articles). Without it the row has no
  -- provable knowledge bound and is never used in REPLAY.
  FOR v_e IN SELECT * FROM pg_catalog.jsonb_array_elements(coalesce(p -> 'evidence_basis', '[]')) LOOP
    IF v_e ->> 'object_type' = 'claim' AND EXISTS (SELECT 1 FROM lfhe.claims WHERE id = (v_e ->> 'object_id')::uuid)
       OR v_e ->> 'object_type' = 'article' AND EXISTS (SELECT 1 FROM lfhe.articles WHERE id = (v_e ->> 'object_id')::uuid) THEN
      INSERT INTO lfhe.claim_lineage_evidence (lineage_id, object_type, object_id)
      VALUES (v_id, v_e ->> 'object_type', (v_e ->> 'object_id')::uuid) ON CONFLICT DO NOTHING;
    ELSE
      RAISE EXCEPTION 'EVIDENCE_BASIS_INVALID: %', left(v_e::text, 200) USING ERRCODE = 'check_violation';
    END IF;
  END LOOP;
  RETURN v_id;
END $$;
