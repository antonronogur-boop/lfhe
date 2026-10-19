-- LFHÉ CG3 corrective pass — CG3-02: a full split (no retained remainder) is terminal.
--
-- Problem: split_event with retained = null redistributed every claim to child
-- events while the parent stayed open with its previous head and complete claim
-- set (event_is_open did not treat SPLIT_INTO as terminal) — two current
-- representations of the same claims.
--
-- Semantics now:
--   SPLIT WITH RETAINED  the parent gets the retained version (newer than the
--                        version the SPLIT_INTO relationships start from); it stays
--                        open as the retained remainder, current only with the
--                        retained claim set.
--   FULL SPLIT           SPLIT_INTO relationships start from the parent's current
--                        head (no retained version followed). The parent keeps its
--                        ID, all versions and its SPLIT_INTO lineage, but is no longer
--                        open/current: no M05 candidate (event_asof, migration 2300),
--                        no update / merge / supersede / split (require_event_head →
--                        EVENT_NOT_OPEN), and event_heads presents no current version
--                        (current_version_id NULL, is_current false,
--                        structural_status SPLIT_INTO).
-- Nothing is deleted or rewritten. resolve_event(parent) stays relationship-based.
-- Forward-only.

CREATE OR REPLACE FUNCTION lfhe.event_fully_split(p_event uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT EXISTS (SELECT 1 FROM lfhe.event_relationships r
                 WHERE r.from_event_id = p_event AND r.relationship_type = 'SPLIT_INTO'
                   AND r.from_version_id = (lfhe.event_head_version(p_event)).id)
$$;
REVOKE ALL ON FUNCTION lfhe.event_fully_split(uuid) FROM PUBLIC, anon, service_role, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.event_fully_split(uuid) TO authenticated, lfhe_worker;

CREATE OR REPLACE FUNCTION lfhe.event_is_open(p_event uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT EXISTS (SELECT 1 FROM lfhe.events WHERE id = p_event)
     AND lfhe.event_current_state(p_event) IS DISTINCT FROM 'REJECTED'
     AND lfhe.event_successor(p_event) IS NULL
     AND NOT lfhe.event_fully_split(p_event)
$$;

CREATE OR REPLACE FUNCTION lfhe.require_event_head(p_event uuid, p_expected_version uuid)
RETURNS lfhe.event_versions LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_head lfhe.event_versions;
BEGIN
  PERFORM 1 FROM lfhe.events WHERE id = p_event FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'unknown event %', p_event USING ERRCODE = 'no_data_found';
  END IF;
  v_head := lfhe.event_head_version(p_event);
  IF v_head.id IS DISTINCT FROM p_expected_version THEN
    RAISE EXCEPTION 'EVENT_HEAD_STALE: event % head is %, not %', p_event, v_head.id, p_expected_version
      USING ERRCODE = 'serialization_failure';
  END IF;
  IF NOT lfhe.event_is_open(p_event) THEN
    RAISE EXCEPTION 'EVENT_NOT_OPEN: event % is rejected, merged, superseded or fully split', p_event
      USING ERRCODE = 'object_not_in_prerequisite_state';
  END IF;
  RETURN v_head;
END $$;

-- set_event_state: a fully split parent has no current representation to change
CREATE OR REPLACE FUNCTION lfhe.set_event_state(p_event uuid, p_expected_state lfhe.event_state,
                                                p_new_state lfhe.event_state, p_reason text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('EVENT_ACTION');
  v_cur   lfhe.event_state;
BEGIN
  IF p_reason IS NULL OR length(btrim(p_reason)) < 5 THEN
    RAISE EXCEPTION 'a reason is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  IF p_new_state = 'REJECTED' THEN
    RAISE EXCEPTION 'use lfhe.reject_event for REJECT' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  PERFORM 1 FROM lfhe.events WHERE id = p_event FOR UPDATE;
  v_cur := lfhe.event_current_state(p_event);
  IF v_cur IS DISTINCT FROM p_expected_state THEN
    RAISE EXCEPTION 'EVENT_STATE_STALE: state is %, not %', v_cur, p_expected_state USING ERRCODE = 'serialization_failure';
  END IF;
  IF v_cur = 'REJECTED' THEN
    RAISE EXCEPTION 'EVENT_NOT_OPEN: a rejected event keeps its history and is not reopened here'
      USING ERRCODE = 'object_not_in_prerequisite_state';
  END IF;
  IF lfhe.event_fully_split(p_event) THEN
    RAISE EXCEPTION 'EVENT_NOT_OPEN: event % was fully split; its children carry the current state', p_event
      USING ERRCODE = 'object_not_in_prerequisite_state';
  END IF;
  INSERT INTO lfhe.event_state_history (event_id, old_state, new_state, actor_type, actor_user_id, reason)
  VALUES (p_event, v_cur, p_new_state, 'HUMAN', v_actor, p_reason);
  IF v_cur = 'CANDIDATE' THEN
    PERFORM lfhe.write_audit('EVENT_MANUALLY_PROMOTED', 'event', p_event::text, NULL, NULL,
      pg_catalog.jsonb_build_object('from', v_cur, 'to', p_new_state));
  END IF;
END $$;

-- event_heads: same columns, plus current_version_id / is_current (appended).
-- structural_status now also reports SPLIT_INTO for a fully split parent.
CREATE OR REPLACE VIEW lfhe.event_heads WITH (security_invoker = true) AS
SELECT e.id AS event_id, e.origin, h.id AS head_version_id, h.version_no AS head_version_no,
       h.content_hash AS head_content_hash, h.title, h.event_type,
       (SELECT s.new_state FROM lfhe.event_state_history s WHERE s.event_id = e.id ORDER BY s.seq DESC LIMIT 1) AS state,
       coalesce((SELECT r.relationship_type FROM lfhe.event_relationships r WHERE r.from_event_id = e.id
                   AND r.relationship_type IN ('MERGED_INTO', 'SUPERSEDED_BY')),
                CASE WHEN EXISTS (SELECT 1 FROM lfhe.event_relationships r WHERE r.from_event_id = e.id
                                  AND r.relationship_type = 'SPLIT_INTO' AND r.from_version_id = h.id)
                     THEN 'SPLIT_INTO'::lfhe.event_relationship_type END) AS structural_status,
       (SELECT r.to_event_id FROM lfhe.event_relationships r WHERE r.from_event_id = e.id
          AND r.relationship_type IN ('MERGED_INTO', 'SUPERSEDED_BY')) AS successor_event_id,
       (SELECT rv.decision FROM lfhe.event_version_reviews rv WHERE rv.event_version_id = h.id ORDER BY rv.seq DESC LIMIT 1)
         AS head_review_decision,
       (h.origin = 'AI' AND NOT EXISTS (SELECT 1 FROM lfhe.event_version_reviews rv WHERE rv.event_version_id = h.id))
         AS head_pending_review,
       CASE WHEN lfhe.event_is_open(e.id) THEN h.id END AS current_version_id,
       lfhe.event_is_open(e.id) AS is_current
FROM lfhe.events e
JOIN LATERAL (SELECT * FROM lfhe.event_versions v WHERE v.event_id = e.id ORDER BY v.version_no DESC LIMIT 1) h ON true;
