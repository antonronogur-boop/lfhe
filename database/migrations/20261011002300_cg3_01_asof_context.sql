-- LFHÉ CG3 corrective pass — CG3-01: as-of (knowledge-bound) lineage and event context.
--
-- PO decision: docs/specs/PO_Decision_2026-10-19_CG3_Targeted_Corrective_Pass.md.
-- Problem: M04/M05 context used CURRENT lineage, independence groups and event
-- heads (title, description, dates, locations, membership, state, merge/supersede
-- outcome), filtering only the claims inside the current head by cutoff.
--
-- Rule introduced here: an authoritative object may enter a run with
-- (report_mode, information_cutoff) only if its KNOWLEDGE BOUND is provably
-- cutoff-eligible. Bounds are computed from immutable, already-stored evidence
-- (reproducible), never from processing / decision timestamps alone:
--
--   claim_lineage row   endpoints (child claim, parent claim | parent article,
--                       external-origin evidence claim)
--                       + PROPOSAL_ACCEPTED: every input/context object of the
--                         proposing M04 run (recursively for context lineage)
--                       + HUMAN_RECORDED: the evidence basis the human declared
--                         (lfhe.claim_lineage_evidence). Without a declared basis
--                         the row is UNBOUNDED: never usable in REPLAY; in LIVE
--                         only if recorded at or before the cutoff.
--   event_version       its member claims, every previous version, the AI run's
--                       inputs/context (incl. event versions it was shown), and
--                       the versions it consumed (MERGED_INTO sources, SPLIT_INTO
--                       parent).
--   event state row     bound to the head version current when it was written
--                       (lfhe.event_state_version_bindings, filled by trigger);
--                       usable iff that version is eligible. Unbound rows fail closed.
--   event relationship  usable iff both bound versions are eligible.
--
-- Processing / validation after the cutoff remains allowed: a decision taken
-- later on cutoff-eligible evidence is usable (PO CG3-01 item 7).
-- Retracted lineage is never used (a retraction removes an asserted dependence).
-- Forward-only: earlier migrations are not edited.

-- ---------------------------------------------------------------------------
-- Article eligibility (same rule as lfhe.claim_cutoff_eligible, any snapshot)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.article_cutoff_eligible(p_article uuid, p_mode text, p_cutoff timestamptz)
RETURNS boolean LANGUAGE sql STABLE SET search_path = pg_catalog, pg_temp AS $$
  SELECT EXISTS (
    SELECT 1 FROM lfhe.article_snapshots s WHERE s.article_id = p_article AND CASE p_mode
      WHEN 'LIVE' THEN s.system_retrieval_datetime <= p_cutoff
                       AND (s.public_availability_datetime IS NULL OR s.public_availability_datetime <= p_cutoff)
      WHEN 'REPLAY' THEN s.public_availability_datetime IS NOT NULL AND s.public_availability_datetime <= p_cutoff
      ELSE false END)
$$;
REVOKE ALL ON FUNCTION lfhe.article_cutoff_eligible(uuid, text, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION lfhe.article_cutoff_eligible(uuid, text, timestamptz) TO authenticated, lfhe_worker;

-- ---------------------------------------------------------------------------
-- Declared evidence basis of human-recorded lineage
-- ---------------------------------------------------------------------------
CREATE TABLE lfhe.claim_lineage_evidence (
  lineage_id   uuid NOT NULL REFERENCES lfhe.claim_lineage(id),
  object_type  text NOT NULL CHECK (object_type IN ('claim', 'article')),
  object_id    uuid NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (lineage_id, object_type, object_id)
);
CREATE TRIGGER claim_lineage_evidence_immutable BEFORE UPDATE OR DELETE ON lfhe.claim_lineage_evidence
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();

-- State row → head version at the moment it was written
CREATE TABLE lfhe.event_state_version_bindings (
  state_history_id  uuid PRIMARY KEY REFERENCES lfhe.event_state_history(id),
  event_version_id  uuid NOT NULL REFERENCES lfhe.event_versions(id),
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER event_state_version_bindings_immutable BEFORE UPDATE OR DELETE ON lfhe.event_state_version_bindings
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();

CREATE OR REPLACE FUNCTION lfhe.bind_event_state_to_head()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_head uuid := (lfhe.event_head_version(NEW.event_id)).id;
BEGIN
  IF v_head IS NOT NULL THEN
    INSERT INTO lfhe.event_state_version_bindings (state_history_id, event_version_id) VALUES (NEW.id, v_head);
  END IF;
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION lfhe.bind_event_state_to_head() FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
CREATE TRIGGER event_state_history_bind_version AFTER INSERT ON lfhe.event_state_history
  FOR EACH ROW EXECUTE FUNCTION lfhe.bind_event_state_to_head();

REVOKE ALL ON lfhe.claim_lineage_evidence, lfhe.event_state_version_bindings
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT SELECT ON lfhe.claim_lineage_evidence, lfhe.event_state_version_bindings TO authenticated, lfhe_worker;
DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['claim_lineage_evidence', 'event_state_version_bindings'] LOOP
    EXECUTE format('ALTER TABLE lfhe.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY %I ON lfhe.%I FOR SELECT TO authenticated USING (lfhe.has_permission(''CLAIM_READ''))',
                   t || '_read_human', t);
    EXECUTE format('CREATE POLICY %I ON lfhe.%I FOR SELECT TO lfhe_worker USING (true)', t || '_read_worker', t);
  END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- Knowledge-bound checks (mutually recursive; depth-limited over cross links)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.run_evidence_eligible(p_run uuid, p_mode text, p_cutoff timestamptz, p_depth integer DEFAULT 0)
RETURNS boolean LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  r record;
BEGIN
  IF p_depth > 50 OR p_run IS NULL OR NOT EXISTS (SELECT 1 FROM lfhe.model_runs WHERE id = p_run) THEN
    RETURN false;
  END IF;
  FOR r IN SELECT x ->> 'object_type' AS t, x ->> 'object_id' AS i
           FROM lfhe.model_runs m,
                pg_catalog.jsonb_array_elements(coalesce(m.input_manifest, '[]') || coalesce(m.context_manifest, '[]')) x
           WHERE m.id = p_run LOOP
    IF r.t = 'claim' THEN
      IF NOT lfhe.claim_cutoff_eligible(r.i::uuid, p_mode, p_cutoff) THEN RETURN false; END IF;
    ELSIF r.t = 'article' THEN
      IF NOT lfhe.article_cutoff_eligible(r.i::uuid, p_mode, p_cutoff) THEN RETURN false; END IF;
    ELSIF r.t = 'claim_lineage' THEN
      IF NOT lfhe.lineage_usable(r.i::uuid, p_mode, p_cutoff, p_depth + 1) THEN RETURN false; END IF;
    ELSIF r.t = 'event_version' THEN
      IF NOT lfhe.event_version_eligible(r.i::uuid, p_mode, p_cutoff, p_depth + 1) THEN RETURN false; END IF;
    ELSE
      RETURN false;           -- evidence of a kind without a provable bound: fail closed
    END IF;
  END LOOP;
  RETURN true;
END $$;

CREATE OR REPLACE FUNCTION lfhe.lineage_usable(p_lineage uuid, p_mode text, p_cutoff timestamptz, p_depth integer DEFAULT 0)
RETURNS boolean LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  l lfhe.claim_lineage%ROWTYPE;
BEGIN
  IF p_depth > 50 OR p_mode NOT IN ('LIVE', 'REPLAY') OR p_cutoff IS NULL THEN
    RETURN false;
  END IF;
  SELECT * INTO l FROM lfhe.claim_lineage WHERE id = p_lineage;
  IF NOT FOUND OR EXISTS (SELECT 1 FROM lfhe.claim_lineage_retractions r WHERE r.lineage_id = l.id) THEN
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

CREATE OR REPLACE FUNCTION lfhe.event_version_eligible(p_version uuid, p_mode text, p_cutoff timestamptz,
                                                       p_depth integer DEFAULT 0)
RETURNS boolean LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v lfhe.event_versions%ROWTYPE;
  v_cur uuid := p_version;
BEGIN
  IF p_depth > 50 OR p_mode NOT IN ('LIVE', 'REPLAY') OR p_cutoff IS NULL THEN
    RETURN false;
  END IF;
  LOOP                                             -- walk the version chain iteratively
    SELECT * INTO v FROM lfhe.event_versions WHERE id = v_cur;
    IF NOT FOUND THEN
      RETURN false;
    END IF;
    IF EXISTS (SELECT 1 FROM lfhe.event_claims ec WHERE ec.event_version_id = v.id
               AND NOT lfhe.claim_cutoff_eligible(ec.claim_id, p_mode, p_cutoff)) THEN
      RETURN false;
    END IF;
    IF v.origin = 'AI' AND NOT lfhe.run_evidence_eligible(v.created_by_model_run_id, p_mode, p_cutoff, p_depth + 1) THEN
      RETURN false;
    END IF;
    IF EXISTS (SELECT 1 FROM lfhe.event_relationships r WHERE r.to_version_id = v.id
               AND r.relationship_type IN ('MERGED_INTO', 'SPLIT_INTO')
               AND NOT lfhe.event_version_eligible(r.from_version_id, p_mode, p_cutoff, p_depth + 1)) THEN
      RETURN false;
    END IF;
    EXIT WHEN v.previous_version_id IS NULL;
    v_cur := v.previous_version_id;
  END LOOP;
  RETURN true;
END $$;

-- As-of representation of one event: the latest version whose bound is eligible,
-- the latest state bound to an eligible version, and only structural outcomes
-- whose two versions are eligible. No row when nothing can be proven.
CREATE OR REPLACE FUNCTION lfhe.event_asof(p_event uuid, p_mode text, p_cutoff timestamptz)
RETURNS TABLE (event_id uuid, version_id uuid, state lfhe.event_state, structural_status text, is_open boolean)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_ver   uuid;
  v_state lfhe.event_state;
  v_struc text;
BEGIN
  SELECT v.id INTO v_ver FROM lfhe.event_versions v
  WHERE v.event_id = p_event AND lfhe.event_version_eligible(v.id, p_mode, p_cutoff)
  ORDER BY v.version_no DESC LIMIT 1;
  IF v_ver IS NULL THEN
    RETURN;
  END IF;
  SELECT s.new_state INTO v_state FROM lfhe.event_state_history s
  JOIN lfhe.event_state_version_bindings b ON b.state_history_id = s.id
  WHERE s.event_id = p_event AND lfhe.event_version_eligible(b.event_version_id, p_mode, p_cutoff)
  ORDER BY s.seq DESC LIMIT 1;
  SELECT r.relationship_type::text INTO v_struc FROM lfhe.event_relationships r
  WHERE r.from_event_id = p_event AND r.relationship_type IN ('MERGED_INTO', 'SUPERSEDED_BY')
    AND lfhe.event_version_eligible(r.from_version_id, p_mode, p_cutoff)
    AND lfhe.event_version_eligible(r.to_version_id, p_mode, p_cutoff)
  LIMIT 1;
  IF v_struc IS NULL AND EXISTS (
       SELECT 1 FROM lfhe.event_relationships r
       WHERE r.from_event_id = p_event AND r.relationship_type = 'SPLIT_INTO' AND r.from_version_id = v_ver
         AND lfhe.event_version_eligible(r.to_version_id, p_mode, p_cutoff)) THEN
    v_struc := 'SPLIT_INTO';                       -- fully split as of the cutoff (CG3-02)
  END IF;
  event_id := p_event;
  version_id := v_ver;
  state := v_state;
  structural_status := v_struc;
  is_open := v_state IS NOT NULL AND v_state <> 'REJECTED' AND v_struc IS NULL;
  RETURN NEXT;
END $$;

-- As-of independence groups: connected components over USABLE lineage only.
CREATE OR REPLACE FUNCTION lfhe.claim_independence_group_asof(p_claim uuid, p_mode text, p_cutoff timestamptz)
RETURNS TABLE (claim_id uuid, independence_group text, lineage_known boolean)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  WITH RECURSIVE usable AS (
    SELECT l.* FROM lfhe.claim_lineage l WHERE lfhe.lineage_usable(l.id, p_mode, p_cutoff)
  ), edges AS (
    SELECT 'c:' || l.child_claim_id AS a,
           CASE WHEN l.parent_claim_id IS NOT NULL THEN 'c:' || l.parent_claim_id
                WHEN l.parent_article_id IS NOT NULL THEN 'a:' || l.parent_article_id
                ELSE 'o:' || l.external_origin_id END AS b
    FROM usable l
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

CREATE OR REPLACE FUNCTION lfhe.independence_summary_asof(p_claims uuid[], p_mode text, p_cutoff timestamptz)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  WITH g AS (SELECT (lfhe.claim_independence_group_asof(c, p_mode, p_cutoff)).* FROM pg_catalog.unnest(p_claims) c)
  SELECT pg_catalog.jsonb_build_object(
    'claims', (SELECT count(*) FROM g),
    'distinct_groups_upper_bound', (SELECT count(DISTINCT independence_group) FROM g),
    'claims_with_validated_lineage', (SELECT count(*) FROM g WHERE lineage_known),
    'claims_with_unknown_lineage', (SELECT count(*) FROM g WHERE NOT lineage_known),
    'independence_established', false,
    'basis', 'VALIDATED_LINEAGE_DEPENDENCE_ONLY',
    'report_mode', p_mode, 'information_cutoff', p_cutoff)
$$;

REVOKE ALL ON FUNCTION
  lfhe.run_evidence_eligible(uuid, text, timestamptz, integer),
  lfhe.lineage_usable(uuid, text, timestamptz, integer),
  lfhe.event_version_eligible(uuid, text, timestamptz, integer),
  lfhe.event_asof(uuid, text, timestamptz),
  lfhe.claim_independence_group_asof(uuid, text, timestamptz),
  lfhe.independence_summary_asof(uuid[], text, timestamptz)
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
-- definer functions (they read model-run manifests): worker only, for envelope building
GRANT EXECUTE ON FUNCTION
  lfhe.run_evidence_eligible(uuid, text, timestamptz, integer),
  lfhe.lineage_usable(uuid, text, timestamptz, integer),
  lfhe.event_version_eligible(uuid, text, timestamptz, integer),
  lfhe.event_asof(uuid, text, timestamptz),
  lfhe.claim_independence_group_asof(uuid, text, timestamptz),
  lfhe.independence_summary_asof(uuid[], text, timestamptz)
  TO lfhe_worker;

-- ---------------------------------------------------------------------------
-- Human-recorded lineage may carry a declared evidence basis (p.evidence_basis:
-- [{object_type: claim|article, object_id}])
-- ---------------------------------------------------------------------------
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
  IF p ? 'external_origin' THEN
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

-- ---------------------------------------------------------------------------
-- M05 ingestion: referenced events must have been supplied by their AS-OF
-- version for this run (not the current head)
-- ---------------------------------------------------------------------------
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
    ELSIF NOT lfhe.run_has_object(p_run, 'context', 'event_version',
                                  (SELECT a.version_id FROM lfhe.event_asof(v_c::uuid, p_mode, p_cutoff) a)::text) THEN
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
      -- CG3-01: an update may only be materialised against the version the model was shown,
      -- and only when that as-of version IS the current head (no later knowledge exists)
      IF NOT lfhe.run_has_object(p_run, 'context', 'event_version', x ->> 'target_event_version_id') THEN
        v_out := v_out || 'UPDATE_TARGET_VERSION_NOT_SUPPLIED'::text;
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
