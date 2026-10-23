-- LFHÉ Phase 7 (P7-01) — pilot data model & instrumentation (measurement only).
-- Baseline: docs/specs/LFHE_Phase7_Authoritative_Baseline_v1.0.md §4, §8–§12, §17, §19–§23, §24 P7-01, §25.
--
-- * Every object here is PILOT MEASUREMENT, prefixed pilot_ and marked in its comment. Nothing here is
--   analytical evidence (§19): no Phase 1–6 table, function, trigger or view is changed, and no pilot
--   function writes anything outside the pilot_* tables (and the audit log for low-volume human
--   pilot decisions, §21). Analytical / QA / approval / release state is only READ.
-- * Pilot cycles bind to the exact LFHÉ objects they measure (a report, its exact model runs). The
--   pilot mode and cutoff of a cycle are copied from — and must equal — the bound report (§7, test 3).
-- * Analyst time exists only as server-clock timer segments started / stopped by the analyst
--   (clock_timestamp()); no API accepts a typed-in duration or timestamp, so active time is never
--   inferred retrospectively (PO authorisation, "Pilot measurement priority"). ended_at >= started_at.
-- * Cost assumptions and provider prices are explicit, versioned, immutable inputs; none is seeded
--   (§11, test 11). Capacity value is computed elsewhere from these inputs; cash savings are separate
--   evidence records and are never derived from capacity value (§11, test 13).
-- * Benchmark labels are evaluator-only (PILOT_EVALUATE / lfhe_evaluator); the worker cannot read them
--   and no envelope builder references them (§23, test 9). A label is human-authored truth of an
--   allowed kind; model or deterministic findings can never be recorded as benchmark truth (§22, test 10).
-- * Missing measurements are reported, never filled: pilot_cycle_missing_metrics() lists what is
--   absent and pilot_complete_cycle() fails closed while anything is missing (§8, test 7).

INSERT INTO lfhe.audit_event_types (code, spec_source) VALUES
  ('PILOT_CYCLE_CREATED', 'Phase 7 §24 P7-01'),
  ('PILOT_CYCLE_REPORT_BOUND', 'Phase 7 §24 P7-01'),
  ('PILOT_CYCLE_CLOSED', 'Phase 7 §8, §27'),
  ('PILOT_COMPARATOR_RECORDED', 'Phase 7 §9'),
  ('PILOT_COST_ASSUMPTION_RECORDED', 'Phase 7 §11'),
  ('PILOT_PROVIDER_PRICE_RECORDED', 'Phase 7 §10 E'),
  ('PILOT_CASH_EVIDENCE_RECORDED', 'Phase 7 §11'),
  ('PILOT_UX_FINDING_RECORDED', 'Phase 7 §17'),
  ('PILOT_UX_FINDING_DISPOSED', 'Phase 7 §17'),
  ('PILOT_BENCHMARK_RECORDED', 'Phase 7 §23, P7-05'),
  ('PILOT_BENCHMARK_LABEL_RECORDED', 'Phase 7 §22, §23')
ON CONFLICT (code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- RBAC (additive): pilot participation / management / evaluation; no analytical authority.
-- ---------------------------------------------------------------------------
INSERT INTO lfhe.roles (code, description) VALUES
  ('PILOT_LEAD', 'Phase 7 pilot management and benchmark evaluation (measurement only; no analytical, QA, approval, security or release authority)')
ON CONFLICT (code) DO NOTHING;
INSERT INTO lfhe.permissions (code, description, phase_introduced) VALUES
  ('PILOT_READ',        'Read pilot measurement records (Phase 7)', 7),
  ('PILOT_PARTICIPATE', 'Record own pilot timing, workload and UX observations (Phase 7)', 7),
  ('PILOT_MANAGE',      'Create / bind / close pilot cycles; record comparators, cost assumptions, prices, cash evidence; dispose UX findings (Phase 7)', 7),
  ('PILOT_EVALUATE',    'Record and read benchmark labels (evaluator-only, Phase 7)', 7)
ON CONFLICT (code) DO NOTHING;
INSERT INTO lfhe.role_permissions (role_code, permission_code) VALUES
  ('PILOT_LEAD', 'PILOT_READ'), ('PILOT_LEAD', 'PILOT_PARTICIPATE'), ('PILOT_LEAD', 'PILOT_MANAGE'), ('PILOT_LEAD', 'PILOT_EVALUATE'),
  ('PILOT_LEAD', 'SOURCE_READ'), ('PILOT_LEAD', 'ARTICLE_READ'), ('PILOT_LEAD', 'CLAIM_READ'), ('PILOT_LEAD', 'SYSTEM_READ'),
  ('ANALYST', 'PILOT_READ'), ('ANALYST', 'PILOT_PARTICIPATE'),
  ('REVIEWER', 'PILOT_READ'), ('REVIEWER', 'PILOT_PARTICIPATE'),
  ('SECURITY_REVIEWER', 'PILOT_READ'), ('SECURITY_REVIEWER', 'PILOT_PARTICIPATE'),
  ('RELEASE_AUTHORITY', 'PILOT_READ'), ('RELEASE_AUTHORITY', 'PILOT_PARTICIPATE'),
  ('ADMIN', 'PILOT_READ')
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- Closed vocabularies
-- ---------------------------------------------------------------------------
CREATE TYPE lfhe.pilot_comparator_method AS ENUM (
  'PRIOR_DOCUMENTED_MANUAL_WORKFLOW', 'MATCHED_MANUAL_CONTROL', 'MATCHED_HISTORICAL_CYCLE',
  'CONTROLLED_ANALYST_BENCHMARK', 'EQUIVALENT_TASK_WITHOUT_LFHE', 'NONE');
CREATE TYPE lfhe.pilot_stage AS ENUM (
  'SOURCE_REVIEW', 'CLAIM_REVIEW', 'EVENT_REVIEW', 'ASSESSMENT_REVIEW', 'REPORT_SELECTION', 'REPORT_EDIT',
  'QA_RESOLUTION', 'WARNING_HANDLING', 'CONTENT_APPROVAL', 'SECURITY_REVIEW', 'RELEASE', 'PROVENANCE_INSPECTION',
  'CORRECTION', 'OTHER');
CREATE TYPE lfhe.pilot_ux_area AS ENUM (
  'SOURCE_REVIEW', 'CLAIM_REVIEW', 'EVENT_ASSESSMENT', 'REPORT_WORKSPACE', 'QA_VIEW', 'WARNING_HANDLING',
  'CONTENT_APPROVAL', 'SECURITY_REVIEW', 'RELEASE', 'RELEASED_PROVENANCE', 'PILOT_WORKSPACE', 'OTHER');
CREATE TYPE lfhe.pilot_ux_severity AS ENUM ('BLOCKING', 'MAJOR', 'MINOR', 'ENHANCEMENT');
CREATE TYPE lfhe.pilot_finding_class AS ENUM (
  'MEASUREMENT', 'USABILITY_DEFECT', 'SOFTWARE_DEFECT', 'ANALYTICAL_DEFECT', 'MODEL_PERFORMANCE_LIMITATION',
  'CONFIGURATION_PROBLEM', 'FEATURE_REQUEST', 'FUTURE_CAPABILITY_OPPORTUNITY');
CREATE TYPE lfhe.pilot_label_kind AS ENUM (
  'OBSERVED_TRUTH', 'ANALYST_JUDGEMENT', 'BENCHMARK_LABEL', 'SEEDED_SYNTHETIC_ERROR', 'MODEL_FINDING',
  'DETERMINISTIC_FINDING', 'HUMAN_CORRECTION', 'PILOT_INTERPRETATION');
CREATE TYPE lfhe.pilot_cash_category AS ENUM (
  'AVOIDED_OVERTIME', 'AVOIDED_CONTRACTOR_EXPENDITURE', 'AVOIDED_FUTURE_HIRING', 'REDUCED_EXTERNAL_RESEARCH_COST',
  'ACTUAL_CASH_SAVING');

-- ---------------------------------------------------------------------------
-- Explicit configuration inputs (immutable, versioned; nothing seeded)
-- ---------------------------------------------------------------------------
CREATE TABLE lfhe.pilot_cost_assumptions (
  id                      uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  code                    text NOT NULL UNIQUE CHECK (code ~ '^COST-[A-Z0-9][A-Z0-9_-]{1,40}$'),
  currency                text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
  loaded_hourly_cost      numeric(12, 2) NOT NULL CHECK (loaded_hourly_cost > 0),
  weekly_work_hours       numeric(5, 2) NOT NULL CHECK (weekly_work_hours > 0 AND weekly_work_hours <= 80),
  working_weeks_per_year  numeric(4, 1) NOT NULL CHECK (working_weeks_per_year > 0 AND working_weeks_per_year <= 52),
  basis                   text NOT NULL CHECK (length(btrim(basis)) >= 10),
  created_by              uuid NOT NULL,
  created_at              timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE lfhe.pilot_cost_assumptions IS 'PILOT MEASUREMENT (Phase 7 §11): explicit analysis input, never a universal value';

CREATE TABLE lfhe.pilot_provider_prices (
  id                     uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  provider               text NOT NULL,
  model                  text NOT NULL,
  currency               text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
  input_cost_per_mtok    numeric(12, 4) NOT NULL CHECK (input_cost_per_mtok >= 0),
  output_cost_per_mtok   numeric(12, 4) NOT NULL CHECK (output_cost_per_mtok >= 0),
  effective_from         timestamptz NOT NULL,
  source                 text NOT NULL CHECK (length(btrim(source)) >= 5),
  created_by             uuid NOT NULL,
  created_at             timestamptz NOT NULL DEFAULT now(),
  UNIQUE (provider, model, effective_from)
);
COMMENT ON TABLE lfhe.pilot_provider_prices IS 'PILOT MEASUREMENT (Phase 7 §10 E): explicit price input; a run without a matching price has unknown cost, never zero';

-- ---------------------------------------------------------------------------
-- Pilot cycles and the exact objects they measure
-- ---------------------------------------------------------------------------
CREATE TABLE lfhe.pilot_cycles (
  id                   uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  code                 text NOT NULL UNIQUE CHECK (code ~ '^P7C-[A-Z0-9][A-Z0-9_-]{1,40}$'),
  pilot_mode           lfhe.report_mode NOT NULL,
  information_cutoff   timestamptz NOT NULL,
  input_scope          text NOT NULL CHECK (length(btrim(input_scope)) >= 10),
  data_boundary        text NOT NULL CHECK (data_boundary IN ('PUBLIC_OSINT', 'SYNTHETIC', 'AUTHORISED_PUBLIC_REPLAY')),
  analyst_user_id      uuid NOT NULL,
  provider_setup       text NOT NULL CHECK (length(btrim(provider_setup)) >= 3),
  report_id            uuid UNIQUE REFERENCES lfhe.reports(id),
  status               text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'COMPLETED', 'STOPPED')),
  terminal_state       text,
  stop_reason          text,
  closure_note         text,
  created_by           uuid NOT NULL,
  started_at           timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  closed_at            timestamptz,
  closed_by            uuid,
  CHECK ((status = 'OPEN') = (closed_at IS NULL AND closed_by IS NULL)),
  CHECK ((status = 'COMPLETED') = (terminal_state IS NOT NULL)),
  CHECK ((status = 'STOPPED') = (stop_reason IS NOT NULL)),
  CHECK (closed_at IS NULL OR closed_at >= started_at),
  CHECK (pilot_mode = 'REPLAY' OR data_boundary <> 'AUTHORISED_PUBLIC_REPLAY')
);
COMMENT ON TABLE lfhe.pilot_cycles IS 'PILOT MEASUREMENT (Phase 7 §8): one end-to-end pilot cycle; not analytical evidence';

CREATE TABLE lfhe.pilot_cycle_model_runs (
  cycle_id      uuid NOT NULL REFERENCES lfhe.pilot_cycles(id),
  model_run_id  uuid NOT NULL REFERENCES lfhe.model_runs(id),
  binding       text NOT NULL CHECK (binding IN ('REPORT_CHAIN', 'TRIAL')),
  bound_by      uuid NOT NULL,
  bound_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (cycle_id, model_run_id)
);
COMMENT ON TABLE lfhe.pilot_cycle_model_runs IS 'PILOT MEASUREMENT (Phase 7 §10 E, test 8): provider metrics bind to an exact model_run';

CREATE TABLE lfhe.pilot_comparators (
  id                       uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  cycle_id                 uuid NOT NULL UNIQUE REFERENCES lfhe.pilot_cycles(id),
  method                   lfhe.pilot_comparator_method NOT NULL,
  baseline_analyst_seconds integer CHECK (baseline_analyst_seconds > 0),
  baseline_basis           text CHECK (baseline_basis IN ('TIMED_MEASUREMENT', 'DOCUMENTED_RECORD', 'NONE')),
  comparable_scope         boolean NOT NULL,
  reference                text NOT NULL CHECK (length(btrim(reference)) >= 5),
  recorded_by              uuid NOT NULL,
  recorded_at              timestamptz NOT NULL DEFAULT now(),
  CHECK ((method = 'NONE') = (baseline_analyst_seconds IS NULL)),
  CHECK ((baseline_analyst_seconds IS NULL) = (baseline_basis IS NULL OR baseline_basis = 'NONE'))
);
COMMENT ON TABLE lfhe.pilot_comparators IS 'PILOT MEASUREMENT (Phase 7 §9): comparison method recorded with every result';

CREATE TABLE lfhe.pilot_timing_segments (
  id          uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  cycle_id    uuid NOT NULL REFERENCES lfhe.pilot_cycles(id),
  user_id     uuid NOT NULL,
  stage       lfhe.pilot_stage NOT NULL,
  started_at  timestamptz NOT NULL,
  ended_at    timestamptz,
  end_reason  text CHECK (end_reason IN ('STOPPED', 'STAGE_SWITCH', 'CYCLE_CLOSED')),
  CHECK (ended_at IS NULL OR ended_at >= started_at),
  CHECK ((ended_at IS NULL) = (end_reason IS NULL))
);
CREATE UNIQUE INDEX pilot_timing_one_open ON lfhe.pilot_timing_segments (cycle_id, user_id) WHERE ended_at IS NULL;
COMMENT ON TABLE lfhe.pilot_timing_segments IS 'PILOT MEASUREMENT (Phase 7 §10 A): server-clock active-time segments; not audited (§21 telemetry)';

CREATE TABLE lfhe.pilot_workload_ratings (
  cycle_id     uuid NOT NULL REFERENCES lfhe.pilot_cycles(id),
  user_id      uuid NOT NULL,
  instrument   text NOT NULL CHECK (instrument = 'NASA_TLX_RAW'),
  mental       smallint NOT NULL CHECK (mental BETWEEN 0 AND 100),
  physical     smallint NOT NULL CHECK (physical BETWEEN 0 AND 100),
  temporal     smallint NOT NULL CHECK (temporal BETWEEN 0 AND 100),
  performance  smallint NOT NULL CHECK (performance BETWEEN 0 AND 100),
  effort       smallint NOT NULL CHECK (effort BETWEEN 0 AND 100),
  frustration  smallint NOT NULL CHECK (frustration BETWEEN 0 AND 100),
  note         text,
  recorded_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (cycle_id, user_id)
);
COMMENT ON TABLE lfhe.pilot_workload_ratings IS 'PILOT MEASUREMENT (Phase 7 §10 F): analyst subjective workload (raw TLX, 0–100)';

CREATE TABLE lfhe.pilot_ux_findings (
  id            uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  finding_no    bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
  cycle_id      uuid REFERENCES lfhe.pilot_cycles(id),
  area          lfhe.pilot_ux_area NOT NULL,
  severity      lfhe.pilot_ux_severity NOT NULL,
  finding_class lfhe.pilot_finding_class NOT NULL,
  title         text NOT NULL CHECK (length(btrim(title)) BETWEEN 5 AND 200),
  description   text NOT NULL CHECK (length(btrim(description)) >= 10),
  route         text CHECK (route IS NULL OR route ~ '^/[A-Za-z0-9/_\[\]-]*$'),
  recorded_by   uuid NOT NULL,
  observed_at   timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE lfhe.pilot_ux_findings IS 'PILOT MEASUREMENT (Phase 7 §4, §17): evidence first; never an implementation requirement by itself';

CREATE TABLE lfhe.pilot_ux_finding_dispositions (
  seq          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  finding_id   uuid NOT NULL REFERENCES lfhe.pilot_ux_findings(id),
  disposition  text NOT NULL CHECK (disposition IN ('RESOLVED', 'PATH_DECLARED_UNUSABLE', 'BACKLOG', 'NOT_A_DEFECT', 'REOPENED')),
  note         text NOT NULL CHECK (length(btrim(note)) >= 5),
  decided_by   uuid NOT NULL,
  decided_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE lfhe.pilot_cash_evidence (
  id          uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  cycle_id    uuid REFERENCES lfhe.pilot_cycles(id),
  period_start date NOT NULL,
  period_end   date NOT NULL CHECK (period_end >= period_start),
  category    lfhe.pilot_cash_category NOT NULL,
  amount      numeric(14, 2) NOT NULL CHECK (amount >= 0),
  currency    text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
  evidence    text NOT NULL CHECK (length(btrim(evidence)) >= 10),
  recorded_by uuid NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE lfhe.pilot_cash_evidence IS 'PILOT MEASUREMENT (Phase 7 §11): documented cash effects; never derived from capacity value';

-- ---------------------------------------------------------------------------
-- Benchmark (evaluator-only labels)
-- ---------------------------------------------------------------------------
CREATE TABLE lfhe.pilot_benchmarks (
  id           uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  code         text NOT NULL UNIQUE CHECK (code ~ '^P7-BM-[A-Z0-9][A-Z0-9_-]{0,40}$'),
  description  text NOT NULL CHECK (length(btrim(description)) >= 10),
  material     text NOT NULL CHECK (material IN ('SYNTHETIC', 'AUTHORISED_PUBLIC_REPLAY')),
  created_by   uuid NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE lfhe.pilot_benchmark_cases (
  id                   uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  benchmark_id         uuid NOT NULL REFERENCES lfhe.pilot_benchmarks(id),
  case_code            text NOT NULL CHECK (case_code ~ '^[A-Z0-9][A-Z0-9_-]{1,40}$'),
  report_version_id    uuid NOT NULL,
  report_version_hash  text NOT NULL,
  created_by           uuid NOT NULL,
  created_at           timestamptz NOT NULL DEFAULT now(),
  UNIQUE (benchmark_id, case_code),
  UNIQUE (benchmark_id, report_version_id),
  FOREIGN KEY (report_version_id, report_version_hash) REFERENCES lfhe.report_versions (id, report_version_hash)
);
CREATE TABLE lfhe.pilot_benchmark_labels (
  id                     uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  case_id                uuid NOT NULL REFERENCES lfhe.pilot_benchmark_cases(id),
  label_kind             lfhe.pilot_label_kind NOT NULL
                           CHECK (label_kind IN ('BENCHMARK_LABEL', 'SEEDED_SYNTHETIC_ERROR', 'OBSERVED_TRUTH', 'ANALYST_JUDGEMENT')),
  expected_layer         text NOT NULL CHECK (expected_layer IN ('D', 'S')),
  expected_check_id      text NOT NULL,
  expected_finding_code  text CHECK (expected_finding_code IS NULL OR expected_finding_code ~ '^[A-Z][A-Z0-9_]{2,60}$'),
  critical               boolean NOT NULL,
  note                   text NOT NULL CHECK (length(btrim(note)) >= 5),
  created_by             uuid NOT NULL,
  created_at             timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (expected_check_id, expected_layer) REFERENCES lfhe.qa_checks (check_id, layer)
);
COMMENT ON TABLE lfhe.pilot_benchmark_labels IS 'PILOT MEASUREMENT (Phase 7 §22–§23): evaluator-only benchmark truth, human-authored; never model input; model output is never truth';

-- immutability of measurement inputs / records (corrections are new rows)
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['pilot_cost_assumptions', 'pilot_provider_prices', 'pilot_cycle_model_runs', 'pilot_comparators',
                           'pilot_workload_ratings', 'pilot_ux_findings', 'pilot_ux_finding_dispositions', 'pilot_cash_evidence',
                           'pilot_benchmarks', 'pilot_benchmark_cases', 'pilot_benchmark_labels'] LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON lfhe.%I FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation()',
                   t || '_immutable', t);
  END LOOP;
END $$;

-- cycles: identity is immutable; a closed cycle never changes; segments only ever close, once.
CREATE OR REPLACE FUNCTION lfhe.pilot_cycles_guard()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'pilot cycles are never deleted' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF OLD.status <> 'OPEN' THEN
    RAISE EXCEPTION 'pilot cycle % is closed and immutable', OLD.code USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF (NEW.id, NEW.code, NEW.pilot_mode, NEW.information_cutoff, NEW.input_scope, NEW.data_boundary, NEW.analyst_user_id,
      NEW.provider_setup, NEW.created_by, NEW.started_at)
     IS DISTINCT FROM
     (OLD.id, OLD.code, OLD.pilot_mode, OLD.information_cutoff, OLD.input_scope, OLD.data_boundary, OLD.analyst_user_id,
      OLD.provider_setup, OLD.created_by, OLD.started_at)
     OR (OLD.report_id IS NOT NULL AND NEW.report_id IS DISTINCT FROM OLD.report_id) THEN
    RAISE EXCEPTION 'pilot cycle identity fields are immutable' USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER pilot_cycles_guard BEFORE UPDATE OR DELETE ON lfhe.pilot_cycles
  FOR EACH ROW EXECUTE FUNCTION lfhe.pilot_cycles_guard();

CREATE OR REPLACE FUNCTION lfhe.pilot_timing_guard()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'timing segments are never deleted' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF OLD.ended_at IS NOT NULL OR (NEW.id, NEW.cycle_id, NEW.user_id, NEW.stage, NEW.started_at)
       IS DISTINCT FROM (OLD.id, OLD.cycle_id, OLD.user_id, OLD.stage, OLD.started_at) THEN
    RAISE EXCEPTION 'a timing segment can only be closed, once' USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER pilot_timing_guard BEFORE UPDATE OR DELETE ON lfhe.pilot_timing_segments
  FOR EACH ROW EXECUTE FUNCTION lfhe.pilot_timing_guard();
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['pilot_cycles', 'pilot_timing_segments', 'pilot_cost_assumptions', 'pilot_provider_prices',
                           'pilot_cycle_model_runs', 'pilot_comparators', 'pilot_workload_ratings', 'pilot_ux_findings',
                           'pilot_ux_finding_dispositions', 'pilot_cash_evidence', 'pilot_benchmarks', 'pilot_benchmark_cases',
                           'pilot_benchmark_labels'] LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE TRUNCATE ON lfhe.%I FOR EACH STATEMENT EXECUTE FUNCTION lfhe.block_mutation()',
                   t || '_no_truncate', t);
  END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- Derived measurement (read-only over authoritative records)
-- ---------------------------------------------------------------------------
-- The exact model runs of a report's analytical chain: M09 report versions, M07 assessment versions
-- pinned / cited by any version of the report, M08 challenge runs on those, M10-S QA runs, plus the
-- failed originals of any repair run (repair_of_model_run_id) so provider failures stay visible.
CREATE OR REPLACE FUNCTION lfhe.pilot_report_chain_model_runs(p_report uuid)
RETURNS uuid[] LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  WITH av AS (
    SELECT i.pinned_assessment_version_id AS id FROM lfhe.report_items i
      JOIN lfhe.report_versions v ON v.id = i.report_version_id
     WHERE v.report_id = p_report AND i.pinned_assessment_version_id IS NOT NULL
    UNION
    SELECT s.assessment_version_id FROM lfhe.report_statement_sources s
      JOIN lfhe.report_item_statements st ON st.id = s.report_item_statement_id
      JOIN lfhe.report_items i ON i.id = st.report_item_id
      JOIN lfhe.report_versions v ON v.id = i.report_version_id
     WHERE v.report_id = p_report
  ), direct AS (
    SELECT v.created_by_model_run_id AS id FROM lfhe.report_versions v
     WHERE v.report_id = p_report AND v.created_by_model_run_id IS NOT NULL
    UNION SELECT a.created_by_model_run_id FROM lfhe.assessment_versions a JOIN av ON av.id = a.id
     WHERE a.created_by_model_run_id IS NOT NULL
    UNION SELECT c.model_run_id FROM lfhe.challenge_runs c JOIN av ON av.id = c.assessment_version_id
    UNION SELECT q.model_run_id FROM lfhe.qa_runs q WHERE q.report_id = p_report AND q.model_run_id IS NOT NULL
  ), repairs AS (
    SELECT r.repair_of_model_run_id AS id FROM lfhe.assessment_ingestion_results r JOIN direct d ON d.id = r.model_run_id
     WHERE r.repair_of_model_run_id IS NOT NULL
    UNION SELECT r.repair_of_model_run_id FROM lfhe.challenge_ingestion_results r JOIN direct d ON d.id = r.model_run_id
     WHERE r.repair_of_model_run_id IS NOT NULL
    UNION SELECT r.repair_of_model_run_id FROM lfhe.report_edit_ingestion_results r JOIN direct d ON d.id = r.model_run_id
     WHERE r.repair_of_model_run_id IS NOT NULL
    UNION SELECT q.repair_of_model_run_id FROM lfhe.qa_runs q JOIN direct d ON d.id = q.model_run_id
     WHERE q.repair_of_model_run_id IS NOT NULL
  )
  SELECT coalesce(array_agg(id ORDER BY id::text), '{}') FROM (SELECT id FROM direct UNION SELECT id FROM repairs) x
$$;

CREATE VIEW lfhe.pilot_model_run_metrics WITH (security_invoker = true) AS
SELECT b.cycle_id, b.binding, r.id AS model_run_id, r.module_code, r.provider, r.model, r.model_configuration_id,
       r.model_config_hash, mc.settings AS model_settings, r.prompt_version_id, r.prompt_semver, r.prompt_content_hash,
       r.environment, r.status::text AS status, r.error_code, r.started_at, r.completed_at,
       CASE WHEN r.completed_at IS NOT NULL
            THEN round(extract(epoch FROM (r.completed_at - r.started_at)) * 1000)::bigint END AS latency_ms,
       CASE WHEN jsonb_typeof(r.usage -> 'input_tokens') = 'number' THEN (r.usage ->> 'input_tokens')::bigint END AS input_tokens,
       CASE WHEN jsonb_typeof(r.usage -> 'output_tokens') = 'number' THEN (r.usage ->> 'output_tokens')::bigint END AS output_tokens,
       rep.repair_of_model_run_id,
       (rep.repair_of_model_run_id IS NOT NULL) AS is_repair_run,
       p.id AS price_id, p.currency AS cost_currency,
       CASE WHEN p.id IS NOT NULL AND jsonb_typeof(r.usage -> 'input_tokens') = 'number'
                 AND jsonb_typeof(r.usage -> 'output_tokens') = 'number'
            THEN round(((r.usage ->> 'input_tokens')::numeric * p.input_cost_per_mtok
                      + (r.usage ->> 'output_tokens')::numeric * p.output_cost_per_mtok) / 1000000, 6) END AS model_cost
FROM lfhe.pilot_cycle_model_runs b
JOIN lfhe.model_runs r ON r.id = b.model_run_id
JOIN lfhe.model_configurations mc ON mc.id = r.model_configuration_id
LEFT JOIN LATERAL (
  SELECT x.repair_of_model_run_id FROM (
    SELECT repair_of_model_run_id FROM lfhe.assessment_ingestion_results WHERE model_run_id = r.id
    UNION ALL SELECT repair_of_model_run_id FROM lfhe.challenge_ingestion_results WHERE model_run_id = r.id
    UNION ALL SELECT repair_of_model_run_id FROM lfhe.report_edit_ingestion_results WHERE model_run_id = r.id
    UNION ALL SELECT repair_of_model_run_id FROM lfhe.qa_runs WHERE model_run_id = r.id) x
  WHERE x.repair_of_model_run_id IS NOT NULL LIMIT 1) rep ON true
LEFT JOIN LATERAL (
  SELECT * FROM lfhe.pilot_provider_prices pp
   WHERE pp.provider = r.provider AND pp.model = r.model AND pp.effective_from <= r.started_at
   ORDER BY pp.effective_from DESC LIMIT 1) p ON true;
COMMENT ON VIEW lfhe.pilot_model_run_metrics IS 'PILOT MEASUREMENT (Phase 7 §10 E): provider metrics of the exact bound model runs; cost NULL = unknown';

CREATE VIEW lfhe.pilot_cycle_timing WITH (security_invoker = true) AS
SELECT s.cycle_id, s.stage, s.user_id, count(*) AS segments,
       count(*) FILTER (WHERE s.ended_at IS NULL) AS open_segments,
       coalesce(sum(extract(epoch FROM (s.ended_at - s.started_at))) FILTER (WHERE s.ended_at IS NOT NULL), 0)::numeric(14, 3)
         AS active_seconds
FROM lfhe.pilot_timing_segments s GROUP BY s.cycle_id, s.stage, s.user_id;

-- the latest-version workflow state of the bound report (read from the Phase 6 derived view)
CREATE OR REPLACE FUNCTION lfhe.pilot_report_workflow_state(p_report uuid)
RETURNS text LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT w.workflow_state FROM lfhe.report_version_workflow w
   WHERE w.report_id = p_report AND w.is_latest LIMIT 1
$$;

CREATE OR REPLACE FUNCTION lfhe.pilot_terminal_states()
RETURNS text[] LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
  SELECT ARRAY['RELEASED', 'RELEASE_REJECTED', 'SECURITY_REJECTED', 'CONTENT_REJECTED']
$$;

-- what a cycle still lacks; empty = complete measurement (§8). Never fills anything in.
CREATE OR REPLACE FUNCTION lfhe.pilot_cycle_missing_metrics(p_cycle uuid)
RETURNS text[] LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  c      lfhe.pilot_cycles;
  v_out  text[] := '{}';
  v_state text;
BEGIN
  SELECT * INTO c FROM lfhe.pilot_cycles WHERE id = p_cycle;
  IF NOT FOUND THEN
    RETURN ARRAY['CYCLE_UNKNOWN'];
  END IF;
  IF c.report_id IS NULL THEN
    v_out := v_out || 'REPORT_NOT_BOUND'::text;
  ELSE
    v_state := lfhe.pilot_report_workflow_state(c.report_id);
    IF v_state IS NULL OR NOT (v_state = ANY (lfhe.pilot_terminal_states())) THEN
      v_out := v_out || ('REPORT_NOT_AT_TERMINAL_STATE:' || coalesce(v_state, 'NO_VERSION'));
    END IF;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM lfhe.pilot_timing_segments s WHERE s.cycle_id = c.id AND s.user_id = c.analyst_user_id
                  AND s.ended_at IS NOT NULL) THEN
    v_out := v_out || 'ANALYST_TIMING_MISSING'::text;
  END IF;
  IF EXISTS (SELECT 1 FROM lfhe.pilot_timing_segments s WHERE s.cycle_id = c.id AND s.ended_at IS NULL) THEN
    v_out := v_out || 'TIMING_SEGMENT_OPEN'::text;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM lfhe.pilot_comparators x WHERE x.cycle_id = c.id) THEN
    v_out := v_out || 'COMPARATOR_METHOD_NOT_RECORDED'::text;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM lfhe.pilot_workload_ratings w WHERE w.cycle_id = c.id AND w.user_id = c.analyst_user_id) THEN
    v_out := v_out || 'ANALYST_WORKLOAD_MISSING'::text;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM lfhe.pilot_cycle_model_runs b WHERE b.cycle_id = c.id) THEN
    v_out := v_out || 'MODEL_RUNS_NOT_BOUND'::text;
  ELSIF c.report_id IS NOT NULL AND EXISTS (
      SELECT 1 FROM unnest(lfhe.pilot_report_chain_model_runs(c.report_id)) r(id)
       WHERE NOT EXISTS (SELECT 1 FROM lfhe.pilot_cycle_model_runs b WHERE b.cycle_id = c.id AND b.model_run_id = r.id)) THEN
    v_out := v_out || 'REPORT_CHAIN_MODEL_RUNS_NOT_BOUND'::text;
  END IF;
  IF EXISTS (SELECT 1 FROM lfhe.pilot_ux_findings f WHERE f.cycle_id = c.id AND f.severity = 'BLOCKING'
              AND coalesce((SELECT d.disposition FROM lfhe.pilot_ux_finding_dispositions d WHERE d.finding_id = f.id
                            ORDER BY d.seq DESC LIMIT 1), 'OPEN') IN ('OPEN', 'REOPENED', 'BACKLOG')) THEN
    v_out := v_out || 'BLOCKING_UX_FINDING_OPEN'::text;
  END IF;
  RETURN v_out;
END $$;

-- ---------------------------------------------------------------------------
-- HUMAN_ONLY pilot functions (write pilot_* only)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.pilot_create_cycle(p jsonb)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('PILOT_MANAGE');
  v_id    uuid;
  v_analyst uuid := (p ->> 'analyst_user_id')::uuid;
BEGIN
  IF v_analyst IS NULL OR NOT lfhe.user_has_permission(v_analyst, 'PILOT_PARTICIPATE') THEN
    RAISE EXCEPTION 'PILOT_ANALYST_INVALID: the cycle analyst must hold PILOT_PARTICIPATE' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  INSERT INTO lfhe.pilot_cycles (code, pilot_mode, information_cutoff, input_scope, data_boundary, analyst_user_id,
                                 provider_setup, created_by)
  VALUES (p ->> 'code', (p ->> 'pilot_mode')::lfhe.report_mode, (p ->> 'information_cutoff')::timestamptz, p ->> 'input_scope',
          p ->> 'data_boundary', v_analyst, p ->> 'provider_setup', v_actor)
  RETURNING id INTO v_id;
  PERFORM lfhe.write_audit('PILOT_CYCLE_CREATED', 'pilot_cycle', v_id::text, NULL,
    pg_catalog.jsonb_build_object('code', p ->> 'code', 'pilot_mode', p ->> 'pilot_mode', 'information_cutoff', p ->> 'information_cutoff',
                                  'data_boundary', p ->> 'data_boundary', 'analyst_user_id', v_analyst), '{}');
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.pilot_create_cycle(jsonb) IS 'HUMAN_ONLY';

-- bind the cycle's report: mode and cutoff must equal the report's (cutoff semantics preserved, §7)
CREATE OR REPLACE FUNCTION lfhe.pilot_bind_report(p_cycle uuid, p_report uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('PILOT_MANAGE');
  c lfhe.pilot_cycles;
  r lfhe.reports;
BEGIN
  SELECT * INTO c FROM lfhe.pilot_cycles WHERE id = p_cycle FOR UPDATE;
  IF NOT FOUND OR c.status <> 'OPEN' THEN
    RAISE EXCEPTION 'PILOT_CYCLE_NOT_OPEN: %', p_cycle USING ERRCODE = 'check_violation';
  END IF;
  IF c.report_id IS NOT NULL THEN
    RAISE EXCEPTION 'PILOT_REPORT_ALREADY_BOUND' USING ERRCODE = 'unique_violation';
  END IF;
  SELECT * INTO r FROM lfhe.reports WHERE id = p_report;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'PILOT_REPORT_UNKNOWN: %', p_report USING ERRCODE = 'foreign_key_violation';
  END IF;
  IF r.report_mode <> c.pilot_mode OR r.information_cutoff <> c.information_cutoff THEN
    RAISE EXCEPTION 'PILOT_MODE_OR_CUTOFF_MISMATCH: cycle %/% vs report %/%', c.pilot_mode, c.information_cutoff,
      r.report_mode, r.information_cutoff USING ERRCODE = 'check_violation';
  END IF;
  UPDATE lfhe.pilot_cycles SET report_id = r.id WHERE id = c.id;
  PERFORM lfhe.write_audit('PILOT_CYCLE_REPORT_BOUND', 'pilot_cycle', c.id::text, NULL,
    pg_catalog.jsonb_build_object('report_id', r.id, 'report_code', r.code), '{}');
  RETURN pg_catalog.jsonb_build_object('cycle_id', c.id, 'report_id', r.id);
END $$;
COMMENT ON FUNCTION lfhe.pilot_bind_report(uuid, uuid) IS 'HUMAN_ONLY';

-- bind the exact model runs of the report chain (REPORT_CHAIN) or a named trial run (TRIAL)
CREATE OR REPLACE FUNCTION lfhe.pilot_bind_model_runs(p_cycle uuid, p_runs uuid[], p_binding text)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('PILOT_MANAGE');
  c lfhe.pilot_cycles;
  v_runs uuid[];
  v_n integer;
BEGIN
  SELECT * INTO c FROM lfhe.pilot_cycles WHERE id = p_cycle;
  IF NOT FOUND OR c.status <> 'OPEN' THEN
    RAISE EXCEPTION 'PILOT_CYCLE_NOT_OPEN: %', p_cycle USING ERRCODE = 'check_violation';
  END IF;
  IF p_binding = 'REPORT_CHAIN' THEN
    IF c.report_id IS NULL THEN
      RAISE EXCEPTION 'PILOT_REPORT_NOT_BOUND' USING ERRCODE = 'check_violation';
    END IF;
    v_runs := lfhe.pilot_report_chain_model_runs(c.report_id);
  ELSIF p_binding = 'TRIAL' THEN
    v_runs := coalesce(p_runs, '{}');
    IF EXISTS (SELECT 1 FROM unnest(v_runs) u(id) WHERE NOT EXISTS (SELECT 1 FROM lfhe.model_runs m WHERE m.id = u.id)) THEN
      RAISE EXCEPTION 'PILOT_MODEL_RUN_UNKNOWN' USING ERRCODE = 'foreign_key_violation';
    END IF;
  ELSE
    RAISE EXCEPTION 'PILOT_BINDING_UNKNOWN: %', p_binding USING ERRCODE = 'invalid_parameter_value';
  END IF;
  INSERT INTO lfhe.pilot_cycle_model_runs (cycle_id, model_run_id, binding, bound_by)
  SELECT c.id, u.id, p_binding, v_actor FROM unnest(v_runs) u(id)
  ON CONFLICT (cycle_id, model_run_id) DO NOTHING;
  GET DIAGNOSTICS v_n = ROW_COUNT;
  RETURN v_n;
END $$;
COMMENT ON FUNCTION lfhe.pilot_bind_model_runs(uuid, uuid[], text) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.pilot_record_comparator(p_cycle uuid, p jsonb)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('PILOT_MANAGE');
  v_id uuid;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM lfhe.pilot_cycles WHERE id = p_cycle AND status = 'OPEN') THEN
    RAISE EXCEPTION 'PILOT_CYCLE_NOT_OPEN: %', p_cycle USING ERRCODE = 'check_violation';
  END IF;
  INSERT INTO lfhe.pilot_comparators (cycle_id, method, baseline_analyst_seconds, baseline_basis, comparable_scope, reference, recorded_by)
  VALUES (p_cycle, (p ->> 'method')::lfhe.pilot_comparator_method, (p ->> 'baseline_analyst_seconds')::integer,
          p ->> 'baseline_basis', (p ->> 'comparable_scope')::boolean, p ->> 'reference', v_actor)
  RETURNING id INTO v_id;
  PERFORM lfhe.write_audit('PILOT_COMPARATOR_RECORDED', 'pilot_cycle', p_cycle::text, NULL,
    pg_catalog.jsonb_build_object('comparator_id', v_id) || (p - 'reference'), '{}');
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.pilot_record_comparator(uuid, jsonb) IS 'HUMAN_ONLY';

-- timers: server clock only; one open segment per analyst per cycle; starting a new stage closes the open one
CREATE OR REPLACE FUNCTION lfhe.pilot_start_timer(p_cycle uuid, p_stage text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('PILOT_PARTICIPATE');
  v_now timestamptz := pg_catalog.clock_timestamp();
  v_id uuid;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM lfhe.pilot_cycles WHERE id = p_cycle AND status = 'OPEN') THEN
    RAISE EXCEPTION 'PILOT_CYCLE_NOT_OPEN: %', p_cycle USING ERRCODE = 'check_violation';
  END IF;
  UPDATE lfhe.pilot_timing_segments SET ended_at = v_now, end_reason = 'STAGE_SWITCH'
   WHERE cycle_id = p_cycle AND user_id = v_actor AND ended_at IS NULL;
  INSERT INTO lfhe.pilot_timing_segments (cycle_id, user_id, stage, started_at)
  VALUES (p_cycle, v_actor, p_stage::lfhe.pilot_stage, v_now) RETURNING id INTO v_id;
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.pilot_start_timer(uuid, text) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.pilot_stop_timer(p_cycle uuid)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('PILOT_PARTICIPATE');
  v_n integer;
BEGIN
  UPDATE lfhe.pilot_timing_segments SET ended_at = pg_catalog.clock_timestamp(), end_reason = 'STOPPED'
   WHERE cycle_id = p_cycle AND user_id = v_actor AND ended_at IS NULL;
  GET DIAGNOSTICS v_n = ROW_COUNT;
  RETURN v_n;
END $$;
COMMENT ON FUNCTION lfhe.pilot_stop_timer(uuid) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.pilot_record_workload(p_cycle uuid, p jsonb)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('PILOT_PARTICIPATE');
BEGIN
  IF NOT EXISTS (SELECT 1 FROM lfhe.pilot_cycles WHERE id = p_cycle AND status = 'OPEN') THEN
    RAISE EXCEPTION 'PILOT_CYCLE_NOT_OPEN: %', p_cycle USING ERRCODE = 'check_violation';
  END IF;
  INSERT INTO lfhe.pilot_workload_ratings (cycle_id, user_id, instrument, mental, physical, temporal, performance, effort,
                                           frustration, note)
  VALUES (p_cycle, v_actor, 'NASA_TLX_RAW', (p ->> 'mental')::smallint, (p ->> 'physical')::smallint,
          (p ->> 'temporal')::smallint, (p ->> 'performance')::smallint, (p ->> 'effort')::smallint,
          (p ->> 'frustration')::smallint, p ->> 'note');
END $$;
COMMENT ON FUNCTION lfhe.pilot_record_workload(uuid, jsonb) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.pilot_record_ux_finding(p jsonb)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('PILOT_PARTICIPATE');
  v_id uuid;
BEGIN
  IF p ? 'cycle_id' AND NOT EXISTS (SELECT 1 FROM lfhe.pilot_cycles WHERE id = (p ->> 'cycle_id')::uuid) THEN
    RAISE EXCEPTION 'PILOT_CYCLE_UNKNOWN' USING ERRCODE = 'foreign_key_violation';
  END IF;
  INSERT INTO lfhe.pilot_ux_findings (cycle_id, area, severity, finding_class, title, description, route, recorded_by)
  VALUES ((p ->> 'cycle_id')::uuid, (p ->> 'area')::lfhe.pilot_ux_area, (p ->> 'severity')::lfhe.pilot_ux_severity,
          (p ->> 'finding_class')::lfhe.pilot_finding_class, p ->> 'title', p ->> 'description', p ->> 'route', v_actor)
  RETURNING id INTO v_id;
  PERFORM lfhe.write_audit('PILOT_UX_FINDING_RECORDED', 'pilot_ux_finding', v_id::text, NULL,
    pg_catalog.jsonb_build_object('cycle_id', p ->> 'cycle_id', 'area', p ->> 'area', 'severity', p ->> 'severity',
                                  'finding_class', p ->> 'finding_class'), '{}');
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.pilot_record_ux_finding(jsonb) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.pilot_dispose_ux_finding(p_finding uuid, p_disposition text, p_note text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('PILOT_MANAGE');
BEGIN
  IF NOT EXISTS (SELECT 1 FROM lfhe.pilot_ux_findings WHERE id = p_finding) THEN
    RAISE EXCEPTION 'PILOT_UX_FINDING_UNKNOWN' USING ERRCODE = 'foreign_key_violation';
  END IF;
  INSERT INTO lfhe.pilot_ux_finding_dispositions (finding_id, disposition, note, decided_by)
  VALUES (p_finding, p_disposition, p_note, v_actor);
  PERFORM lfhe.write_audit('PILOT_UX_FINDING_DISPOSED', 'pilot_ux_finding', p_finding::text, NULL,
    pg_catalog.jsonb_build_object('disposition', p_disposition, 'note', p_note), '{}');
END $$;
COMMENT ON FUNCTION lfhe.pilot_dispose_ux_finding(uuid, text, text) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.pilot_record_cost_assumption(p jsonb)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('PILOT_MANAGE');
  v_id uuid;
BEGIN
  INSERT INTO lfhe.pilot_cost_assumptions (code, currency, loaded_hourly_cost, weekly_work_hours, working_weeks_per_year, basis, created_by)
  VALUES (p ->> 'code', p ->> 'currency', (p ->> 'loaded_hourly_cost')::numeric, (p ->> 'weekly_work_hours')::numeric,
          (p ->> 'working_weeks_per_year')::numeric, p ->> 'basis', v_actor)
  RETURNING id INTO v_id;
  PERFORM lfhe.write_audit('PILOT_COST_ASSUMPTION_RECORDED', 'pilot_cost_assumption', v_id::text, NULL, p, '{}');
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.pilot_record_cost_assumption(jsonb) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.pilot_record_provider_price(p jsonb)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('PILOT_MANAGE');
  v_id uuid;
BEGIN
  INSERT INTO lfhe.pilot_provider_prices (provider, model, currency, input_cost_per_mtok, output_cost_per_mtok, effective_from,
                                          source, created_by)
  VALUES (p ->> 'provider', p ->> 'model', p ->> 'currency', (p ->> 'input_cost_per_mtok')::numeric,
          (p ->> 'output_cost_per_mtok')::numeric, (p ->> 'effective_from')::timestamptz, p ->> 'source', v_actor)
  RETURNING id INTO v_id;
  PERFORM lfhe.write_audit('PILOT_PROVIDER_PRICE_RECORDED', 'pilot_provider_price', v_id::text, NULL, p, '{}');
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.pilot_record_provider_price(jsonb) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.pilot_record_cash_evidence(p jsonb)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('PILOT_MANAGE');
  v_id uuid;
BEGIN
  INSERT INTO lfhe.pilot_cash_evidence (cycle_id, period_start, period_end, category, amount, currency, evidence, recorded_by)
  VALUES ((p ->> 'cycle_id')::uuid, (p ->> 'period_start')::date, (p ->> 'period_end')::date,
          (p ->> 'category')::lfhe.pilot_cash_category, (p ->> 'amount')::numeric, p ->> 'currency', p ->> 'evidence', v_actor)
  RETURNING id INTO v_id;
  PERFORM lfhe.write_audit('PILOT_CASH_EVIDENCE_RECORDED', 'pilot_cash_evidence', v_id::text, NULL, p - 'evidence', '{}');
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.pilot_record_cash_evidence(jsonb) IS 'HUMAN_ONLY';

-- close a cycle: COMPLETED only when nothing is missing (fail closed); STOPPED records why (§8, §27)
CREATE OR REPLACE FUNCTION lfhe.pilot_close_cycle(p_cycle uuid, p_outcome text, p_note text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('PILOT_MANAGE');
  c lfhe.pilot_cycles;
  v_missing text[];
  v_state text;
  v_now timestamptz := pg_catalog.clock_timestamp();
BEGIN
  SELECT * INTO c FROM lfhe.pilot_cycles WHERE id = p_cycle FOR UPDATE;
  IF NOT FOUND OR c.status <> 'OPEN' THEN
    RAISE EXCEPTION 'PILOT_CYCLE_NOT_OPEN: %', p_cycle USING ERRCODE = 'check_violation';
  END IF;
  IF p_note IS NULL OR length(btrim(p_note)) < 10 THEN
    RAISE EXCEPTION 'a closure note (>= 10 characters) is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  IF p_outcome = 'COMPLETED' THEN
    v_missing := lfhe.pilot_cycle_missing_metrics(c.id);
    IF cardinality(v_missing) > 0 THEN
      RAISE EXCEPTION 'PILOT_MEASUREMENT_INCOMPLETE: %', array_to_string(v_missing, ', ') USING ERRCODE = 'check_violation';
    END IF;
    v_state := lfhe.pilot_report_workflow_state(c.report_id);
    UPDATE lfhe.pilot_cycles SET status = 'COMPLETED', terminal_state = v_state, closure_note = p_note,
                                 closed_at = v_now, closed_by = v_actor WHERE id = c.id;
  ELSIF p_outcome = 'STOPPED' THEN
    UPDATE lfhe.pilot_timing_segments SET ended_at = v_now, end_reason = 'CYCLE_CLOSED'
     WHERE cycle_id = c.id AND ended_at IS NULL;
    UPDATE lfhe.pilot_cycles SET status = 'STOPPED', stop_reason = p_note, closure_note = p_note,
                                 closed_at = v_now, closed_by = v_actor WHERE id = c.id;
  ELSE
    RAISE EXCEPTION 'PILOT_OUTCOME_UNKNOWN: %', p_outcome USING ERRCODE = 'invalid_parameter_value';
  END IF;
  PERFORM lfhe.write_audit('PILOT_CYCLE_CLOSED', 'pilot_cycle', c.id::text,
    pg_catalog.jsonb_build_object('status', 'OPEN'),
    pg_catalog.jsonb_build_object('status', p_outcome, 'terminal_state', v_state, 'note', p_note), '{}');
  RETURN pg_catalog.jsonb_build_object('cycle_id', c.id, 'status', p_outcome, 'terminal_state', v_state);
END $$;
COMMENT ON FUNCTION lfhe.pilot_close_cycle(uuid, text, text) IS 'HUMAN_ONLY';

-- benchmark (PILOT_EVALUATE): cases bind to exact report versions; labels are human-authored truth
CREATE OR REPLACE FUNCTION lfhe.pilot_record_benchmark(p jsonb)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('PILOT_EVALUATE');
  v_id uuid;
BEGIN
  INSERT INTO lfhe.pilot_benchmarks (code, description, material, created_by)
  VALUES (p ->> 'code', p ->> 'description', p ->> 'material', v_actor) RETURNING id INTO v_id;
  PERFORM lfhe.write_audit('PILOT_BENCHMARK_RECORDED', 'pilot_benchmark', v_id::text, NULL,
    pg_catalog.jsonb_build_object('code', p ->> 'code', 'material', p ->> 'material'), '{}');
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.pilot_record_benchmark(jsonb) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.pilot_record_benchmark_case(p_benchmark uuid, p_case_code text, p_version uuid, p_hash text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('PILOT_EVALUATE');
  v_id uuid;
BEGIN
  INSERT INTO lfhe.pilot_benchmark_cases (benchmark_id, case_code, report_version_id, report_version_hash, created_by)
  VALUES (p_benchmark, p_case_code, p_version, p_hash, v_actor) RETURNING id INTO v_id;
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.pilot_record_benchmark_case(uuid, text, uuid, text) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.pilot_record_benchmark_label(p_case uuid, p jsonb)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('PILOT_EVALUATE');
  v_kind text := p ->> 'label_kind';
  v_id uuid;
BEGIN
  IF v_kind IN ('MODEL_FINDING', 'DETERMINISTIC_FINDING', 'HUMAN_CORRECTION', 'PILOT_INTERPRETATION') THEN
    RAISE EXCEPTION 'PILOT_LABEL_KIND_NOT_TRUTH: % cannot be benchmark truth', v_kind USING ERRCODE = 'check_violation';
  END IF;
  IF p ? 'model_run_id' OR p ? 'qa_check_result_id' OR p ? 'finding_id' THEN
    RAISE EXCEPTION 'PILOT_LABEL_FROM_FINDING: a benchmark label cannot be derived from a recorded finding'
      USING ERRCODE = 'check_violation';
  END IF;
  INSERT INTO lfhe.pilot_benchmark_labels (case_id, label_kind, expected_layer, expected_check_id, expected_finding_code,
                                           critical, note, created_by)
  VALUES (p_case, v_kind::lfhe.pilot_label_kind, p ->> 'expected_layer', p ->> 'expected_check_id',
          p ->> 'expected_finding_code', (p ->> 'critical')::boolean, p ->> 'note', v_actor)
  RETURNING id INTO v_id;
  PERFORM lfhe.write_audit('PILOT_BENCHMARK_LABEL_RECORDED', 'pilot_benchmark_case', p_case::text, NULL,
    pg_catalog.jsonb_build_object('label_id', v_id), '{}');
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.pilot_record_benchmark_label(uuid, jsonb) IS 'HUMAN_ONLY';

-- per-label scoring against the latest QA result of each case version, D and S separately (§10 D).
-- A finding matches a label when layer and check_id agree (and the finding_code when the label names one)
-- and its status is WARNING or FAIL. Unmatched non-PASS findings are false positives.
CREATE OR REPLACE FUNCTION lfhe.pilot_benchmark_outcomes(p_benchmark uuid)
RETURNS TABLE (case_code text, layer text, kind text, check_id text, finding_code text, critical boolean,
               label_id uuid, finding_id uuid, qa_result_id uuid)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  IF lfhe.current_human_user() IS NOT NULL THEN
    PERFORM lfhe.require_human_permission('PILOT_EVALUATE');
  ELSIF NOT pg_catalog.pg_has_role(session_user, 'lfhe_evaluator', 'MEMBER') THEN
    RAISE EXCEPTION 'evaluator access required' USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN QUERY
  WITH cs AS (
    SELECT c.id, c.case_code, q.id AS qa_result_id, q.deterministic_qa_run_id AS d_run, q.semantic_qa_run_id AS s_run
      FROM lfhe.pilot_benchmark_cases c
      LEFT JOIN LATERAL (SELECT * FROM lfhe.qa_results x WHERE x.report_version_id = c.report_version_id
                          ORDER BY x.result_no DESC LIMIT 1) q ON true
     WHERE c.benchmark_id = p_benchmark
  ), f AS (
    SELECT cs.id AS case_id, r.id, r.layer, r.check_id, r.finding_code, r.severity
      FROM cs JOIN lfhe.qa_check_results r ON r.qa_run_id IN (cs.d_run, cs.s_run)
     WHERE r.status IN ('WARNING', 'FAIL')
  ), l AS (
    SELECT b.*, (SELECT f.id FROM f WHERE f.case_id = b.case_id AND f.layer = b.expected_layer AND f.check_id = b.expected_check_id
                   AND (b.expected_finding_code IS NULL OR f.finding_code = b.expected_finding_code)
                 ORDER BY f.id LIMIT 1) AS matched
      FROM lfhe.pilot_benchmark_labels b JOIN cs ON cs.id = b.case_id
  )
  SELECT cs.case_code, l.expected_layer, CASE WHEN l.matched IS NULL THEN 'FALSE_NEGATIVE' ELSE 'TRUE_POSITIVE' END,
         l.expected_check_id, l.expected_finding_code, l.critical, l.id, l.matched, cs.qa_result_id
    FROM l JOIN cs ON cs.id = l.case_id
  UNION ALL
  SELECT cs.case_code, f.layer, 'FALSE_POSITIVE', f.check_id, f.finding_code, false, NULL::uuid, f.id, cs.qa_result_id
    FROM f JOIN cs ON cs.id = f.case_id
   WHERE NOT EXISTS (SELECT 1 FROM l WHERE l.case_id = f.case_id AND l.matched = f.id)
     AND NOT EXISTS (SELECT 1 FROM lfhe.pilot_benchmark_labels b WHERE b.case_id = f.case_id AND b.expected_layer = f.layer
                       AND b.expected_check_id = f.check_id
                       AND (b.expected_finding_code IS NULL OR b.expected_finding_code = f.finding_code))
  UNION ALL
  SELECT cs.case_code, NULL, 'QA_RESULT_MISSING', NULL, NULL, false, NULL::uuid, NULL::uuid, NULL::uuid
    FROM cs WHERE cs.qa_result_id IS NULL
  ORDER BY 1, 2, 3, 4, 5;
END $$;

-- ---------------------------------------------------------------------------
-- Grants / RLS
-- ---------------------------------------------------------------------------
DO $$
DECLARE
  f text;
BEGIN
  FOREACH f IN ARRAY ARRAY['lfhe.pilot_create_cycle(jsonb)', 'lfhe.pilot_bind_report(uuid, uuid)',
                           'lfhe.pilot_bind_model_runs(uuid, uuid[], text)', 'lfhe.pilot_record_comparator(uuid, jsonb)',
                           'lfhe.pilot_start_timer(uuid, text)', 'lfhe.pilot_stop_timer(uuid)',
                           'lfhe.pilot_record_workload(uuid, jsonb)', 'lfhe.pilot_record_ux_finding(jsonb)',
                           'lfhe.pilot_dispose_ux_finding(uuid, text, text)', 'lfhe.pilot_record_cost_assumption(jsonb)',
                           'lfhe.pilot_record_provider_price(jsonb)', 'lfhe.pilot_record_cash_evidence(jsonb)',
                           'lfhe.pilot_close_cycle(uuid, text, text)', 'lfhe.pilot_record_benchmark(jsonb)',
                           'lfhe.pilot_record_benchmark_case(uuid, text, uuid, text)',
                           'lfhe.pilot_record_benchmark_label(uuid, jsonb)'] LOOP
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC, anon, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar', f);
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO authenticated', f);
  END LOOP;
END $$;
REVOKE ALL ON FUNCTION lfhe.pilot_report_chain_model_runs(uuid), lfhe.pilot_report_workflow_state(uuid),
  lfhe.pilot_cycle_missing_metrics(uuid)
  FROM PUBLIC, anon, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.pilot_report_chain_model_runs(uuid), lfhe.pilot_cycle_missing_metrics(uuid) TO authenticated;
REVOKE ALL ON FUNCTION lfhe.pilot_report_workflow_state(uuid) FROM authenticated;
REVOKE ALL ON FUNCTION lfhe.pilot_benchmark_outcomes(uuid) FROM PUBLIC, anon, service_role, lfhe_worker, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.pilot_benchmark_outcomes(uuid) TO authenticated, lfhe_evaluator;
REVOKE ALL ON FUNCTION lfhe.pilot_cycles_guard(), lfhe.pilot_timing_guard(), lfhe.pilot_terminal_states() FROM PUBLIC;

DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['pilot_cycles', 'pilot_timing_segments', 'pilot_cost_assumptions', 'pilot_provider_prices',
                           'pilot_cycle_model_runs', 'pilot_comparators', 'pilot_workload_ratings', 'pilot_ux_findings',
                           'pilot_ux_finding_dispositions', 'pilot_cash_evidence', 'pilot_benchmarks', 'pilot_benchmark_cases',
                           'pilot_benchmark_labels'] LOOP
    EXECUTE format('REVOKE ALL ON lfhe.%I FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar', t);
    EXECUTE format('ALTER TABLE lfhe.%I ENABLE ROW LEVEL SECURITY', t);
  END LOOP;
  -- measurement records: humans with PILOT_READ; never the worker (pilot data is not model input)
  FOREACH t IN ARRAY ARRAY['pilot_cycles', 'pilot_timing_segments', 'pilot_cost_assumptions', 'pilot_provider_prices',
                           'pilot_cycle_model_runs', 'pilot_comparators', 'pilot_workload_ratings', 'pilot_ux_findings',
                           'pilot_ux_finding_dispositions', 'pilot_cash_evidence', 'pilot_benchmarks'] LOOP
    EXECUTE format('GRANT SELECT ON lfhe.%I TO authenticated', t);
    EXECUTE format('CREATE POLICY %I ON lfhe.%I FOR SELECT TO authenticated USING (lfhe.has_permission(''PILOT_READ''))',
                   t || '_read_pilot', t);
  END LOOP;
  -- benchmark cases and labels: evaluator-only
  FOREACH t IN ARRAY ARRAY['pilot_benchmark_cases', 'pilot_benchmark_labels'] LOOP
    EXECUTE format('GRANT SELECT ON lfhe.%I TO authenticated, lfhe_evaluator', t);
    EXECUTE format('CREATE POLICY %I ON lfhe.%I FOR SELECT TO authenticated USING (lfhe.has_permission(''PILOT_EVALUATE''))',
                   t || '_read_evaluate', t);
    EXECUTE format('CREATE POLICY %I ON lfhe.%I FOR SELECT TO lfhe_evaluator USING (true)', t || '_read_evaluator', t);
  END LOOP;
END $$;
REVOKE ALL ON lfhe.pilot_model_run_metrics, lfhe.pilot_cycle_timing
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT SELECT ON lfhe.pilot_model_run_metrics, lfhe.pilot_cycle_timing TO authenticated;
