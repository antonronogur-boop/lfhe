-- LFHÉ Phase 3 (P3-04) — M05 AI update: carry existing claims forward.
--
-- Found while wiring the real M05 input builder: the model receives an existing
-- event only as context (its current head, with its cutoff-ELIGIBLE claims);
-- new claims are the run inputs. 20261011001900 required every claim of an
-- UPDATE candidate to be a run input AND required the model to restate every
-- existing claim, which (a) rejected every realistic update and (b) could never
-- be satisfied for an event holding post-cutoff claims withheld from the model.
--
-- Now (Addendum §11 / §13 unchanged in substance):
--   * existing head claims are carried forward automatically with their roles
--     (an AI update still cannot remove a claim);
--   * the model may re-list an existing claim only with its unchanged role
--     (AI_UPDATE_MAY_NOT_REMOVE_OR_RECAST_CLAIMS);
--   * every other claim must be a run input; all listed claims must be
--     cutoff-eligible; dates / locations may come only from new claims or the
--     head's cutoff-eligible claims.
-- Forward-only migration: 20261011001900 is not edited.

CREATE OR REPLACE FUNCTION lfhe.event_proposal_problems(p_run uuid, p_mode text, p_cutoff timestamptz, x jsonb)
RETURNS text[] LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_out    text[] := '{}';
  v_type   text := x ->> 'proposal';
  v_cand   jsonb := x -> 'event_candidate';
  v_c      text;
  v_head   lfhe.event_versions;
  v_all    uuid[];
  v_kept   uuid[] := '{}';
  v_uuid   constant text := '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$';
BEGIN
  IF v_type IS NULL OR v_type NOT IN ('CREATE_NEW_EVENT', 'UPDATE_EXISTING_EVENT', 'SUGGEST_MERGE', 'SUGGEST_SPLIT',
      'SUGGEST_SUPERSEDE', 'KEEP_SEPARATE', 'INSUFFICIENT_INFORMATION', 'HUMAN_REVIEW_REQUIRED') THEN
    RETURN ARRAY['PROPOSAL_TYPE_NOT_ALLOWED:' || left(coalesce(v_type, 'null'), 60)];
  END IF;
  -- an UPDATE may re-list claims of the target's current head (carried forward
  -- automatically); every other claim must be a run input. All must be cutoff-eligible.
  IF v_type = 'UPDATE_EXISTING_EVENT' AND (x ->> 'target_event_id') ~ v_uuid
     AND EXISTS (SELECT 1 FROM lfhe.events WHERE id = (x ->> 'target_event_id')::uuid) THEN
    v_kept := ARRAY(SELECT claim_id FROM lfhe.event_claims
                    WHERE event_version_id = (lfhe.event_head_version((x ->> 'target_event_id')::uuid)).id);
  END IF;
  FOR v_c IN SELECT pg_catalog.jsonb_array_elements_text(coalesce(x -> 'claim_ids', '[]'))
             UNION SELECT c ->> 'claim_id' FROM pg_catalog.jsonb_array_elements(coalesce(v_cand -> 'claims', '[]')) c LOOP
    IF v_c IS NULL OR v_c !~ v_uuid
       OR NOT (lfhe.run_has_object(p_run, 'input', 'claim', v_c) OR v_c::uuid = ANY (v_kept)) THEN
      v_out := v_out || ('CLAIM_NOT_IN_MODEL_RUN_INPUT:' || left(coalesce(v_c, 'null'), 80));
    ELSIF NOT lfhe.claim_cutoff_eligible(v_c::uuid, p_mode, p_cutoff) THEN
      v_out := v_out || ('CLAIM_NOT_CUTOFF_ELIGIBLE:' || v_c);
    END IF;
  END LOOP;
  -- every referenced existing event must have been supplied as context (by its head version)
  FOR v_c IN SELECT x ->> 'target_event_id' WHERE x ->> 'target_event_id' IS NOT NULL
             UNION SELECT pg_catalog.jsonb_array_elements_text(coalesce(x -> 'related_event_ids', '[]')) LOOP
    IF v_c !~ v_uuid OR NOT EXISTS (SELECT 1 FROM lfhe.events WHERE id = v_c::uuid) THEN
      v_out := v_out || ('UNKNOWN_EVENT:' || left(v_c, 80));
    ELSIF NOT lfhe.run_has_object(p_run, 'context', 'event_version', (lfhe.event_head_version(v_c::uuid)).id::text) THEN
      v_out := v_out || ('EVENT_NOT_IN_MODEL_RUN_CONTEXT_OR_STALE:' || v_c);
    END IF;
  END LOOP;
  IF v_type IN ('UPDATE_EXISTING_EVENT', 'SUGGEST_MERGE', 'SUGGEST_SPLIT', 'SUGGEST_SUPERSEDE')
     AND (x ->> 'target_event_id') IS NULL THEN
    v_out := v_out || ('TARGET_EVENT_REQUIRED:' || v_type);
  END IF;
  IF v_type IN ('SUGGEST_MERGE', 'SUGGEST_SUPERSEDE')
     AND pg_catalog.jsonb_array_length(coalesce(x -> 'related_event_ids', '[]')) = 0 THEN
    v_out := v_out || ('RELATED_EVENTS_REQUIRED:' || v_type);
  END IF;
  IF v_type IN ('CREATE_NEW_EVENT', 'UPDATE_EXISTING_EVENT') THEN
    IF v_cand IS NULL OR pg_catalog.jsonb_typeof(v_cand) <> 'object'
       OR pg_catalog.jsonb_array_length(coalesce(v_cand -> 'claims', '[]')) = 0 THEN
      RETURN v_out || 'EVENT_CANDIDATE_WITH_CLAIMS_REQUIRED'::text;
    END IF;
    IF (v_cand ->> 'event_type') IS NULL OR NOT ((v_cand ->> 'event_type') = ANY (
         ARRAY(SELECT pg_catalog.unnest(pg_catalog.enum_range(NULL::lfhe.claim_type))::text))) THEN
      v_out := v_out || 'EVENT_TYPE_NOT_ALLOWED'::text;
    END IF;
    v_all := ARRAY(SELECT (c ->> 'claim_id')::uuid FROM pg_catalog.jsonb_array_elements(v_cand -> 'claims') c
                   WHERE (c ->> 'claim_id') ~ v_uuid);
    IF v_type = 'UPDATE_EXISTING_EVENT' AND (x ->> 'target_event_id') ~ v_uuid THEN
      v_head := lfhe.event_head_version((x ->> 'target_event_id')::uuid);
      IF v_head.id IS DISTINCT FROM (x ->> 'target_event_version_id')::uuid THEN
        v_out := v_out || 'TARGET_VERSION_NOT_CURRENT_HEAD'::text;
      END IF;
      IF NOT lfhe.event_is_open((x ->> 'target_event_id')::uuid) THEN
        v_out := v_out || 'TARGET_EVENT_NOT_OPEN'::text;
      END IF;
      -- an AI update may only ADD claims: existing claims are carried forward by the
      -- materialiser (they cannot be removed); a re-listed existing claim must keep its role
      IF EXISTS (SELECT 1 FROM lfhe.event_claims ec JOIN pg_catalog.jsonb_array_elements(v_cand -> 'claims') c
                   ON c ->> 'claim_id' = ec.claim_id::text
                 WHERE ec.event_version_id = v_head.id AND c ->> 'role' IS DISTINCT FROM ec.role::text) THEN
        v_out := v_out || 'AI_UPDATE_MAY_NOT_REMOVE_OR_RECAST_CLAIMS'::text;
      END IF;
      -- dates / places may come from the head's claims the model could see (cutoff-eligible)
      v_all := v_all || ARRAY(SELECT claim_id FROM lfhe.event_claims WHERE event_version_id = v_head.id
                              AND lfhe.claim_cutoff_eligible(claim_id, p_mode, p_cutoff));
    END IF;
    -- no invented dates / places: every date and location must come from the claims
    IF v_cand ->> 'event_date_start' IS NOT NULL AND NOT EXISTS (
         SELECT 1 FROM lfhe.claims WHERE id = ANY (v_all) AND event_date = v_cand ->> 'event_date_start') THEN
      v_out := v_out || 'EVENT_DATE_NOT_FROM_CLAIMS'::text;
    END IF;
    IF v_cand ->> 'event_date_end' IS NOT NULL AND NOT EXISTS (
         SELECT 1 FROM lfhe.claims WHERE id = ANY (v_all) AND event_date = v_cand ->> 'event_date_end') THEN
      v_out := v_out || 'EVENT_DATE_NOT_FROM_CLAIMS'::text;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_catalog.jsonb_array_elements_text(coalesce(v_cand -> 'locations', '[]')) l
               WHERE NOT EXISTS (SELECT 1 FROM lfhe.claims c WHERE c.id = ANY (v_all)
                                 AND c.location_mentions ? l)) THEN
      v_out := v_out || 'EVENT_LOCATION_NOT_FROM_CLAIMS'::text;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_catalog.jsonb_array_elements(v_cand -> 'claims') c
               WHERE c ->> 'role' IS NULL OR c ->> 'role' NOT IN ('SUPPORTS', 'CONTRADICTS', 'UPDATES', 'CONTEXTUALISES')) THEN
      v_out := v_out || 'CLAIM_ROLE_NOT_ALLOWED'::text;
    END IF;
  END IF;
  RETURN v_out;
END $$;
REVOKE ALL ON FUNCTION lfhe.event_proposal_problems(uuid, text, timestamptz, jsonb)
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;

CREATE OR REPLACE FUNCTION lfhe.ingest_event_proposals(p jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_run      lfhe.model_runs%ROWTYPE;
  v_mode     text;
  v_cutoff   timestamptz;
  v_reasons  text[] := '{}';
  v_x        jsonb;
  v_i        integer := 0;
  v_n        integer;
  v_outcome  text;
  v_status   text := p ->> 'output_status';
  v_event    uuid;
  v_version  uuid;
  v_created  integer := 0;
  v_versions integer := 0;
  v_ids      jsonb := '[]'::jsonb;
BEGIN
  SELECT * INTO v_run FROM lfhe.model_runs WHERE id = (p ->> 'model_run_id')::uuid;
  IF NOT FOUND OR v_run.module_code <> 'M05_EVENT_BUILDER' OR v_run.status = 'RUNNING' THEN
    RAISE EXCEPTION 'model run % is not a finished M05_EVENT_BUILDER run', p ->> 'model_run_id'
      USING ERRCODE = 'object_not_in_prerequisite_state';
  END IF;
  SELECT * INTO v_mode, v_cutoff FROM lfhe.model_run_cutoff(v_run.id);
  IF v_run.status <> 'SUCCEEDED' THEN
    INSERT INTO lfhe.event_ingestion_results (model_run_id, model_run_status, outcome, report_mode, information_cutoff,
      human_review_required, repair_of_model_run_id)
    VALUES (v_run.id, v_run.status, v_run.status::text, v_mode, v_cutoff, false, (p ->> 'repair_of_model_run_id')::uuid);
    RETURN pg_catalog.jsonb_build_object('outcome', v_run.status::text);
  END IF;

  FOR v_x IN SELECT * FROM pg_catalog.jsonb_array_elements(coalesce(p -> 'proposals', '[]')) LOOP
    v_reasons := v_reasons || lfhe.event_proposal_problems(v_run.id, v_mode, v_cutoff, v_x);
  END LOOP;
  -- a claim may be placed into at most one materialising proposal of an output
  IF EXISTS (SELECT c ->> 'claim_id' FROM pg_catalog.jsonb_array_elements(coalesce(p -> 'proposals', '[]')) x,
                    pg_catalog.jsonb_array_elements(coalesce(x -> 'event_candidate' -> 'claims', '[]')) c
             WHERE x ->> 'proposal' IN ('CREATE_NEW_EVENT', 'UPDATE_EXISTING_EVENT')
             GROUP BY 1 HAVING count(*) > 1) THEN
    v_reasons := v_reasons || 'CLAIM_IN_MULTIPLE_MATERIALISING_PROPOSALS'::text;
  END IF;
  -- two updates of the same event in one output are ambiguous
  IF EXISTS (SELECT x ->> 'target_event_id' FROM pg_catalog.jsonb_array_elements(coalesce(p -> 'proposals', '[]')) x
             WHERE x ->> 'proposal' = 'UPDATE_EXISTING_EVENT' GROUP BY 1 HAVING count(*) > 1) THEN
    v_reasons := v_reasons || 'MULTIPLE_UPDATES_OF_ONE_EVENT'::text;
  END IF;

  v_n := pg_catalog.jsonb_array_length(coalesce(p -> 'proposals', '[]'));
  v_reasons := ARRAY(SELECT DISTINCT r FROM pg_catalog.unnest(v_reasons) r ORDER BY r);
  v_outcome := CASE
    WHEN cardinality(v_reasons) > 0 THEN 'OUTPUT_REJECTED'
    WHEN v_n > 0 THEN 'PROPOSALS_RECORDED'
    WHEN v_status = 'INSUFFICIENT_INFORMATION' THEN 'INSUFFICIENT_INFORMATION'
    WHEN v_status = 'HUMAN_REVIEW_REQUIRED' THEN 'HUMAN_REVIEW_REQUIRED'
    ELSE 'NO_PROPOSALS' END;

  INSERT INTO lfhe.event_ingestion_results (model_run_id, model_run_status, output_status, outcome, report_mode,
    information_cutoff, proposals_recorded, rejection_reasons, human_review_required, warnings, repair_of_model_run_id)
  VALUES (v_run.id, v_run.status, v_status, v_outcome, v_mode, v_cutoff,
    CASE WHEN v_outcome = 'PROPOSALS_RECORDED' THEN v_n ELSE 0 END, v_reasons,
    coalesce((p ->> 'human_review_required')::boolean, false) OR v_outcome IN ('OUTPUT_REJECTED', 'HUMAN_REVIEW_REQUIRED'),
    coalesce(p -> 'warnings', '[]'), (p ->> 'repair_of_model_run_id')::uuid);
  IF v_outcome <> 'PROPOSALS_RECORDED' THEN
    RETURN pg_catalog.jsonb_build_object('outcome', v_outcome, 'rejection_reasons', pg_catalog.to_jsonb(v_reasons));
  END IF;

  FOR v_x IN SELECT * FROM pg_catalog.jsonb_array_elements(p -> 'proposals') LOOP
    v_event := NULL;
    v_version := NULL;
    IF v_x ->> 'proposal' = 'CREATE_NEW_EVENT' THEN
      INSERT INTO lfhe.events (origin, created_by_model_run_id) VALUES ('AI', v_run.id) RETURNING id INTO v_event;
      v_version := lfhe.write_event_version(v_event, v_x -> 'event_candidate', v_x -> 'event_candidate' -> 'claims',
                                            'AI', v_run.id, NULL, NULL);
      INSERT INTO lfhe.event_state_history (event_id, old_state, new_state, actor_type, reason)
      VALUES (v_event, NULL, 'CANDIDATE', 'WORKER', 'AI-originated candidate (M05 CREATE_NEW_EVENT); not validated');
      v_created := v_created + 1;
    ELSIF v_x ->> 'proposal' = 'UPDATE_EXISTING_EVENT' THEN
      v_event := (v_x ->> 'target_event_id')::uuid;
      v_version := lfhe.write_event_version(v_event, v_x -> 'event_candidate',
        lfhe.version_claims((lfhe.event_head_version(v_event)).id) || coalesce((
          SELECT pg_catalog.jsonb_agg(c) FROM pg_catalog.jsonb_array_elements(v_x -> 'event_candidate' -> 'claims') c
          WHERE NOT EXISTS (SELECT 1 FROM lfhe.event_claims ec
                            WHERE ec.event_version_id = (lfhe.event_head_version(v_event)).id
                              AND ec.claim_id::text = c ->> 'claim_id')), '[]'::jsonb),
        'AI', v_run.id, NULL, NULL);
      v_versions := v_versions + 1;
    END IF;
    INSERT INTO lfhe.event_proposals (model_run_id, proposal_index, proposal_type, target_event_id,
      target_event_version_id, related_event_ids, claim_ids, event_candidate, reason, proposal_confidence,
      materialised_event_id, materialised_version_id)
    VALUES (v_run.id, v_i, (v_x ->> 'proposal')::lfhe.event_proposal_type, (v_x ->> 'target_event_id')::uuid,
      (v_x ->> 'target_event_version_id')::uuid,
      ARRAY(SELECT pg_catalog.jsonb_array_elements_text(coalesce(v_x -> 'related_event_ids', '[]'))::uuid),
      ARRAY(SELECT pg_catalog.jsonb_array_elements_text(coalesce(v_x -> 'claim_ids', '[]'))::uuid),
      v_x -> 'event_candidate', coalesce(nullif(v_x ->> 'reason', ''), 'no reason given'),
      (v_x ->> 'confidence')::lfhe.assignment_confidence, v_event, v_version);
    v_ids := v_ids || pg_catalog.jsonb_build_object('proposal', v_x ->> 'proposal', 'event_id', v_event, 'version_id', v_version);
    v_i := v_i + 1;
  END LOOP;
  RETURN pg_catalog.jsonb_build_object('outcome', v_outcome, 'proposals', v_n, 'events_created', v_created,
                                       'versions_created', v_versions, 'materialised', v_ids);
END $$;
REVOKE ALL ON FUNCTION lfhe.ingest_event_proposals(jsonb) FROM PUBLIC, anon, authenticated, service_role, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.ingest_event_proposals(jsonb) TO lfhe_worker;
