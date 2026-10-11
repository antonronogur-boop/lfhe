-- ============================================================================
-- P2-02  Claim pipeline schema (Phase 2 Addendum v1.0 §5–§13; CG0 §3/§5;
--        Module Prompt Pack v1.2 §5, §6, §11, §12)
--
-- Chain owned by Phase 2:
--   SOURCE → ORIGINAL-LANGUAGE ARTICLE_SNAPSHOT → TEXT_REPRESENTATION
--          → EXACT ORIGINAL-LANGUAGE EVIDENCE SPAN → CLAIM
--
-- * claims are immutable. A row can only exist if the DATABASE verified its
--   evidence_span_original against the immutable original-language
--   text_representation (QA-D18, lfhe.claim_grounding_problems). Otherwise:
--   CLAIM_NOT_GROUNDED_IN_ORIGINAL_SOURCE. Candidates that fail are recorded
--   in claim_extraction_rejections, never as claims.
-- * claim_status_history (append-only): UNVERIFIED at extraction; later
--   transitions by a human, or — for LOW-impact claims only — by an
--   owner-configured, audited automatic rule. HIGH-impact transitions are
--   human only; low→high after an automatic status ⇒ revalidation required.
-- * High impact is object specific (claim_id → high_impact + reasons).
-- * Human review uses the canonical review_decision enum, bound to the claim
--   id + claim hash + the expected previous review (stale decisions fail).
-- * Entities: mentions (original text) are separate from resolution.
--   Automatic resolution = exact normalised alias rule with a unique match;
--   otherwise UNRESOLVED / AMBIGUOUS. No similarity merging. Entities,
--   aliases (with an evidence/rule basis) and relationships are human-only.
-- * Taxonomy: closed, versioned, immutable items (v1.2 IDs); M03
--   assignments must name a supplied taxonomy item and a target claim that
--   was an input of the model run; anything else rejects the whole output.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Closed vocabularies
-- ---------------------------------------------------------------------------
CREATE TYPE lfhe.claim_type AS ENUM (
  'OBSERVATION', 'ANNOUNCEMENT', 'PROCUREMENT', 'DEPLOYMENT', 'OPERATION', 'LOSS',
  'CAPABILITY', 'TEST', 'DELIVERY', 'PRODUCTION', 'TRAINING', 'POLICY', 'DOCTRINE',
  'ORGANISATION', 'TECHNOLOGY', 'ASSESSMENT_BY_SOURCE', 'OTHER');
CREATE TYPE lfhe.claim_status AS ENUM (
  'UNVERIFIED', 'PARTIALLY_CORROBORATED', 'CORROBORATED', 'CONFIRMED_PRIMARY',
  'CONTESTED', 'DISPROVEN', 'SUPERSEDED');
CREATE TYPE lfhe.source_statement_status AS ENUM (
  'FACT_REPORTED_BY_SOURCE', 'SOURCE_ASSESSMENT', 'SOURCE_EXPECTATION',
  'SOURCE_CLAIM_UNVERIFIED', 'DIRECT_OBSERVATION_REPORTED', 'UNKNOWN');
-- Implementation choices (reported as specification deviations for PO confirmation):
CREATE TYPE lfhe.evidence_directness AS ENUM ('DIRECT', 'INDIRECT', 'UNKNOWN');
CREATE TYPE lfhe.evidence_type AS ENUM (
  'OFFICIAL_STATEMENT', 'COMPANY_STATEMENT', 'MEDIA_REPORT', 'EXPERT_COMMENTARY',
  'DOCUMENT_OR_DATA', 'IMAGERY_DESCRIPTION', 'OTHER', 'UNKNOWN');
CREATE TYPE lfhe.entity_type AS ENUM (
  'ORGANISATION', 'PERSON', 'COUNTRY', 'LOCATION', 'MILITARY_UNIT', 'SYSTEM', 'OTHER');
CREATE TYPE lfhe.entity_resolution_status AS ENUM ('RESOLVED', 'UNRESOLVED', 'AMBIGUOUS');
CREATE TYPE lfhe.assignment_confidence AS ENUM ('HIGH', 'MODERATE', 'LOW');
CREATE TYPE lfhe.taxonomy_type AS ENUM ('TOPIC', 'TAG', 'PIR', 'GEO');
CREATE TYPE lfhe.high_impact_reason AS ENUM (
  'SUPPORTS_APPROVED_ASSESSMENT', 'SUPPORTS_REPORT_CANDIDATE', 'SUPPORTS_KEY_JUDGMENT_CANDIDATE',
  'SUPPORTS_SIGNIFICANT_DEVELOPMENT', 'MAY_CHANGE_ANALYTIC_CONFIDENCE', 'MAY_CHANGE_TREND',
  'MAY_CHANGE_INDICATOR', 'SUPPORTS_HIGH_PRIORITY_EVENT', 'SUPPORTS_CRITICAL_PRIORITY_EVENT',
  'KEY_NUMERICAL_ASSERTION', 'KEY_CAPABILITY_ASSERTION', 'KEY_CAUSAL_ASSERTION',
  'HUMAN_MARKED_HIGH_IMPACT');

-- Review flags a claim may carry; every flag forces human_review_required.
CREATE OR REPLACE FUNCTION lfhe.claim_review_flags()
RETURNS text[] LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
  SELECT ARRAY[
    'TRANSLATION_MATERIAL_MISMATCH', 'SOURCE_LANGUAGE_INTERPRETATION_UNCERTAIN',
    'NORMALISATION_ACTOR_MISMATCH', 'NORMALISATION_ACTION_MISMATCH',
    'NORMALISATION_ATTRIBUTION_LOSS', 'NORMALISATION_UNCERTAINTY_LOSS',
    'NORMALISATION_MODALITY_LOSS', 'NORMALISATION_QUANTITY_MISMATCH',
    'NORMALISATION_UNIT_MISMATCH', 'NORMALISATION_TIME_MISMATCH',
    'NORMALISATION_LOCATION_MISMATCH', 'NORMALISATION_NEGATION_LOSS',
    'NORMALISATION_CONDITIONALITY_LOSS', 'NORMALISATION_SOURCE_ASSESSMENT_LOSS',
    'HIGH_IMPACT_POTENTIAL_CONTRADICTION', 'ENTITY_MENTION_NOT_IN_SOURCE',
    'MODEL_REQUESTED_HUMAN_REVIEW']::text[]
$$;
REVOKE ALL ON FUNCTION lfhe.claim_review_flags() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION lfhe.claim_review_flags() TO authenticated, lfhe_worker;

INSERT INTO lfhe.permissions (code, description, phase_introduced) VALUES
  ('CLAIM_READ',    'Read claims, evidence spans, entities and taxonomy assignments', 2),
  ('ENTITY_MANAGE', 'Create canonical entities, evidence-based aliases, relationships; link mentions', 2);
INSERT INTO lfhe.role_permissions (role_code, permission_code)
SELECT rp.role_code, 'CLAIM_READ' FROM lfhe.role_permissions rp WHERE rp.permission_code = 'ARTICLE_READ';
INSERT INTO lfhe.role_permissions (role_code, permission_code) VALUES ('ANALYST', 'ENTITY_MANAGE');

INSERT INTO lfhe.audit_event_types (code, spec_source) VALUES
  ('CLAIM_EXTRACTION_RECORDED', 'Phase 2 impl.'),
  ('CLAIM_EXTRACTION_REJECTED', 'Phase 2 impl.'),
  ('CLAIM_REVIEW_RECORDED', 'Phase 2 impl.'),
  ('CLAIM_HIGH_IMPACT_SET', 'Phase 2 impl.'),
  ('ENTITY_CREATED', 'Phase 2 impl.'),
  ('ENTITY_ALIAS_CREATED', 'Phase 2 impl.'),
  ('ENTITY_MENTION_LINKED', 'Phase 2 impl.'),
  ('ENTITY_RELATIONSHIP_CREATED', 'Phase 2 impl.'),
  ('TAXONOMY_ITEM_CREATED', 'Phase 2 impl.'),
  ('TAXONOMY_ASSIGNMENT_CREATED', 'Phase 2 impl.'),
  ('CLAIM_CLASSIFICATION_RECORDED', 'Phase 2 impl.'),
  ('CLAIM_STATUS_AUTO_RULE_CONFIGURED', 'Phase 2 impl.');

-- ---------------------------------------------------------------------------
-- Closed taxonomy (Prompt Pack v1.2 §12; Addendum §11–§13)
-- ---------------------------------------------------------------------------
CREATE TABLE lfhe.taxonomy_items (
  id               text PRIMARY KEY CHECK (id ~ '^(TOPIC|TAG|PIR|GEO)_[A-Z0-9_]{1,60}$'),
  taxonomy_type    lfhe.taxonomy_type NOT NULL,
  label            text NOT NULL CHECK (length(btrim(label)) BETWEEN 2 AND 200),
  description      text,
  taxonomy_version text NOT NULL CHECK (taxonomy_version ~ '^LFHE-TAX-[0-9]+\.[0-9]+$'),
  spec_source      text NOT NULL,
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id, taxonomy_type),
  CONSTRAINT taxonomy_prefix_matches_type CHECK (
    split_part(id, '_', 1) = CASE taxonomy_type WHEN 'TOPIC' THEN 'TOPIC' WHEN 'TAG' THEN 'TAG'
                                                WHEN 'PIR' THEN 'PIR' ELSE 'GEO' END)
);

INSERT INTO lfhe.taxonomy_items (id, taxonomy_type, label, description, taxonomy_version, spec_source)
SELECT t.id, t.tt::lfhe.taxonomy_type, t.label, t.descr, 'LFHE-TAX-1.2', t.src FROM (VALUES
  ('TOPIC_AIR_POWER', 'TOPIC', 'Air power (general)', NULL, 'MPP v1.2 §12'),
  ('TOPIC_COMBAT_AVIATION', 'TOPIC', 'Combat aviation', NULL, 'MPP v1.2 §12'),
  ('TOPIC_AIR_DEFENCE', 'TOPIC', 'Air defence', NULL, 'MPP v1.2 §12'),
  ('TOPIC_IAMD', 'TOPIC', 'Integrated air and missile defence', NULL, 'MPP v1.2 §12'),
  ('TOPIC_UAS', 'TOPIC', 'Uncrewed aircraft systems', NULL, 'MPP v1.2 §12'),
  ('TOPIC_UCAV', 'TOPIC', 'Uncrewed combat air vehicles', NULL, 'MPP v1.2 §12'),
  ('TOPIC_C_UAS', 'TOPIC', 'Counter-UAS', NULL, 'MPP v1.2 §12'),
  ('TOPIC_ISR', 'TOPIC', 'Intelligence, surveillance and reconnaissance', NULL, 'MPP v1.2 §12'),
  ('TOPIC_AEWC', 'TOPIC', 'Airborne early warning and control', NULL, 'MPP v1.2 §12'),
  ('TOPIC_EW', 'TOPIC', 'Electronic warfare', NULL, 'MPP v1.2 §12'),
  ('TOPIC_AIR_C2', 'TOPIC', 'Air command and control', NULL, 'MPP v1.2 §12'),
  ('TOPIC_SENSOR', 'TOPIC', 'Sensors', NULL, 'MPP v1.2 §12'),
  ('TOPIC_SENSOR_FUSION', 'TOPIC', 'Sensor and data fusion', NULL, 'MPP v1.2 §12'),
  ('TOPIC_PRECISION_STRIKE', 'TOPIC', 'Precision strike', NULL, 'MPP v1.2 §12'),
  ('TOPIC_LONG_RANGE_STRIKE', 'TOPIC', 'Long-range strike', NULL, 'MPP v1.2 §12'),
  ('TOPIC_AIR_LAUNCHED_WEAPONS', 'TOPIC', 'Air-launched weapons', NULL, 'MPP v1.2 §12'),
  ('TOPIC_AIR_MOBILITY', 'TOPIC', 'Air mobility', NULL, 'MPP v1.2 §12'),
  ('TOPIC_AERIAL_REFUELLING', 'TOPIC', 'Aerial refuelling', NULL, 'MPP v1.2 §12'),
  ('TOPIC_READINESS', 'TOPIC', 'Readiness', NULL, 'MPP v1.2 §12'),
  ('TOPIC_DEPLOYMENT', 'TOPIC', 'Deployment', NULL, 'MPP v1.2 §12'),
  ('TOPIC_EXERCISE', 'TOPIC', 'Exercises', NULL, 'MPP v1.2 §12'),
  ('TOPIC_TRAINING', 'TOPIC', 'Training', NULL, 'MPP v1.2 §12'),
  ('TOPIC_LOGISTICS', 'TOPIC', 'Logistics', NULL, 'MPP v1.2 §12'),
  ('TOPIC_MAINTENANCE', 'TOPIC', 'Maintenance', NULL, 'MPP v1.2 §12'),
  ('TOPIC_INFRASTRUCTURE', 'TOPIC', 'Air infrastructure', NULL, 'MPP v1.2 §12'),
  ('TOPIC_MANPOWER', 'TOPIC', 'Manpower', NULL, 'MPP v1.2 §12'),
  ('TOPIC_STOCKPILES', 'TOPIC', 'Stockpiles', NULL, 'MPP v1.2 §12'),
  ('TOPIC_PROCUREMENT', 'TOPIC', 'Procurement / capability development', NULL, 'MPP v1.2 §12'),
  ('TOPIC_DEFENCE_INDUSTRY', 'TOPIC', 'Defence industry (where capability-affecting)', NULL, 'MPP v1.2 §12'),
  ('TOPIC_PRODUCTION', 'TOPIC', 'Production', NULL, 'MPP v1.2 §12'),
  ('TOPIC_SUSTAINMENT', 'TOPIC', 'Sustainment', NULL, 'MPP v1.2 §12'),
  ('TOPIC_AI', 'TOPIC', 'Artificial intelligence', NULL, 'MPP v1.2 §12'),
  ('TOPIC_AUTONOMY', 'TOPIC', 'Autonomy', NULL, 'MPP v1.2 §12'),
  ('TOPIC_DOCTRINE', 'TOPIC', 'Doctrine / concepts (where real capability change is involved)', NULL, 'MPP v1.2 §12'),
  ('TOPIC_ORGANISATION', 'TOPIC', 'Organisation (where real capability change is involved)', NULL, 'MPP v1.2 §12'),
  ('TOPIC_INTERNATIONAL_COOPERATION', 'TOPIC', 'International cooperation', NULL, 'MPP v1.2 §12'),
  ('TOPIC_LESSONS_IDENTIFIED', 'TOPIC', 'Conflict lessons / adaptation', NULL, 'MPP v1.2 §12'),
  ('TAG_AI_ENABLED', 'TAG', 'AI / ML enabled', NULL, 'MPP v1.2 §12'),
  ('TAG_AUTONOMY', 'TAG', 'Autonomy', NULL, 'MPP v1.2 §12'),
  ('TAG_MASS', 'TAG', 'Mass', NULL, 'MPP v1.2 §12'),
  ('TAG_ATTRITABLE_SYSTEMS', 'TAG', 'Attritable systems', NULL, 'MPP v1.2 §12'),
  ('TAG_HUMAN_MACHINE_TEAMING', 'TAG', 'Human-machine teaming', NULL, 'MPP v1.2 §12'),
  ('TAG_SENSOR_TO_DECISION', 'TAG', 'Sensor-to-decision', NULL, 'MPP v1.2 §12'),
  ('TAG_EW_RESILIENCE', 'TAG', 'EW resilience', NULL, 'MPP v1.2 §12'),
  ('TAG_NAVIGATION_RESILIENCE', 'TAG', 'Navigation resilience', NULL, 'MPP v1.2 §12'),
  ('TAG_INDUSTRIAL_SCALE', 'TAG', 'Industrial scalability', NULL, 'MPP v1.2 §12'),
  ('TAG_INTEROPERABILITY', 'TAG', 'Interoperability', NULL, 'MPP v1.2 §12'),
  ('TAG_COST_EXCHANGE', 'TAG', 'Cost exchange / cost-effectiveness', NULL, 'MPP v1.2 §12'),
  ('TAG_COMBAT_ADAPTATION', 'TAG', 'Combat adaptation / lessons', NULL, 'MPP v1.2 §12'),
  ('TAG_SWARMING', 'TAG', 'Swarming', NULL, 'MPP v1.2 §12'),
  ('PIR_01', 'PIR', 'Capability change',
   'Combat aviation, air defence, UAS/UCAV, C-UAS, ISR, AEW&C, EW, tanker/mobility, precision/long-range strike, C2, sensor/data fusion and other approved air-domain/supporting capability change.', 'Addendum v1.0 §11'),
  ('PIR_02', 'PIR', 'Methods / adaptation',
   'Operational methods, tactics, procedures, doctrine-related adaptation and employment change.', 'Addendum v1.0 §11'),
  ('PIR_03', 'PIR', 'Readiness / operational capability',
   'Readiness, deployment, exercises, force availability, operational capability and posture.', 'Addendum v1.0 §11'),
  ('PIR_04', 'PIR', 'Technology / industrial evolution',
   'Technology, procurement and defence-industrial development. Preserve maturity distinctions such as intention -> announcement -> contract -> production -> delivery -> IOC -> FOC.', 'Addendum v1.0 §11'),
  ('PIR_05', 'PIR', 'UAS / C-UAS',
   'UAS, UCAV, autonomy, swarm, navigation resilience, sensors, AI, EW resilience, detection, soft-kill/hard-kill, cost exchange and scale.', 'Addendum v1.0 §11'),
  ('PIR_06', 'PIR', 'ISR / data / decision support',
   'ISR, AEW&C, sensing, data fusion, decision-support and sensor-to-decision developments.', 'Addendum v1.0 §11'),
  ('PIR_07', 'PIR', 'Hungary / NATO relevance',
   'Why the development matters to Hungary and/or NATO. M03 may classify relevance to the PIR; it must not write the later M06/M07 assessment.', 'Addendum v1.0 §11'),
  ('PIR_08', 'PIR', 'Indicators / warning',
   'Observable developments relevant to warning, monitoring and future change.', 'Addendum v1.0 §11'),
  ('GEO_PRIORITY_1', 'GEO', 'Geographic priority 1',
   'Russia; Ukraine; Belarus; NATO eastern flank; Central / Eastern Europe where relevant to the eastern-flank air picture.', 'Addendum v1.0 §13'),
  ('GEO_PRIORITY_2', 'GEO', 'Geographic priority 2', 'United States; major NATO allies.', 'Addendum v1.0 §13'),
  ('GEO_PRIORITY_3', 'GEO', 'Geographic priority 3',
   'Selective Middle East; selective Indo-Pacific; other locations only when directly relevant to the approved intelligence requirement.', 'Addendum v1.0 §13'),
  ('GEO_GLOBAL_WATCH', 'GEO', 'Global watch', 'GLOBAL_WATCH (Addendum §13).', 'MPP v1.2 §12; Addendum v1.0 §13')
) AS t(id, tt, label, descr, src);

CREATE TRIGGER taxonomy_items_immutable BEFORE UPDATE OR DELETE ON lfhe.taxonomy_items
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();
CREATE OR REPLACE FUNCTION lfhe.audit_taxonomy_item()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  PERFORM lfhe.write_audit('TAXONOMY_ITEM_CREATED', 'taxonomy_item', NEW.id, NULL, pg_catalog.to_jsonb(NEW), '{}'::jsonb);
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION lfhe.audit_taxonomy_item() FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
CREATE TRIGGER taxonomy_items_audit AFTER INSERT ON lfhe.taxonomy_items
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_taxonomy_item();

-- ---------------------------------------------------------------------------
-- QA-D18: deterministic original-language grounding (authoritative).
-- Mirrored by lfhe_shared.grounding.grounding_problems (same reason codes).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.claim_grounding_problems(
  p_text_representation_id uuid, p_article_snapshot_id uuid, p_article_id uuid, p_source_id uuid,
  p_language text, p_locator_type text, p_start integer, p_end integer, p_exact_text text,
  p_claim_text_original text)
RETURNS text[] LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_rep  lfhe.text_representations%ROWTYPE;
  v_snap lfhe.article_snapshots%ROWTYPE;
  v_art  lfhe.articles%ROWTYPE;
  v_out  text[] := '{}';
BEGIN
  IF p_locator_type IS DISTINCT FROM 'TEXT_REPRESENTATION_CODE_POINTS' THEN
    v_out := v_out || 'LOCATOR_TYPE_UNSUPPORTED'::text;
  END IF;
  SELECT * INTO v_rep FROM lfhe.text_representations WHERE id = p_text_representation_id;
  IF NOT FOUND THEN
    RETURN v_out || 'TEXT_REPRESENTATION_NOT_FOUND'::text;
  END IF;
  IF v_rep.snapshot_id IS DISTINCT FROM p_article_snapshot_id THEN
    RETURN v_out || 'TEXT_REPRESENTATION_NOT_OF_SNAPSHOT'::text;
  END IF;
  SELECT * INTO v_snap FROM lfhe.article_snapshots WHERE id = v_rep.snapshot_id;
  IF v_snap.article_id IS DISTINCT FROM p_article_id THEN
    v_out := v_out || 'SNAPSHOT_NOT_OF_ARTICLE'::text;
  END IF;
  SELECT * INTO v_art FROM lfhe.articles WHERE id = v_snap.article_id;
  IF v_art.source_id IS DISTINCT FROM p_source_id THEN
    v_out := v_out || 'ARTICLE_NOT_OF_SOURCE'::text;
  END IF;
  IF v_snap.retention_mode_applied = 'METADATA_ONLY' THEN
    v_out := v_out || 'METADATA_ONLY_SNAPSHOT'::text;
  END IF;
  IF NOT v_rep.is_original_language THEN
    v_out := v_out || 'NOT_ORIGINAL_LANGUAGE'::text;
  END IF;
  IF v_rep.language IS NULL THEN
    v_out := v_out || 'ORIGINAL_LANGUAGE_UNKNOWN'::text;
  ELSIF p_language IS DISTINCT FROM v_rep.language THEN
    v_out := v_out || 'LANGUAGE_MISMATCH'::text;
  END IF;
  IF p_start IS NULL OR p_end IS NULL OR p_start < 0 OR p_end <= p_start OR p_end > v_rep.char_length THEN
    RETURN v_out || 'OFFSETS_INVALID'::text;
  END IF;
  IF p_exact_text IS NULL OR p_exact_text = '' THEN
    RETURN v_out || 'EXACT_TEXT_MISSING'::text;
  END IF;
  IF NOT (p_exact_text IS NFC NORMALIZED) THEN
    v_out := v_out || 'EXACT_TEXT_NOT_NFC'::text;
  END IF;
  IF pg_catalog.substr(v_rep.text_content, p_start + 1, p_end - p_start) IS DISTINCT FROM p_exact_text THEN
    v_out := v_out || 'EXACT_TEXT_MISMATCH'::text;
  ELSIF p_claim_text_original IS NULL OR p_claim_text_original = ''
        OR pg_catalog.strpos(p_exact_text, p_claim_text_original) = 0 THEN
    v_out := v_out || 'CLAIM_TEXT_ORIGINAL_NOT_IN_SPAN'::text;
  END IF;
  RETURN v_out;
END $$;
REVOKE ALL ON FUNCTION lfhe.claim_grounding_problems(uuid, uuid, uuid, uuid, text, text, integer, integer, text, text)
  FROM PUBLIC, anon, authenticated, service_role, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.claim_grounding_problems(uuid, uuid, uuid, uuid, text, text, integer, integer, text, text)
  TO lfhe_worker;

-- ---------------------------------------------------------------------------
-- Extraction results (one per M02 model run; idempotency + outcome record)
-- ---------------------------------------------------------------------------
CREATE TABLE lfhe.claim_extraction_results (
  model_run_id           uuid PRIMARY KEY REFERENCES lfhe.model_runs(id),
  id                     uuid NOT NULL UNIQUE DEFAULT pg_catalog.gen_random_uuid(),
  article_snapshot_id    uuid NOT NULL REFERENCES lfhe.article_snapshots(id),
  text_representation_id uuid NOT NULL REFERENCES lfhe.text_representations(id),
  model_run_status       lfhe.model_run_status NOT NULL,
  output_status          text CHECK (output_status IN ('SUCCESS', 'SUCCESS_WITH_WARNINGS',
                           'INSUFFICIENT_INFORMATION', 'AMBIGUOUS', 'FAILED', 'HUMAN_REVIEW_REQUIRED')),
  outcome                text NOT NULL CHECK (outcome IN ('CLAIMS_PERSISTED', 'NO_CLAIMS', 'ALL_REJECTED',
                           'INSUFFICIENT_INFORMATION', 'HUMAN_REVIEW_REQUIRED', 'SCHEMA_VALIDATION_FAILED',
                           'PROVIDER_ERROR', 'OUTPUT_REJECTED')),
  claims_persisted       integer NOT NULL CHECK (claims_persisted >= 0),
  claims_rejected        integer NOT NULL CHECK (claims_rejected >= 0),
  human_review_required  boolean NOT NULL,
  warnings               jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(warnings) = 'array'),
  rejection_reasons      text[] NOT NULL DEFAULT '{}',
  repair_of_model_run_id uuid REFERENCES lfhe.model_runs(id),
  created_at             timestamptz NOT NULL DEFAULT now(),
  CHECK ((outcome = 'CLAIMS_PERSISTED') = (claims_persisted > 0))
);

-- ---------------------------------------------------------------------------
-- claims (immutable)
-- ---------------------------------------------------------------------------
CREATE TABLE lfhe.claims (
  id                            uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  source_id                     uuid NOT NULL REFERENCES lfhe.sources(id),
  article_id                    uuid NOT NULL REFERENCES lfhe.articles(id),
  article_snapshot_id           uuid NOT NULL REFERENCES lfhe.article_snapshots(id),
  text_representation_id        uuid NOT NULL REFERENCES lfhe.text_representations(id),
  created_by_model_run_id       uuid NOT NULL REFERENCES lfhe.claim_extraction_results(model_run_id),
  claim_local_id                text NOT NULL CHECK (claim_local_id ~ '^[A-Za-z0-9_.-]{1,40}$'),
  language_original             text NOT NULL,
  claim_text_original           text NOT NULL CHECK (length(claim_text_original) BETWEEN 1 AND 4000),
  claim_text_normalised         text NOT NULL CHECK (length(btrim(claim_text_normalised)) BETWEEN 1 AND 4000),
  claim_type                    lfhe.claim_type NOT NULL,
  source_statement_status       lfhe.source_statement_status NOT NULL,
  attribution                   text CHECK (attribution IS NULL OR length(btrim(attribution)) BETWEEN 1 AND 1000),
  event_date                    text CHECK (event_date ~ '^[0-9]{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12][0-9]|3[01]))?)?$'),
  event_date_confidence         lfhe.timestamp_confidence NOT NULL,
  location_mentions             jsonb NOT NULL DEFAULT '[]'::jsonb,
  quantity                      numeric,
  unit                          text CHECK (unit IS NULL OR length(btrim(unit)) BETWEEN 1 AND 100),
  evidence_type                 lfhe.evidence_type NOT NULL,
  evidence_directness           lfhe.evidence_directness NOT NULL,
  source_uncertainty_preserved  boolean NOT NULL,
  potential_contradiction       boolean NOT NULL,
  -- The SOURCE's statement category (not an LFHÉ judgment): FACT / ASSESSMENT / ASSUMPTION.
  fact_assumption_marker        text GENERATED ALWAYS AS (CASE source_statement_status
                                  WHEN 'FACT_REPORTED_BY_SOURCE' THEN 'FACT'
                                  WHEN 'DIRECT_OBSERVATION_REPORTED' THEN 'FACT'
                                  WHEN 'SOURCE_CLAIM_UNVERIFIED' THEN 'FACT'
                                  WHEN 'SOURCE_ASSESSMENT' THEN 'ASSESSMENT'
                                  WHEN 'SOURCE_EXPECTATION' THEN 'ASSUMPTION' END) STORED,
  -- Workflow-compatible placeholders; not assessed in Phase 2 (M04 / later phases).
  source_reliability_assessment text CHECK (source_reliability_assessment IS NULL),
  claim_credibility             text CHECK (claim_credibility IS NULL),
  independent_confirmation      text NOT NULL DEFAULT 'NOT_ASSESSED' CHECK (independent_confirmation = 'NOT_ASSESSED'),
  -- evidence_span_original (canonical field; jsonb built from the verified columns)
  span_locator_type             text NOT NULL,
  span_start                    integer NOT NULL,
  span_end                      integer NOT NULL,
  span_exact_text               text NOT NULL,
  evidence_span_original        jsonb NOT NULL,
  grounding_check               text NOT NULL DEFAULT 'QA-D18/1' CHECK (grounding_check = 'QA-D18/1'),
  review_flags                  text[] NOT NULL DEFAULT '{}',
  human_review_required         boolean NOT NULL,
  claim_hash                    text NOT NULL CHECK (claim_hash ~ '^[0-9a-f]{64}$'),
  created_at                    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (created_by_model_run_id, claim_local_id),
  UNIQUE (id, claim_hash),
  CONSTRAINT claim_event_date_confidence CHECK (event_date IS NOT NULL OR event_date_confidence = 'UNKNOWN'),
  CONSTRAINT claim_unit_needs_quantity CHECK (unit IS NULL OR quantity IS NOT NULL),
  CONSTRAINT claim_locations_are_strings CHECK (jsonb_typeof(location_mentions) = 'array'
    AND NOT jsonb_path_exists(location_mentions, '$[*] ? (@.type() != "string")')),
  CONSTRAINT claim_review_flags_closed CHECK (review_flags <@ lfhe.claim_review_flags()),
  CONSTRAINT claim_flags_force_review CHECK (cardinality(review_flags) = 0 OR human_review_required),
  CONSTRAINT claim_span_jsonb_consistent CHECK (evidence_span_original = jsonb_build_object(
    'article_snapshot_id', article_snapshot_id::text, 'text_representation_id', text_representation_id::text,
    'language', language_original, 'exact_text', span_exact_text, 'start', span_start, 'end', span_end,
    'locator_type', span_locator_type, 'offset_unit', 'UNICODE_CODE_POINT'))
);
CREATE INDEX claims_snapshot_idx ON lfhe.claims (article_snapshot_id);
CREATE INDEX claims_article_idx ON lfhe.claims (article_id);

-- Canonical claim content hash ('lfhe-claim/1'); binds reviews to exact content.
CREATE OR REPLACE FUNCTION lfhe.claim_content_sha256(c lfhe.claims)
RETURNS text LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
  SELECT pg_catalog.encode(extensions.digest(pg_catalog.convert_to('lfhe-claim/1' || E'\n' ||
    (pg_catalog.to_jsonb(c) - 'claim_hash' - 'created_at' - 'id' - 'fact_assumption_marker')::text, 'UTF8'), 'sha256'), 'hex')
$$;
REVOKE ALL ON FUNCTION lfhe.claim_content_sha256(lfhe.claims) FROM PUBLIC;

CREATE OR REPLACE FUNCTION lfhe.claims_before_insert()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_problems text[];
  v_run      lfhe.model_runs%ROWTYPE;
BEGIN
  v_problems := lfhe.claim_grounding_problems(NEW.text_representation_id, NEW.article_snapshot_id,
    NEW.article_id, NEW.source_id, NEW.language_original, NEW.span_locator_type, NEW.span_start,
    NEW.span_end, NEW.span_exact_text, NEW.claim_text_original);
  IF cardinality(v_problems) > 0 THEN
    RAISE EXCEPTION 'CLAIM_NOT_GROUNDED_IN_ORIGINAL_SOURCE: %', pg_catalog.array_to_string(v_problems, ', ')
      USING ERRCODE = 'check_violation';
  END IF;
  SELECT * INTO v_run FROM lfhe.model_runs WHERE id = NEW.created_by_model_run_id;
  IF v_run.module_code IS DISTINCT FROM 'M02_CLAIM_EXTRACTOR' OR v_run.status IS DISTINCT FROM 'SUCCEEDED'
     OR NOT coalesce(v_run.input_manifest @> pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object(
          'object_type', 'text_representation', 'object_id', NEW.text_representation_id::text)), false) THEN
    RAISE EXCEPTION 'CLAIM_PROVENANCE_INVALID: claim must come from a SUCCEEDED M02_CLAIM_EXTRACTOR run whose input manifest contains its text representation'
      USING ERRCODE = 'check_violation';
  END IF;
  NEW.evidence_span_original := pg_catalog.jsonb_build_object(
    'article_snapshot_id', NEW.article_snapshot_id::text, 'text_representation_id', NEW.text_representation_id::text,
    'language', NEW.language_original, 'exact_text', NEW.span_exact_text, 'start', NEW.span_start,
    'end', NEW.span_end, 'locator_type', NEW.span_locator_type, 'offset_unit', 'UNICODE_CODE_POINT');
  NEW.created_at := pg_catalog.now();
  NEW.claim_hash := pg_catalog.repeat('0', 64);
  NEW.claim_hash := lfhe.claim_content_sha256(NEW);
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION lfhe.claims_before_insert() FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
CREATE TRIGGER claims_before_insert BEFORE INSERT ON lfhe.claims
  FOR EACH ROW EXECUTE FUNCTION lfhe.claims_before_insert();
CREATE TRIGGER claims_immutable BEFORE UPDATE OR DELETE ON lfhe.claims
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();
CREATE TRIGGER claims_audit AFTER INSERT ON lfhe.claims
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_row_change('CLAIM_CREATED', '-', '-', 'claim');

-- Rejected candidates: recorded for review/debug, never usable as claims.
CREATE TABLE lfhe.claim_extraction_rejections (
  id                 uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  model_run_id       uuid NOT NULL REFERENCES lfhe.claim_extraction_results(model_run_id),
  claim_local_id     text,
  reason_codes       text[] NOT NULL CHECK (cardinality(reason_codes) > 0),
  grounding_failure  boolean NOT NULL,
  candidate          jsonb NOT NULL,
  created_at         timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER claim_extraction_rejections_immutable BEFORE UPDATE OR DELETE ON lfhe.claim_extraction_rejections
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();
CREATE OR REPLACE FUNCTION lfhe.audit_claim_extraction_rejection()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  PERFORM lfhe.write_audit(CASE WHEN NEW.grounding_failure THEN 'CLAIM_EXTRACTION_GROUNDING_FAILED'
                                ELSE 'CLAIM_EXTRACTION_REJECTED' END,
    'claim_extraction_rejection', NEW.id::text, NULL, pg_catalog.to_jsonb(NEW),
    pg_catalog.jsonb_build_object('model_run_id', NEW.model_run_id));
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION lfhe.audit_claim_extraction_rejection() FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
CREATE TRIGGER claim_extraction_rejections_audit AFTER INSERT ON lfhe.claim_extraction_rejections
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_claim_extraction_rejection();

CREATE TRIGGER claim_extraction_results_immutable BEFORE UPDATE OR DELETE ON lfhe.claim_extraction_results
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();
CREATE OR REPLACE FUNCTION lfhe.audit_claim_extraction_result()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  PERFORM lfhe.write_audit('CLAIM_EXTRACTION_RECORDED', 'claim_extraction_result', NEW.model_run_id::text,
    NULL, pg_catalog.to_jsonb(NEW), '{}'::jsonb);
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION lfhe.audit_claim_extraction_result() FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
CREATE TRIGGER claim_extraction_results_audit AFTER INSERT ON lfhe.claim_extraction_results
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_claim_extraction_result();

-- ---------------------------------------------------------------------------
-- Entities (conservative)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.normalise_entity_name(p text)
RETURNS text LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
  SELECT pg_catalog.lower(pg_catalog.regexp_replace(pg_catalog.btrim(pg_catalog.normalize(p, 'NFKC')), '\s+', ' ', 'g'))
$$;
REVOKE ALL ON FUNCTION lfhe.normalise_entity_name(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION lfhe.normalise_entity_name(text) TO authenticated, lfhe_worker;

CREATE TABLE lfhe.entities (
  id              uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  canonical_name  text NOT NULL CHECK (length(btrim(canonical_name)) BETWEEN 1 AND 300),
  entity_type     lfhe.entity_type NOT NULL,
  description     text,
  created_by      uuid NOT NULL,
  reason          text NOT NULL CHECK (length(btrim(reason)) >= 5),
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE lfhe.entity_aliases (
  id               uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  entity_id        uuid NOT NULL REFERENCES lfhe.entities(id),
  alias_text       text NOT NULL CHECK (length(btrim(alias_text)) BETWEEN 1 AND 300),
  alias_normalised text NOT NULL,
  language         text CHECK (language ~ '^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$'),
  alias_basis      text NOT NULL CHECK (length(btrim(alias_basis)) >= 10),
  created_by       uuid NOT NULL,
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (entity_id, alias_normalised),
  CONSTRAINT alias_normalised_matches CHECK (alias_normalised = lfhe.normalise_entity_name(alias_text))
);
CREATE INDEX entity_aliases_lookup_idx ON lfhe.entity_aliases (alias_normalised);

CREATE TABLE lfhe.entity_mentions (
  id                     uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  claim_id               uuid NOT NULL REFERENCES lfhe.claims(id),
  mention_index          integer NOT NULL CHECK (mention_index >= 0),
  mention_text_original  text NOT NULL CHECK (length(mention_text_original) BETWEEN 1 AND 300),
  mention_normalised     text NOT NULL,
  entity_type_hint       lfhe.entity_type,
  model_run_id           uuid NOT NULL REFERENCES lfhe.model_runs(id),
  created_at             timestamptz NOT NULL DEFAULT now(),
  UNIQUE (claim_id, mention_index),
  CONSTRAINT mention_normalised_matches CHECK (mention_normalised = lfhe.normalise_entity_name(mention_text_original))
);

CREATE TABLE lfhe.entity_links (
  seq                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id                    uuid NOT NULL UNIQUE DEFAULT pg_catalog.gen_random_uuid(),
  mention_id            uuid NOT NULL REFERENCES lfhe.entity_mentions(id),
  resolution_status     lfhe.entity_resolution_status NOT NULL,
  entity_id             uuid REFERENCES lfhe.entities(id),
  candidate_entity_ids  uuid[] NOT NULL DEFAULT '{}',
  method                text NOT NULL CHECK (method IN ('EXACT_ALIAS_RULE', 'HUMAN')),
  actor_user_id         uuid,
  reason                text,
  created_at            timestamptz NOT NULL DEFAULT now(),
  CHECK ((resolution_status = 'RESOLVED') = (entity_id IS NOT NULL)),
  CHECK (resolution_status <> 'AMBIGUOUS' OR cardinality(candidate_entity_ids) >= 2),
  CHECK ((method = 'HUMAN') = (actor_user_id IS NOT NULL)),
  CHECK (method <> 'HUMAN' OR length(btrim(coalesce(reason, ''))) >= 5)
);

CREATE TABLE lfhe.entity_relationships (
  id                uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  subject_entity_id uuid NOT NULL REFERENCES lfhe.entities(id),
  relation_type     text NOT NULL CHECK (relation_type IN
                      ('PART_OF', 'SUBORDINATE_TO', 'OPERATED_BY', 'MANUFACTURED_BY', 'VARIANT_OF', 'LOCATED_IN')),
  object_entity_id  uuid NOT NULL REFERENCES lfhe.entities(id),
  basis             text NOT NULL CHECK (length(btrim(basis)) >= 10),
  created_by        uuid NOT NULL,
  created_at        timestamptz NOT NULL DEFAULT now(),
  CHECK (subject_entity_id <> object_entity_id),
  UNIQUE (subject_entity_id, relation_type, object_entity_id)
);

CREATE TRIGGER entities_immutable BEFORE UPDATE OR DELETE ON lfhe.entities
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();
CREATE TRIGGER entity_aliases_immutable BEFORE UPDATE OR DELETE ON lfhe.entity_aliases
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();
CREATE TRIGGER entity_mentions_immutable BEFORE UPDATE OR DELETE ON lfhe.entity_mentions
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();
CREATE TRIGGER entity_links_append_only BEFORE UPDATE OR DELETE ON lfhe.entity_links
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();
CREATE TRIGGER entity_relationships_immutable BEFORE UPDATE OR DELETE ON lfhe.entity_relationships
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();
CREATE TRIGGER entities_audit AFTER INSERT ON lfhe.entities
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_row_change('ENTITY_CREATED', '-', '-', 'entity');
CREATE TRIGGER entity_aliases_audit AFTER INSERT ON lfhe.entity_aliases
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_row_change('ENTITY_ALIAS_CREATED', '-', '-', 'entity_alias');
CREATE TRIGGER entity_links_audit AFTER INSERT ON lfhe.entity_links
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_row_change('ENTITY_MENTION_LINKED', '-', '-', 'entity_link');
CREATE TRIGGER entity_relationships_audit AFTER INSERT ON lfhe.entity_relationships
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_row_change('ENTITY_RELATIONSHIP_CREATED', '-', '-', 'entity_relationship');

CREATE VIEW lfhe.entity_mention_resolution WITH (security_invoker = true) AS
SELECT m.id AS mention_id, m.claim_id, m.mention_index, m.mention_text_original, m.entity_type_hint,
       coalesce(l.resolution_status, 'UNRESOLVED'::lfhe.entity_resolution_status) AS resolution_status,
       l.entity_id, l.candidate_entity_ids, l.method, l.actor_user_id, l.created_at AS resolved_at
FROM lfhe.entity_mentions m
LEFT JOIN LATERAL (SELECT * FROM lfhe.entity_links x WHERE x.mention_id = m.id ORDER BY x.seq DESC LIMIT 1) l ON true;
-- CG0 name for the claim ↔ entity relation.
CREATE VIEW lfhe.claim_entities WITH (security_invoker = true) AS
SELECT claim_id, mention_id, mention_text_original, entity_type_hint, resolution_status, entity_id
FROM lfhe.entity_mention_resolution;

-- Deterministic, conservative resolution of one mention (exact normalised
-- alias, type-compatible, unique). Never overrides a human link.
CREATE OR REPLACE FUNCTION lfhe.auto_resolve_mention(p_mention_id uuid)
RETURNS lfhe.entity_resolution_status LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_m          lfhe.entity_mentions%ROWTYPE;
  v_last       lfhe.entity_links%ROWTYPE;
  v_candidates uuid[];
  v_status     lfhe.entity_resolution_status;
  v_has_last   boolean;
BEGIN
  SELECT * INTO v_m FROM lfhe.entity_mentions WHERE id = p_mention_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'unknown entity mention %', p_mention_id USING ERRCODE = 'no_data_found';
  END IF;
  PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtext('lfhe.mention:' || p_mention_id::text));
  SELECT * INTO v_last FROM lfhe.entity_links WHERE mention_id = p_mention_id ORDER BY seq DESC LIMIT 1;
  v_has_last := FOUND;
  IF v_has_last AND v_last.method = 'HUMAN' THEN
    RETURN v_last.resolution_status;
  END IF;
  SELECT coalesce(pg_catalog.array_agg(DISTINCT a.entity_id ORDER BY a.entity_id), '{}') INTO v_candidates
  FROM lfhe.entity_aliases a JOIN lfhe.entities e ON e.id = a.entity_id
  WHERE a.alias_normalised = v_m.mention_normalised
    AND (v_m.entity_type_hint IS NULL OR e.entity_type = v_m.entity_type_hint);
  v_status := CASE pg_catalog.cardinality(v_candidates) WHEN 0 THEN 'UNRESOLVED' WHEN 1 THEN 'RESOLVED' ELSE 'AMBIGUOUS' END;
  IF v_has_last AND v_last.resolution_status = v_status AND v_last.entity_id IS NOT DISTINCT FROM
       (CASE WHEN v_status = 'RESOLVED' THEN v_candidates[1] END)
     AND v_last.candidate_entity_ids = (CASE WHEN v_status = 'AMBIGUOUS' THEN v_candidates ELSE '{}' END) THEN
    RETURN v_status;   -- unchanged; no duplicate link row
  END IF;
  INSERT INTO lfhe.entity_links (mention_id, resolution_status, entity_id, candidate_entity_ids, method)
  VALUES (p_mention_id, v_status, CASE WHEN v_status = 'RESOLVED' THEN v_candidates[1] END,
          CASE WHEN v_status = 'AMBIGUOUS' THEN v_candidates ELSE '{}' END, 'EXACT_ALIAS_RULE');
  RETURN v_status;
END $$;
REVOKE ALL ON FUNCTION lfhe.auto_resolve_mention(uuid) FROM PUBLIC, anon, authenticated, service_role, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.auto_resolve_mention(uuid) TO lfhe_worker;

-- ---------------------------------------------------------------------------
-- Claim status, high impact, revalidation
-- ---------------------------------------------------------------------------
CREATE TABLE lfhe.claim_status_auto_rules (
  rule_code    text PRIMARY KEY CHECK (rule_code ~ '^[A-Z][A-Z0-9_]{2,60}$'),
  id           uuid NOT NULL UNIQUE DEFAULT pg_catalog.gen_random_uuid(),
  from_status  lfhe.claim_status NOT NULL,
  to_status    lfhe.claim_status NOT NULL,
  description  text NOT NULL,
  configured_at timestamptz NOT NULL DEFAULT now(),
  CHECK (from_status <> to_status)
);
-- Owner-configured only (migration / operator). Empty in Phase 2.
CREATE TRIGGER claim_status_auto_rules_immutable BEFORE UPDATE OR DELETE ON lfhe.claim_status_auto_rules
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();
CREATE TRIGGER claim_status_auto_rules_audit AFTER INSERT ON lfhe.claim_status_auto_rules
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_row_change('CLAIM_STATUS_AUTO_RULE_CONFIGURED', '-', '-', 'claim_status_auto_rule');

CREATE TABLE lfhe.claim_reviews (
  seq                            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id                             uuid NOT NULL UNIQUE DEFAULT pg_catalog.gen_random_uuid(),
  claim_id                       uuid NOT NULL,
  claim_hash                     text NOT NULL,
  previous_review_id             uuid REFERENCES lfhe.claim_reviews(id),
  decision                       lfhe.review_decision NOT NULL,
  reviewer_user_id               uuid NOT NULL,
  reason                         text NOT NULL CHECK (length(btrim(reason)) >= 5),
  modified_claim_text_normalised text CHECK (modified_claim_text_normalised IS NULL
                                   OR length(btrim(modified_claim_text_normalised)) BETWEEN 1 AND 4000),
  modified_claim_type            lfhe.claim_type,
  modified_attribution           text,
  high_impact_at_review          boolean NOT NULL,
  created_at                     timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (claim_id, claim_hash) REFERENCES lfhe.claims (id, claim_hash),
  UNIQUE (claim_id, previous_review_id),
  CHECK ((decision = 'MODIFY_AND_APPROVE') = (modified_claim_text_normalised IS NOT NULL
         OR modified_claim_type IS NOT NULL OR modified_attribution IS NOT NULL))
);
CREATE UNIQUE INDEX claim_reviews_one_first ON lfhe.claim_reviews (claim_id) WHERE previous_review_id IS NULL;

CREATE TABLE lfhe.claim_status_history (
  seq                       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id                        uuid NOT NULL UNIQUE DEFAULT pg_catalog.gen_random_uuid(),
  claim_id                  uuid NOT NULL REFERENCES lfhe.claims(id),
  old_status                lfhe.claim_status,
  new_status                lfhe.claim_status NOT NULL,
  basis                     text NOT NULL CHECK (basis IN ('INITIAL_EXTRACTION', 'HUMAN_DECISION',
                              'AUTOMATIC_RULE', 'HIGH_IMPACT_REVALIDATION_REJECTED')),
  actor_type                lfhe.actor_type NOT NULL,
  actor_user_id             uuid,
  auto_rule_code            text REFERENCES lfhe.claim_status_auto_rules(rule_code),
  recommending_model_run_id uuid REFERENCES lfhe.model_runs(id),
  review_id                 uuid REFERENCES lfhe.claim_reviews(id),
  high_impact_at_change     boolean NOT NULL,
  high_impact_revalidation  boolean NOT NULL DEFAULT false,
  reason                    text NOT NULL,
  created_at                timestamptz NOT NULL DEFAULT now(),
  CHECK ((basis = 'INITIAL_EXTRACTION') = (old_status IS NULL)),
  CHECK (basis <> 'INITIAL_EXTRACTION' OR new_status = 'UNVERIFIED'),
  CHECK (old_status IS NULL OR old_status <> new_status OR basis = 'HIGH_IMPACT_REVALIDATION_REJECTED'),
  CHECK ((basis IN ('HUMAN_DECISION', 'HIGH_IMPACT_REVALIDATION_REJECTED')) = (actor_user_id IS NOT NULL)),
  CHECK (actor_user_id IS NULL OR actor_type = 'HUMAN'),
  CHECK ((basis = 'AUTOMATIC_RULE') = (auto_rule_code IS NOT NULL)),
  CHECK (basis <> 'AUTOMATIC_RULE' OR (NOT high_impact_at_change AND recommending_model_run_id IS NOT NULL))
);
CREATE UNIQUE INDEX claim_status_history_one_initial ON lfhe.claim_status_history (claim_id)
  WHERE basis = 'INITIAL_EXTRACTION';

CREATE TABLE lfhe.claim_high_impact (
  seq            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id             uuid NOT NULL UNIQUE DEFAULT pg_catalog.gen_random_uuid(),
  claim_id       uuid NOT NULL REFERENCES lfhe.claims(id),
  high_impact    boolean NOT NULL,
  reasons        lfhe.high_impact_reason[] NOT NULL DEFAULT '{}',
  actor_type     lfhe.actor_type NOT NULL,
  actor_user_id  uuid,
  basis          text NOT NULL CHECK (length(btrim(basis)) >= 5),
  created_at     timestamptz NOT NULL DEFAULT now(),
  CHECK (high_impact = (cardinality(reasons) > 0)),
  -- the human-mark reason can only be recorded by a human
  CHECK (NOT ('HUMAN_MARKED_HIGH_IMPACT' = ANY (reasons)) OR actor_user_id IS NOT NULL),
  CHECK ((actor_user_id IS NOT NULL) = (actor_type = 'HUMAN'))
);

CREATE TABLE lfhe.claim_revalidations (
  id                    uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  claim_id              uuid NOT NULL REFERENCES lfhe.claims(id),
  status_history_id     uuid NOT NULL REFERENCES lfhe.claim_status_history(id),
  high_impact_id        uuid NOT NULL REFERENCES lfhe.claim_high_impact(id),
  created_at            timestamptz NOT NULL DEFAULT now(),
  UNIQUE (status_history_id)
);
CREATE TABLE lfhe.claim_revalidation_decisions (
  revalidation_id   uuid PRIMARY KEY REFERENCES lfhe.claim_revalidations(id),
  id                uuid NOT NULL UNIQUE DEFAULT pg_catalog.gen_random_uuid(),
  decision          text NOT NULL CHECK (decision IN ('APPROVED', 'REJECTED')),
  actor_user_id     uuid NOT NULL,
  reason            text NOT NULL CHECK (length(btrim(reason)) >= 5),
  created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TRIGGER claim_reviews_append_only BEFORE UPDATE OR DELETE ON lfhe.claim_reviews
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();
CREATE TRIGGER claim_status_history_append_only BEFORE UPDATE OR DELETE ON lfhe.claim_status_history
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();
CREATE TRIGGER claim_high_impact_append_only BEFORE UPDATE OR DELETE ON lfhe.claim_high_impact
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();
CREATE TRIGGER claim_revalidations_append_only BEFORE UPDATE OR DELETE ON lfhe.claim_revalidations
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();
CREATE TRIGGER claim_revalidation_decisions_append_only BEFORE UPDATE OR DELETE ON lfhe.claim_revalidation_decisions
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();

CREATE TRIGGER claim_status_history_audit AFTER INSERT ON lfhe.claim_status_history
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_row_change('CLAIM_STATUS_CHANGED', '-', '-', 'claim_status_history');
CREATE TRIGGER claim_revalidations_audit AFTER INSERT ON lfhe.claim_revalidations
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_row_change('HIGH_IMPACT_REVALIDATION_REQUIRED', '-', '-', 'claim_revalidation');

CREATE OR REPLACE FUNCTION lfhe.audit_claim_high_impact()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  PERFORM lfhe.write_audit(CASE WHEN NEW.actor_user_id IS NOT NULL AND NEW.high_impact
                                THEN 'CLAIM_MARKED_HIGH_IMPACT_BY_HUMAN' ELSE 'CLAIM_HIGH_IMPACT_SET' END,
    'claim', NEW.claim_id::text, NULL, pg_catalog.to_jsonb(NEW), '{}'::jsonb);
  RETURN NULL;
END $$;
CREATE OR REPLACE FUNCTION lfhe.audit_claim_revalidation_decision()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  PERFORM lfhe.write_audit(CASE NEW.decision WHEN 'APPROVED' THEN 'HIGH_IMPACT_REVALIDATION_APPROVED'
                                ELSE 'HIGH_IMPACT_REVALIDATION_REJECTED' END,
    'claim_revalidation', NEW.revalidation_id::text, NULL, pg_catalog.to_jsonb(NEW), '{}'::jsonb);
  RETURN NULL;
END $$;
CREATE OR REPLACE FUNCTION lfhe.audit_claim_review()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_event text := CASE NEW.decision
    WHEN 'ESCALATE' THEN 'REVIEW_ESCALATED'
    WHEN 'REQUEST_REPROCESSING' THEN 'REPROCESSING_REQUESTED'
    WHEN 'MODIFY_AND_APPROVE' THEN 'CLAIM_MODIFIED'
    ELSE CASE WHEN NEW.high_impact_at_review THEN 'HIGH_IMPACT_CLAIM_REVIEWED' ELSE 'CLAIM_REVIEW_RECORDED' END END;
BEGIN
  PERFORM lfhe.write_audit(v_event, 'claim', NEW.claim_id::text, NULL, pg_catalog.to_jsonb(NEW),
    pg_catalog.jsonb_build_object('claim_review_id', NEW.id, 'decision', NEW.decision,
                                  'claim_hash', NEW.claim_hash, 'previous_review_id', NEW.previous_review_id));
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION lfhe.audit_claim_high_impact(), lfhe.audit_claim_revalidation_decision(), lfhe.audit_claim_review()
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
CREATE TRIGGER claim_high_impact_audit AFTER INSERT ON lfhe.claim_high_impact
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_claim_high_impact();
CREATE TRIGGER claim_revalidation_decisions_audit AFTER INSERT ON lfhe.claim_revalidation_decisions
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_claim_revalidation_decision();
CREATE TRIGGER claim_reviews_audit AFTER INSERT ON lfhe.claim_reviews
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_claim_review();

-- Current state, derived from the append-only logs.
CREATE VIEW lfhe.claim_state WITH (security_invoker = true) AS
SELECT c.id AS claim_id,
       s.new_status AS claim_status, s.basis AS status_basis, s.id AS status_history_id, s.created_at AS status_changed_at,
       coalesce(h.high_impact, false) AS high_impact, coalesce(h.reasons::text[], '{}') AS high_impact_reasons,
       EXISTS (SELECT 1 FROM lfhe.claim_revalidations r
               WHERE r.claim_id = c.id
                 AND NOT EXISTS (SELECT 1 FROM lfhe.claim_revalidation_decisions d WHERE d.revalidation_id = r.id))
         AS revalidation_pending,
       (s.basis IN ('HUMAN_DECISION', 'HIGH_IMPACT_REVALIDATION_REJECTED', 'INITIAL_EXTRACTION')
        OR EXISTS (SELECT 1 FROM lfhe.claim_revalidations r JOIN lfhe.claim_revalidation_decisions d
                     ON d.revalidation_id = r.id AND d.decision = 'APPROVED'
                   WHERE r.status_history_id = s.id)) AS status_human_confirmed,
       rv.id AS latest_review_id, rv.decision AS latest_review_decision,
       CASE WHEN rv.id IS NULL THEN 'PENDING'
            WHEN rv.decision = 'APPROVE' THEN 'VALIDATED'
            WHEN rv.decision = 'MODIFY_AND_APPROVE' THEN 'MODIFIED'
            WHEN rv.decision = 'REJECT' THEN 'REJECTED'
            WHEN rv.decision = 'ESCALATE' THEN 'ESCALATED'
            ELSE 'REPROCESSING_REQUESTED' END AS review_state,
       c.human_review_required,
       coalesce(mod.modified_claim_text_normalised, c.claim_text_normalised) AS effective_claim_text_normalised,
       coalesce(mod.modified_claim_type, c.claim_type) AS effective_claim_type,
       CASE WHEN mod.id IS NOT NULL AND mod.modified_attribution IS NOT NULL THEN mod.modified_attribution
            ELSE c.attribution END AS effective_attribution
FROM lfhe.claims c
LEFT JOIN LATERAL (SELECT * FROM lfhe.claim_status_history x WHERE x.claim_id = c.id ORDER BY x.seq DESC LIMIT 1) s ON true
LEFT JOIN LATERAL (SELECT * FROM lfhe.claim_high_impact x WHERE x.claim_id = c.id ORDER BY x.seq DESC LIMIT 1) h ON true
LEFT JOIN LATERAL (SELECT * FROM lfhe.claim_reviews x WHERE x.claim_id = c.id ORDER BY x.seq DESC LIMIT 1) rv ON true
LEFT JOIN LATERAL (SELECT * FROM lfhe.claim_reviews x WHERE x.claim_id = c.id AND x.decision = 'MODIFY_AND_APPROVE'
                   ORDER BY x.seq DESC LIMIT 1) mod ON rv.decision = 'MODIFY_AND_APPROVE';

-- A strengthened status may justify stronger epistemic treatment / attribution
-- omission only when it is not awaiting revalidation and, for a high-impact
-- claim, was set by a human. (Addendum §8)
CREATE VIEW lfhe.claim_status_usability WITH (security_invoker = true) AS
SELECT st.claim_id, st.claim_status, st.status_basis, st.high_impact, st.revalidation_pending, st.status_human_confirmed,
       (NOT st.revalidation_pending
        AND (NOT st.high_impact OR st.status_human_confirmed)
        AND st.review_state NOT IN ('REJECTED', 'REPROCESSING_REQUESTED')) AS status_usable
FROM lfhe.claim_state st;

-- Internal helper: current high-impact flag.
CREATE OR REPLACE FUNCTION lfhe.claim_is_high_impact(p_claim uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT coalesce((SELECT h.high_impact FROM lfhe.claim_high_impact h WHERE h.claim_id = p_claim
                   ORDER BY h.seq DESC LIMIT 1), false)
$$;
REVOKE ALL ON FUNCTION lfhe.claim_is_high_impact(uuid) FROM PUBLIC, anon, authenticated, service_role, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.claim_is_high_impact(uuid) TO lfhe_worker;

CREATE OR REPLACE FUNCTION lfhe.claim_current_status(p_claim uuid)
RETURNS lfhe.claim_status_history LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT * FROM lfhe.claim_status_history WHERE claim_id = p_claim ORDER BY seq DESC LIMIT 1
$$;
REVOKE ALL ON FUNCTION lfhe.claim_current_status(uuid) FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;

-- Records a high-impact change and, on low→high after an automatic status,
-- requires revalidation (shared by the worker and the human path).
CREATE OR REPLACE FUNCTION lfhe.record_claim_high_impact(
  p_claim uuid, p_high_impact boolean, p_reasons lfhe.high_impact_reason[], p_actor uuid, p_basis text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_was    boolean;
  v_id     uuid;
  v_status lfhe.claim_status_history;
BEGIN
  PERFORM 1 FROM lfhe.claims WHERE id = p_claim FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'unknown claim %', p_claim USING ERRCODE = 'no_data_found';
  END IF;
  v_was := lfhe.claim_is_high_impact(p_claim);
  INSERT INTO lfhe.claim_high_impact (claim_id, high_impact, reasons, actor_type, actor_user_id, basis)
  VALUES (p_claim, p_high_impact, CASE WHEN p_high_impact THEN p_reasons ELSE '{}' END,
          CASE WHEN p_actor IS NULL THEN 'WORKER'::lfhe.actor_type ELSE 'HUMAN' END, p_actor, p_basis)
  RETURNING id INTO v_id;
  IF p_high_impact AND NOT v_was THEN
    v_status := lfhe.claim_current_status(p_claim);
    IF v_status.basis = 'AUTOMATIC_RULE' THEN
      INSERT INTO lfhe.claim_revalidations (claim_id, status_history_id, high_impact_id)
      VALUES (p_claim, v_status.id, v_id)
      ON CONFLICT (status_history_id) DO NOTHING;
    END IF;
  END IF;
  RETURN v_id;
END $$;
REVOKE ALL ON FUNCTION lfhe.record_claim_high_impact(uuid, boolean, lfhe.high_impact_reason[], uuid, text)
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;

-- Worker: orchestrator-computed high impact (MPP v1.2 §5). Cannot claim a
-- human mark and cannot remove one.
CREATE OR REPLACE FUNCTION lfhe.set_claim_high_impact(
  p_claim uuid, p_high_impact boolean, p_reasons lfhe.high_impact_reason[], p_basis text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_last lfhe.claim_high_impact%ROWTYPE;
BEGIN
  IF 'HUMAN_MARKED_HIGH_IMPACT' = ANY (coalesce(p_reasons, '{}')) THEN
    RAISE EXCEPTION 'HUMAN_MARKED_HIGH_IMPACT can only be set by a human' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF p_high_impact AND cardinality(coalesce(p_reasons, '{}')) = 0 THEN
    RAISE EXCEPTION 'high impact requires at least one reason' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  SELECT * INTO v_last FROM lfhe.claim_high_impact WHERE claim_id = p_claim ORDER BY seq DESC LIMIT 1;
  IF FOUND AND v_last.actor_user_id IS NOT NULL THEN
    RAISE EXCEPTION 'the high-impact state of claim % was set by a human; only a human may change it', p_claim
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN lfhe.record_claim_high_impact(p_claim, p_high_impact, p_reasons, NULL, p_basis);
END $$;
REVOKE ALL ON FUNCTION lfhe.set_claim_high_impact(uuid, boolean, lfhe.high_impact_reason[], text)
  FROM PUBLIC, anon, authenticated, service_role, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.set_claim_high_impact(uuid, boolean, lfhe.high_impact_reason[], text) TO lfhe_worker;

-- Worker: automatic status transition (LOW-impact claims only, configured rule).
CREATE OR REPLACE FUNCTION lfhe.apply_automatic_claim_status(
  p_claim uuid, p_rule_code text, p_recommending_model_run uuid, p_reason text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_rule   lfhe.claim_status_auto_rules%ROWTYPE;
  v_cur    lfhe.claim_status_history;
  v_id     uuid;
BEGIN
  PERFORM 1 FROM lfhe.claims WHERE id = p_claim FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'unknown claim %', p_claim USING ERRCODE = 'no_data_found';
  END IF;
  SELECT * INTO v_rule FROM lfhe.claim_status_auto_rules WHERE rule_code = p_rule_code;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'AUTO_RULE_NOT_CONFIGURED: %', p_rule_code USING ERRCODE = 'object_not_in_prerequisite_state';
  END IF;
  IF lfhe.claim_is_high_impact(p_claim) THEN
    RAISE EXCEPTION 'HIGH_IMPACT_REQUIRES_HUMAN: status of high-impact claim % can only be changed by a human', p_claim
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  v_cur := lfhe.claim_current_status(p_claim);
  IF v_cur.new_status IS DISTINCT FROM v_rule.from_status THEN
    RAISE EXCEPTION 'AUTO_RULE_NOT_APPLICABLE: claim status is %, rule expects %', v_cur.new_status, v_rule.from_status
      USING ERRCODE = 'object_not_in_prerequisite_state';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM lfhe.model_runs r WHERE r.id = p_recommending_model_run AND r.status = 'SUCCEEDED') THEN
    RAISE EXCEPTION 'recommending model run % is not a SUCCEEDED run', p_recommending_model_run
      USING ERRCODE = 'object_not_in_prerequisite_state';
  END IF;
  INSERT INTO lfhe.claim_status_history (claim_id, old_status, new_status, basis, actor_type, auto_rule_code,
    recommending_model_run_id, high_impact_at_change, reason)
  VALUES (p_claim, v_cur.new_status, v_rule.to_status, 'AUTOMATIC_RULE', 'WORKER', v_rule.rule_code,
    p_recommending_model_run, false, coalesce(p_reason, v_rule.description))
  RETURNING id INTO v_id;
  RETURN v_id;
END $$;
REVOKE ALL ON FUNCTION lfhe.apply_automatic_claim_status(uuid, text, uuid, text)
  FROM PUBLIC, anon, authenticated, service_role, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.apply_automatic_claim_status(uuid, text, uuid, text) TO lfhe_worker;

-- ---------------------------------------------------------------------------
-- HUMAN_ONLY functions
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.review_claim(
  p_claim_id uuid, p_claim_hash text, p_expected_previous_review_id uuid,
  p_decision lfhe.review_decision, p_reason text, p_modifications jsonb DEFAULT NULL)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('CLAIM_REVIEW');
  v_claim lfhe.claims%ROWTYPE;
  v_last  uuid;
  v_mods  jsonb := coalesce(p_modifications, '{}'::jsonb);
  v_id    uuid;
BEGIN
  IF p_reason IS NULL OR length(btrim(p_reason)) < 5 THEN
    RAISE EXCEPTION 'a reason is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  SELECT * INTO v_claim FROM lfhe.claims WHERE id = p_claim_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'unknown claim %', p_claim_id USING ERRCODE = 'no_data_found';
  END IF;
  IF v_claim.claim_hash IS DISTINCT FROM p_claim_hash THEN
    RAISE EXCEPTION 'REVIEW_OBJECT_MISMATCH: claim hash does not match the reviewed content'
      USING ERRCODE = 'check_violation';
  END IF;
  SELECT id INTO v_last FROM lfhe.claim_reviews WHERE claim_id = p_claim_id ORDER BY seq DESC LIMIT 1;
  IF v_last IS DISTINCT FROM p_expected_previous_review_id THEN
    RAISE EXCEPTION 'REVIEW_STALE: claim % has a newer review than the one the decision was based on', p_claim_id
      USING ERRCODE = 'serialization_failure';
  END IF;
  IF jsonb_typeof(v_mods) <> 'object' OR EXISTS (SELECT 1 FROM jsonb_object_keys(v_mods) k
       WHERE k NOT IN ('claim_text_normalised', 'claim_type', 'attribution')) THEN
    RAISE EXCEPTION 'modifications may only contain claim_text_normalised, claim_type, attribution'
      USING ERRCODE = 'invalid_parameter_value';
  END IF;
  IF (p_decision = 'MODIFY_AND_APPROVE') <> (v_mods <> '{}'::jsonb) THEN
    RAISE EXCEPTION 'modifications are required for, and only allowed with, MODIFY_AND_APPROVE'
      USING ERRCODE = 'invalid_parameter_value';
  END IF;
  INSERT INTO lfhe.claim_reviews (claim_id, claim_hash, previous_review_id, decision, reviewer_user_id, reason,
    modified_claim_text_normalised, modified_claim_type, modified_attribution, high_impact_at_review)
  VALUES (p_claim_id, p_claim_hash, v_last, p_decision, v_actor, p_reason,
    v_mods ->> 'claim_text_normalised', (v_mods ->> 'claim_type')::lfhe.claim_type, v_mods ->> 'attribution',
    lfhe.claim_is_high_impact(p_claim_id))
  RETURNING id INTO v_id;
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.review_claim(uuid, text, uuid, lfhe.review_decision, text, jsonb) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.set_claim_status(
  p_claim_id uuid, p_expected_current_status lfhe.claim_status, p_new_status lfhe.claim_status,
  p_reason text, p_review_id uuid DEFAULT NULL)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('CLAIM_REVIEW');
  v_cur   lfhe.claim_status_history;
  v_id    uuid;
BEGIN
  IF p_reason IS NULL OR length(btrim(p_reason)) < 5 THEN
    RAISE EXCEPTION 'a reason is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  PERFORM 1 FROM lfhe.claims WHERE id = p_claim_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'unknown claim %', p_claim_id USING ERRCODE = 'no_data_found';
  END IF;
  v_cur := lfhe.claim_current_status(p_claim_id);
  IF v_cur.new_status IS DISTINCT FROM p_expected_current_status THEN
    RAISE EXCEPTION 'STATUS_STALE: claim status is %, not %', v_cur.new_status, p_expected_current_status
      USING ERRCODE = 'serialization_failure';
  END IF;
  IF p_review_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM lfhe.claim_reviews r
                                             WHERE r.id = p_review_id AND r.claim_id = p_claim_id) THEN
    RAISE EXCEPTION 'review % does not belong to claim %', p_review_id, p_claim_id USING ERRCODE = 'check_violation';
  END IF;
  INSERT INTO lfhe.claim_status_history (claim_id, old_status, new_status, basis, actor_type, actor_user_id,
    review_id, high_impact_at_change, reason)
  VALUES (p_claim_id, v_cur.new_status, p_new_status, 'HUMAN_DECISION', 'HUMAN', v_actor, p_review_id,
    lfhe.claim_is_high_impact(p_claim_id), p_reason)
  RETURNING id INTO v_id;
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.set_claim_status(uuid, lfhe.claim_status, lfhe.claim_status, text, uuid) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.mark_claim_high_impact(
  p_claim_id uuid, p_high_impact boolean, p_reasons lfhe.high_impact_reason[], p_reason text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor   uuid := lfhe.require_human_permission('CLAIM_REVIEW');
  v_reasons lfhe.high_impact_reason[];
BEGIN
  IF p_reason IS NULL OR length(btrim(p_reason)) < 5 THEN
    RAISE EXCEPTION 'a reason is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  v_reasons := CASE WHEN p_high_impact THEN
    ARRAY(SELECT DISTINCT r FROM unnest(coalesce(p_reasons, '{}') || 'HUMAN_MARKED_HIGH_IMPACT'::lfhe.high_impact_reason) r ORDER BY r)
    ELSE '{}' END;
  RETURN lfhe.record_claim_high_impact(p_claim_id, p_high_impact, v_reasons, v_actor, p_reason);
END $$;
COMMENT ON FUNCTION lfhe.mark_claim_high_impact(uuid, boolean, lfhe.high_impact_reason[], text) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.decide_high_impact_revalidation(
  p_revalidation_id uuid, p_approve boolean, p_reason text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('CLAIM_REVIEW');
  v_rv    lfhe.claim_revalidations%ROWTYPE;
  v_cur   lfhe.claim_status_history;
  v_auto  lfhe.claim_status_history%ROWTYPE;
BEGIN
  IF p_reason IS NULL OR length(btrim(p_reason)) < 5 THEN
    RAISE EXCEPTION 'a reason is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  SELECT * INTO v_rv FROM lfhe.claim_revalidations WHERE id = p_revalidation_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'unknown revalidation %', p_revalidation_id USING ERRCODE = 'no_data_found';
  END IF;
  PERFORM 1 FROM lfhe.claims WHERE id = v_rv.claim_id FOR UPDATE;
  INSERT INTO lfhe.claim_revalidation_decisions (revalidation_id, decision, actor_user_id, reason)
  VALUES (p_revalidation_id, CASE WHEN p_approve THEN 'APPROVED' ELSE 'REJECTED' END, v_actor, p_reason);
  IF NOT p_approve THEN
    -- Revert the automatically assigned status to the status it replaced.
    SELECT * INTO v_auto FROM lfhe.claim_status_history WHERE id = v_rv.status_history_id;
    v_cur := lfhe.claim_current_status(v_rv.claim_id);
    IF v_cur.id = v_auto.id THEN
      INSERT INTO lfhe.claim_status_history (claim_id, old_status, new_status, basis, actor_type, actor_user_id,
        high_impact_at_change, high_impact_revalidation, reason)
      VALUES (v_rv.claim_id, v_cur.new_status, v_auto.old_status, 'HIGH_IMPACT_REVALIDATION_REJECTED', 'HUMAN',
        v_actor, true, true, p_reason);
    END IF;
  END IF;
END $$;
COMMENT ON FUNCTION lfhe.decide_high_impact_revalidation(uuid, boolean, text) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.create_entity(
  p_canonical_name text, p_entity_type lfhe.entity_type, p_description text, p_reason text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('ENTITY_MANAGE');
  v_id    uuid;
BEGIN
  INSERT INTO lfhe.entities (canonical_name, entity_type, description, created_by, reason)
  VALUES (p_canonical_name, p_entity_type, p_description, v_actor, p_reason) RETURNING id INTO v_id;
  INSERT INTO lfhe.entity_aliases (entity_id, alias_text, alias_normalised, alias_basis, created_by)
  VALUES (v_id, p_canonical_name, lfhe.normalise_entity_name(p_canonical_name),
          'CANONICAL_NAME: canonical name set by the creating analyst', v_actor);
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.create_entity(text, lfhe.entity_type, text, text) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.add_entity_alias(p_entity_id uuid, p_alias text, p_language text, p_basis text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('ENTITY_MANAGE');
  v_id    uuid;
BEGIN
  INSERT INTO lfhe.entity_aliases (entity_id, alias_text, alias_normalised, language, alias_basis, created_by)
  VALUES (p_entity_id, p_alias, lfhe.normalise_entity_name(p_alias), p_language, p_basis, v_actor)
  RETURNING id INTO v_id;
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.add_entity_alias(uuid, text, text, text) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.link_entity_mention(
  p_mention_id uuid, p_resolution lfhe.entity_resolution_status, p_entity_id uuid, p_reason text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('ENTITY_MANAGE');
  v_id    uuid;
BEGIN
  IF p_resolution = 'AMBIGUOUS' THEN
    RAISE EXCEPTION 'a human link is RESOLVED or UNRESOLVED' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtext('lfhe.mention:' || p_mention_id::text));
  INSERT INTO lfhe.entity_links (mention_id, resolution_status, entity_id, method, actor_user_id, reason)
  VALUES (p_mention_id, p_resolution, p_entity_id, 'HUMAN', v_actor, p_reason) RETURNING id INTO v_id;
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.link_entity_mention(uuid, lfhe.entity_resolution_status, uuid, text) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.create_entity_relationship(
  p_subject uuid, p_relation_type text, p_object uuid, p_basis text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('ENTITY_MANAGE');
  v_id    uuid;
BEGIN
  INSERT INTO lfhe.entity_relationships (subject_entity_id, relation_type, object_entity_id, basis, created_by)
  VALUES (p_subject, p_relation_type, p_object, p_basis, v_actor) RETURNING id INTO v_id;
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.create_entity_relationship(uuid, text, uuid, text) IS 'HUMAN_ONLY';

REVOKE ALL ON FUNCTION
  lfhe.review_claim(uuid, text, uuid, lfhe.review_decision, text, jsonb),
  lfhe.set_claim_status(uuid, lfhe.claim_status, lfhe.claim_status, text, uuid),
  lfhe.mark_claim_high_impact(uuid, boolean, lfhe.high_impact_reason[], text),
  lfhe.decide_high_impact_revalidation(uuid, boolean, text),
  lfhe.create_entity(text, lfhe.entity_type, text, text),
  lfhe.add_entity_alias(uuid, text, text, text),
  lfhe.link_entity_mention(uuid, lfhe.entity_resolution_status, uuid, text),
  lfhe.create_entity_relationship(uuid, text, uuid, text)
  FROM PUBLIC, anon, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION
  lfhe.review_claim(uuid, text, uuid, lfhe.review_decision, text, jsonb),
  lfhe.set_claim_status(uuid, lfhe.claim_status, lfhe.claim_status, text, uuid),
  lfhe.mark_claim_high_impact(uuid, boolean, lfhe.high_impact_reason[], text),
  lfhe.decide_high_impact_revalidation(uuid, boolean, text),
  lfhe.create_entity(text, lfhe.entity_type, text, text),
  lfhe.add_entity_alias(uuid, text, text, text),
  lfhe.link_entity_mention(uuid, lfhe.entity_resolution_status, uuid, text),
  lfhe.create_entity_relationship(uuid, text, uuid, text)
  TO authenticated;

-- ---------------------------------------------------------------------------
-- Taxonomy assignments (M03)
-- ---------------------------------------------------------------------------
CREATE TABLE lfhe.claim_classification_results (
  model_run_id              uuid PRIMARY KEY REFERENCES lfhe.model_runs(id),
  id                        uuid NOT NULL UNIQUE DEFAULT pg_catalog.gen_random_uuid(),
  model_run_status          lfhe.model_run_status NOT NULL,
  output_status             text CHECK (output_status IN ('SUCCESS', 'SUCCESS_WITH_WARNINGS',
                              'INSUFFICIENT_INFORMATION', 'AMBIGUOUS', 'FAILED', 'HUMAN_REVIEW_REQUIRED')),
  outcome                   text NOT NULL CHECK (outcome IN ('ASSIGNMENTS_PERSISTED', 'NO_ASSIGNMENTS',
                              'OUTPUT_REJECTED', 'INSUFFICIENT_INFORMATION', 'HUMAN_REVIEW_REQUIRED',
                              'SCHEMA_VALIDATION_FAILED', 'PROVIDER_ERROR')),
  taxonomy_version          text NOT NULL,
  classification_confidence lfhe.assignment_confidence,
  assignments_persisted     integer NOT NULL CHECK (assignments_persisted >= 0),
  rejection_reasons         text[] NOT NULL DEFAULT '{}',
  human_review_required     boolean NOT NULL,
  warnings                  jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(warnings) = 'array'),
  repair_of_model_run_id    uuid REFERENCES lfhe.model_runs(id),
  created_at                timestamptz NOT NULL DEFAULT now(),
  CHECK ((outcome = 'ASSIGNMENTS_PERSISTED') = (assignments_persisted > 0)),
  CHECK ((outcome = 'OUTPUT_REJECTED') = (cardinality(rejection_reasons) > 0))
);
CREATE TABLE lfhe.taxonomy_assignments (
  id                 uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  model_run_id       uuid NOT NULL REFERENCES lfhe.claim_classification_results(model_run_id),
  taxonomy_type      lfhe.taxonomy_type NOT NULL,
  taxonomy_id        text NOT NULL,
  target_object_type text NOT NULL CHECK (target_object_type = 'CLAIM'),
  target_object_id   uuid NOT NULL REFERENCES lfhe.claims(id),
  -- M03 output field "confidence" (assignment confidence; NOT analytic confidence)
  assignment_confidence lfhe.assignment_confidence NOT NULL,
  created_at         timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (taxonomy_id, taxonomy_type) REFERENCES lfhe.taxonomy_items (id, taxonomy_type),
  UNIQUE (model_run_id, target_object_id, taxonomy_id)
);
CREATE INDEX taxonomy_assignments_target_idx ON lfhe.taxonomy_assignments (target_object_id);

CREATE OR REPLACE FUNCTION lfhe.taxonomy_assignment_guard()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_run lfhe.model_runs%ROWTYPE;
  v_res lfhe.claim_classification_results%ROWTYPE;
BEGIN
  SELECT * INTO v_run FROM lfhe.model_runs WHERE id = NEW.model_run_id;
  SELECT * INTO v_res FROM lfhe.claim_classification_results WHERE model_run_id = NEW.model_run_id;
  IF v_run.module_code IS DISTINCT FROM 'M03_CLASSIFIER' OR v_run.status IS DISTINCT FROM 'SUCCEEDED' THEN
    RAISE EXCEPTION 'TAXONOMY_PROVENANCE_INVALID: assignment must come from a SUCCEEDED M03_CLASSIFIER run'
      USING ERRCODE = 'check_violation';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM lfhe.taxonomy_items t WHERE t.id = NEW.taxonomy_id
                 AND t.taxonomy_type = NEW.taxonomy_type AND t.taxonomy_version = v_res.taxonomy_version) THEN
    RAISE EXCEPTION 'TAXONOMY_ID_NOT_IN_SUPPLIED_TAXONOMY: %', NEW.taxonomy_id USING ERRCODE = 'check_violation';
  END IF;
  IF NOT coalesce(v_run.input_manifest @> pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object(
       'object_type', 'claim', 'object_id', NEW.target_object_id::text)), false) THEN
    RAISE EXCEPTION 'TARGET_NOT_IN_MODEL_RUN_INPUT: %', NEW.target_object_id USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION lfhe.taxonomy_assignment_guard() FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
CREATE TRIGGER taxonomy_assignments_guard BEFORE INSERT ON lfhe.taxonomy_assignments
  FOR EACH ROW EXECUTE FUNCTION lfhe.taxonomy_assignment_guard();
CREATE TRIGGER taxonomy_assignments_immutable BEFORE UPDATE OR DELETE ON lfhe.taxonomy_assignments
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();
CREATE TRIGGER claim_classification_results_immutable BEFORE UPDATE OR DELETE ON lfhe.claim_classification_results
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();
CREATE TRIGGER taxonomy_assignments_audit AFTER INSERT ON lfhe.taxonomy_assignments
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_row_change('TAXONOMY_ASSIGNMENT_CREATED', '-', '-', 'taxonomy_assignment');
CREATE TRIGGER claim_classification_results_audit AFTER INSERT ON lfhe.claim_classification_results
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_row_change('CLAIM_CLASSIFICATION_RECORDED', '-', '-', 'claim_classification_result');

-- ---------------------------------------------------------------------------
-- Worker ingestion (atomic per model run)
-- ---------------------------------------------------------------------------
-- p: {model_run_id, article_snapshot_id, text_representation_id, output_status,
--     human_review_required, warnings[], repair_of_model_run_id,
--     claims: [{claim_local_id, claim_text_original, claim_text_normalised, claim_type,
--               source_statement_status, attribution, event_date, event_date_confidence,
--               entities:[{mention_text_original, entity_type}], locations:[text],
--               quantity, unit, evidence_type, evidence_directness,
--               source_uncertainty_preserved, potential_contradiction,
--               evidence_span_original:{exact_text, start, end, language, locator_type},
--               review_flags[], human_review_required}],
--     pre_rejections: [{claim_local_id, reason_codes[], candidate}]}   (Python-side checks)
-- A non-SUCCEEDED run is recorded with its outcome and no claims.
CREATE OR REPLACE FUNCTION lfhe.ingest_claim_extraction(p jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_run       lfhe.model_runs%ROWTYPE;
  v_rep       lfhe.text_representations%ROWTYPE;
  v_snap      lfhe.article_snapshots%ROWTYPE;
  v_art       lfhe.articles%ROWTYPE;
  v_claim     jsonb;
  v_span      jsonb;
  v_problems  text[];
  v_flags     text[];
  v_review    boolean;
  v_claim_id  uuid;
  v_mention   jsonb;
  v_idx       integer;
  v_persisted integer := 0;
  v_rejected  integer := 0;
  v_outcome   text;
  v_reasons   text[] := '{}';
  v_out_status text := p ->> 'output_status';
  v_ids       jsonb := '[]'::jsonb;
  v_mention_id uuid;
  v_items     jsonb := '[]'::jsonb;
  v_item      jsonb;
BEGIN
  SELECT * INTO v_run FROM lfhe.model_runs WHERE id = (p ->> 'model_run_id')::uuid;
  IF NOT FOUND OR v_run.module_code <> 'M02_CLAIM_EXTRACTOR' OR v_run.status = 'RUNNING' THEN
    RAISE EXCEPTION 'model run % is not a finished M02_CLAIM_EXTRACTOR run', p ->> 'model_run_id'
      USING ERRCODE = 'object_not_in_prerequisite_state';
  END IF;
  SELECT * INTO v_rep FROM lfhe.text_representations WHERE id = (p ->> 'text_representation_id')::uuid;
  IF NOT FOUND OR v_rep.snapshot_id IS DISTINCT FROM (p ->> 'article_snapshot_id')::uuid
     OR NOT coalesce(v_run.input_manifest @> jsonb_build_array(jsonb_build_object(
          'object_type', 'text_representation', 'object_id', v_rep.id::text)), false) THEN
    RAISE EXCEPTION 'CLAIM_PROVENANCE_INVALID: text representation is not of the snapshot or not an input of the run'
      USING ERRCODE = 'check_violation';
  END IF;
  SELECT * INTO v_snap FROM lfhe.article_snapshots WHERE id = v_rep.snapshot_id;
  SELECT * INTO v_art FROM lfhe.articles WHERE id = v_snap.article_id;

  IF v_run.status <> 'SUCCEEDED' THEN
    INSERT INTO lfhe.claim_extraction_results (model_run_id, article_snapshot_id, text_representation_id,
      model_run_status, output_status, outcome, claims_persisted, claims_rejected, human_review_required,
      warnings, repair_of_model_run_id)
    VALUES (v_run.id, v_snap.id, v_rep.id, v_run.status, NULL, v_run.status::text, 0, 0, false, '[]',
      (p ->> 'repair_of_model_run_id')::uuid);
    RETURN jsonb_build_object('outcome', v_run.status::text, 'claim_ids', '[]'::jsonb);
  END IF;

  -- Grounding is evaluated for every candidate first, so the result row
  -- (which claims reference) carries the final counts.
  FOR v_claim IN SELECT * FROM jsonb_array_elements(coalesce(p -> 'claims', '[]')) LOOP
    v_span := v_claim -> 'evidence_span_original';
    v_problems := lfhe.claim_grounding_problems(v_rep.id, v_snap.id, v_art.id, v_art.source_id,
      v_span ->> 'language', v_span ->> 'locator_type', (v_span ->> 'start')::integer,
      (v_span ->> 'end')::integer, v_span ->> 'exact_text', v_claim ->> 'claim_text_original');
    v_items := v_items || jsonb_build_array(jsonb_build_object('claim', v_claim, 'reasons', to_jsonb(v_problems)));
    IF cardinality(v_problems) = 0 THEN
      v_persisted := v_persisted + 1;
    ELSE
      v_rejected := v_rejected + 1;
    END IF;
  END LOOP;
  v_rejected := v_rejected + jsonb_array_length(coalesce(p -> 'pre_rejections', '[]'));
  v_outcome := CASE
    WHEN v_persisted > 0 THEN 'CLAIMS_PERSISTED'
    WHEN v_out_status = 'INSUFFICIENT_INFORMATION' THEN 'INSUFFICIENT_INFORMATION'
    WHEN v_out_status = 'HUMAN_REVIEW_REQUIRED' THEN 'HUMAN_REVIEW_REQUIRED'
    WHEN v_rejected > 0 THEN 'ALL_REJECTED'
    ELSE 'NO_CLAIMS' END;

  INSERT INTO lfhe.claim_extraction_results (model_run_id, article_snapshot_id, text_representation_id,
    model_run_status, output_status, outcome, claims_persisted, claims_rejected, human_review_required,
    warnings, repair_of_model_run_id)
  VALUES (v_run.id, v_snap.id, v_rep.id, v_run.status, v_out_status, v_outcome, v_persisted, v_rejected,
    coalesce((p ->> 'human_review_required')::boolean, false) OR v_out_status = 'HUMAN_REVIEW_REQUIRED',
    coalesce(p -> 'warnings', '[]'), (p ->> 'repair_of_model_run_id')::uuid);

  FOR v_claim IN SELECT * FROM jsonb_array_elements(coalesce(p -> 'pre_rejections', '[]')) LOOP
    INSERT INTO lfhe.claim_extraction_rejections (model_run_id, claim_local_id, reason_codes, grounding_failure, candidate)
    VALUES (v_run.id, v_claim ->> 'claim_local_id',
      ARRAY(SELECT jsonb_array_elements_text(v_claim -> 'reason_codes')),
      EXISTS (SELECT 1 FROM jsonb_array_elements_text(v_claim -> 'reason_codes') r
              WHERE r.value = 'CLAIM_NOT_GROUNDED_IN_ORIGINAL_SOURCE'),
      coalesce(v_claim -> 'candidate', '{}'));
  END LOOP;

  FOR v_item IN SELECT * FROM jsonb_array_elements(v_items) LOOP
    v_claim := v_item -> 'claim';
    v_problems := ARRAY(SELECT jsonb_array_elements_text(v_item -> 'reasons'));
    IF cardinality(v_problems) > 0 THEN
      INSERT INTO lfhe.claim_extraction_rejections (model_run_id, claim_local_id, reason_codes, grounding_failure, candidate)
      VALUES (v_run.id, v_claim ->> 'claim_local_id', 'CLAIM_NOT_GROUNDED_IN_ORIGINAL_SOURCE'::text || v_problems, true, v_claim);
      CONTINUE;
    END IF;
    v_span := v_claim -> 'evidence_span_original';
    v_flags := ARRAY(SELECT DISTINCT jsonb_array_elements_text(coalesce(v_claim -> 'review_flags', '[]')));
    -- entity / location mentions must occur verbatim in the original text
    IF EXISTS (SELECT 1 FROM jsonb_array_elements(coalesce(v_claim -> 'entities', '[]')) e
               WHERE strpos(v_rep.text_content, e ->> 'mention_text_original') = 0)
       OR EXISTS (SELECT 1 FROM jsonb_array_elements_text(coalesce(v_claim -> 'locations', '[]')) l
                  WHERE strpos(v_rep.text_content, l) = 0) THEN
      v_flags := ARRAY(SELECT DISTINCT x FROM unnest(v_flags || 'ENTITY_MENTION_NOT_IN_SOURCE'::text) x);
    END IF;
    v_review := coalesce((v_claim ->> 'human_review_required')::boolean, false) OR cardinality(v_flags) > 0;
    INSERT INTO lfhe.claims (source_id, article_id, article_snapshot_id, text_representation_id,
      created_by_model_run_id, claim_local_id, language_original, claim_text_original, claim_text_normalised,
      claim_type, source_statement_status, attribution, event_date, event_date_confidence, location_mentions,
      quantity, unit, evidence_type, evidence_directness, source_uncertainty_preserved, potential_contradiction,
      span_locator_type, span_start, span_end, span_exact_text, evidence_span_original,
      review_flags, human_review_required, claim_hash)
    VALUES (v_art.source_id, v_art.id, v_snap.id, v_rep.id, v_run.id, v_claim ->> 'claim_local_id',
      v_span ->> 'language', v_claim ->> 'claim_text_original', v_claim ->> 'claim_text_normalised',
      (v_claim ->> 'claim_type')::lfhe.claim_type, (v_claim ->> 'source_statement_status')::lfhe.source_statement_status,
      nullif(v_claim ->> 'attribution', ''), v_claim ->> 'event_date',
      coalesce(v_claim ->> 'event_date_confidence', 'UNKNOWN')::lfhe.timestamp_confidence,
      coalesce((SELECT jsonb_agg(l) FROM jsonb_array_elements_text(coalesce(v_claim -> 'locations', '[]')) l
                WHERE strpos(v_rep.text_content, l) > 0), '[]'),
      (v_claim ->> 'quantity')::numeric, v_claim ->> 'unit',
      (v_claim ->> 'evidence_type')::lfhe.evidence_type, (v_claim ->> 'evidence_directness')::lfhe.evidence_directness,
      (v_claim ->> 'source_uncertainty_preserved')::boolean, (v_claim ->> 'potential_contradiction')::boolean,
      v_span ->> 'locator_type', (v_span ->> 'start')::integer, (v_span ->> 'end')::integer, v_span ->> 'exact_text',
      '{}'::jsonb, v_flags, v_review, repeat('0', 64))
    RETURNING id INTO v_claim_id;
    v_ids := v_ids || to_jsonb(v_claim_id);

    INSERT INTO lfhe.claim_status_history (claim_id, old_status, new_status, basis, actor_type,
      high_impact_at_change, reason)
    VALUES (v_claim_id, NULL, 'UNVERIFIED', 'INITIAL_EXTRACTION', 'WORKER', false,
      'initial status at extraction (no corroboration assessed)');

    v_idx := 0;
    FOR v_mention IN SELECT * FROM jsonb_array_elements(coalesce(v_claim -> 'entities', '[]')) LOOP
      IF strpos(v_rep.text_content, v_mention ->> 'mention_text_original') > 0 THEN
        INSERT INTO lfhe.entity_mentions (claim_id, mention_index, mention_text_original, mention_normalised,
          entity_type_hint, model_run_id)
        VALUES (v_claim_id, v_idx, v_mention ->> 'mention_text_original',
          lfhe.normalise_entity_name(v_mention ->> 'mention_text_original'),
          (v_mention ->> 'entity_type')::lfhe.entity_type, v_run.id)
        RETURNING id INTO v_mention_id;
        PERFORM lfhe.auto_resolve_mention(v_mention_id);
      END IF;
      v_idx := v_idx + 1;
    END LOOP;
  END LOOP;

  RETURN jsonb_build_object('outcome', v_outcome, 'claim_ids', v_ids,
                            'claims_persisted', v_persisted, 'claims_rejected', v_rejected);
END $$;
REVOKE ALL ON FUNCTION lfhe.ingest_claim_extraction(jsonb) FROM PUBLIC, anon, authenticated, service_role, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.ingest_claim_extraction(jsonb) TO lfhe_worker;

-- p: {model_run_id, output_status, classification_confidence, human_review_required,
--     warnings[], repair_of_model_run_id, assignments:[{taxonomy_type, taxonomy_id,
--     target_object_type, target_object_id, confidence}]}
-- Any assignment naming an unknown taxonomy ID, a non-CLAIM target or a claim
-- that was not an input of the run rejects the WHOLE output (fail closed).
CREATE OR REPLACE FUNCTION lfhe.ingest_classification(p jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_run      lfhe.model_runs%ROWTYPE;
  v_version  text;
  v_reasons  text[] := '{}';
  v_a        jsonb;
  v_n        integer := 0;
  v_outcome  text;
  v_status   text := p ->> 'output_status';
BEGIN
  SELECT * INTO v_run FROM lfhe.model_runs WHERE id = (p ->> 'model_run_id')::uuid;
  IF NOT FOUND OR v_run.module_code <> 'M03_CLASSIFIER' OR v_run.status = 'RUNNING' THEN
    RAISE EXCEPTION 'model run % is not a finished M03_CLASSIFIER run', p ->> 'model_run_id'
      USING ERRCODE = 'object_not_in_prerequisite_state';
  END IF;
  v_version := v_run.task_parameters ->> 'taxonomy_version';
  IF v_version IS NULL OR NOT coalesce(v_run.context_manifest @> jsonb_build_array(jsonb_build_object(
       'object_type', 'taxonomy', 'object_id', v_version)), false) THEN
    RAISE EXCEPTION 'TAXONOMY_NOT_SUPPLIED: model run must name its taxonomy version and carry it as context'
      USING ERRCODE = 'check_violation';
  END IF;
  IF v_run.status <> 'SUCCEEDED' THEN
    INSERT INTO lfhe.claim_classification_results (model_run_id, model_run_status, output_status, outcome,
      taxonomy_version, assignments_persisted, human_review_required, repair_of_model_run_id)
    VALUES (v_run.id, v_run.status, NULL, v_run.status::text, v_version, 0, false, (p ->> 'repair_of_model_run_id')::uuid);
    RETURN jsonb_build_object('outcome', v_run.status::text, 'assignments', 0);
  END IF;

  FOR v_a IN SELECT * FROM jsonb_array_elements(coalesce(p -> 'assignments', '[]')) LOOP
    IF NOT EXISTS (SELECT 1 FROM lfhe.taxonomy_items t WHERE t.id = v_a ->> 'taxonomy_id'
                   AND t.taxonomy_type::text = v_a ->> 'taxonomy_type' AND t.taxonomy_version = v_version) THEN
      v_reasons := v_reasons || ('TAXONOMY_ID_NOT_IN_SUPPLIED_TAXONOMY:' || left(coalesce(v_a ->> 'taxonomy_id', 'null'), 80));
    END IF;
    IF v_a ->> 'target_object_type' IS DISTINCT FROM 'CLAIM' THEN
      v_reasons := v_reasons || 'TARGET_OBJECT_TYPE_NOT_ALLOWED'::text;
    ELSIF coalesce(v_a ->> 'target_object_id', '') !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
       OR NOT coalesce(v_run.input_manifest @> jsonb_build_array(jsonb_build_object(
            'object_type', 'claim', 'object_id', v_a ->> 'target_object_id')), false) THEN
      v_reasons := v_reasons || ('TARGET_NOT_IN_MODEL_RUN_INPUT:' || left(coalesce(v_a ->> 'target_object_id', 'null'), 80));
    END IF;
  END LOOP;
  v_n := jsonb_array_length(coalesce(p -> 'assignments', '[]'));
  v_outcome := CASE
    WHEN cardinality(v_reasons) > 0 THEN 'OUTPUT_REJECTED'
    WHEN v_n > 0 THEN 'ASSIGNMENTS_PERSISTED'
    WHEN v_status = 'INSUFFICIENT_INFORMATION' THEN 'INSUFFICIENT_INFORMATION'
    WHEN v_status = 'HUMAN_REVIEW_REQUIRED' THEN 'HUMAN_REVIEW_REQUIRED'
    ELSE 'NO_ASSIGNMENTS' END;

  INSERT INTO lfhe.claim_classification_results (model_run_id, model_run_status, output_status, outcome,
    taxonomy_version, classification_confidence, assignments_persisted, rejection_reasons,
    human_review_required, warnings, repair_of_model_run_id)
  VALUES (v_run.id, v_run.status, v_status, v_outcome, v_version,
    (p ->> 'classification_confidence')::lfhe.assignment_confidence,
    CASE WHEN v_outcome = 'ASSIGNMENTS_PERSISTED' THEN v_n ELSE 0 END,
    (SELECT coalesce(array_agg(DISTINCT r), '{}') FROM unnest(v_reasons) r),
    coalesce((p ->> 'human_review_required')::boolean, false) OR v_outcome IN ('OUTPUT_REJECTED', 'HUMAN_REVIEW_REQUIRED'),
    coalesce(p -> 'warnings', '[]'), (p ->> 'repair_of_model_run_id')::uuid);

  IF v_outcome = 'ASSIGNMENTS_PERSISTED' THEN
    INSERT INTO lfhe.taxonomy_assignments (model_run_id, taxonomy_type, taxonomy_id, target_object_type,
      target_object_id, assignment_confidence)
    SELECT DISTINCT ON (a ->> 'target_object_id', a ->> 'taxonomy_id')
      v_run.id, (a ->> 'taxonomy_type')::lfhe.taxonomy_type, a ->> 'taxonomy_id', 'CLAIM',
      (a ->> 'target_object_id')::uuid, (a ->> 'confidence')::lfhe.assignment_confidence
    FROM jsonb_array_elements(p -> 'assignments') a;
  END IF;
  RETURN jsonb_build_object('outcome', v_outcome, 'assignments',
                            CASE WHEN v_outcome = 'ASSIGNMENTS_PERSISTED' THEN v_n ELSE 0 END,
                            'rejection_reasons', to_jsonb(v_reasons));
END $$;
REVOKE ALL ON FUNCTION lfhe.ingest_classification(jsonb) FROM PUBLIC, anon, authenticated, service_role, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.ingest_classification(jsonb) TO lfhe_worker;

-- ---------------------------------------------------------------------------
-- Read access: humans need CLAIM_READ; workers read all. No direct writes.
-- ---------------------------------------------------------------------------
REVOKE ALL ON lfhe.taxonomy_items, lfhe.claim_extraction_results, lfhe.claims, lfhe.claim_extraction_rejections,
  lfhe.entities, lfhe.entity_aliases, lfhe.entity_mentions, lfhe.entity_links, lfhe.entity_relationships,
  lfhe.claim_status_auto_rules, lfhe.claim_reviews, lfhe.claim_status_history, lfhe.claim_high_impact,
  lfhe.claim_revalidations, lfhe.claim_revalidation_decisions, lfhe.claim_classification_results,
  lfhe.taxonomy_assignments, lfhe.entity_mention_resolution, lfhe.claim_entities, lfhe.claim_state,
  lfhe.claim_status_usability
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT SELECT ON lfhe.taxonomy_items, lfhe.claim_extraction_results, lfhe.claims, lfhe.claim_extraction_rejections,
  lfhe.entities, lfhe.entity_aliases, lfhe.entity_mentions, lfhe.entity_links, lfhe.entity_relationships,
  lfhe.claim_status_auto_rules, lfhe.claim_reviews, lfhe.claim_status_history, lfhe.claim_high_impact,
  lfhe.claim_revalidations, lfhe.claim_revalidation_decisions, lfhe.claim_classification_results,
  lfhe.taxonomy_assignments, lfhe.entity_mention_resolution, lfhe.claim_entities, lfhe.claim_state,
  lfhe.claim_status_usability
  TO authenticated, lfhe_worker;

DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['taxonomy_items', 'claim_extraction_results', 'claims', 'claim_extraction_rejections',
    'entities', 'entity_aliases', 'entity_mentions', 'entity_links', 'entity_relationships',
    'claim_status_auto_rules', 'claim_reviews', 'claim_status_history', 'claim_high_impact',
    'claim_revalidations', 'claim_revalidation_decisions', 'claim_classification_results',
    'taxonomy_assignments'] LOOP
    EXECUTE format('ALTER TABLE lfhe.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY %I ON lfhe.%I FOR SELECT TO authenticated USING (lfhe.has_permission(''CLAIM_READ''))',
                   t || '_read_human', t);
    EXECUTE format('CREATE POLICY %I ON lfhe.%I FOR SELECT TO lfhe_worker USING (true)', t || '_read_worker', t);
  END LOOP;
END $$;
