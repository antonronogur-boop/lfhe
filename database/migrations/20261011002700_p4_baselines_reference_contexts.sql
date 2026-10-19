-- LFHÉ Phase 4 (P4-01) — versioned baselines, curated reference contexts, as-of
-- claim status. Baseline: docs/specs/LFHE_Phase4_Authoritative_Baseline_Addendum_v1.0.md
-- §5 (baseline), §6 (reference context), §19 (cutoff discipline); Prompt Pack v1.2 §2
-- (REFERENCE_CONTEXT boundary, PG-17), PG-07 (baseline versions).
--
-- Pattern for every Phase 4 versioned object: the version row stores its canonical
-- content (jsonb) and content_hash = SHA-256('<tag>\n' || content::text), enforced by
-- CHECK; derived child rows (evidence references) give referential integrity and are
-- written only by the HUMAN_ONLY / worker functions in the same transaction. Versions
-- are immutable (block_mutation); a change is a new version.
--
-- Usability for (report_mode, information_cutoff) is knowledge-bound (Phase 3 rule):
--   approved AND knowledge_as_of <= cutoff AND every factual evidence object is itself
--   eligible for (mode, cutoff). Approval may be recorded after the cutoff; only the
--   evidence decides. created_at is never the historical criterion.

INSERT INTO lfhe.audit_event_types (code, spec_source) VALUES
  ('BASELINE_CREATED', 'Phase 4 impl.'),
  ('BASELINE_VERSION_CREATED', 'Phase 4 impl.'),
  ('BASELINE_VERSION_APPROVED', 'Phase 4 impl.'),
  ('BASELINE_VERSION_REJECTED', 'Phase 4 impl.')
ON CONFLICT (code) DO NOTHING;

CREATE OR REPLACE FUNCTION lfhe.p4_hash(p_tag text, p_content jsonb)
RETURNS text LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
  SELECT pg_catalog.encode(extensions.digest(pg_catalog.convert_to(p_tag || E'\n' || p_content::text, 'UTF8'), 'sha256'), 'hex')
$$;
REVOKE ALL ON FUNCTION lfhe.p4_hash(text, jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION lfhe.p4_hash(text, jsonb) TO authenticated, lfhe_worker;

-- Generic object eligibility used by Phase 4 evidence references
CREATE OR REPLACE FUNCTION lfhe.p4_object_eligible(p_type text, p_id uuid, p_mode text, p_cutoff timestamptz,
                                                   p_depth integer DEFAULT 0)
RETURNS boolean LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  IF p_depth > 20 OR p_mode NOT IN ('LIVE', 'REPLAY') OR p_cutoff IS NULL THEN
    RETURN false;
  END IF;
  RETURN CASE p_type
    WHEN 'claim' THEN lfhe.claim_cutoff_eligible(p_id, p_mode, p_cutoff)
    WHEN 'article' THEN lfhe.article_cutoff_eligible(p_id, p_mode, p_cutoff)
    WHEN 'event_version' THEN lfhe.event_version_eligible(p_id, p_mode, p_cutoff, p_depth + 1)
    WHEN 'reference_context_version' THEN lfhe.reference_context_version_usable(p_id, p_mode, p_cutoff, p_depth + 1)
    ELSE false END;
END $$;

-- ---------------------------------------------------------------------------
-- As-of claim status (§3, §10, §19): a status row counts for (mode, cutoff) only if
-- its knowledge bound is eligible. INITIAL_EXTRACTION: the claim itself; a row tied
-- to a recommending model run: that run's full evidence; any other row has no
-- reproducible bound: LIVE only if recorded <= cutoff, never in REPLAY.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.claim_status_row_usable(p_row lfhe.claim_status_history, p_mode text, p_cutoff timestamptz)
RETURNS boolean LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  IF NOT lfhe.claim_cutoff_eligible(p_row.claim_id, p_mode, p_cutoff) THEN
    RETURN false;
  END IF;
  IF p_row.basis = 'INITIAL_EXTRACTION' THEN
    RETURN true;
  END IF;
  IF p_row.recommending_model_run_id IS NOT NULL THEN
    RETURN lfhe.run_evidence_eligible(p_row.recommending_model_run_id, p_mode, p_cutoff);
  END IF;
  RETURN p_mode = 'LIVE' AND p_row.created_at <= p_cutoff;
END $$;

CREATE OR REPLACE FUNCTION lfhe.claim_status_asof(p_claim uuid, p_mode text, p_cutoff timestamptz)
RETURNS TABLE (claim_id uuid, claim_status lfhe.claim_status, basis text, actor_type lfhe.actor_type,
               high_impact_at_change boolean, status_history_id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT h.claim_id, h.new_status, h.basis, h.actor_type, h.high_impact_at_change, h.id
  FROM lfhe.claim_status_history h
  WHERE h.claim_id = p_claim AND lfhe.claim_status_row_usable(h, p_mode, p_cutoff)
  ORDER BY h.seq DESC LIMIT 1
$$;

-- ---------------------------------------------------------------------------
-- Reference contexts (curated, versioned background — not model memory)
-- ---------------------------------------------------------------------------
CREATE TABLE lfhe.reference_contexts (
  id            uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  code          text NOT NULL UNIQUE CHECK (code ~ '^RC-[A-Z0-9][A-Z0-9_-]{1,60}$'),
  context_type  text NOT NULL CHECK (context_type ~ '^[A-Z][A-Z0-9_]{2,60}$'),
  title         text NOT NULL CHECK (length(btrim(title)) BETWEEN 3 AND 300),
  created_by    uuid NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now()
);

-- content: {title, text, valid_from, valid_to, provenance_refs: [[type, id] sorted]}
CREATE TABLE lfhe.reference_context_versions (
  id                    uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  reference_context_id  uuid NOT NULL REFERENCES lfhe.reference_contexts(id),
  version_no            integer NOT NULL CHECK (version_no >= 1),
  previous_version_id   uuid REFERENCES lfhe.reference_context_versions(id),
  knowledge_as_of       timestamptz NOT NULL,
  content               jsonb NOT NULL,
  content_hash          text NOT NULL,
  created_by            uuid NOT NULL,
  reason                text NOT NULL CHECK (length(btrim(reason)) >= 5),
  created_at            timestamptz NOT NULL DEFAULT now(),
  UNIQUE (reference_context_id, version_no),
  UNIQUE (id, content_hash),
  CHECK ((version_no = 1) = (previous_version_id IS NULL)),
  CHECK (content_hash = lfhe.p4_hash('lfhe-reference-context-version/1',
           content || pg_catalog.jsonb_build_object('reference_context_id', reference_context_id,
                                                    'version_no', version_no, 'previous_version_id', previous_version_id,
                                                    'knowledge_as_of_epoch', extract(epoch FROM knowledge_as_of)))),
  CHECK (pg_catalog.jsonb_array_length(content -> 'provenance_refs') >= 1)
);

CREATE TABLE lfhe.reference_context_provenance (
  reference_context_version_id  uuid NOT NULL REFERENCES lfhe.reference_context_versions(id),
  object_type                   text NOT NULL CHECK (object_type IN ('claim', 'article', 'event_version')),
  object_id                     uuid NOT NULL,
  PRIMARY KEY (reference_context_version_id, object_type, object_id)
);

CREATE TABLE lfhe.reference_context_decisions (
  seq                           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id                            uuid NOT NULL UNIQUE DEFAULT pg_catalog.gen_random_uuid(),
  reference_context_version_id  uuid NOT NULL,
  content_hash                  text NOT NULL,
  decision                      text NOT NULL CHECK (decision IN ('APPROVE', 'REJECT')),
  actor_user_id                 uuid NOT NULL,
  reason                        text NOT NULL CHECK (length(btrim(reason)) >= 5),
  created_at                    timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (reference_context_version_id, content_hash) REFERENCES lfhe.reference_context_versions (id, content_hash),
  UNIQUE (reference_context_version_id)              -- one decision per version (immutable)
);

-- ---------------------------------------------------------------------------
-- Baselines (prior known state against which change is evaluated)
-- ---------------------------------------------------------------------------
CREATE TABLE lfhe.baselines (
  id          uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  code        text NOT NULL UNIQUE CHECK (code ~ '^BL-[A-Z0-9][A-Z0-9_-]{1,60}$'),
  title       text NOT NULL CHECK (length(btrim(title)) BETWEEN 3 AND 300),
  scope       text NOT NULL CHECK (length(btrim(scope)) BETWEEN 3 AND 2000),
  created_by  uuid NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- content: {title, components: [{component_no, text, evidence: [[type, id] sorted]}]}
CREATE TABLE lfhe.baseline_versions (
  id                   uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  baseline_id          uuid NOT NULL REFERENCES lfhe.baselines(id),
  version_no           integer NOT NULL CHECK (version_no >= 1),
  previous_version_id  uuid REFERENCES lfhe.baseline_versions(id),
  knowledge_as_of      timestamptz NOT NULL,
  content              jsonb NOT NULL,
  content_hash         text NOT NULL,
  created_by           uuid NOT NULL,
  reason               text NOT NULL CHECK (length(btrim(reason)) >= 5),
  created_at           timestamptz NOT NULL DEFAULT now(),
  UNIQUE (baseline_id, version_no),
  UNIQUE (id, content_hash),
  CHECK ((version_no = 1) = (previous_version_id IS NULL)),
  CHECK (content_hash = lfhe.p4_hash('lfhe-baseline-version/1',
           content || pg_catalog.jsonb_build_object('baseline_id', baseline_id, 'version_no', version_no,
                                                    'previous_version_id', previous_version_id,
                                                    'knowledge_as_of_epoch', extract(epoch FROM knowledge_as_of)))),
  CHECK (pg_catalog.jsonb_array_length(content -> 'components') >= 1)
);

CREATE TABLE lfhe.baseline_component_evidence (
  baseline_version_id  uuid NOT NULL REFERENCES lfhe.baseline_versions(id),
  component_no         integer NOT NULL,
  object_type          text NOT NULL CHECK (object_type IN ('claim', 'event_version', 'reference_context_version')),
  object_id            uuid NOT NULL,
  PRIMARY KEY (baseline_version_id, component_no, object_type, object_id)
);

CREATE TABLE lfhe.baseline_version_decisions (
  seq                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id                   uuid NOT NULL UNIQUE DEFAULT pg_catalog.gen_random_uuid(),
  baseline_version_id  uuid NOT NULL,
  content_hash         text NOT NULL,
  decision             text NOT NULL CHECK (decision IN ('APPROVE', 'REJECT')),
  actor_user_id        uuid NOT NULL,
  reason               text NOT NULL CHECK (length(btrim(reason)) >= 5),
  created_at           timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (baseline_version_id, content_hash) REFERENCES lfhe.baseline_versions (id, content_hash),
  UNIQUE (baseline_version_id)
);

DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['reference_contexts', 'reference_context_versions', 'reference_context_provenance',
    'reference_context_decisions', 'baselines', 'baseline_versions', 'baseline_component_evidence',
    'baseline_version_decisions'] LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON lfhe.%I FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation()',
                   t || '_immutable', t);
  END LOOP;
END $$;

-- Usability ------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.reference_context_version_usable(p_version uuid, p_mode text, p_cutoff timestamptz,
                                                                 p_depth integer DEFAULT 0)
RETURNS boolean LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v lfhe.reference_context_versions%ROWTYPE;
BEGIN
  IF p_depth > 20 THEN
    RETURN false;
  END IF;
  SELECT * INTO v FROM lfhe.reference_context_versions WHERE id = p_version;
  IF NOT FOUND OR v.knowledge_as_of > p_cutoff THEN
    RETURN false;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM lfhe.reference_context_decisions d WHERE d.reference_context_version_id = v.id
                 AND d.decision = 'APPROVE') THEN
    RETURN false;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM lfhe.reference_context_provenance p WHERE p.reference_context_version_id = v.id) THEN
    RETURN false;                                  -- no provenance = unusable (§6)
  END IF;
  RETURN NOT EXISTS (SELECT 1 FROM lfhe.reference_context_provenance p WHERE p.reference_context_version_id = v.id
                     AND NOT lfhe.p4_object_eligible(p.object_type, p.object_id, p_mode, p_cutoff, p_depth + 1));
END $$;

CREATE OR REPLACE FUNCTION lfhe.baseline_version_usable(p_version uuid, p_mode text, p_cutoff timestamptz)
RETURNS boolean LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v lfhe.baseline_versions%ROWTYPE;
BEGIN
  SELECT * INTO v FROM lfhe.baseline_versions WHERE id = p_version;
  IF NOT FOUND OR p_mode NOT IN ('LIVE', 'REPLAY') OR p_cutoff IS NULL OR v.knowledge_as_of > p_cutoff THEN
    RETURN false;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM lfhe.baseline_version_decisions d WHERE d.baseline_version_id = v.id
                 AND d.decision = 'APPROVE') THEN
    RETURN false;
  END IF;
  RETURN NOT EXISTS (SELECT 1 FROM lfhe.baseline_component_evidence e WHERE e.baseline_version_id = v.id
                     AND NOT lfhe.p4_object_eligible(e.object_type, e.object_id, p_mode, p_cutoff));
END $$;

-- latest usable version (a later version never leaks backwards)
CREATE OR REPLACE FUNCTION lfhe.baseline_asof(p_baseline uuid, p_mode text, p_cutoff timestamptz)
RETURNS uuid LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT v.id FROM lfhe.baseline_versions v
  WHERE v.baseline_id = p_baseline AND lfhe.baseline_version_usable(v.id, p_mode, p_cutoff)
  ORDER BY v.version_no DESC LIMIT 1
$$;

CREATE OR REPLACE FUNCTION lfhe.reference_context_asof(p_context uuid, p_mode text, p_cutoff timestamptz)
RETURNS uuid LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT v.id FROM lfhe.reference_context_versions v
  WHERE v.reference_context_id = p_context AND lfhe.reference_context_version_usable(v.id, p_mode, p_cutoff)
  ORDER BY v.version_no DESC LIMIT 1
$$;

-- ---------------------------------------------------------------------------
-- Normalisation of evidence references: [{object_type, object_id}] → sorted [[t, id]]
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.p4_refs(p jsonb, p_allowed text[])
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  e jsonb;
  v_out jsonb := '[]';
BEGIN
  FOR e IN SELECT * FROM pg_catalog.jsonb_array_elements(coalesce(p, '[]')) LOOP
    IF NOT (e ->> 'object_type' = ANY (p_allowed))
       OR (e ->> 'object_id') !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
       OR NOT (CASE e ->> 'object_type'
         WHEN 'claim' THEN EXISTS (SELECT 1 FROM lfhe.claims WHERE id = (e ->> 'object_id')::uuid)
         WHEN 'article' THEN EXISTS (SELECT 1 FROM lfhe.articles WHERE id = (e ->> 'object_id')::uuid)
         WHEN 'event_version' THEN EXISTS (SELECT 1 FROM lfhe.event_versions WHERE id = (e ->> 'object_id')::uuid)
         WHEN 'reference_context_version' THEN EXISTS (SELECT 1 FROM lfhe.reference_context_versions WHERE id = (e ->> 'object_id')::uuid)
         ELSE false END) THEN
      RAISE EXCEPTION 'EVIDENCE_REFERENCE_INVALID: %', left(e::text, 200) USING ERRCODE = 'check_violation';
    END IF;
  END LOOP;
  SELECT coalesce(pg_catalog.jsonb_agg(DISTINCT pg_catalog.jsonb_build_array(x ->> 'object_type', x ->> 'object_id')), '[]')
  INTO v_out FROM pg_catalog.jsonb_array_elements(coalesce(p, '[]')) x;
  SELECT coalesce(pg_catalog.jsonb_agg(r ORDER BY (r ->> 0) COLLATE "C", (r ->> 1) COLLATE "C"), '[]') INTO v_out
  FROM pg_catalog.jsonb_array_elements(v_out) r;
  RETURN v_out;
END $$;

-- evidence may not post-date the knowledge it is claimed to represent
CREATE OR REPLACE FUNCTION lfhe.p4_refs_known_at(p_refs jsonb, p_as_of timestamptz)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  -- a referenced reference context counts by its own knowledge_as_of (its approval is checked at use)
  SELECT NOT EXISTS (SELECT 1 FROM pg_catalog.jsonb_array_elements(p_refs) r
                     WHERE CASE WHEN r ->> 0 = 'reference_context_version'
                       THEN NOT coalesce((SELECT v.knowledge_as_of <= p_as_of FROM lfhe.reference_context_versions v
                                          WHERE v.id = (r ->> 1)::uuid), false)
                       ELSE NOT (lfhe.p4_object_eligible(r ->> 0, (r ->> 1)::uuid, 'LIVE', p_as_of)
                                 OR lfhe.p4_object_eligible(r ->> 0, (r ->> 1)::uuid, 'REPLAY', p_as_of)) END)
$$;

-- ---------------------------------------------------------------------------
-- HUMAN_ONLY: create / version / decide (permission ASSESSMENT_REVIEW)
-- ---------------------------------------------------------------------------
-- p: {code, context_type, title, text, valid_from?, valid_to?, knowledge_as_of, provenance_refs:[{object_type, object_id}]}
CREATE OR REPLACE FUNCTION lfhe.create_reference_context_version(p jsonb, p_reason text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('ASSESSMENT_REVIEW');
  v_rc    lfhe.reference_contexts%ROWTYPE;
  v_prev  lfhe.reference_context_versions%ROWTYPE;
  v_refs  jsonb := lfhe.p4_refs(p -> 'provenance_refs', ARRAY['claim', 'article', 'event_version']);
  v_asof  timestamptz := (p ->> 'knowledge_as_of')::timestamptz;
  v_id    uuid;
  v_content jsonb;
BEGIN
  IF pg_catalog.jsonb_array_length(v_refs) = 0 THEN
    RAISE EXCEPTION 'REFERENCE_CONTEXT_PROVENANCE_REQUIRED' USING ERRCODE = 'check_violation';
  END IF;
  IF v_asof IS NULL OR v_asof > now() THEN
    RAISE EXCEPTION 'KNOWLEDGE_AS_OF_INVALID' USING ERRCODE = 'check_violation';
  END IF;
  IF NOT lfhe.p4_refs_known_at(v_refs, v_asof) THEN
    RAISE EXCEPTION 'PROVENANCE_POSTDATES_KNOWLEDGE_AS_OF' USING ERRCODE = 'check_violation';
  END IF;
  IF p_reason IS NULL OR length(btrim(p_reason)) < 5 THEN
    RAISE EXCEPTION 'a reason is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  SELECT * INTO v_rc FROM lfhe.reference_contexts WHERE code = p ->> 'code' FOR UPDATE;
  IF NOT FOUND THEN
    INSERT INTO lfhe.reference_contexts (code, context_type, title, created_by)
    VALUES (p ->> 'code', p ->> 'context_type', p ->> 'title', v_actor) RETURNING * INTO v_rc;
  END IF;
  SELECT * INTO v_prev FROM lfhe.reference_context_versions WHERE reference_context_id = v_rc.id
  ORDER BY version_no DESC LIMIT 1;
  v_content := pg_catalog.jsonb_build_object('title', p ->> 'title', 'text', p ->> 'text',
    'valid_from', p ->> 'valid_from', 'valid_to', p ->> 'valid_to', 'context_type', v_rc.context_type,
    'provenance_refs', v_refs);
  IF coalesce(length(btrim(p ->> 'text')), 0) < 10 THEN
    RAISE EXCEPTION 'reference context text is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  INSERT INTO lfhe.reference_context_versions (reference_context_id, version_no, previous_version_id, knowledge_as_of,
    content, content_hash, created_by, reason)
  VALUES (v_rc.id, coalesce(v_prev.version_no, 0) + 1, v_prev.id, v_asof, v_content,
    lfhe.p4_hash('lfhe-reference-context-version/1', v_content || pg_catalog.jsonb_build_object(
      'reference_context_id', v_rc.id, 'version_no', coalesce(v_prev.version_no, 0) + 1,
      'previous_version_id', v_prev.id, 'knowledge_as_of_epoch', extract(epoch FROM v_asof))), v_actor, p_reason)
  RETURNING id INTO v_id;
  INSERT INTO lfhe.reference_context_provenance (reference_context_version_id, object_type, object_id)
  SELECT v_id, r ->> 0, (r ->> 1)::uuid FROM pg_catalog.jsonb_array_elements(v_refs) r;
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.create_reference_context_version(jsonb, text) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.decide_reference_context_version(p_version uuid, p_content_hash text, p_decision text,
                                                                 p_reason text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('ASSESSMENT_REVIEW');
  v_id    uuid;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM lfhe.reference_context_versions WHERE id = p_version AND content_hash = p_content_hash) THEN
    RAISE EXCEPTION 'VERSION_HASH_MISMATCH' USING ERRCODE = 'serialization_failure';
  END IF;
  INSERT INTO lfhe.reference_context_decisions (reference_context_version_id, content_hash, decision, actor_user_id, reason)
  VALUES (p_version, p_content_hash, p_decision, v_actor, p_reason) RETURNING id INTO v_id;
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.decide_reference_context_version(uuid, text, text, text) IS 'HUMAN_ONLY';

-- p: {code, title, scope, knowledge_as_of, components: [{text, evidence: [{object_type, object_id}]}]}
CREATE OR REPLACE FUNCTION lfhe.create_baseline_version(p jsonb, p_reason text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('ASSESSMENT_REVIEW');
  v_bl    lfhe.baselines%ROWTYPE;
  v_prev  lfhe.baseline_versions%ROWTYPE;
  v_asof  timestamptz := (p ->> 'knowledge_as_of')::timestamptz;
  v_comps jsonb := '[]';
  v_c     jsonb;
  v_refs  jsonb;
  v_n     integer := 0;
  v_id    uuid;
  v_content jsonb;
BEGIN
  IF v_asof IS NULL OR v_asof > now() THEN
    RAISE EXCEPTION 'KNOWLEDGE_AS_OF_INVALID' USING ERRCODE = 'check_violation';
  END IF;
  IF p_reason IS NULL OR length(btrim(p_reason)) < 5 THEN
    RAISE EXCEPTION 'a reason is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  FOR v_c IN SELECT * FROM pg_catalog.jsonb_array_elements(coalesce(p -> 'components', '[]')) LOOP
    v_n := v_n + 1;
    v_refs := lfhe.p4_refs(v_c -> 'evidence', ARRAY['claim', 'event_version', 'reference_context_version']);
    IF pg_catalog.jsonb_array_length(v_refs) = 0 THEN
      RAISE EXCEPTION 'BASELINE_COMPONENT_UNATTRIBUTED: component % has no evidence', v_n USING ERRCODE = 'check_violation';
    END IF;
    IF coalesce(length(btrim(v_c ->> 'text')), 0) < 3 THEN
      RAISE EXCEPTION 'baseline component text is required' USING ERRCODE = 'invalid_parameter_value';
    END IF;
    IF NOT lfhe.p4_refs_known_at(v_refs, v_asof) THEN
      RAISE EXCEPTION 'EVIDENCE_POSTDATES_KNOWLEDGE_AS_OF: component %', v_n USING ERRCODE = 'check_violation';
    END IF;
    v_comps := v_comps || pg_catalog.jsonb_build_object('component_no', v_n, 'text', v_c ->> 'text', 'evidence', v_refs);
  END LOOP;
  IF v_n = 0 THEN
    RAISE EXCEPTION 'a baseline needs at least one component' USING ERRCODE = 'check_violation';
  END IF;
  SELECT * INTO v_bl FROM lfhe.baselines WHERE code = p ->> 'code' FOR UPDATE;
  IF NOT FOUND THEN
    INSERT INTO lfhe.baselines (code, title, scope, created_by) VALUES (p ->> 'code', p ->> 'title', p ->> 'scope', v_actor)
    RETURNING * INTO v_bl;
  END IF;
  SELECT * INTO v_prev FROM lfhe.baseline_versions WHERE baseline_id = v_bl.id ORDER BY version_no DESC LIMIT 1;
  v_content := pg_catalog.jsonb_build_object('title', coalesce(p ->> 'title', v_bl.title), 'components', v_comps);
  INSERT INTO lfhe.baseline_versions (baseline_id, version_no, previous_version_id, knowledge_as_of, content, content_hash,
    created_by, reason)
  VALUES (v_bl.id, coalesce(v_prev.version_no, 0) + 1, v_prev.id, v_asof, v_content,
    lfhe.p4_hash('lfhe-baseline-version/1', v_content || pg_catalog.jsonb_build_object(
      'baseline_id', v_bl.id, 'version_no', coalesce(v_prev.version_no, 0) + 1,
      'previous_version_id', v_prev.id, 'knowledge_as_of_epoch', extract(epoch FROM v_asof))), v_actor, p_reason)
  RETURNING id INTO v_id;
  INSERT INTO lfhe.baseline_component_evidence (baseline_version_id, component_no, object_type, object_id)
  SELECT v_id, (c ->> 'component_no')::integer, r ->> 0, (r ->> 1)::uuid
  FROM pg_catalog.jsonb_array_elements(v_comps) c, pg_catalog.jsonb_array_elements(c -> 'evidence') r;
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.create_baseline_version(jsonb, text) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.decide_baseline_version(p_version uuid, p_content_hash text, p_decision text, p_reason text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('ASSESSMENT_REVIEW');
  v_id    uuid;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM lfhe.baseline_versions WHERE id = p_version AND content_hash = p_content_hash) THEN
    RAISE EXCEPTION 'VERSION_HASH_MISMATCH' USING ERRCODE = 'serialization_failure';
  END IF;
  INSERT INTO lfhe.baseline_version_decisions (baseline_version_id, content_hash, decision, actor_user_id, reason)
  VALUES (p_version, p_content_hash, p_decision, v_actor, p_reason) RETURNING id INTO v_id;
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.decide_baseline_version(uuid, text, text, text) IS 'HUMAN_ONLY';

-- ---------------------------------------------------------------------------
-- Audit
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.audit_p4_objects()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_event text := TG_ARGV[0];
  v_obj   text := TG_ARGV[1];
  v_id    text := pg_catalog.to_jsonb(NEW) ->> TG_ARGV[2];
  v_doc   jsonb := pg_catalog.to_jsonb(NEW);
BEGIN
  IF TG_ARGV[3] <> '' THEN                    -- decision tables: event code depends on the decision
    v_event := CASE WHEN v_doc ->> 'decision' = 'APPROVE' THEN TG_ARGV[0] ELSE TG_ARGV[3] END;
  END IF;
  PERFORM lfhe.write_audit(v_event, v_obj, v_id, NULL, v_doc - 'content', pg_catalog.jsonb_build_object(
    'content_hash', v_doc ->> 'content_hash'));
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION lfhe.audit_p4_objects() FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;

CREATE TRIGGER reference_contexts_audit AFTER INSERT ON lfhe.reference_contexts
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_p4_objects('REFERENCE_CONTEXT_CREATED', 'reference_context', 'id', '');
CREATE TRIGGER reference_context_versions_audit AFTER INSERT ON lfhe.reference_context_versions
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_p4_objects('REFERENCE_CONTEXT_VERSION_CREATED', 'reference_context_version', 'id', '');
CREATE TRIGGER reference_context_decisions_audit AFTER INSERT ON lfhe.reference_context_decisions
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_p4_objects('REFERENCE_CONTEXT_APPROVED', 'reference_context_version',
                                                      'reference_context_version_id', 'REFERENCE_CONTEXT_REJECTED');
CREATE TRIGGER baselines_audit AFTER INSERT ON lfhe.baselines
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_p4_objects('BASELINE_CREATED', 'baseline', 'id', '');
CREATE TRIGGER baseline_versions_audit AFTER INSERT ON lfhe.baseline_versions
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_p4_objects('BASELINE_VERSION_CREATED', 'baseline_version', 'id', '');
CREATE TRIGGER baseline_version_decisions_audit AFTER INSERT ON lfhe.baseline_version_decisions
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_p4_objects('BASELINE_VERSION_APPROVED', 'baseline_version',
                                                      'baseline_version_id', 'BASELINE_VERSION_REJECTED');

-- ---------------------------------------------------------------------------
-- Grants / RLS
-- ---------------------------------------------------------------------------
REVOKE ALL ON FUNCTION
  lfhe.create_reference_context_version(jsonb, text), lfhe.decide_reference_context_version(uuid, text, text, text),
  lfhe.create_baseline_version(jsonb, text), lfhe.decide_baseline_version(uuid, text, text, text)
  FROM PUBLIC, anon, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION
  lfhe.create_reference_context_version(jsonb, text), lfhe.decide_reference_context_version(uuid, text, text, text),
  lfhe.create_baseline_version(jsonb, text), lfhe.decide_baseline_version(uuid, text, text, text)
  TO authenticated;
REVOKE ALL ON FUNCTION
  lfhe.p4_object_eligible(text, uuid, text, timestamptz, integer),
  lfhe.claim_status_row_usable(lfhe.claim_status_history, text, timestamptz),
  lfhe.claim_status_asof(uuid, text, timestamptz),
  lfhe.reference_context_version_usable(uuid, text, timestamptz, integer),
  lfhe.baseline_version_usable(uuid, text, timestamptz),
  lfhe.baseline_asof(uuid, text, timestamptz), lfhe.reference_context_asof(uuid, text, timestamptz),
  lfhe.p4_refs(jsonb, text[]), lfhe.p4_refs_known_at(jsonb, timestamptz)
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION
  lfhe.p4_object_eligible(text, uuid, text, timestamptz, integer),
  lfhe.claim_status_asof(uuid, text, timestamptz),
  lfhe.reference_context_version_usable(uuid, text, timestamptz, integer),
  lfhe.baseline_version_usable(uuid, text, timestamptz),
  lfhe.baseline_asof(uuid, text, timestamptz), lfhe.reference_context_asof(uuid, text, timestamptz)
  TO lfhe_worker;

REVOKE ALL ON lfhe.reference_contexts, lfhe.reference_context_versions, lfhe.reference_context_provenance,
  lfhe.reference_context_decisions, lfhe.baselines, lfhe.baseline_versions, lfhe.baseline_component_evidence,
  lfhe.baseline_version_decisions
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT SELECT ON lfhe.reference_contexts, lfhe.reference_context_versions, lfhe.reference_context_provenance,
  lfhe.reference_context_decisions, lfhe.baselines, lfhe.baseline_versions, lfhe.baseline_component_evidence,
  lfhe.baseline_version_decisions
  TO authenticated, lfhe_worker;
DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['reference_contexts', 'reference_context_versions', 'reference_context_provenance',
    'reference_context_decisions', 'baselines', 'baseline_versions', 'baseline_component_evidence',
    'baseline_version_decisions'] LOOP
    EXECUTE format('ALTER TABLE lfhe.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY %I ON lfhe.%I FOR SELECT TO authenticated USING (lfhe.has_permission(''CLAIM_READ''))',
                   t || '_read_human', t);
    EXECUTE format('CREATE POLICY %I ON lfhe.%I FOR SELECT TO lfhe_worker USING (true)', t || '_read_worker', t);
  END LOOP;
END $$;
