-- ============================================================================
-- P1-03  Database foundation
--   * lfhe schema and restricted roles
--   * canonical enums (Enforcement Addendum A3, G-03, G-04, Prompt Pack v1.2 §8)
--   * deployment environment record (DEV / TEST / PROD guard)
--   * audit event-type catalogue (Prompt Pack v1.2 §55 + v1.2.1 §10)
--
-- Supabase provides: schema auth, auth.uid(), roles anon / authenticated /
-- service_role, schema extensions with pgcrypto. This migration only
-- consumes them.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions;

-- ---------------------------------------------------------------------------
-- Roles
--   lfhe_worker    : group role for Python workers (collector, later pipeline)
--   lfhe_evaluator : group role for gold-standard evaluation (Phase 4+)
-- Login roles are created per environment by the operator (never here),
-- with passwords from the platform secret manager.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lfhe_worker') THEN
    CREATE ROLE lfhe_worker NOLOGIN NOINHERIT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lfhe_evaluator') THEN
    CREATE ROLE lfhe_evaluator NOLOGIN NOINHERIT;
  END IF;
END $$;

CREATE SCHEMA IF NOT EXISTS lfhe;
REVOKE ALL ON SCHEMA lfhe FROM PUBLIC;
GRANT USAGE ON SCHEMA lfhe TO authenticated, lfhe_worker, lfhe_evaluator;
GRANT USAGE ON SCHEMA extensions TO lfhe_worker;

-- No implicit privileges on future objects in lfhe for anyone.
ALTER DEFAULT PRIVILEGES IN SCHEMA lfhe REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA lfhe REVOKE ALL ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA lfhe REVOKE ALL ON SEQUENCES FROM PUBLIC;

-- ---------------------------------------------------------------------------
-- Canonical human-decision enums (Enforcement Addendum A3). One vocabulary
-- per function; used by every UI and backend path (G-10).
-- ---------------------------------------------------------------------------
CREATE TYPE lfhe.review_decision AS ENUM (
  'APPROVE', 'MODIFY_AND_APPROVE', 'REJECT', 'ESCALATE', 'REQUEST_REPROCESSING'
);
CREATE TYPE lfhe.event_action AS ENUM (
  'CREATE', 'UPDATE', 'MERGE', 'SPLIT', 'KEEP_SEPARATE', 'SUPERSEDE', 'REJECT'
);
CREATE TYPE lfhe.release_decision AS ENUM (
  'APPROVE_FOR_RELEASE', 'RETURN_FOR_REVISION', 'REJECT_RELEASE'
);
CREATE TYPE lfhe.security_review_status AS ENUM (
  'PENDING', 'APPROVED', 'RETURN_FOR_REVISION', 'REJECTED'
);

-- ---------------------------------------------------------------------------
-- Time / eligibility vocabulary (G-03, G-04, Prompt Pack v1.2 §8)
-- ---------------------------------------------------------------------------
CREATE TYPE lfhe.report_mode AS ENUM ('LIVE', 'REPLAY');

CREATE TYPE lfhe.public_availability_basis AS ENUM (
  -- Enforcement Addendum G-03 base values
  'SOURCE_PUBLISHED_TIMESTAMP', 'RSS_TIMESTAMP', 'SITEMAP_TIMESTAMP',
  'HTTP_METADATA', 'ARCHIVED_SNAPSHOT', 'MANUAL_VERIFICATION', 'UNKNOWN',
  -- Prompt Pack v1.2 §8 replay-grade values
  'ARCHIVED_SNAPSHOT_VERIFIED', 'SOURCE_TIMESTAMP_WITH_FROZEN_SNAPSHOT',
  'RSS_TIMESTAMP_WITH_FROZEN_CONTENT', 'SITEMAP_TIMESTAMP_WITH_FROZEN_CONTENT',
  'SIGNED_OR_VERSIONED_OFFICIAL_ARCHIVE', 'MANUAL_VERIFICATION_WITH_ARCHIVED_EVIDENCE',
  -- Prompt Pack v1.2 §8 normally-insufficient values
  'INFERRED', 'CURRENT_PAGE_ONLY', 'LOW_CONFIDENCE_TIMESTAMP'
);

-- Confidence about a *timestamp* only. Deliberately not an analytic
-- confidence scale (see PROJECT_STATUS DC-01).
CREATE TYPE lfhe.timestamp_confidence AS ENUM ('HIGH', 'MODERATE', 'LOW', 'UNKNOWN');
CREATE TYPE lfhe.date_status AS ENUM ('OK', 'DATE_UNCERTAIN');

-- ---------------------------------------------------------------------------
-- Operational vocabulary
-- ---------------------------------------------------------------------------
CREATE TYPE lfhe.actor_type AS ENUM ('HUMAN', 'WORKER', 'SYSTEM');

CREATE TYPE lfhe.retention_mode AS ENUM ('FULL', 'PERMITTED_EXCERPT', 'METADATA_ONLY');

-- DS §28 preferred order. BROWSER_AUTOMATION is listed for completeness but
-- has no adapter in Phase 1 and cannot be approved until one exists.
CREATE TYPE lfhe.collection_method AS ENUM (
  'OFFICIAL_API', 'RSS_ATOM', 'STRUCTURED_FEED', 'HTTP_FETCH', 'BROWSER_AUTOMATION'
);

CREATE TYPE lfhe.job_status AS ENUM (
  'PENDING', 'RUNNING', 'SUCCESS', 'FAILED', 'HUMAN_REVIEW', 'SKIPPED'
);

CREATE TYPE lfhe.collection_run_status AS ENUM (
  'RUNNING', 'SUCCESS', 'PARTIAL', 'FAILED', 'SOURCE_UNAVAILABLE'
);

-- ---------------------------------------------------------------------------
-- Deployment environment: recorded once per database by the operator.
-- Workers compare it with LFHE_ENV at connect time (lfhe_shared.db).
-- ---------------------------------------------------------------------------
CREATE TABLE lfhe.deployment_environment (
  singleton   boolean PRIMARY KEY DEFAULT true CHECK (singleton),
  environment text NOT NULL CHECK (environment IN ('DEV', 'TEST', 'PROD')),
  set_at      timestamptz NOT NULL DEFAULT now(),
  set_by_role text NOT NULL DEFAULT session_user
);
GRANT SELECT ON lfhe.deployment_environment TO authenticated, lfhe_worker, lfhe_evaluator;

CREATE OR REPLACE FUNCTION lfhe.deployment_environment_immutable()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  RAISE EXCEPTION 'lfhe.deployment_environment is immutable once set'
    USING ERRCODE = 'insufficient_privilege';
END $$;

CREATE TRIGGER deployment_environment_no_update
  BEFORE UPDATE OR DELETE ON lfhe.deployment_environment
  FOR EACH ROW EXECUTE FUNCTION lfhe.deployment_environment_immutable();

-- Operator-only (owner); EXECUTE is not granted to any application role.
CREATE OR REPLACE FUNCTION lfhe.set_deployment_environment(p_env text)
RETURNS void LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  INSERT INTO lfhe.deployment_environment (environment) VALUES (p_env);
END $$;
REVOKE ALL ON FUNCTION lfhe.set_deployment_environment(text) FROM PUBLIC;

-- ---------------------------------------------------------------------------
-- Audit event-type catalogue. A reference table (not an enum) so later
-- phases extend it with a migration INSERT. audit_log.event_type has an FK.
-- ---------------------------------------------------------------------------
CREATE TABLE lfhe.audit_event_types (
  code        text PRIMARY KEY CHECK (code ~ '^[A-Z][A-Z0-9_]*$'),
  spec_source text NOT NULL,
  description text
);
GRANT SELECT ON lfhe.audit_event_types TO authenticated, lfhe_worker, lfhe_evaluator;

INSERT INTO lfhe.audit_event_types (code, spec_source) VALUES
  -- Module Prompt Pack v1.2 §55
  ('SOURCE_CREATED', 'MPP v1.2 §55'), ('SOURCE_UPDATED', 'MPP v1.2 §55'),
  ('SOURCE_ACTIVATED', 'MPP v1.2 §55'), ('SOURCE_DEACTIVATED', 'MPP v1.2 §55'),
  ('ARTICLE_SNAPSHOT_CREATED', 'MPP v1.2 §55'),
  ('CLAIM_CREATED', 'MPP v1.2 §55'), ('CLAIM_MODIFIED', 'MPP v1.2 §55'),
  ('CLAIM_STATUS_CHANGED', 'MPP v1.2 §55'), ('HIGH_IMPACT_CLAIM_REVIEWED', 'MPP v1.2 §55'),
  ('LINEAGE_RECOMMENDATION_CREATED', 'MPP v1.2 §55'), ('LINEAGE_VALIDATED', 'MPP v1.2 §55'),
  ('INDEPENDENCE_GROUP_CHANGED', 'MPP v1.2 §55'),
  ('EVENT_CREATED', 'MPP v1.2 §55'), ('EVENT_UPDATED', 'MPP v1.2 §55'),
  ('EVENT_MERGED', 'MPP v1.2 §55'), ('EVENT_SPLIT', 'MPP v1.2 §55'),
  ('EVENT_SUPERSEDED', 'MPP v1.2 §55'), ('EVENT_KEEP_SEPARATE_DECISION', 'MPP v1.2 §55'),
  ('EVENT_REJECTED', 'MPP v1.2 §55'),
  ('RELEVANCE_SCORE_OVERRIDDEN', 'MPP v1.2 §55'), ('EXECUTIVE_RELEVANCE_VALIDATED', 'MPP v1.2 §55'),
  ('ASSESSMENT_CREATED', 'MPP v1.2 §55'), ('ASSESSMENT_MODIFIED', 'MPP v1.2 §55'),
  ('ASSESSMENT_APPROVED', 'MPP v1.2 §55'), ('ASSESSMENT_REJECTED', 'MPP v1.2 §55'),
  ('FINAL_CONFIDENCE_SET', 'MPP v1.2 §55'), ('FINAL_CONFIDENCE_CHANGED', 'MPP v1.2 §55'),
  ('CHALLENGER_FLAG_DISPOSITIONED', 'MPP v1.2 §55'),
  ('REPORT_CANDIDATE_SELECTED', 'MPP v1.2 §55'), ('REPORT_CANDIDATE_REMOVED', 'MPP v1.2 §55'),
  ('REPORT_CONTENT_REORDERED', 'MPP v1.2 §55'), ('REPORT_TEXT_EDITED', 'MPP v1.2 §55'),
  ('QA_RUN_CREATED', 'MPP v1.2 §55'), ('QA_RESULT_CHANGED_BY_RERUN', 'MPP v1.2 §55'),
  ('QA_WARNING_ACKNOWLEDGED', 'MPP v1.2 §55'), ('SECURITY_REVIEW_DECIDED', 'MPP v1.2 §55'),
  ('REPORT_RELEASE_APPROVED', 'MPP v1.2 §55'), ('REPORT_RELEASE_REJECTED', 'MPP v1.2 §55'),
  ('REPORT_CORRECTION_CREATED', 'MPP v1.2 §55'),
  ('PROMPT_VERSION_CREATED', 'MPP v1.2 §55'), ('PROMPT_VERSION_ACTIVATED', 'MPP v1.2 §55'),
  ('MODEL_CONFIGURATION_CHANGED', 'MPP v1.2 §55'),
  ('USER_ROLE_CHANGED', 'MPP v1.2 §55'), ('PERMISSION_CHANGED', 'MPP v1.2 §55'),
  -- Module Prompt Pack v1.2.1 §10
  ('REVIEW_ESCALATED', 'MPP v1.2.1 §10'), ('REPROCESSING_REQUESTED', 'MPP v1.2.1 §10'),
  ('RELEASE_RETURNED_FOR_REVISION', 'MPP v1.2.1 §10'),
  ('REFERENCE_CONTEXT_CREATED', 'MPP v1.2.1 §10'), ('REFERENCE_CONTEXT_UPDATED', 'MPP v1.2.1 §10'),
  ('REFERENCE_CONTEXT_VERSION_CREATED', 'MPP v1.2.1 §10'),
  ('REFERENCE_CONTEXT_APPROVED', 'MPP v1.2.1 §10'), ('REFERENCE_CONTEXT_REJECTED', 'MPP v1.2.1 §10'),
  ('CLAIM_MARKED_HIGH_IMPACT_BY_HUMAN', 'MPP v1.2.1 §10'),
  ('HIGH_IMPACT_REVALIDATION_REQUIRED', 'MPP v1.2.1 §10'),
  ('HIGH_IMPACT_REVALIDATION_APPROVED', 'MPP v1.2.1 §10'),
  ('HIGH_IMPACT_REVALIDATION_REJECTED', 'MPP v1.2.1 §10'),
  ('EVENT_MANUALLY_PROMOTED', 'MPP v1.2.1 §10'), ('MANUAL_ASSESSMENT_REQUESTED', 'MPP v1.2.1 §10'),
  ('REPLAY_EVIDENCE_ELIGIBILITY_OVERRIDDEN', 'MPP v1.2.1 §10'),
  ('REPLAY_EVIDENCE_EXCLUDED_BY_HUMAN', 'MPP v1.2.1 §10'),
  ('REPORT_RELEASE_MANIFEST_CREATED', 'MPP v1.2.1 §10'),
  ('REPORT_VERSION_CREATED', 'MPP v1.2.1 §10'), ('REPORT_VERSION_HASH_CHANGED', 'MPP v1.2.1 §10'),
  ('ANALYTICAL_APPROVAL_INVALIDATED', 'MPP v1.2.1 §10'),
  ('SECURITY_APPROVAL_INVALIDATED', 'MPP v1.2.1 §10'),
  ('QA_INVALIDATED_BY_REPORT_CHANGE', 'MPP v1.2.1 §10'),
  ('CLAIM_EXTRACTION_GROUNDING_FAILED', 'MPP v1.2.1 §10'),
  -- Phase 1 implementation additions (documented in docs/audit-catalogue.md)
  ('DEPLOYMENT_ENVIRONMENT_SET', 'Phase 1 impl.'),
  ('SOURCE_COLLECTION_METHOD_APPROVED', 'Phase 1 impl.'),
  ('SOURCE_COLLECTION_METHOD_REVOKED', 'Phase 1 impl.'),
  ('ARTICLE_CREATED', 'Phase 1 impl.'),
  ('TEXT_REPRESENTATION_CREATED', 'Phase 1 impl.'),
  ('PROMPT_VERSION_DEACTIVATED', 'Phase 1 impl.');
