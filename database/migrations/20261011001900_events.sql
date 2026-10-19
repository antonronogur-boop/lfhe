-- ============================================================================
-- P3-02  Persistent events (Phase 3 Addendum v1.0 §5–§11, §14; CG0 EVENT
--        state machine; Prompt Pack v1.2 §14 M05; G-17)
--
-- * events: stable identity, immutable. event_versions: immutable versions with
--   a DATABASE-verified canonical hash ('lfhe-event-version/1') over the version
--   content AND its exact claim membership (event_claims). A material change is
--   a new version; nothing is edited in place; nothing is deleted.
-- * M05 (worker, lfhe.ingest_event_proposals) may only:
--     CREATE_NEW_EVENT      → new AI-originated event in state CANDIDATE (+ version 1)
--     UPDATE_EXISTING_EVENT → new AI-originated version of the CURRENT head that
--                             keeps every existing claim (it may only add claims)
--   Every other proposal (SUGGEST_MERGE / SPLIT / SUPERSEDE, KEEP_SEPARATE,
--   INSUFFICIENT_INFORMATION, HUMAN_REVIEW_REQUIRED) is stored as a proposal only.
--   AI versions are PENDING review until a human decides.
-- * Human EVENT_ACTION (permission EVENT_ACTION, HUMAN_ONLY): CREATE, UPDATE,
--   MERGE, SPLIT, KEEP_SEPARATE, SUPERSEDE, REJECT, plus lifecycle state changes.
--   Each is recorded in event_actions (actor, reason, time, involved version
--   hashes); MERGE / SPLIT / SUPERSEDE add event_relationships and an explicit
--   claim redistribution; no claim may disappear.
-- * Historical references stay resolvable: lfhe.resolve_event follows
--   MERGED_INTO / SUPERSEDED_BY to the current event.
-- * Event type vocabulary = claim_type (PO Phase 3 decision, Addendum §7).
-- ============================================================================

CREATE TYPE lfhe.event_state AS ENUM ('CANDIDATE', 'ACTIVE', 'DEVELOPING', 'CONFIRMED', 'CONTESTED', 'CLOSED', 'REJECTED');
CREATE TYPE lfhe.event_proposal_type AS ENUM (
  'CREATE_NEW_EVENT', 'UPDATE_EXISTING_EVENT', 'SUGGEST_MERGE', 'SUGGEST_SPLIT', 'SUGGEST_SUPERSEDE',
  'KEEP_SEPARATE', 'INSUFFICIENT_INFORMATION', 'HUMAN_REVIEW_REQUIRED');
CREATE TYPE lfhe.event_claim_role AS ENUM ('SUPPORTS', 'CONTRADICTS', 'UPDATES', 'CONTEXTUALISES');
CREATE TYPE lfhe.event_relationship_type AS ENUM ('MERGED_INTO', 'SUPERSEDED_BY', 'SPLIT_INTO');

INSERT INTO lfhe.audit_event_types (code, spec_source) VALUES
  ('EVENT_VERSION_CREATED', 'Phase 3 impl.'),
  ('EVENT_STATE_CHANGED', 'Phase 3 impl.'),
  ('EVENT_ACTION_RECORDED', 'Phase 3 impl.'),
  ('EVENT_PROPOSAL_RECORDED', 'Phase 3 impl.'),
  ('EVENT_INGESTION_RECORDED', 'Phase 3 impl.'),
  ('EVENT_VERSION_REVIEWED', 'Phase 3 impl.'),
  ('EVENT_RELATIONSHIP_CREATED', 'Phase 3 impl.');

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------
CREATE TABLE lfhe.events (
  id                       uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  origin                   text NOT NULL CHECK (origin IN ('AI', 'HUMAN')),
  created_by_model_run_id  uuid REFERENCES lfhe.model_runs(id),
  created_by_user          uuid,
  created_at               timestamptz NOT NULL DEFAULT now(),
  CHECK ((origin = 'AI') = (created_by_model_run_id IS NOT NULL AND created_by_user IS NULL)),
  CHECK ((origin = 'HUMAN') = (created_by_user IS NOT NULL AND created_by_model_run_id IS NULL))
);

CREATE TABLE lfhe.event_actions (
  id             uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  action         lfhe.event_action NOT NULL,
  actor_user_id  uuid NOT NULL,
  reason         text NOT NULL CHECK (length(btrim(reason)) >= 5),
  proposal_id    uuid,
  details        jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE lfhe.event_versions (
  id                       uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  event_id                 uuid NOT NULL REFERENCES lfhe.events(id),
  version_no               integer NOT NULL CHECK (version_no >= 1),
  previous_version_id      uuid REFERENCES lfhe.event_versions(id),
  title                    text NOT NULL CHECK (length(btrim(title)) BETWEEN 3 AND 300),
  description              text NOT NULL CHECK (length(btrim(description)) BETWEEN 1 AND 4000),
  event_type               lfhe.claim_type NOT NULL,
  event_date_start         text CHECK (event_date_start ~ '^[0-9]{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12][0-9]|3[01]))?)?$'),
  event_date_end           text CHECK (event_date_end ~ '^[0-9]{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12][0-9]|3[01]))?)?$'),
  event_date_confidence    lfhe.timestamp_confidence NOT NULL,
  locations                text[] NOT NULL DEFAULT '{}',
  origin                   text NOT NULL CHECK (origin IN ('AI', 'HUMAN')),
  created_by_model_run_id  uuid REFERENCES lfhe.model_runs(id),
  created_by_user          uuid,
  action_id                uuid REFERENCES lfhe.event_actions(id),
  content_hash             text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  created_at               timestamptz NOT NULL DEFAULT now(),
  UNIQUE (event_id, version_no),
  UNIQUE (id, content_hash),
  CHECK ((version_no = 1) = (previous_version_id IS NULL)),
  CHECK ((origin = 'AI') = (created_by_model_run_id IS NOT NULL AND created_by_user IS NULL)),
  CHECK ((origin = 'HUMAN') = (created_by_user IS NOT NULL AND created_by_model_run_id IS NULL AND action_id IS NOT NULL)),
  CHECK (event_date_start IS NOT NULL OR event_date_end IS NULL),
  CHECK (event_date_start IS NOT NULL OR event_date_confidence = 'UNKNOWN')
);

CREATE TABLE lfhe.event_claims (
  event_version_id  uuid NOT NULL REFERENCES lfhe.event_versions(id),
  claim_id          uuid NOT NULL REFERENCES lfhe.claims(id),
  role              lfhe.event_claim_role NOT NULL,
  PRIMARY KEY (event_version_id, claim_id)
);
CREATE INDEX event_claims_claim_idx ON lfhe.event_claims (claim_id);

CREATE TABLE lfhe.event_state_history (
  seq            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id             uuid NOT NULL UNIQUE DEFAULT pg_catalog.gen_random_uuid(),
  event_id       uuid NOT NULL REFERENCES lfhe.events(id),
  old_state      lfhe.event_state,
  new_state      lfhe.event_state NOT NULL,
  actor_type     lfhe.actor_type NOT NULL,
  actor_user_id  uuid,
  action_id      uuid REFERENCES lfhe.event_actions(id),
  reason         text NOT NULL,
  created_at     timestamptz NOT NULL DEFAULT now(),
  CHECK ((actor_user_id IS NOT NULL) = (actor_type = 'HUMAN')),
  -- an AI/worker may only ever create the initial CANDIDATE state
  CHECK (actor_type = 'HUMAN' OR (old_state IS NULL AND new_state = 'CANDIDATE')),
  CHECK (old_state IS DISTINCT FROM new_state)
);
CREATE UNIQUE INDEX event_state_history_one_initial ON lfhe.event_state_history (event_id) WHERE old_state IS NULL;

CREATE TABLE lfhe.event_relationships (
  id                 uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  relationship_type  lfhe.event_relationship_type NOT NULL,
  from_event_id      uuid NOT NULL REFERENCES lfhe.events(id),
  to_event_id        uuid NOT NULL REFERENCES lfhe.events(id),
  from_version_id    uuid NOT NULL,
  from_version_hash  text NOT NULL,
  to_version_id      uuid NOT NULL,
  to_version_hash    text NOT NULL,
  action_id          uuid NOT NULL REFERENCES lfhe.event_actions(id),
  created_at         timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (from_version_id, from_version_hash) REFERENCES lfhe.event_versions (id, content_hash),
  FOREIGN KEY (to_version_id, to_version_hash) REFERENCES lfhe.event_versions (id, content_hash),
  CHECK (from_event_id <> to_event_id)
);
-- an event can be merged into / superseded by at most one successor
CREATE UNIQUE INDEX event_relationships_one_successor ON lfhe.event_relationships (from_event_id)
  WHERE relationship_type IN ('MERGED_INTO', 'SUPERSEDED_BY');

CREATE TABLE lfhe.event_claim_redistributions (
  action_id        uuid NOT NULL REFERENCES lfhe.event_actions(id),
  claim_id         uuid NOT NULL REFERENCES lfhe.claims(id),
  from_event_id    uuid NOT NULL REFERENCES lfhe.events(id),
  from_version_id  uuid NOT NULL REFERENCES lfhe.event_versions(id),
  to_event_id      uuid NOT NULL REFERENCES lfhe.events(id),
  to_version_id    uuid NOT NULL REFERENCES lfhe.event_versions(id),
  PRIMARY KEY (action_id, claim_id, from_event_id, to_event_id)
);

CREATE TABLE lfhe.event_ingestion_results (
  model_run_id           uuid PRIMARY KEY REFERENCES lfhe.model_runs(id),
  id                     uuid NOT NULL UNIQUE DEFAULT pg_catalog.gen_random_uuid(),
  model_run_status       lfhe.model_run_status NOT NULL,
  output_status          text,
  outcome                text NOT NULL CHECK (outcome IN ('PROPOSALS_RECORDED', 'NO_PROPOSALS',
                           'INSUFFICIENT_INFORMATION', 'HUMAN_REVIEW_REQUIRED', 'OUTPUT_REJECTED',
                           'SCHEMA_VALIDATION_FAILED', 'PROVIDER_ERROR')),
  report_mode            text,
  information_cutoff     timestamptz,
  proposals_recorded     integer NOT NULL DEFAULT 0,
  events_created         integer NOT NULL DEFAULT 0,
  versions_created       integer NOT NULL DEFAULT 0,
  rejection_reasons      text[] NOT NULL DEFAULT '{}',
  human_review_required  boolean NOT NULL,
  warnings               jsonb NOT NULL DEFAULT '[]'::jsonb,
  repair_of_model_run_id uuid REFERENCES lfhe.model_runs(id),
  created_at             timestamptz NOT NULL DEFAULT now(),
  CHECK ((outcome = 'OUTPUT_REJECTED') = (cardinality(rejection_reasons) > 0)),
  CHECK (outcome = 'PROPOSALS_RECORDED' OR (proposals_recorded = 0 AND events_created = 0 AND versions_created = 0))
);

CREATE TABLE lfhe.event_proposals (
  id                       uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  model_run_id             uuid NOT NULL REFERENCES lfhe.event_ingestion_results(model_run_id),
  proposal_index           integer NOT NULL,
  proposal_type            lfhe.event_proposal_type NOT NULL,
  target_event_id          uuid REFERENCES lfhe.events(id),
  target_event_version_id  uuid REFERENCES lfhe.event_versions(id),
  related_event_ids        uuid[] NOT NULL DEFAULT '{}',
  claim_ids                uuid[] NOT NULL DEFAULT '{}',
  event_candidate          jsonb,
  reason                   text NOT NULL,
  proposal_confidence      lfhe.assignment_confidence,
  materialised_event_id    uuid REFERENCES lfhe.events(id),
  materialised_version_id  uuid REFERENCES lfhe.event_versions(id),
  created_at               timestamptz NOT NULL DEFAULT now(),
  UNIQUE (model_run_id, proposal_index),
  CHECK ((proposal_type IN ('CREATE_NEW_EVENT', 'UPDATE_EXISTING_EVENT')) = (materialised_version_id IS NOT NULL))
);
ALTER TABLE lfhe.event_actions ADD CONSTRAINT event_actions_proposal_fk
  FOREIGN KEY (proposal_id) REFERENCES lfhe.event_proposals(id);

CREATE TABLE lfhe.event_version_reviews (
  seq               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id                uuid NOT NULL UNIQUE DEFAULT pg_catalog.gen_random_uuid(),
  event_version_id  uuid NOT NULL,
  content_hash      text NOT NULL,
  decision          lfhe.review_decision NOT NULL CHECK (decision <> 'MODIFY_AND_APPROVE'),
  actor_user_id     uuid NOT NULL,
  reason            text NOT NULL CHECK (length(btrim(reason)) >= 5),
  created_at        timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (event_version_id, content_hash) REFERENCES lfhe.event_versions (id, content_hash)
);

DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['events', 'event_actions', 'event_versions', 'event_claims', 'event_state_history',
    'event_relationships', 'event_claim_redistributions', 'event_ingestion_results', 'event_proposals',
    'event_version_reviews'] LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON lfhe.%I FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation()',
                   t || '_immutable', t);
  END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- Canonical version hash (from the stored rows; verified at commit)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.event_version_hash(p_event uuid, p_version_no integer, p_previous uuid, p_fields jsonb,
                                                   p_claims jsonb)
RETURNS text LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
  SELECT pg_catalog.encode(extensions.digest(pg_catalog.convert_to('lfhe-event-version/1' || E'\n' ||
    pg_catalog.jsonb_build_object(
      'event_id', p_event, 'version_no', p_version_no, 'previous_version_id', p_previous,
      'title', p_fields ->> 'title', 'description', p_fields ->> 'description',
      'event_type', p_fields ->> 'event_type', 'event_date_start', p_fields ->> 'event_date_start',
      'event_date_end', p_fields ->> 'event_date_end', 'event_date_confidence', p_fields ->> 'event_date_confidence',
      'locations', coalesce((SELECT pg_catalog.jsonb_agg(l ORDER BY l COLLATE "C")
                             FROM pg_catalog.jsonb_array_elements_text(coalesce(p_fields -> 'locations', '[]')) l), '[]'),
      'claims', coalesce((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(c ->> 'claim_id', c ->> 'role')
                                                      ORDER BY c ->> 'claim_id' COLLATE "C")
                          FROM pg_catalog.jsonb_array_elements(p_claims) c), '[]'))::text, 'UTF8'), 'sha256'), 'hex')
$$;
REVOKE ALL ON FUNCTION lfhe.event_version_hash(uuid, integer, uuid, jsonb, jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION lfhe.event_version_hash(uuid, integer, uuid, jsonb, jsonb) TO authenticated, lfhe_worker;

CREATE OR REPLACE FUNCTION lfhe.event_version_stored_hash(p_version uuid)
RETURNS text LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT lfhe.event_version_hash(v.event_id, v.version_no, v.previous_version_id,
    pg_catalog.jsonb_build_object('title', v.title, 'description', v.description, 'event_type', v.event_type,
      'event_date_start', v.event_date_start, 'event_date_end', v.event_date_end,
      'event_date_confidence', v.event_date_confidence, 'locations', pg_catalog.to_jsonb(v.locations)),
    coalesce((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('claim_id', ec.claim_id, 'role', ec.role))
              FROM lfhe.event_claims ec WHERE ec.event_version_id = v.id), '[]'))
  FROM lfhe.event_versions v WHERE v.id = p_version
$$;
REVOKE ALL ON FUNCTION lfhe.event_version_stored_hash(uuid) FROM PUBLIC, anon, service_role, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.event_version_stored_hash(uuid) TO authenticated, lfhe_worker;

CREATE OR REPLACE FUNCTION lfhe.event_version_verify()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_id uuid := (CASE TG_TABLE_NAME WHEN 'event_versions' THEN pg_catalog.to_jsonb(NEW) ->> 'id'
                 ELSE pg_catalog.to_jsonb(NEW) ->> 'event_version_id' END)::uuid;
  v_v  lfhe.event_versions%ROWTYPE;
BEGIN
  SELECT * INTO v_v FROM lfhe.event_versions WHERE id = v_id;
  IF NOT EXISTS (SELECT 1 FROM lfhe.event_claims WHERE event_version_id = v_id) THEN
    RAISE EXCEPTION 'EVENT_VERSION_WITHOUT_CLAIMS: version % has no claims', v_id USING ERRCODE = 'check_violation';
  END IF;
  IF v_v.content_hash IS DISTINCT FROM lfhe.event_version_stored_hash(v_id) THEN
    RAISE EXCEPTION 'EVENT_VERSION_HASH_MISMATCH: version %', v_id USING ERRCODE = 'check_violation';
  END IF;
  IF v_v.previous_version_id IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM lfhe.event_versions p WHERE p.id = v_v.previous_version_id
       AND p.event_id = v_v.event_id AND p.version_no = v_v.version_no - 1) THEN
    RAISE EXCEPTION 'EVENT_VERSION_CHAIN_INVALID: version %', v_id USING ERRCODE = 'check_violation';
  END IF;
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION lfhe.event_version_verify() FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
CREATE CONSTRAINT TRIGGER event_versions_verify AFTER INSERT ON lfhe.event_versions
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION lfhe.event_version_verify();
CREATE CONSTRAINT TRIGGER event_claims_verify AFTER INSERT ON lfhe.event_claims
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION lfhe.event_version_verify();

-- ---------------------------------------------------------------------------
-- Derived heads, state and resolution
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.event_head_version(p_event uuid)
RETURNS lfhe.event_versions LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT * FROM lfhe.event_versions WHERE event_id = p_event ORDER BY version_no DESC LIMIT 1
$$;
CREATE OR REPLACE FUNCTION lfhe.event_current_state(p_event uuid)
RETURNS lfhe.event_state LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT new_state FROM lfhe.event_state_history WHERE event_id = p_event ORDER BY seq DESC LIMIT 1
$$;
CREATE OR REPLACE FUNCTION lfhe.event_successor(p_event uuid)
RETURNS uuid LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT to_event_id FROM lfhe.event_relationships
  WHERE from_event_id = p_event AND relationship_type IN ('MERGED_INTO', 'SUPERSEDED_BY')
$$;
-- Historical reference → current event (follows MERGED_INTO / SUPERSEDED_BY).
CREATE OR REPLACE FUNCTION lfhe.resolve_event(p_event uuid)
RETURNS uuid LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_cur  uuid := p_event;
  v_next uuid;
  v_n    integer := 0;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM lfhe.events WHERE id = p_event) THEN
    RETURN NULL;
  END IF;
  LOOP
    v_next := lfhe.event_successor(v_cur);
    EXIT WHEN v_next IS NULL;
    v_cur := v_next;
    v_n := v_n + 1;
    IF v_n > 100 THEN
      RAISE EXCEPTION 'EVENT_RESOLUTION_CYCLE at %', p_event USING ERRCODE = 'data_exception';
    END IF;
  END LOOP;
  RETURN v_cur;
END $$;
REVOKE ALL ON FUNCTION lfhe.event_head_version(uuid), lfhe.event_current_state(uuid), lfhe.event_successor(uuid)
  FROM PUBLIC, anon, service_role, lfhe_evaluator, lfhe_registrar;
REVOKE ALL ON FUNCTION lfhe.resolve_event(uuid) FROM PUBLIC, anon, service_role, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.event_head_version(uuid), lfhe.event_current_state(uuid), lfhe.event_successor(uuid),
  lfhe.resolve_event(uuid) TO authenticated, lfhe_worker;

CREATE VIEW lfhe.event_heads WITH (security_invoker = true) AS
SELECT e.id AS event_id, e.origin, h.id AS head_version_id, h.version_no AS head_version_no,
       h.content_hash AS head_content_hash, h.title, h.event_type,
       (SELECT s.new_state FROM lfhe.event_state_history s WHERE s.event_id = e.id ORDER BY s.seq DESC LIMIT 1) AS state,
       (SELECT r.relationship_type FROM lfhe.event_relationships r WHERE r.from_event_id = e.id
          AND r.relationship_type IN ('MERGED_INTO', 'SUPERSEDED_BY')) AS structural_status,
       (SELECT r.to_event_id FROM lfhe.event_relationships r WHERE r.from_event_id = e.id
          AND r.relationship_type IN ('MERGED_INTO', 'SUPERSEDED_BY')) AS successor_event_id,
       (SELECT rv.decision FROM lfhe.event_version_reviews rv WHERE rv.event_version_id = h.id ORDER BY rv.seq DESC LIMIT 1)
         AS head_review_decision,
       (h.origin = 'AI' AND NOT EXISTS (SELECT 1 FROM lfhe.event_version_reviews rv WHERE rv.event_version_id = h.id))
         AS head_pending_review
FROM lfhe.events e
JOIN LATERAL (SELECT * FROM lfhe.event_versions v WHERE v.event_id = e.id ORDER BY v.version_no DESC LIMIT 1) h ON true;

-- An event can take new versions / structural actions only while it is not
-- rejected and not merged / superseded.
CREATE OR REPLACE FUNCTION lfhe.event_is_open(p_event uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT EXISTS (SELECT 1 FROM lfhe.events WHERE id = p_event)
     AND lfhe.event_current_state(p_event) IS DISTINCT FROM 'REJECTED'
     AND lfhe.event_successor(p_event) IS NULL
$$;
REVOKE ALL ON FUNCTION lfhe.event_is_open(uuid) FROM PUBLIC, anon, service_role, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.event_is_open(uuid) TO authenticated, lfhe_worker;

-- ---------------------------------------------------------------------------
-- Internal writers (not executable by any application role)
-- ---------------------------------------------------------------------------
-- p_fields: {title, description, event_type, event_date_start, event_date_end,
--            event_date_confidence, locations[]};  p_claims: [{claim_id, role}]
CREATE OR REPLACE FUNCTION lfhe.write_event_version(
  p_event uuid, p_fields jsonb, p_claims jsonb, p_origin text, p_run uuid, p_user uuid, p_action uuid)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_head lfhe.event_versions;
  v_no   integer;
  v_id   uuid;
  v_hash text;
BEGIN
  PERFORM 1 FROM lfhe.events WHERE id = p_event FOR UPDATE;
  v_head := lfhe.event_head_version(p_event);
  v_no := coalesce(v_head.version_no, 0) + 1;
  IF pg_catalog.jsonb_typeof(p_claims) <> 'array' OR pg_catalog.jsonb_array_length(p_claims) = 0 THEN
    RAISE EXCEPTION 'EVENT_VERSION_WITHOUT_CLAIMS' USING ERRCODE = 'check_violation';
  END IF;
  IF (SELECT count(*) FROM pg_catalog.jsonb_array_elements(p_claims)) <>
     (SELECT count(DISTINCT c ->> 'claim_id') FROM pg_catalog.jsonb_array_elements(p_claims) c) THEN
    RAISE EXCEPTION 'DUPLICATE_CLAIM_IN_EVENT_VERSION' USING ERRCODE = 'check_violation';
  END IF;
  -- normalise exactly as the stored row will read back (verified at commit)
  p_fields := pg_catalog.jsonb_build_object('title', p_fields ->> 'title', 'description', p_fields ->> 'description',
    'event_type', p_fields ->> 'event_type', 'event_date_start', p_fields ->> 'event_date_start',
    'event_date_end', p_fields ->> 'event_date_end',
    'event_date_confidence', coalesce(p_fields ->> 'event_date_confidence', 'UNKNOWN'),
    'locations', coalesce(p_fields -> 'locations', '[]'::jsonb));
  v_hash := lfhe.event_version_hash(p_event, v_no, v_head.id, p_fields, p_claims);
  INSERT INTO lfhe.event_versions (event_id, version_no, previous_version_id, title, description, event_type,
    event_date_start, event_date_end, event_date_confidence, locations, origin, created_by_model_run_id,
    created_by_user, action_id, content_hash)
  VALUES (p_event, v_no, v_head.id, p_fields ->> 'title', p_fields ->> 'description',
    (p_fields ->> 'event_type')::lfhe.claim_type, p_fields ->> 'event_date_start', p_fields ->> 'event_date_end',
    (p_fields ->> 'event_date_confidence')::lfhe.timestamp_confidence,
    ARRAY(SELECT pg_catalog.jsonb_array_elements_text(p_fields -> 'locations')),
    p_origin, p_run, p_user, p_action, v_hash)
  RETURNING id INTO v_id;
  INSERT INTO lfhe.event_claims (event_version_id, claim_id, role)
  SELECT v_id, (c ->> 'claim_id')::uuid, (c ->> 'role')::lfhe.event_claim_role FROM pg_catalog.jsonb_array_elements(p_claims) c;
  RETURN v_id;
END $$;

CREATE OR REPLACE FUNCTION lfhe.version_claims(p_version uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT coalesce(pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('claim_id', claim_id, 'role', role)
                                       ORDER BY claim_id), '[]')
  FROM lfhe.event_claims WHERE event_version_id = p_version
$$;

CREATE OR REPLACE FUNCTION lfhe.version_fields(p_version uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT pg_catalog.jsonb_build_object('title', title, 'description', description, 'event_type', event_type,
    'event_date_start', event_date_start, 'event_date_end', event_date_end,
    'event_date_confidence', event_date_confidence, 'locations', pg_catalog.to_jsonb(locations))
  FROM lfhe.event_versions WHERE id = p_version
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
    RAISE EXCEPTION 'EVENT_NOT_OPEN: event % is rejected, merged or superseded', p_event
      USING ERRCODE = 'object_not_in_prerequisite_state';
  END IF;
  RETURN v_head;
END $$;

REVOKE ALL ON FUNCTION lfhe.write_event_version(uuid, jsonb, jsonb, text, uuid, uuid, uuid),
  lfhe.version_claims(uuid), lfhe.version_fields(uuid), lfhe.require_event_head(uuid, uuid)
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;

-- ---------------------------------------------------------------------------
-- Audit
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.audit_event_objects()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_event text;
  v_obj   text;
  v_id    text;
BEGIN
  CASE TG_TABLE_NAME
    WHEN 'events' THEN v_event := 'EVENT_CREATED'; v_obj := 'event'; v_id := NEW.id::text;
    WHEN 'event_versions' THEN
      v_event := CASE WHEN NEW.version_no = 1 THEN 'EVENT_VERSION_CREATED' ELSE 'EVENT_UPDATED' END;
      v_obj := 'event'; v_id := NEW.event_id::text;
    WHEN 'event_state_history' THEN v_event := 'EVENT_STATE_CHANGED'; v_obj := 'event'; v_id := NEW.event_id::text;
    WHEN 'event_relationships' THEN v_event := 'EVENT_RELATIONSHIP_CREATED'; v_obj := 'event'; v_id := NEW.from_event_id::text;
    WHEN 'event_proposals' THEN v_event := 'EVENT_PROPOSAL_RECORDED'; v_obj := 'event_proposal'; v_id := NEW.id::text;
    WHEN 'event_ingestion_results' THEN v_event := 'EVENT_INGESTION_RECORDED'; v_obj := 'event_ingestion_result'; v_id := NEW.model_run_id::text;
    WHEN 'event_version_reviews' THEN v_event := 'EVENT_VERSION_REVIEWED'; v_obj := 'event_version'; v_id := NEW.event_version_id::text;
    WHEN 'event_actions' THEN
      v_event := CASE NEW.action WHEN 'MERGE' THEN 'EVENT_MERGED' WHEN 'SPLIT' THEN 'EVENT_SPLIT'
                   WHEN 'SUPERSEDE' THEN 'EVENT_SUPERSEDED' WHEN 'KEEP_SEPARATE' THEN 'EVENT_KEEP_SEPARATE_DECISION'
                   WHEN 'REJECT' THEN 'EVENT_REJECTED' ELSE 'EVENT_ACTION_RECORDED' END;
      v_obj := 'event_action'; v_id := NEW.id::text;
  END CASE;
  PERFORM lfhe.write_audit(v_event, v_obj, v_id, NULL, pg_catalog.to_jsonb(NEW), '{}'::jsonb);
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION lfhe.audit_event_objects() FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['events', 'event_versions', 'event_state_history', 'event_relationships',
    'event_proposals', 'event_ingestion_results', 'event_version_reviews', 'event_actions'] LOOP
    EXECUTE format('CREATE TRIGGER %I AFTER INSERT ON lfhe.%I FOR EACH ROW EXECUTE FUNCTION lfhe.audit_event_objects()',
                   t || '_audit', t);
  END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- Worker: M05 ingestion (fail closed: any invalid proposal rejects the output)
-- p: {model_run_id, output_status, human_review_required, warnings[], repair_of_model_run_id,
--     proposals:[{proposal, target_event_id, target_event_version_id, related_event_ids[],
--                 claim_ids[], event_candidate:{title, description, event_type, event_date_start,
--                 event_date_end, event_date_confidence, locations[], claims:[{claim_id, role}]},
--                 reason, confidence}]}
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
  v_uuid   constant text := '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$';
BEGIN
  IF v_type IS NULL OR v_type NOT IN ('CREATE_NEW_EVENT', 'UPDATE_EXISTING_EVENT', 'SUGGEST_MERGE', 'SUGGEST_SPLIT',
      'SUGGEST_SUPERSEDE', 'KEEP_SEPARATE', 'INSUFFICIENT_INFORMATION', 'HUMAN_REVIEW_REQUIRED') THEN
    RETURN ARRAY['PROPOSAL_TYPE_NOT_ALLOWED:' || left(coalesce(v_type, 'null'), 60)];
  END IF;
  -- every claim must be a run input and cutoff-eligible
  FOR v_c IN SELECT pg_catalog.jsonb_array_elements_text(coalesce(x -> 'claim_ids', '[]'))
             UNION SELECT c ->> 'claim_id' FROM pg_catalog.jsonb_array_elements(coalesce(v_cand -> 'claims', '[]')) c LOOP
    IF v_c IS NULL OR v_c !~ v_uuid OR NOT lfhe.run_has_object(p_run, 'input', 'claim', v_c) THEN
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
      -- an AI update may only ADD claims: every existing claim keeps its role
      IF EXISTS (SELECT 1 FROM lfhe.event_claims ec WHERE ec.event_version_id = v_head.id
                 AND NOT EXISTS (SELECT 1 FROM pg_catalog.jsonb_array_elements(v_cand -> 'claims') c
                                 WHERE c ->> 'claim_id' = ec.claim_id::text AND c ->> 'role' = ec.role::text)) THEN
        v_out := v_out || 'AI_UPDATE_MAY_NOT_REMOVE_OR_RECAST_CLAIMS'::text;
      END IF;
      v_all := v_all || ARRAY(SELECT claim_id FROM lfhe.event_claims WHERE event_version_id = v_head.id);
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
      v_version := lfhe.write_event_version(v_event, v_x -> 'event_candidate', v_x -> 'event_candidate' -> 'claims',
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

-- ---------------------------------------------------------------------------
-- HUMAN_ONLY event actions (permission EVENT_ACTION)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.new_event_action(
  p_action lfhe.event_action, p_actor uuid, p_reason text, p_proposal uuid, p_details jsonb)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_id uuid;
BEGIN
  IF p_reason IS NULL OR length(btrim(p_reason)) < 5 THEN
    RAISE EXCEPTION 'a reason is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  INSERT INTO lfhe.event_actions (action, actor_user_id, reason, proposal_id, details)
  VALUES (p_action, p_actor, p_reason, p_proposal, coalesce(p_details, '{}'::jsonb)) RETURNING id INTO v_id;
  RETURN v_id;
END $$;
REVOKE ALL ON FUNCTION lfhe.new_event_action(lfhe.event_action, uuid, text, uuid, jsonb)
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;

-- p: {title, description, event_type, event_date_*, locations[], claims:[{claim_id, role}], state?}
CREATE OR REPLACE FUNCTION lfhe.create_event(p jsonb, p_reason text, p_proposal uuid DEFAULT NULL)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor  uuid := lfhe.require_human_permission('EVENT_ACTION');
  v_action uuid;
  v_event  uuid;
  v_ver    uuid;
  v_state  lfhe.event_state := coalesce(p ->> 'state', 'ACTIVE')::lfhe.event_state;
BEGIN
  IF v_state = 'REJECTED' THEN
    RAISE EXCEPTION 'a new event cannot start REJECTED' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  v_action := lfhe.new_event_action('CREATE', v_actor, p_reason, p_proposal, '{}'::jsonb);
  INSERT INTO lfhe.events (origin, created_by_user) VALUES ('HUMAN', v_actor) RETURNING id INTO v_event;
  v_ver := lfhe.write_event_version(v_event, p, p -> 'claims', 'HUMAN', NULL, v_actor, v_action);
  INSERT INTO lfhe.event_state_history (event_id, old_state, new_state, actor_type, actor_user_id, action_id, reason)
  VALUES (v_event, NULL, v_state, 'HUMAN', v_actor, v_action, p_reason);
  RETURN v_event;
END $$;
COMMENT ON FUNCTION lfhe.create_event(jsonb, text, uuid) IS 'HUMAN_ONLY';

-- Human UPDATE: a new version of the current head (claims removed by a human are recorded).
CREATE OR REPLACE FUNCTION lfhe.update_event(p_event uuid, p_expected_head uuid, p jsonb, p_reason text,
                                             p_proposal uuid DEFAULT NULL)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor  uuid := lfhe.require_human_permission('EVENT_ACTION');
  v_head   lfhe.event_versions := lfhe.require_event_head(p_event, p_expected_head);
  v_action uuid;
BEGIN
  v_action := lfhe.new_event_action('UPDATE', v_actor, p_reason, p_proposal, pg_catalog.jsonb_build_object(
    'event_id', p_event, 'previous_version_id', v_head.id, 'previous_version_hash', v_head.content_hash,
    'removed_claim_ids', (SELECT coalesce(pg_catalog.jsonb_agg(ec.claim_id), '[]') FROM lfhe.event_claims ec
                          WHERE ec.event_version_id = v_head.id AND NOT EXISTS (
                            SELECT 1 FROM pg_catalog.jsonb_array_elements(p -> 'claims') c
                            WHERE c ->> 'claim_id' = ec.claim_id::text))));
  RETURN lfhe.write_event_version(p_event, p, p -> 'claims', 'HUMAN', NULL, v_actor, v_action);
END $$;
COMMENT ON FUNCTION lfhe.update_event(uuid, uuid, jsonb, text, uuid) IS 'HUMAN_ONLY';

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
  INSERT INTO lfhe.event_state_history (event_id, old_state, new_state, actor_type, actor_user_id, reason)
  VALUES (p_event, v_cur, p_new_state, 'HUMAN', v_actor, p_reason);
  IF v_cur = 'CANDIDATE' THEN
    PERFORM lfhe.write_audit('EVENT_MANUALLY_PROMOTED', 'event', p_event::text, NULL, NULL,
      pg_catalog.jsonb_build_object('from', v_cur, 'to', p_new_state));
  END IF;
END $$;
COMMENT ON FUNCTION lfhe.set_event_state(uuid, lfhe.event_state, lfhe.event_state, text) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.reject_event(p_event uuid, p_expected_state lfhe.event_state, p_reason text,
                                             p_proposal uuid DEFAULT NULL)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor  uuid := lfhe.require_human_permission('EVENT_ACTION');
  v_cur    lfhe.event_state;
  v_action uuid;
BEGIN
  PERFORM 1 FROM lfhe.events WHERE id = p_event FOR UPDATE;
  v_cur := lfhe.event_current_state(p_event);
  IF v_cur IS DISTINCT FROM p_expected_state THEN
    RAISE EXCEPTION 'EVENT_STATE_STALE: state is %, not %', v_cur, p_expected_state USING ERRCODE = 'serialization_failure';
  END IF;
  v_action := lfhe.new_event_action('REJECT', v_actor, p_reason, p_proposal, pg_catalog.jsonb_build_object(
    'event_id', p_event, 'head_version_id', (lfhe.event_head_version(p_event)).id,
    'head_version_hash', (lfhe.event_head_version(p_event)).content_hash));
  INSERT INTO lfhe.event_state_history (event_id, old_state, new_state, actor_type, actor_user_id, action_id, reason)
  VALUES (p_event, v_cur, 'REJECTED', 'HUMAN', v_actor, v_action, p_reason);
  RETURN v_action;
END $$;
COMMENT ON FUNCTION lfhe.reject_event(uuid, lfhe.event_state, text, uuid) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.review_event_version(p_version uuid, p_content_hash text,
                                                     p_decision lfhe.review_decision, p_reason text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('EVENT_ACTION');
  v_id    uuid;
BEGIN
  IF p_decision = 'MODIFY_AND_APPROVE' THEN
    RAISE EXCEPTION 'modify by creating a new version (lfhe.update_event)' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  INSERT INTO lfhe.event_version_reviews (event_version_id, content_hash, decision, actor_user_id, reason)
  VALUES (p_version, p_content_hash, p_decision, v_actor, p_reason) RETURNING id INTO v_id;
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.review_event_version(uuid, text, lfhe.review_decision, text) IS 'HUMAN_ONLY';

-- MERGE: sources' current heads are merged into the target as a new target version
-- (claim union; a CONTRADICTS role is never weakened); sources stay with all versions.
-- p_expected_heads: {"<event_id>": "<head version id>", ...} for target and every source
CREATE OR REPLACE FUNCTION lfhe.merge_events(p_target uuid, p_sources uuid[], p_expected_heads jsonb, p_reason text,
                                             p_proposal uuid DEFAULT NULL)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor   uuid := lfhe.require_human_permission('EVENT_ACTION');
  v_target  lfhe.event_versions;
  v_src     uuid;
  v_shead   lfhe.event_versions;
  v_heads   lfhe.event_versions[] := '{}';
  v_claims  jsonb;
  v_action  uuid;
  v_new     uuid;
  v_newhash text;
BEGIN
  IF p_sources IS NULL OR cardinality(p_sources) = 0 OR p_target = ANY (p_sources)
     OR cardinality(p_sources) <> (SELECT count(DISTINCT s) FROM pg_catalog.unnest(p_sources) s) THEN
    RAISE EXCEPTION 'merge needs distinct source events different from the target' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  v_target := lfhe.require_event_head(p_target, (p_expected_heads ->> p_target::text)::uuid);
  FOREACH v_src IN ARRAY p_sources LOOP
    v_shead := lfhe.require_event_head(v_src, (p_expected_heads ->> v_src::text)::uuid);
    v_heads := v_heads || v_shead;
  END LOOP;
  -- claim union with role priority CONTRADICTS > UPDATES > SUPPORTS > CONTEXTUALISES
  SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('claim_id', claim_id, 'role', role) ORDER BY claim_id)
  INTO v_claims FROM (
    SELECT DISTINCT ON (ec.claim_id) ec.claim_id, ec.role FROM lfhe.event_claims ec
    WHERE ec.event_version_id = v_target.id OR ec.event_version_id = ANY (ARRAY(SELECT (h).id FROM pg_catalog.unnest(v_heads) h))
    ORDER BY ec.claim_id, CASE ec.role WHEN 'CONTRADICTS' THEN 0 WHEN 'UPDATES' THEN 1 WHEN 'SUPPORTS' THEN 2 ELSE 3 END) u;
  v_action := lfhe.new_event_action('MERGE', v_actor, p_reason, p_proposal, pg_catalog.jsonb_build_object(
    'target_event_id', p_target, 'target_previous_version_id', v_target.id,
    'target_previous_version_hash', v_target.content_hash,
    'sources', (SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('event_id', (h).event_id,
                  'version_id', (h).id, 'version_hash', (h).content_hash)) FROM pg_catalog.unnest(v_heads) h)));
  v_new := lfhe.write_event_version(p_target, lfhe.version_fields(v_target.id), v_claims, 'HUMAN', NULL, v_actor, v_action);
  SELECT content_hash INTO v_newhash FROM lfhe.event_versions WHERE id = v_new;
  FOREACH v_shead IN ARRAY v_heads LOOP
    INSERT INTO lfhe.event_relationships (relationship_type, from_event_id, to_event_id, from_version_id,
      from_version_hash, to_version_id, to_version_hash, action_id)
    VALUES ('MERGED_INTO', v_shead.event_id, p_target, v_shead.id, v_shead.content_hash, v_new, v_newhash, v_action);
    INSERT INTO lfhe.event_claim_redistributions (action_id, claim_id, from_event_id, from_version_id, to_event_id, to_version_id)
    SELECT v_action, ec.claim_id, v_shead.event_id, v_shead.id, p_target, v_new
    FROM lfhe.event_claims ec WHERE ec.event_version_id = v_shead.id;
  END LOOP;
  RETURN v_new;
END $$;
COMMENT ON FUNCTION lfhe.merge_events(uuid, uuid[], jsonb, text, uuid) IS 'HUMAN_ONLY';

-- SPLIT: p = {children:[{title, description, event_type, ..., claims:[{claim_id, role}]}],
--             retained: {fields..., claims:[...]} | null}
-- Every claim of the parent head must go to at least one child or be retained;
-- no claim outside the parent head may appear.
CREATE OR REPLACE FUNCTION lfhe.split_event(p_parent uuid, p_expected_head uuid, p jsonb, p_reason text,
                                            p_proposal uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor    uuid := lfhe.require_human_permission('EVENT_ACTION');
  v_head     lfhe.event_versions := lfhe.require_event_head(p_parent, p_expected_head);
  v_action   uuid;
  v_child    jsonb;
  v_event    uuid;
  v_ver      uuid;
  v_hash     text;
  v_retained uuid;
  v_out      jsonb := '[]'::jsonb;
  v_state    lfhe.event_state := lfhe.event_current_state(p_parent);
BEGIN
  IF pg_catalog.jsonb_array_length(coalesce(p -> 'children', '[]')) = 0 THEN
    RAISE EXCEPTION 'a split needs at least one child' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  IF EXISTS (SELECT 1 FROM lfhe.event_claims ec WHERE ec.event_version_id = v_head.id AND NOT EXISTS (
               SELECT 1 FROM pg_catalog.jsonb_array_elements(p -> 'children') ch,
                             pg_catalog.jsonb_array_elements(ch -> 'claims') c
               WHERE c ->> 'claim_id' = ec.claim_id::text
               UNION ALL
               SELECT 1 FROM pg_catalog.jsonb_array_elements(coalesce(p -> 'retained' -> 'claims', '[]')) c
               WHERE c ->> 'claim_id' = ec.claim_id::text)) THEN
    RAISE EXCEPTION 'SPLIT_WOULD_DROP_CLAIMS: every claim of the parent must go to a child or be retained'
      USING ERRCODE = 'check_violation';
  END IF;
  IF EXISTS (SELECT 1 FROM (SELECT c ->> 'claim_id' AS cid FROM pg_catalog.jsonb_array_elements(p -> 'children') ch,
                                   pg_catalog.jsonb_array_elements(ch -> 'claims') c
                            UNION ALL SELECT c ->> 'claim_id' FROM pg_catalog.jsonb_array_elements(coalesce(p -> 'retained' -> 'claims', '[]')) c) x
             WHERE NOT EXISTS (SELECT 1 FROM lfhe.event_claims ec WHERE ec.event_version_id = v_head.id
                               AND ec.claim_id::text = x.cid)) THEN
    RAISE EXCEPTION 'SPLIT_INTRODUCES_FOREIGN_CLAIMS: a split may only redistribute the parent''s claims'
      USING ERRCODE = 'check_violation';
  END IF;
  v_action := lfhe.new_event_action('SPLIT', v_actor, p_reason, p_proposal, pg_catalog.jsonb_build_object(
    'parent_event_id', p_parent, 'parent_version_id', v_head.id, 'parent_version_hash', v_head.content_hash));
  IF p ? 'retained' AND pg_catalog.jsonb_typeof(p -> 'retained') = 'object' THEN
    v_retained := lfhe.write_event_version(p_parent, p -> 'retained', p -> 'retained' -> 'claims', 'HUMAN', NULL, v_actor, v_action);
    INSERT INTO lfhe.event_claim_redistributions (action_id, claim_id, from_event_id, from_version_id, to_event_id, to_version_id)
    SELECT v_action, (c ->> 'claim_id')::uuid, p_parent, v_head.id, p_parent, v_retained
    FROM pg_catalog.jsonb_array_elements(p -> 'retained' -> 'claims') c;
  END IF;
  FOR v_child IN SELECT * FROM pg_catalog.jsonb_array_elements(p -> 'children') LOOP
    INSERT INTO lfhe.events (origin, created_by_user) VALUES ('HUMAN', v_actor) RETURNING id INTO v_event;
    v_ver := lfhe.write_event_version(v_event, v_child, v_child -> 'claims', 'HUMAN', NULL, v_actor, v_action);
    INSERT INTO lfhe.event_state_history (event_id, old_state, new_state, actor_type, actor_user_id, action_id, reason)
    VALUES (v_event, NULL, CASE WHEN v_state = 'CANDIDATE' THEN 'CANDIDATE' ELSE 'ACTIVE' END::lfhe.event_state,
            'HUMAN', v_actor, v_action, p_reason);
    SELECT content_hash INTO v_hash FROM lfhe.event_versions WHERE id = v_ver;
    INSERT INTO lfhe.event_relationships (relationship_type, from_event_id, to_event_id, from_version_id,
      from_version_hash, to_version_id, to_version_hash, action_id)
    VALUES ('SPLIT_INTO', p_parent, v_event, v_head.id, v_head.content_hash, v_ver, v_hash, v_action);
    INSERT INTO lfhe.event_claim_redistributions (action_id, claim_id, from_event_id, from_version_id, to_event_id, to_version_id)
    SELECT v_action, (c ->> 'claim_id')::uuid, p_parent, v_head.id, v_event, v_ver
    FROM pg_catalog.jsonb_array_elements(v_child -> 'claims') c;
    v_out := v_out || pg_catalog.jsonb_build_object('event_id', v_event, 'version_id', v_ver);
  END LOOP;
  RETURN pg_catalog.jsonb_build_object('action_id', v_action, 'children', v_out, 'retained_version_id', v_retained);
END $$;
COMMENT ON FUNCTION lfhe.split_event(uuid, uuid, jsonb, text, uuid) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.supersede_event(p_old uuid, p_replacement uuid, p_expected_heads jsonb, p_reason text,
                                                p_proposal uuid DEFAULT NULL)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor  uuid := lfhe.require_human_permission('EVENT_ACTION');
  v_old    lfhe.event_versions;
  v_new    lfhe.event_versions;
  v_action uuid;
BEGIN
  IF p_old = p_replacement THEN
    RAISE EXCEPTION 'an event cannot supersede itself' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  v_old := lfhe.require_event_head(p_old, (p_expected_heads ->> p_old::text)::uuid);
  v_new := lfhe.require_event_head(p_replacement, (p_expected_heads ->> p_replacement::text)::uuid);
  v_action := lfhe.new_event_action('SUPERSEDE', v_actor, p_reason, p_proposal, pg_catalog.jsonb_build_object(
    'old_event_id', p_old, 'old_version_id', v_old.id, 'old_version_hash', v_old.content_hash,
    'replacement_event_id', p_replacement, 'replacement_version_id', v_new.id,
    'replacement_version_hash', v_new.content_hash));
  INSERT INTO lfhe.event_relationships (relationship_type, from_event_id, to_event_id, from_version_id,
    from_version_hash, to_version_id, to_version_hash, action_id)
  VALUES ('SUPERSEDED_BY', p_old, p_replacement, v_old.id, v_old.content_hash, v_new.id, v_new.content_hash, v_action);
  RETURN v_action;
END $$;
COMMENT ON FUNCTION lfhe.supersede_event(uuid, uuid, jsonb, text, uuid) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.keep_events_separate(p_events uuid[], p_reason text, p_proposal uuid DEFAULT NULL)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('EVENT_ACTION');
BEGIN
  IF p_events IS NULL OR cardinality(p_events) < 2
     OR (SELECT count(*) FROM lfhe.events WHERE id = ANY (p_events)) <> cardinality(p_events) THEN
    RAISE EXCEPTION 'KEEP_SEPARATE needs at least two existing events' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  RETURN lfhe.new_event_action('KEEP_SEPARATE', v_actor, p_reason, p_proposal, pg_catalog.jsonb_build_object(
    'events', (SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('event_id', e,
                 'version_id', (lfhe.event_head_version(e)).id, 'version_hash', (lfhe.event_head_version(e)).content_hash))
               FROM pg_catalog.unnest(p_events) e)));
END $$;
COMMENT ON FUNCTION lfhe.keep_events_separate(uuid[], text, uuid) IS 'HUMAN_ONLY';

REVOKE ALL ON FUNCTION
  lfhe.create_event(jsonb, text, uuid), lfhe.update_event(uuid, uuid, jsonb, text, uuid),
  lfhe.set_event_state(uuid, lfhe.event_state, lfhe.event_state, text),
  lfhe.reject_event(uuid, lfhe.event_state, text, uuid),
  lfhe.review_event_version(uuid, text, lfhe.review_decision, text),
  lfhe.merge_events(uuid, uuid[], jsonb, text, uuid), lfhe.split_event(uuid, uuid, jsonb, text, uuid),
  lfhe.supersede_event(uuid, uuid, jsonb, text, uuid), lfhe.keep_events_separate(uuid[], text, uuid)
  FROM PUBLIC, anon, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION
  lfhe.create_event(jsonb, text, uuid), lfhe.update_event(uuid, uuid, jsonb, text, uuid),
  lfhe.set_event_state(uuid, lfhe.event_state, lfhe.event_state, text),
  lfhe.reject_event(uuid, lfhe.event_state, text, uuid),
  lfhe.review_event_version(uuid, text, lfhe.review_decision, text),
  lfhe.merge_events(uuid, uuid[], jsonb, text, uuid), lfhe.split_event(uuid, uuid, jsonb, text, uuid),
  lfhe.supersede_event(uuid, uuid, jsonb, text, uuid), lfhe.keep_events_separate(uuid[], text, uuid)
  TO authenticated;

-- ---------------------------------------------------------------------------
-- Read access (CLAIM_READ, as for the claims the events are built from)
-- ---------------------------------------------------------------------------
REVOKE ALL ON lfhe.events, lfhe.event_actions, lfhe.event_versions, lfhe.event_claims, lfhe.event_state_history,
  lfhe.event_relationships, lfhe.event_claim_redistributions, lfhe.event_ingestion_results, lfhe.event_proposals,
  lfhe.event_version_reviews, lfhe.event_heads
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT SELECT ON lfhe.events, lfhe.event_actions, lfhe.event_versions, lfhe.event_claims, lfhe.event_state_history,
  lfhe.event_relationships, lfhe.event_claim_redistributions, lfhe.event_ingestion_results, lfhe.event_proposals,
  lfhe.event_version_reviews, lfhe.event_heads
  TO authenticated, lfhe_worker;
DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['events', 'event_actions', 'event_versions', 'event_claims', 'event_state_history',
    'event_relationships', 'event_claim_redistributions', 'event_ingestion_results', 'event_proposals',
    'event_version_reviews'] LOOP
    EXECUTE format('ALTER TABLE lfhe.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY %I ON lfhe.%I FOR SELECT TO authenticated USING (lfhe.has_permission(''CLAIM_READ''))',
                   t || '_read_human', t);
    EXECUTE format('CREATE POLICY %I ON lfhe.%I FOR SELECT TO lfhe_worker USING (true)', t || '_read_worker', t);
  END LOOP;
END $$;
