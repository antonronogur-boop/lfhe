-- LFHÉ Phase 5 (P5-01, P5-03 foundation) — reports, report candidate pool, HUMAN selection,
-- frozen selection sets; RFC 8785 JCS canonical serialisation in SQL.
-- Baseline: docs/specs/LFHE_Phase5_Authoritative_Baseline_Addendum_v1.0.md §3–§5, §9, §25;
-- Prompt Pack v1.2 §27–§32; CG0 architecture (table names, REPORT state machine).
--
-- * Section vocabulary = Prompt Pack §29 (closed): KEY_JUDGMENT, SIGNIFICANT_DEVELOPMENT,
--   INDICATOR_WARNING, TREND_WATCH, WHAT_TO_WATCH, CAVEAT. The baseline's "Supporting
--   Developments" / "Indicators" are these higher-authority SIGNIFICANT_DEVELOPMENT /
--   INDICATOR_WARNING codes (SD5-01).
-- * The candidate pool holds only exact, version-bound Phase 4 objects eligible for the report's
--   mode / cutoff (deterministic refresh). Inclusion is HUMAN_ONLY; every candidate stays
--   visible. A frozen selection set (immutable, JCS/SHA-256 hashed) is the only input M09 sees.
-- * Permission REPORT_EDIT (seeded in Phase 1 for Phase 5; ANALYST). Reads: CLAIM_READ.

INSERT INTO lfhe.audit_event_types (code, spec_source) VALUES
  ('REPORT_CREATED', 'Phase 5 impl.'),
  ('REPORT_CANDIDATE_ADDED', 'Phase 5 impl.'),
  ('REPORT_CANDIDATE_RETURNED_FOR_REVISION', 'Phase 5 impl.'),
  ('REPORT_SELECTION_FROZEN', 'Phase 5 impl.')
ON CONFLICT (code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- RFC 8785 JCS (subset used by LFHÉ canonical objects) — mirrors lfhe_shared.canonical_json.
-- Keys are restricted to ASCII identifiers (then UTF-16 order = byte order), numbers to
-- integers in the IEEE-754 safe range; anything else raises (fail closed).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.jcs(p jsonb)
RETURNS text LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_out text;
  v_num numeric;
BEGIN
  CASE pg_catalog.jsonb_typeof(p)
    WHEN 'object' THEN
      IF EXISTS (SELECT 1 FROM pg_catalog.jsonb_object_keys(p) k WHERE k !~ '^[A-Za-z0-9_]{1,100}$') THEN
        RAISE EXCEPTION 'JCS_KEY_NOT_ALLOWED' USING ERRCODE = 'invalid_parameter_value';
      END IF;
      SELECT '{' || coalesce(pg_catalog.string_agg(pg_catalog.to_json(e.key)::text || ':' || lfhe.jcs(e.value), ','
                                                   ORDER BY e.key COLLATE "C"), '') || '}'
      INTO v_out FROM pg_catalog.jsonb_each(p) e;
      RETURN v_out;
    WHEN 'array' THEN
      SELECT '[' || coalesce(pg_catalog.string_agg(lfhe.jcs(e.value), ',' ORDER BY e.n), '') || ']'
      INTO v_out FROM pg_catalog.jsonb_array_elements(p) WITH ORDINALITY e(value, n);
      RETURN v_out;
    WHEN 'string' THEN
      RETURN pg_catalog.to_json(p #>> '{}')::text;
    WHEN 'number' THEN
      v_num := (p #>> '{}')::numeric;
      IF v_num <> pg_catalog.trunc(v_num) OR abs(v_num) > 9007199254740992 THEN
        RAISE EXCEPTION 'JCS_NUMBER_NOT_SAFE_INTEGER' USING ERRCODE = 'invalid_parameter_value';
      END IF;
      RETURN v_num::bigint::text;
    ELSE
      RETURN p::text;                                    -- true / false / null
  END CASE;
END $$;

CREATE OR REPLACE FUNCTION lfhe.jcs_sha256(p jsonb)
RETURNS text LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
  SELECT pg_catalog.encode(extensions.digest(pg_catalog.convert_to(lfhe.jcs(p), 'UTF8'), 'sha256'), 'hex')
$$;

CREATE OR REPLACE FUNCTION lfhe.p5_ts(p timestamptz)
RETURNS text LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
  SELECT pg_catalog.to_char(p AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
$$;

-- ---------------------------------------------------------------------------
-- Vocabularies
-- ---------------------------------------------------------------------------
CREATE TYPE lfhe.report_section AS ENUM (                       -- Prompt Pack v1.2 §29 (closed, report order)
  'KEY_JUDGMENT', 'SIGNIFICANT_DEVELOPMENT', 'INDICATOR_WARNING', 'TREND_WATCH', 'WHAT_TO_WATCH', 'CAVEAT');
CREATE TYPE lfhe.report_candidate_type AS ENUM ('ASSESSMENT_VERSION', 'INDICATOR_VERSION', 'TREND_VERSION');

-- §10 targets (two-page leadership product). NULL = no numeric target defined.
CREATE TABLE lfhe.report_section_targets (
  section     lfhe.report_section PRIMARY KEY,
  target_min  integer,
  target_max  integer,
  hard_max    integer,
  spec_source text NOT NULL
);
INSERT INTO lfhe.report_section_targets VALUES
  ('KEY_JUDGMENT', NULL, 3, 3, 'Phase 5 Addendum §10: maximum 3 Key Judgements'),
  ('SIGNIFICANT_DEVELOPMENT', 4, 5, NULL, 'Phase 5 Addendum §10: 4–5 Supporting Developments'),
  ('INDICATOR_WARNING', 4, 6, NULL, 'Phase 5 Addendum §10: 4–6 Indicators'),
  ('TREND_WATCH', NULL, NULL, NULL, 'Prompt Pack v1.2 §31 (no numeric target)'),
  ('WHAT_TO_WATCH', 3, 3, NULL, 'Phase 5 Addendum §10: 3 What-to-Watch items'),
  ('CAVEAT', NULL, NULL, NULL, 'Prompt Pack v1.2 §29 (no numeric target)');

-- ---------------------------------------------------------------------------
-- Reports
-- ---------------------------------------------------------------------------
CREATE TABLE lfhe.reports (
  id                  uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  code                text NOT NULL UNIQUE CHECK (code ~ '^RPT-[A-Z0-9][A-Z0-9_-]{1,60}$'),
  title               text NOT NULL CHECK (length(btrim(title)) BETWEEN 3 AND 300),
  cycle_label         text NOT NULL CHECK (length(btrim(cycle_label)) BETWEEN 1 AND 60),
  report_mode         lfhe.report_mode NOT NULL,
  information_cutoff  timestamptz NOT NULL,
  created_by          uuid NOT NULL,
  created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE lfhe.report_candidate_pool (
  id                   uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  report_id            uuid NOT NULL REFERENCES lfhe.reports(id),
  candidate_type       lfhe.report_candidate_type NOT NULL,
  object_id            uuid NOT NULL,
  object_hash          text NOT NULL CHECK (object_hash ~ '^[0-9a-f]{64}$'),
  recommended_section  lfhe.report_section NOT NULL,
  recommended_rank     numeric(3, 2),                         -- advisory only (M06 priority of the event version)
  created_at           timestamptz NOT NULL DEFAULT now(),
  UNIQUE (report_id, candidate_type, object_id),
  UNIQUE (id, object_hash)
);

CREATE TABLE lfhe.report_selection_decisions (
  seq                    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id                     uuid NOT NULL UNIQUE DEFAULT pg_catalog.gen_random_uuid(),
  report_id              uuid NOT NULL REFERENCES lfhe.reports(id),
  candidate_id           uuid NOT NULL,
  candidate_object_hash  text NOT NULL,
  decision               text NOT NULL CHECK (decision IN ('INCLUDE', 'EXCLUDE', 'RETURN_FOR_ANALYTICAL_REVISION')),
  section                lfhe.report_section,
  priority               integer CHECK (priority BETWEEN 1 AND 999),
  previous_decision_id   uuid REFERENCES lfhe.report_selection_decisions(id),
  actor_user_id          uuid NOT NULL,
  reason                 text NOT NULL CHECK (length(btrim(reason)) >= 5),
  created_at             timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (candidate_id, candidate_object_hash) REFERENCES lfhe.report_candidate_pool (id, object_hash),
  CHECK ((decision = 'INCLUDE') = (section IS NOT NULL AND priority IS NOT NULL)),
  CHECK (section IS DISTINCT FROM 'CAVEAT')
);

CREATE TABLE lfhe.report_selection_sets (
  id            uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  report_id     uuid NOT NULL REFERENCES lfhe.reports(id),
  set_no        integer NOT NULL CHECK (set_no >= 1),
  content       jsonb NOT NULL,
  content_hash  text NOT NULL,
  created_by    uuid NOT NULL,
  reason        text NOT NULL CHECK (length(btrim(reason)) >= 5),
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (report_id, set_no),
  UNIQUE (id, content_hash),
  CHECK (content_hash = lfhe.jcs_sha256(content)),
  CHECK (pg_catalog.jsonb_array_length(content -> 'items') >= 1)
);

CREATE TABLE lfhe.report_selection_set_items (
  selection_set_id  uuid NOT NULL REFERENCES lfhe.report_selection_sets(id),
  candidate_id      uuid NOT NULL REFERENCES lfhe.report_candidate_pool(id),
  candidate_type    lfhe.report_candidate_type NOT NULL,
  object_id         uuid NOT NULL,
  object_hash       text NOT NULL,
  section           lfhe.report_section NOT NULL,
  priority          integer NOT NULL,
  decision_id       uuid NOT NULL REFERENCES lfhe.report_selection_decisions(id),
  PRIMARY KEY (selection_set_id, candidate_id)
);

DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['report_section_targets', 'reports', 'report_candidate_pool', 'report_selection_decisions',
                           'report_selection_sets', 'report_selection_set_items'] LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON lfhe.%I FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation()',
                   t || '_immutable', t);
  END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- Candidate eligibility (as of the report's mode / cutoff)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.report_object_hash(p_type lfhe.report_candidate_type, p_id uuid)
RETURNS text LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT CASE p_type
    WHEN 'ASSESSMENT_VERSION' THEN (SELECT content_hash FROM lfhe.assessment_versions WHERE id = p_id)
    WHEN 'INDICATOR_VERSION' THEN (SELECT content_hash FROM lfhe.indicator_versions WHERE id = p_id)
    WHEN 'TREND_VERSION' THEN (SELECT content_hash FROM lfhe.trend_versions WHERE id = p_id) END
$$;

-- an eligible candidate is the as-of current version of its object and maps to >= 1 approved
-- assessment statement (no statement = nothing M09 may use)
CREATE OR REPLACE FUNCTION lfhe.report_candidate_eligible(p_type lfhe.report_candidate_type, p_id uuid,
                                                         p_mode text, p_cutoff timestamptz)
RETURNS boolean LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_trend uuid;
  v_ind   uuid;
BEGIN
  IF p_type = 'ASSESSMENT_VERSION' THEN
    RETURN lfhe.assessment_version_approved_asof(p_id, p_mode, p_cutoff);
  ELSIF p_type = 'INDICATOR_VERSION' THEN
    SELECT indicator_id INTO v_ind FROM lfhe.indicator_versions WHERE id = p_id;
    RETURN v_ind IS NOT NULL AND lfhe.indicator_version_usable(p_id, p_mode, p_cutoff)
       AND NOT EXISTS (SELECT 1 FROM lfhe.indicator_versions x WHERE x.indicator_id = v_ind
                       AND x.version_no > (SELECT version_no FROM lfhe.indicator_versions WHERE id = p_id)
                       AND lfhe.indicator_version_usable(x.id, p_mode, p_cutoff));
  ELSE
    SELECT trend_id INTO v_trend FROM lfhe.trend_versions WHERE id = p_id;
    RETURN v_trend IS NOT NULL AND lfhe.trend_asof(v_trend, p_mode, p_cutoff) = p_id
       AND EXISTS (SELECT 1 FROM lfhe.trend_version_assessments a WHERE a.trend_version_id = p_id);
  END IF;
END $$;

-- the approved assessment statements a candidate contributes (M09 statement pool)
CREATE OR REPLACE FUNCTION lfhe.report_candidate_statements(p_type lfhe.report_candidate_type, p_id uuid)
RETURNS TABLE (assessment_version_id uuid, statement_id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT s.assessment_version_id, s.id FROM lfhe.assessment_statements s
  WHERE p_type = 'ASSESSMENT_VERSION' AND s.assessment_version_id = p_id
  UNION
  SELECT s.assessment_version_id, s.id FROM lfhe.indicator_versions v
  JOIN lfhe.assessment_statements s ON s.assessment_version_id = v.assessment_version_id
   AND s.id IN (SELECT (x)::uuid FROM pg_catalog.jsonb_array_elements_text(v.content -> 'related_statement_ids') x)
  WHERE p_type = 'INDICATOR_VERSION' AND v.id = p_id
  UNION
  SELECT s.assessment_version_id, s.id FROM lfhe.trend_version_assessments a
  JOIN lfhe.assessment_statements s ON s.assessment_version_id = a.assessment_version_id
  WHERE p_type = 'TREND_VERSION' AND a.trend_version_id = p_id
$$;

CREATE OR REPLACE FUNCTION lfhe.p5_require_report(p_report uuid)
RETURNS lfhe.reports LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  r lfhe.reports;
BEGIN
  SELECT * INTO r FROM lfhe.reports WHERE id = p_report;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'unknown report %', p_report USING ERRCODE = 'no_data_found';
  END IF;
  RETURN r;
END $$;

-- ---------------------------------------------------------------------------
-- HUMAN_ONLY (REPORT_EDIT)
-- ---------------------------------------------------------------------------
-- p: {code, title, cycle_label, report_mode, information_cutoff}
CREATE OR REPLACE FUNCTION lfhe.create_report(p jsonb, p_reason text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('REPORT_EDIT');
  v_id    uuid;
BEGIN
  IF p_reason IS NULL OR length(btrim(p_reason)) < 5 THEN
    RAISE EXCEPTION 'a reason is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  IF (p ->> 'information_cutoff') IS NULL OR (p ->> 'report_mode') NOT IN ('LIVE', 'REPLAY') THEN
    RAISE EXCEPTION 'REPORT_MODE_AND_CUTOFF_REQUIRED' USING ERRCODE = 'check_violation';
  END IF;
  INSERT INTO lfhe.reports (code, title, cycle_label, report_mode, information_cutoff, created_by)
  VALUES (p ->> 'code', p ->> 'title', p ->> 'cycle_label', (p ->> 'report_mode')::lfhe.report_mode,
          (p ->> 'information_cutoff')::timestamptz, v_actor)
  RETURNING id INTO v_id;
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.create_report(jsonb, text) IS 'HUMAN_ONLY';

-- deterministic refresh: adds every eligible, as-of current Phase 4 object not yet in the pool.
-- Nothing is ever removed from the pool; inclusion is a separate human decision.
CREATE OR REPLACE FUNCTION lfhe.refresh_report_candidates(p_report uuid)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('REPORT_EDIT');
  r       lfhe.reports := lfhe.p5_require_report(p_report);
  v_n     integer := 0;
  c       record;
BEGIN
  PERFORM 1 FROM lfhe.reports WHERE id = r.id FOR UPDATE;
  FOR c IN
    SELECT 'ASSESSMENT_VERSION'::lfhe.report_candidate_type AS t, v.id, v.content_hash AS h,
           'KEY_JUDGMENT'::lfhe.report_section AS sec,
           (SELECT rr.priority_score FROM lfhe.relevance_results rr WHERE rr.event_version_id = v.event_version_id
            ORDER BY rr.created_at DESC, rr.id LIMIT 1) AS rank
    FROM lfhe.assessment_versions v
    WHERE lfhe.report_candidate_eligible('ASSESSMENT_VERSION', v.id, r.report_mode::text, r.information_cutoff)
    UNION ALL
    SELECT 'INDICATOR_VERSION', v.id, v.content_hash, 'INDICATOR_WARNING', NULL
    FROM lfhe.indicator_versions v
    WHERE lfhe.report_candidate_eligible('INDICATOR_VERSION', v.id, r.report_mode::text, r.information_cutoff)
    UNION ALL
    SELECT 'TREND_VERSION', v.id, v.content_hash, 'TREND_WATCH', NULL
    FROM lfhe.trend_versions v
    WHERE lfhe.report_candidate_eligible('TREND_VERSION', v.id, r.report_mode::text, r.information_cutoff)
  LOOP
    INSERT INTO lfhe.report_candidate_pool (report_id, candidate_type, object_id, object_hash, recommended_section,
                                           recommended_rank)
    VALUES (r.id, c.t, c.id, c.h, c.sec, c.rank)
    ON CONFLICT (report_id, candidate_type, object_id) DO NOTHING;
    IF FOUND THEN
      v_n := v_n + 1;
    END IF;
  END LOOP;
  RETURN v_n;
END $$;
COMMENT ON FUNCTION lfhe.refresh_report_candidates(uuid) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.report_candidate_latest_decision(p_candidate uuid)
RETURNS lfhe.report_selection_decisions LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT * FROM lfhe.report_selection_decisions WHERE candidate_id = p_candidate ORDER BY seq DESC LIMIT 1
$$;

CREATE OR REPLACE FUNCTION lfhe.decide_report_candidate(p_candidate uuid, p_object_hash text, p_decision text,
                                                       p_section lfhe.report_section, p_priority integer,
                                                       p_expected_previous_decision uuid, p_reason text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('REPORT_EDIT');
  c       lfhe.report_candidate_pool;
  r       lfhe.reports;
  v_prev  lfhe.report_selection_decisions;
  v_id    uuid;
BEGIN
  SELECT * INTO c FROM lfhe.report_candidate_pool WHERE id = p_candidate;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'unknown report candidate %', p_candidate USING ERRCODE = 'no_data_found';
  END IF;
  PERFORM 1 FROM lfhe.reports WHERE id = c.report_id FOR UPDATE;
  r := lfhe.p5_require_report(c.report_id);
  IF c.object_hash IS DISTINCT FROM p_object_hash
     OR lfhe.report_object_hash(c.candidate_type, c.object_id) IS DISTINCT FROM p_object_hash THEN
    RAISE EXCEPTION 'VERSION_HASH_MISMATCH: report candidate %', p_candidate USING ERRCODE = 'serialization_failure';
  END IF;
  v_prev := lfhe.report_candidate_latest_decision(c.id);
  IF v_prev.id IS DISTINCT FROM p_expected_previous_decision THEN
    RAISE EXCEPTION 'SELECTION_STALE: a newer decision exists for candidate %', p_candidate USING ERRCODE = 'serialization_failure';
  END IF;
  IF p_decision = 'INCLUDE' THEN
    IF NOT lfhe.report_candidate_eligible(c.candidate_type, c.object_id, r.report_mode::text, r.information_cutoff) THEN
      RAISE EXCEPTION 'CANDIDATE_NOT_ELIGIBLE: % % is not the as-of current approved version', c.candidate_type, c.object_id
        USING ERRCODE = 'check_violation';
    END IF;
    IF NOT (c.candidate_type = 'ASSESSMENT_VERSION' AND p_section IN ('KEY_JUDGMENT', 'SIGNIFICANT_DEVELOPMENT', 'INDICATOR_WARNING', 'WHAT_TO_WATCH')
            OR c.candidate_type = 'INDICATOR_VERSION' AND p_section IN ('INDICATOR_WARNING', 'WHAT_TO_WATCH')
            OR c.candidate_type = 'TREND_VERSION' AND p_section = 'TREND_WATCH') THEN
      RAISE EXCEPTION 'SECTION_NOT_ALLOWED_FOR_CANDIDATE: % → %', c.candidate_type, p_section USING ERRCODE = 'check_violation';
    END IF;
  ELSIF p_section IS NOT NULL OR p_priority IS NOT NULL THEN
    RAISE EXCEPTION 'section / priority apply to INCLUDE only' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  INSERT INTO lfhe.report_selection_decisions (report_id, candidate_id, candidate_object_hash, decision, section, priority,
    previous_decision_id, actor_user_id, reason)
  VALUES (c.report_id, c.id, c.object_hash, p_decision, p_section, p_priority, v_prev.id, v_actor, p_reason)
  RETURNING id INTO v_id;
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.decide_report_candidate(uuid, text, text, lfhe.report_section, integer, uuid, text) IS 'HUMAN_ONLY';

-- freeze the current human inclusion decisions into an immutable selection set and request M09
CREATE OR REPLACE FUNCTION lfhe.freeze_report_selection(p_report uuid, p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('REPORT_EDIT');
  r       lfhe.reports := lfhe.p5_require_report(p_report);
  v_items jsonb;
  v_bad   text;
  v_no    integer;
  v_content jsonb;
  v_id    uuid;
  v_hash  text;
BEGIN
  PERFORM 1 FROM lfhe.reports WHERE id = r.id FOR UPDATE;
  SELECT pg_catalog.string_agg(c.candidate_type::text || ':' || c.object_id::text, ', ') INTO v_bad
  FROM lfhe.report_candidate_pool c
  WHERE c.report_id = r.id AND (lfhe.report_candidate_latest_decision(c.id)).decision = 'INCLUDE'
    AND NOT lfhe.report_candidate_eligible(c.candidate_type, c.object_id, r.report_mode::text, r.information_cutoff);
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION 'CANDIDATE_NOT_ELIGIBLE: %', v_bad USING ERRCODE = 'check_violation';
  END IF;
  SELECT coalesce(pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
           'candidate_id', c.id, 'candidate_type', c.candidate_type, 'object_id', c.object_id, 'object_hash', c.object_hash,
           'section', d.section, 'priority', d.priority, 'decision_id', d.id)
         ORDER BY d.section, d.priority, c.id), '[]')
  INTO v_items
  FROM lfhe.report_candidate_pool c, LATERAL lfhe.report_candidate_latest_decision(c.id) d
  WHERE c.report_id = r.id AND d.decision = 'INCLUDE';
  IF pg_catalog.jsonb_array_length(v_items) = 0 THEN
    RAISE EXCEPTION 'SELECTION_EMPTY: include at least one candidate' USING ERRCODE = 'check_violation';
  END IF;
  SELECT coalesce(max(set_no), 0) + 1 INTO v_no FROM lfhe.report_selection_sets WHERE report_id = r.id;
  v_content := pg_catalog.jsonb_build_object('format', 'lfhe-report-selection/1', 'report_id', r.id, 'set_no', v_no,
    'report_mode', r.report_mode, 'information_cutoff', lfhe.p5_ts(r.information_cutoff), 'items', v_items);
  v_hash := lfhe.jcs_sha256(v_content);
  INSERT INTO lfhe.report_selection_sets (report_id, set_no, content, content_hash, created_by, reason)
  VALUES (r.id, v_no, v_content, v_hash, v_actor, p_reason) RETURNING id INTO v_id;
  INSERT INTO lfhe.report_selection_set_items (selection_set_id, candidate_id, candidate_type, object_id, object_hash,
    section, priority, decision_id)
  SELECT v_id, (i ->> 'candidate_id')::uuid, (i ->> 'candidate_type')::lfhe.report_candidate_type, (i ->> 'object_id')::uuid,
         i ->> 'object_hash', (i ->> 'section')::lfhe.report_section, (i ->> 'priority')::integer, (i ->> 'decision_id')::uuid
  FROM pg_catalog.jsonb_array_elements(v_items) i;
  PERFORM lfhe.enqueue_job('EDIT_REPORT', 'report_selection_set', v_id::text, 'EDIT_REPORT:' || v_id,
    pg_catalog.jsonb_build_object('selection_set_hash', v_hash), 100::smallint, 3);
  RETURN pg_catalog.jsonb_build_object('selection_set_id', v_id, 'content_hash', v_hash);
END $$;
COMMENT ON FUNCTION lfhe.freeze_report_selection(uuid, text) IS 'HUMAN_ONLY';

-- worker-side: the statement pool of a frozen selection set
CREATE OR REPLACE FUNCTION lfhe.report_selection_statements(p_set uuid)
RETURNS TABLE (candidate_id uuid, candidate_type lfhe.report_candidate_type, section lfhe.report_section,
               assessment_version_id uuid, statement_id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT i.candidate_id, i.candidate_type, i.section, s.assessment_version_id, s.statement_id
  FROM lfhe.report_selection_set_items i, LATERAL lfhe.report_candidate_statements(i.candidate_type, i.object_id) s
  WHERE i.selection_set_id = p_set
$$;

-- ---------------------------------------------------------------------------
-- Views
-- ---------------------------------------------------------------------------
CREATE VIEW lfhe.report_candidate_state WITH (security_invoker = true) AS
SELECT c.id AS candidate_id, c.report_id, c.candidate_type, c.object_id, c.object_hash, c.recommended_section,
       c.recommended_rank, c.created_at,
       d.id AS latest_decision_id, d.decision AS latest_decision, d.section AS selected_section, d.priority AS selected_priority,
       d.actor_user_id AS decided_by, d.created_at AS decided_at
FROM lfhe.report_candidate_pool c
LEFT JOIN LATERAL (SELECT * FROM lfhe.report_selection_decisions x WHERE x.candidate_id = c.id ORDER BY x.seq DESC LIMIT 1) d ON true;

-- ---------------------------------------------------------------------------
-- Audit
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.audit_p5_objects()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_doc   jsonb := pg_catalog.to_jsonb(NEW);
  v_event text := TG_ARGV[0];
BEGIN
  IF TG_TABLE_NAME = 'report_selection_decisions' THEN
    v_event := CASE v_doc ->> 'decision' WHEN 'INCLUDE' THEN 'REPORT_CANDIDATE_SELECTED'
                 WHEN 'EXCLUDE' THEN 'REPORT_CANDIDATE_REMOVED' ELSE 'REPORT_CANDIDATE_RETURNED_FOR_REVISION' END;
  END IF;
  PERFORM lfhe.write_audit(v_event, TG_ARGV[1], v_doc ->> TG_ARGV[2], NULL, v_doc - 'content' - 'canonical_json',
    pg_catalog.jsonb_build_object('content_hash', coalesce(v_doc ->> 'content_hash', v_doc ->> 'report_version_hash')));
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION lfhe.audit_p5_objects() FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;

CREATE TRIGGER reports_audit AFTER INSERT ON lfhe.reports
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_p5_objects('REPORT_CREATED', 'report', 'id');
CREATE TRIGGER report_candidate_pool_audit AFTER INSERT ON lfhe.report_candidate_pool
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_p5_objects('REPORT_CANDIDATE_ADDED', 'report_candidate', 'id');
CREATE TRIGGER report_selection_decisions_audit AFTER INSERT ON lfhe.report_selection_decisions
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_p5_objects('', 'report_candidate', 'candidate_id');
CREATE TRIGGER report_selection_sets_audit AFTER INSERT ON lfhe.report_selection_sets
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_p5_objects('REPORT_SELECTION_FROZEN', 'report_selection_set', 'id');

-- ---------------------------------------------------------------------------
-- Jobs
-- ---------------------------------------------------------------------------
ALTER TABLE lfhe.processing_jobs DROP CONSTRAINT processing_jobs_job_type_check;
ALTER TABLE lfhe.processing_jobs ADD CONSTRAINT processing_jobs_job_type_check
  CHECK (job_type IN ('COLLECT_SOURCE', 'EXTRACT_CLAIMS', 'CLASSIFY_CLAIMS', 'ANALYSE_LINEAGE', 'BUILD_EVENTS',
                      'ASSESS_RELEVANCE', 'ASSESS_EVENT', 'CHALLENGE_ASSESSMENT', 'EDIT_REPORT', 'RENDER_REPORT'));

-- ---------------------------------------------------------------------------
-- Grants / RLS
-- ---------------------------------------------------------------------------
REVOKE ALL ON FUNCTION lfhe.jcs(jsonb), lfhe.jcs_sha256(jsonb), lfhe.p5_ts(timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION lfhe.jcs(jsonb), lfhe.jcs_sha256(jsonb), lfhe.p5_ts(timestamptz) TO authenticated, lfhe_worker;
REVOKE ALL ON FUNCTION lfhe.create_report(jsonb, text), lfhe.refresh_report_candidates(uuid),
  lfhe.decide_report_candidate(uuid, text, text, lfhe.report_section, integer, uuid, text),
  lfhe.freeze_report_selection(uuid, text)
  FROM PUBLIC, anon, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.create_report(jsonb, text), lfhe.refresh_report_candidates(uuid),
  lfhe.decide_report_candidate(uuid, text, text, lfhe.report_section, integer, uuid, text),
  lfhe.freeze_report_selection(uuid, text) TO authenticated;
REVOKE ALL ON FUNCTION lfhe.report_object_hash(lfhe.report_candidate_type, uuid),
  lfhe.report_candidate_eligible(lfhe.report_candidate_type, uuid, text, timestamptz),
  lfhe.report_candidate_statements(lfhe.report_candidate_type, uuid), lfhe.p5_require_report(uuid),
  lfhe.report_candidate_latest_decision(uuid), lfhe.report_selection_statements(uuid)
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.report_object_hash(lfhe.report_candidate_type, uuid),
  lfhe.report_candidate_eligible(lfhe.report_candidate_type, uuid, text, timestamptz),
  lfhe.report_candidate_statements(lfhe.report_candidate_type, uuid), lfhe.report_selection_statements(uuid)
  TO lfhe_worker;

REVOKE ALL ON lfhe.report_section_targets, lfhe.reports, lfhe.report_candidate_pool, lfhe.report_selection_decisions,
  lfhe.report_selection_sets, lfhe.report_selection_set_items, lfhe.report_candidate_state
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT SELECT ON lfhe.report_section_targets, lfhe.reports, lfhe.report_candidate_pool, lfhe.report_selection_decisions,
  lfhe.report_selection_sets, lfhe.report_selection_set_items, lfhe.report_candidate_state TO authenticated, lfhe_worker;
DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['report_section_targets', 'reports', 'report_candidate_pool', 'report_selection_decisions',
                           'report_selection_sets', 'report_selection_set_items'] LOOP
    EXECUTE format('ALTER TABLE lfhe.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY %I ON lfhe.%I FOR SELECT TO authenticated USING (lfhe.has_permission(''CLAIM_READ''))',
                   t || '_read_human', t);
    EXECUTE format('CREATE POLICY %I ON lfhe.%I FOR SELECT TO lfhe_worker USING (true)', t || '_read_worker', t);
  END LOOP;
END $$;
