-- LFHÉ Phase 4 (P4-07) — persistent trends and indicators. Baseline: Phase 4 Addendum
-- §17, §18, §19, §22.
--
-- TRENDS (§17). The cumulative prompt baseline (MPP v1.2) gives M07 related_trends only
-- as INPUT and defines no AI trend-creation action, so Phase 4 v1.0 implements the
-- persistence / provenance layer and the HUMAN/manual creation path only (§17 last rule).
-- * trend ≠ event: separate tables; a trend version references EXACT event_version_id +
--   content_hash pairs (trend_events) of at least TWO distinct events — one event can
--   never silently establish a multi-event trend (TREND_REQUIRES_MULTIPLE_EVENTS).
-- * direction and velocity are separate fields; uncertainty is mandatory. No normative
--   direction/velocity vocabulary exists in a higher-authority document, so both are
--   human free text (CHANGE REQUEST CR4-02) — nothing is invented.
-- * versions are immutable and hashed; history is kept; as-of use is knowledge-bound
--   (knowledge_as_of <= cutoff AND every member event version eligible AND every cited
--   assessment version approved as of the cutoff).
--
-- INDICATORS (§18). M07 indicators_to_watch stay proposals inside the assessment workflow
-- (assessment_indicator_proposals). An authoritative indicator is created only by a human
-- (HUMAN_ONLY), from an APPROVED assessment version (optionally from one of its proposals),
-- bound to that version + hash, to statements of that version and to claims of its event
-- version (indicator_claims). Deterministic checks reject vague / non-observable /
-- operational indicators; a vague proposal can only become authoritative through a human
-- correction (INDICATOR_REQUIRES_HUMAN_CORRECTION).

INSERT INTO lfhe.audit_event_types (code, spec_source) VALUES
  ('TREND_CREATED', 'Phase 4 Addendum §17'),
  ('TREND_VERSION_CREATED', 'Phase 4 Addendum §17'),
  ('INDICATOR_CREATED', 'Phase 4 Addendum §18'),
  ('INDICATOR_VERSION_CREATED', 'Phase 4 Addendum §18')
ON CONFLICT (code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Trends
-- ---------------------------------------------------------------------------
CREATE TABLE lfhe.trends (
  id          uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  code        text NOT NULL UNIQUE CHECK (code ~ '^TR-[A-Z0-9][A-Z0-9_-]{1,60}$'),
  title       text NOT NULL CHECK (length(btrim(title)) BETWEEN 3 AND 300),
  created_by  uuid NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE lfhe.trend_versions (
  id                   uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  trend_id             uuid NOT NULL REFERENCES lfhe.trends(id),
  version_no           integer NOT NULL CHECK (version_no >= 1),
  previous_version_id  uuid REFERENCES lfhe.trend_versions(id),
  knowledge_as_of      timestamptz NOT NULL,
  content              jsonb NOT NULL,
  content_hash         text NOT NULL,
  created_by           uuid NOT NULL,
  reason               text NOT NULL CHECK (length(btrim(reason)) >= 5),
  created_at           timestamptz NOT NULL DEFAULT now(),
  UNIQUE (trend_id, version_no),
  UNIQUE (id, content_hash),
  CHECK (content_hash = lfhe.p4_hash('lfhe-trend-version/1', content || pg_catalog.jsonb_build_object(
    'trend_id', trend_id, 'version_no', version_no, 'previous_version_id', previous_version_id,
    'knowledge_as_of_epoch', extract(epoch FROM knowledge_as_of)))),
  CHECK (length(btrim(content ->> 'direction')) >= 3 AND length(btrim(content ->> 'velocity')) >= 3
         AND length(btrim(content ->> 'uncertainty')) >= 10)
);

CREATE TABLE lfhe.trend_events (
  trend_version_id    uuid NOT NULL REFERENCES lfhe.trend_versions(id),
  event_version_id    uuid NOT NULL,
  event_version_hash  text NOT NULL,
  event_id            uuid NOT NULL REFERENCES lfhe.events(id),
  PRIMARY KEY (trend_version_id, event_version_id),
  FOREIGN KEY (event_version_id, event_version_hash) REFERENCES lfhe.event_versions (id, content_hash)
);

CREATE TABLE lfhe.trend_version_assessments (
  trend_version_id         uuid NOT NULL REFERENCES lfhe.trend_versions(id),
  assessment_version_id    uuid NOT NULL,
  assessment_version_hash  text NOT NULL,
  PRIMARY KEY (trend_version_id, assessment_version_id),
  FOREIGN KEY (assessment_version_id, assessment_version_hash) REFERENCES lfhe.assessment_versions (id, content_hash)
);

-- ---------------------------------------------------------------------------
-- Indicators
-- ---------------------------------------------------------------------------
CREATE TABLE lfhe.indicators (
  id          uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  code        text NOT NULL UNIQUE CHECK (code ~ '^IND-[A-Z0-9][A-Z0-9_-]{1,60}$'),
  created_by  uuid NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE lfhe.indicator_versions (
  id                       uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  indicator_id             uuid NOT NULL REFERENCES lfhe.indicators(id),
  version_no               integer NOT NULL CHECK (version_no >= 1),
  previous_version_id      uuid REFERENCES lfhe.indicator_versions(id),
  assessment_version_id    uuid NOT NULL,
  assessment_version_hash  text NOT NULL,
  trend_version_id         uuid REFERENCES lfhe.trend_versions(id),
  source_proposal_id       uuid REFERENCES lfhe.assessment_indicator_proposals(id),
  human_corrected          boolean NOT NULL,
  content                  jsonb NOT NULL,
  content_hash             text NOT NULL,
  created_by               uuid NOT NULL,
  reason                   text NOT NULL CHECK (length(btrim(reason)) >= 5),
  created_at               timestamptz NOT NULL DEFAULT now(),
  UNIQUE (indicator_id, version_no),
  UNIQUE (id, content_hash),
  FOREIGN KEY (assessment_version_id, assessment_version_hash) REFERENCES lfhe.assessment_versions (id, content_hash),
  CHECK (content_hash = lfhe.p4_hash('lfhe-indicator-version/1', content || pg_catalog.jsonb_build_object(
    'indicator_id', indicator_id, 'version_no', version_no, 'previous_version_id', previous_version_id,
    'assessment_version_id', assessment_version_id, 'assessment_version_hash', assessment_version_hash,
    'trend_version_id', trend_version_id, 'source_proposal_id', source_proposal_id))),
  CHECK (length(btrim(content ->> 'indicator_text')) >= 5 AND length(btrim(content ->> 'observable_condition')) >= 10),
  CHECK (pg_catalog.jsonb_array_length(content -> 'related_statement_ids') >= 1)
);

CREATE TABLE lfhe.indicator_claims (
  indicator_version_id  uuid NOT NULL REFERENCES lfhe.indicator_versions(id),
  claim_id              uuid NOT NULL REFERENCES lfhe.claims(id),
  PRIMARY KEY (indicator_version_id, claim_id)
);

DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['trends', 'trend_versions', 'trend_events', 'trend_version_assessments', 'indicators',
                           'indicator_versions', 'indicator_claims'] LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON lfhe.%I FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation()',
                   t || '_immutable', t);
  END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- Deterministic indicator checks (heuristic, documented as such)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.p4_indicator_problems(p_text text, p_condition text)
RETURNS text[] LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
  SELECT ARRAY(SELECT x FROM (VALUES
    (CASE WHEN coalesce(length(btrim(p_text)), 0) < 5 OR coalesce(length(btrim(p_condition)), 0) < 10
          THEN 'INDICATOR_NOT_OBSERVABLE' END),
    -- vague: "monitor/watch the situation / developments / any changes" without a concrete
    -- quantity or named subject in the observable condition
    (CASE WHEN (lower(coalesce(p_condition, '')) ~ '\m(monitor|watch|track|follow|keep an eye on|observe)\M[^.]{0,40}\m(situation|developments?|changes?|activity|events|trends?)\M'
                OR lower(coalesce(p_condition, '')) ~ '\many (further )?(changes?|developments?|activity)\M'
                OR lower(coalesce(p_condition, '')) ~ '^\s*(increased|heightened|unusual|more|further|continued) (activity|tension|presence)\s*\.?\s*$')
           AND NOT (coalesce(p_condition, '') ~ '[0-9]' OR coalesce(p_condition, '') ~ '.\m[A-Z][a-z]{2,}')
          THEN 'INDICATOR_VAGUE' END),
    (CASE WHEN lfhe.p4_text_has('operational', coalesce(p_text, '') || ' ' || coalesce(p_condition, ''))
          THEN 'OPERATIONAL_RECOMMENDATION_PROHIBITED' END)) v(x) WHERE x IS NOT NULL)
$$;

-- ---------------------------------------------------------------------------
-- As-of usability
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.trend_version_usable(p_version uuid, p_mode text, p_cutoff timestamptz)
RETURNS boolean LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v lfhe.trend_versions%ROWTYPE;
BEGIN
  SELECT * INTO v FROM lfhe.trend_versions WHERE id = p_version;
  IF NOT FOUND OR p_mode NOT IN ('LIVE', 'REPLAY') OR p_cutoff IS NULL OR v.knowledge_as_of > p_cutoff THEN
    RETURN false;
  END IF;
  RETURN NOT EXISTS (SELECT 1 FROM lfhe.trend_events e WHERE e.trend_version_id = v.id
                     AND NOT lfhe.p4_object_eligible('event_version', e.event_version_id, p_mode, p_cutoff))
     AND NOT EXISTS (SELECT 1 FROM lfhe.trend_version_assessments a WHERE a.trend_version_id = v.id
                     AND NOT lfhe.assessment_version_approved_asof(a.assessment_version_id, p_mode, p_cutoff));
END $$;

CREATE OR REPLACE FUNCTION lfhe.trend_asof(p_trend uuid, p_mode text, p_cutoff timestamptz)
RETURNS uuid LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT v.id FROM lfhe.trend_versions v
  WHERE v.trend_id = p_trend AND lfhe.trend_version_usable(v.id, p_mode, p_cutoff)
  ORDER BY v.version_no DESC LIMIT 1
$$;

CREATE OR REPLACE FUNCTION lfhe.indicator_version_usable(p_version uuid, p_mode text, p_cutoff timestamptz)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT EXISTS (SELECT 1 FROM lfhe.indicator_versions v WHERE v.id = p_version
                 AND lfhe.assessment_version_approved_asof(v.assessment_version_id, p_mode, p_cutoff)
                 AND (v.trend_version_id IS NULL OR lfhe.trend_version_usable(v.trend_version_id, p_mode, p_cutoff)))
     AND NOT EXISTS (SELECT 1 FROM lfhe.indicator_claims c WHERE c.indicator_version_id = p_version
                     AND NOT lfhe.p4_object_eligible('claim', c.claim_id, p_mode, p_cutoff))
$$;

-- ---------------------------------------------------------------------------
-- HUMAN_ONLY: trend versions (permission ASSESSMENT_REVIEW)
-- p: {code, title, description, direction, velocity, uncertainty, knowledge_as_of,
--     event_versions: [{event_version_id, content_hash}], assessment_versions?: [{assessment_version_id, content_hash}]}
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.create_trend_version(p jsonb, p_reason text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor  uuid := lfhe.require_human_permission('ASSESSMENT_REVIEW');
  v_asof   timestamptz := (p ->> 'knowledge_as_of')::timestamptz;
  v_tr     lfhe.trends%ROWTYPE;
  v_prev   lfhe.trend_versions%ROWTYPE;
  v_e      jsonb;
  v_evs    jsonb := '[]';
  v_ass    jsonb := '[]';
  v_ev     lfhe.event_versions%ROWTYPE;
  v_content jsonb;
  v_no     integer;
  v_id     uuid;
BEGIN
  IF v_asof IS NULL OR v_asof > now() THEN
    RAISE EXCEPTION 'KNOWLEDGE_AS_OF_INVALID' USING ERRCODE = 'check_violation';
  END IF;
  IF p_reason IS NULL OR length(btrim(p_reason)) < 5 THEN
    RAISE EXCEPTION 'a reason is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  IF coalesce(length(btrim(p ->> 'uncertainty')), 0) < 10 THEN
    RAISE EXCEPTION 'TREND_UNCERTAINTY_REQUIRED' USING ERRCODE = 'check_violation';
  END IF;
  IF coalesce(length(btrim(p ->> 'direction')), 0) < 3 OR coalesce(length(btrim(p ->> 'velocity')), 0) < 3 THEN
    RAISE EXCEPTION 'TREND_DIRECTION_AND_VELOCITY_REQUIRED (separate fields; "not established" is allowed)'
      USING ERRCODE = 'check_violation';
  END IF;
  FOR v_e IN SELECT * FROM pg_catalog.jsonb_array_elements(coalesce(p -> 'event_versions', '[]')) LOOP
    SELECT * INTO v_ev FROM lfhe.event_versions WHERE id::text = v_e ->> 'event_version_id';
    IF NOT FOUND OR v_ev.content_hash IS DISTINCT FROM v_e ->> 'content_hash' THEN
      RAISE EXCEPTION 'VERSION_HASH_MISMATCH: event version %', left(v_e ->> 'event_version_id', 40)
        USING ERRCODE = 'serialization_failure';
    END IF;
    IF NOT lfhe.p4_refs_known_at(pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_array('event_version', v_ev.id::text)), v_asof) THEN
      RAISE EXCEPTION 'EVIDENCE_POSTDATES_KNOWLEDGE_AS_OF: event version %', v_ev.id USING ERRCODE = 'check_violation';
    END IF;
    v_evs := v_evs || pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_array(v_ev.id::text, v_ev.content_hash, v_ev.event_id::text));
  END LOOP;
  SELECT coalesce(pg_catalog.jsonb_agg(DISTINCT x), '[]') INTO v_evs FROM pg_catalog.jsonb_array_elements(v_evs) x;
  IF (SELECT count(DISTINCT x ->> 2) FROM pg_catalog.jsonb_array_elements(v_evs) x) < 2 THEN
    RAISE EXCEPTION 'TREND_REQUIRES_MULTIPLE_EVENTS: a trend needs event versions of at least two distinct events'
      USING ERRCODE = 'check_violation';
  END IF;
  IF (SELECT count(*) FROM pg_catalog.jsonb_array_elements(v_evs) x) <> (SELECT count(DISTINCT x ->> 2) FROM pg_catalog.jsonb_array_elements(v_evs) x) THEN
    RAISE EXCEPTION 'TREND_EVENT_VERSION_AMBIGUOUS: one version per event' USING ERRCODE = 'check_violation';
  END IF;
  FOR v_e IN SELECT * FROM pg_catalog.jsonb_array_elements(coalesce(p -> 'assessment_versions', '[]')) LOOP
    IF NOT EXISTS (SELECT 1 FROM lfhe.assessment_versions WHERE id::text = v_e ->> 'assessment_version_id'
                   AND content_hash = v_e ->> 'content_hash') THEN
      RAISE EXCEPTION 'VERSION_HASH_MISMATCH: assessment version %', left(v_e ->> 'assessment_version_id', 40)
        USING ERRCODE = 'serialization_failure';
    END IF;
    IF NOT (lfhe.assessment_version_approved_asof((v_e ->> 'assessment_version_id')::uuid, 'LIVE', v_asof)
            OR lfhe.assessment_version_approved_asof((v_e ->> 'assessment_version_id')::uuid, 'REPLAY', v_asof)) THEN
      RAISE EXCEPTION 'TREND_ASSESSMENT_NOT_APPROVED_ASOF: %', v_e ->> 'assessment_version_id' USING ERRCODE = 'check_violation';
    END IF;
    v_ass := v_ass || pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_array(v_e ->> 'assessment_version_id', v_e ->> 'content_hash'));
  END LOOP;
  SELECT coalesce(pg_catalog.jsonb_agg(DISTINCT x), '[]') INTO v_ass FROM pg_catalog.jsonb_array_elements(v_ass) x;
  SELECT coalesce(pg_catalog.jsonb_agg(x ORDER BY (x ->> 0) COLLATE "C"), '[]') INTO v_evs FROM pg_catalog.jsonb_array_elements(v_evs) x;
  SELECT coalesce(pg_catalog.jsonb_agg(x ORDER BY (x ->> 0) COLLATE "C"), '[]') INTO v_ass FROM pg_catalog.jsonb_array_elements(v_ass) x;

  SELECT * INTO v_tr FROM lfhe.trends WHERE code = p ->> 'code' FOR UPDATE;
  IF NOT FOUND THEN
    INSERT INTO lfhe.trends (code, title, created_by) VALUES (p ->> 'code', p ->> 'title', v_actor) RETURNING * INTO v_tr;
  END IF;
  SELECT * INTO v_prev FROM lfhe.trend_versions WHERE trend_id = v_tr.id ORDER BY version_no DESC LIMIT 1;
  v_no := coalesce(v_prev.version_no, 0) + 1;
  v_content := pg_catalog.jsonb_build_object('title', coalesce(p ->> 'title', v_tr.title),
    'description', coalesce(p ->> 'description', ''), 'direction', p ->> 'direction', 'velocity', p ->> 'velocity',
    'uncertainty', p ->> 'uncertainty', 'event_versions', v_evs, 'assessment_versions', v_ass);
  INSERT INTO lfhe.trend_versions (trend_id, version_no, previous_version_id, knowledge_as_of, content, content_hash,
    created_by, reason)
  VALUES (v_tr.id, v_no, v_prev.id, v_asof, v_content,
    lfhe.p4_hash('lfhe-trend-version/1', v_content || pg_catalog.jsonb_build_object('trend_id', v_tr.id, 'version_no', v_no,
      'previous_version_id', v_prev.id, 'knowledge_as_of_epoch', extract(epoch FROM v_asof))), v_actor, p_reason)
  RETURNING id INTO v_id;
  INSERT INTO lfhe.trend_events (trend_version_id, event_version_id, event_version_hash, event_id)
  SELECT v_id, (x ->> 0)::uuid, x ->> 1, (x ->> 2)::uuid FROM pg_catalog.jsonb_array_elements(v_evs) x;
  INSERT INTO lfhe.trend_version_assessments (trend_version_id, assessment_version_id, assessment_version_hash)
  SELECT v_id, (x ->> 0)::uuid, x ->> 1 FROM pg_catalog.jsonb_array_elements(v_ass) x;
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.create_trend_version(jsonb, text) IS 'HUMAN_ONLY';

-- ---------------------------------------------------------------------------
-- HUMAN_ONLY: indicator versions (permission ASSESSMENT_REVIEW)
-- p: {code, assessment_version_id, assessment_version_hash, source_proposal_id?, trend_version_id?,
--     indicator_text?, observable_condition?, related_statement_local_ids?, supporting_claim_ids?}
-- From a proposal, absent fields are taken from the proposal; any supplied text field
-- that differs from the proposal is a human correction.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.create_indicator_version(p jsonb, p_reason text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor   uuid := lfhe.require_human_permission('ASSESSMENT_REVIEW');
  v_av      lfhe.assessment_versions%ROWTYPE;
  v_prop    lfhe.assessment_indicator_proposals%ROWTYPE;
  v_ind     lfhe.indicators%ROWTYPE;
  v_prev    lfhe.indicator_versions%ROWTYPE;
  v_text    text;
  v_cond    text;
  v_stmts   uuid[];
  v_claims  uuid[];
  v_allowed uuid[];
  v_corr    boolean := false;
  v_probs   text[];
  v_tv      uuid := nullif(p ->> 'trend_version_id', '')::uuid;
  v_content jsonb;
  v_no      integer;
  v_id      uuid;
BEGIN
  IF p_reason IS NULL OR length(btrim(p_reason)) < 5 THEN
    RAISE EXCEPTION 'a reason is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  SELECT * INTO v_av FROM lfhe.assessment_versions WHERE id::text = p ->> 'assessment_version_id';
  IF NOT FOUND OR v_av.content_hash IS DISTINCT FROM p ->> 'assessment_version_hash' THEN
    RAISE EXCEPTION 'VERSION_HASH_MISMATCH: assessment version' USING ERRCODE = 'serialization_failure';
  END IF;
  IF lfhe.assessment_version_state(v_av.id) IS DISTINCT FROM 'APPROVED' THEN
    RAISE EXCEPTION 'INDICATOR_ASSESSMENT_NOT_APPROVED: indicators become authoritative only from an approved assessment version'
      USING ERRCODE = 'object_not_in_prerequisite_state';
  END IF;
  IF p ->> 'source_proposal_id' IS NOT NULL THEN
    SELECT * INTO v_prop FROM lfhe.assessment_indicator_proposals WHERE id::text = p ->> 'source_proposal_id';
    IF NOT FOUND OR v_prop.assessment_version_id <> v_av.id THEN
      RAISE EXCEPTION 'INDICATOR_PROPOSAL_NOT_IN_ASSESSMENT_VERSION' USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  v_text := coalesce(p ->> 'indicator_text', v_prop.indicator_text);
  v_cond := coalesce(p ->> 'observable_condition', v_prop.observable_condition);
  IF v_prop.id IS NOT NULL THEN
    v_corr := v_text IS DISTINCT FROM v_prop.indicator_text OR v_cond IS DISTINCT FROM v_prop.observable_condition;
  END IF;
  IF p ? 'related_statement_local_ids' THEN
    v_stmts := ARRAY(SELECT s.id FROM lfhe.assessment_statements s WHERE s.assessment_version_id = v_av.id
                     AND s.statement_local_id IN (SELECT pg_catalog.jsonb_array_elements_text(p -> 'related_statement_local_ids'))
                     ORDER BY s.id);
    IF cardinality(v_stmts) <> (SELECT count(DISTINCT x) FROM pg_catalog.jsonb_array_elements_text(p -> 'related_statement_local_ids') x) THEN
      RAISE EXCEPTION 'INDICATOR_REFERENCES_UNKNOWN_STATEMENT' USING ERRCODE = 'check_violation';
    END IF;
  ELSE
    v_stmts := ARRAY(SELECT x FROM pg_catalog.unnest(v_prop.related_statement_ids) x ORDER BY x);
  END IF;
  IF coalesce(cardinality(v_stmts), 0) = 0 THEN
    RAISE EXCEPTION 'INDICATOR_UNBOUND: an indicator must be tied to statements of the approved assessment'
      USING ERRCODE = 'check_violation';
  END IF;
  IF p ? 'supporting_claim_ids' THEN
    IF EXISTS (SELECT 1 FROM pg_catalog.jsonb_array_elements_text(p -> 'supporting_claim_ids') x
               WHERE x !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') THEN
      RAISE EXCEPTION 'EVIDENCE_REFERENCE_INVALID' USING ERRCODE = 'check_violation';
    END IF;
    v_claims := ARRAY(SELECT DISTINCT x::uuid FROM pg_catalog.jsonb_array_elements_text(p -> 'supporting_claim_ids') x ORDER BY 1);
  ELSE
    v_claims := ARRAY(SELECT DISTINCT x FROM pg_catalog.unnest(coalesce(v_prop.supporting_claim_ids, '{}')) x ORDER BY 1);
  END IF;
  v_allowed := ARRAY(SELECT ec.claim_id FROM lfhe.event_claims ec WHERE ec.event_version_id = v_av.event_version_id);
  IF v_tv IS NOT NULL THEN
    IF NOT EXISTS (SELECT 1 FROM lfhe.trend_versions WHERE id = v_tv) THEN
      RAISE EXCEPTION 'unknown trend version %', v_tv USING ERRCODE = 'no_data_found';
    END IF;
    v_allowed := v_allowed || ARRAY(SELECT ec.claim_id FROM lfhe.trend_events te JOIN lfhe.event_claims ec
                                    ON ec.event_version_id = te.event_version_id WHERE te.trend_version_id = v_tv);
  END IF;
  IF EXISTS (SELECT 1 FROM pg_catalog.unnest(v_claims) c WHERE NOT (c = ANY (v_allowed))) THEN
    RAISE EXCEPTION 'EVIDENCE_NOT_SUPPLIED: indicator claims must belong to the bound event/trend versions'
      USING ERRCODE = 'check_violation';
  END IF;
  v_probs := lfhe.p4_indicator_problems(v_text, v_cond);
  IF cardinality(v_probs) > 0 THEN
    IF v_prop.id IS NOT NULL AND NOT v_corr THEN
      RAISE EXCEPTION 'INDICATOR_REQUIRES_HUMAN_CORRECTION: %', pg_catalog.array_to_string(v_probs, ', ')
        USING ERRCODE = 'check_violation';
    END IF;
    RAISE EXCEPTION 'INDICATOR_INVALID: %', pg_catalog.array_to_string(v_probs, ', ') USING ERRCODE = 'check_violation';
  END IF;

  SELECT * INTO v_ind FROM lfhe.indicators WHERE code = p ->> 'code' FOR UPDATE;
  IF NOT FOUND THEN
    INSERT INTO lfhe.indicators (code, created_by) VALUES (p ->> 'code', v_actor) RETURNING * INTO v_ind;
  END IF;
  SELECT * INTO v_prev FROM lfhe.indicator_versions WHERE indicator_id = v_ind.id ORDER BY version_no DESC LIMIT 1;
  v_no := coalesce(v_prev.version_no, 0) + 1;
  v_content := pg_catalog.jsonb_build_object('indicator_text', v_text, 'observable_condition', v_cond,
    'related_statement_ids', pg_catalog.to_jsonb(v_stmts), 'supporting_claim_ids', pg_catalog.to_jsonb(v_claims),
    'human_corrected', v_corr);
  INSERT INTO lfhe.indicator_versions (indicator_id, version_no, previous_version_id, assessment_version_id,
    assessment_version_hash, trend_version_id, source_proposal_id, human_corrected, content, content_hash, created_by, reason)
  VALUES (v_ind.id, v_no, v_prev.id, v_av.id, v_av.content_hash, v_tv, v_prop.id, v_corr, v_content,
    lfhe.p4_hash('lfhe-indicator-version/1', v_content || pg_catalog.jsonb_build_object(
      'indicator_id', v_ind.id, 'version_no', v_no, 'previous_version_id', v_prev.id,
      'assessment_version_id', v_av.id, 'assessment_version_hash', v_av.content_hash,
      'trend_version_id', v_tv, 'source_proposal_id', v_prop.id)), v_actor, p_reason)
  RETURNING id INTO v_id;
  INSERT INTO lfhe.indicator_claims (indicator_version_id, claim_id) SELECT v_id, c FROM pg_catalog.unnest(v_claims) c;
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.create_indicator_version(jsonb, text) IS 'HUMAN_ONLY';

-- ---------------------------------------------------------------------------
-- Audit
-- ---------------------------------------------------------------------------
CREATE TRIGGER trends_audit AFTER INSERT ON lfhe.trends
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_p4_objects('TREND_CREATED', 'trend', 'id', '');
CREATE TRIGGER trend_versions_audit AFTER INSERT ON lfhe.trend_versions
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_p4_objects('TREND_VERSION_CREATED', 'trend_version', 'id', '');
CREATE TRIGGER indicators_audit AFTER INSERT ON lfhe.indicators
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_p4_objects('INDICATOR_CREATED', 'indicator', 'id', '');
CREATE TRIGGER indicator_versions_audit AFTER INSERT ON lfhe.indicator_versions
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_p4_objects('INDICATOR_VERSION_CREATED', 'indicator_version', 'id', '');

-- ---------------------------------------------------------------------------
-- Grants / RLS
-- ---------------------------------------------------------------------------
REVOKE ALL ON FUNCTION lfhe.create_trend_version(jsonb, text), lfhe.create_indicator_version(jsonb, text)
  FROM PUBLIC, anon, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.create_trend_version(jsonb, text), lfhe.create_indicator_version(jsonb, text) TO authenticated;
REVOKE ALL ON FUNCTION lfhe.trend_version_usable(uuid, text, timestamptz), lfhe.trend_asof(uuid, text, timestamptz),
  lfhe.indicator_version_usable(uuid, text, timestamptz), lfhe.p4_indicator_problems(text, text)
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.trend_version_usable(uuid, text, timestamptz), lfhe.trend_asof(uuid, text, timestamptz),
  lfhe.indicator_version_usable(uuid, text, timestamptz), lfhe.p4_indicator_problems(text, text) TO lfhe_worker;

REVOKE ALL ON lfhe.trends, lfhe.trend_versions, lfhe.trend_events, lfhe.trend_version_assessments, lfhe.indicators,
  lfhe.indicator_versions, lfhe.indicator_claims
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT SELECT ON lfhe.trends, lfhe.trend_versions, lfhe.trend_events, lfhe.trend_version_assessments, lfhe.indicators,
  lfhe.indicator_versions, lfhe.indicator_claims TO authenticated, lfhe_worker;
DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['trends', 'trend_versions', 'trend_events', 'trend_version_assessments', 'indicators',
                           'indicator_versions', 'indicator_claims'] LOOP
    EXECUTE format('ALTER TABLE lfhe.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY %I ON lfhe.%I FOR SELECT TO authenticated USING (lfhe.has_permission(''CLAIM_READ''))',
                   t || '_read_human', t);
    EXECUTE format('CREATE POLICY %I ON lfhe.%I FOR SELECT TO lfhe_worker USING (true)', t || '_read_worker', t);
  END LOOP;
END $$;
