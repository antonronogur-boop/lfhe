-- ============================================================================
-- P1-05  Append-only, tamper-evident audit log (Enforcement Addendum G-14)
--
-- * Inserts happen ONLY through lfhe.write_audit(), which nobody may call
--   directly; it is invoked by SECURITY DEFINER trigger functions attached to
--   audited tables. An audited table change therefore cannot skip its audit
--   entry, and no application role can forge one.
-- * Hash chain: entry_hash = sha256(canonical(entry) || previous_entry_hash).
-- * CONCURRENCY (PO guardrail 1): every write takes one transaction-scoped
--   advisory lock before reading the chain head, so audited transactions are
--   serialised at the audit step and exactly one valid ordering exists.
--   seq is assigned under that lock (not from a sequence), so it is gap-free
--   and matches chain order. Cost: audited transactions serialise on commit of
--   the audit step — acceptable at prototype volume; revisit before scale-up.
-- * UPDATE / DELETE / TRUNCATE are blocked by triggers and privileges.
--   Limitation (stated, not hidden): a database owner/superuser can disable
--   triggers. The chain makes such tampering DETECTABLE (verify + exported
--   chain heads); it does not make it impossible.
-- ============================================================================

CREATE TABLE lfhe.audit_log (
  seq                 bigint PRIMARY KEY CHECK (seq > 0),
  occurred_at         timestamptz NOT NULL,
  actor_type          lfhe.actor_type NOT NULL,
  actor_user_id       uuid,
  actor_db_role       text NOT NULL,
  event_type          text NOT NULL REFERENCES lfhe.audit_event_types(code),
  object_type         text NOT NULL,
  object_id           text NOT NULL,
  previous_state      jsonb,
  new_state           jsonb,
  metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,
  previous_entry_hash text NOT NULL CHECK (previous_entry_hash ~ '^[0-9a-f]{64}$'),
  entry_hash          text NOT NULL UNIQUE CHECK (entry_hash ~ '^[0-9a-f]{64}$'),
  CHECK (actor_type <> 'HUMAN' OR actor_user_id IS NOT NULL)
);
CREATE INDEX audit_log_object_idx ON lfhe.audit_log (object_type, object_id);
CREATE INDEX audit_log_event_idx ON lfhe.audit_log (event_type, occurred_at);

-- Canonical serialisation, version 'v1'. tests/… and lfhe_shared.audit
-- re-implement it independently to verify the chain outside the database.
CREATE OR REPLACE FUNCTION lfhe.audit_canonical_v1(
  p_seq bigint, p_occurred_at timestamptz, p_actor_type lfhe.actor_type,
  p_actor_user_id uuid, p_actor_db_role text, p_event_type text,
  p_object_type text, p_object_id text, p_previous_state jsonb,
  p_new_state jsonb, p_metadata jsonb, p_previous_entry_hash text
) RETURNS text LANGUAGE sql IMMUTABLE
SET search_path = pg_catalog, pg_temp AS $$
  SELECT concat_ws(E'\n',
    'v1',
    p_seq::text,
    to_char(p_occurred_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
    p_actor_type::text,
    coalesce(p_actor_user_id::text, ''),
    p_actor_db_role,
    p_event_type,
    p_object_type,
    p_object_id,
    coalesce(p_previous_state::text, 'null'),
    coalesce(p_new_state::text, 'null'),
    p_metadata::text,
    p_previous_entry_hash)
$$;
REVOKE ALL ON FUNCTION lfhe.audit_canonical_v1(bigint, timestamptz, lfhe.actor_type, uuid, text, text, text, text, jsonb, jsonb, jsonb, text) FROM PUBLIC;

CREATE OR REPLACE FUNCTION lfhe.write_audit(
  p_event_type text, p_object_type text, p_object_id text,
  p_previous_state jsonb, p_new_state jsonb, p_metadata jsonb DEFAULT '{}'::jsonb
) RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_genesis    constant text := repeat('0', 64);
  v_prev_seq   bigint;
  v_prev_hash  text;
  v_seq        bigint;
  v_at         timestamptz;
  v_actor_uid  uuid := lfhe.current_human_user();
  v_actor_type lfhe.actor_type;
  v_hash       text;
BEGIN
  -- Single global ordering point for the chain (released at commit/rollback).
  PERFORM pg_catalog.pg_advisory_xact_lock(7368431201);

  SELECT a.seq, a.entry_hash INTO v_prev_seq, v_prev_hash
  FROM lfhe.audit_log a ORDER BY a.seq DESC LIMIT 1;

  v_seq := coalesce(v_prev_seq, 0) + 1;
  v_prev_hash := coalesce(v_prev_hash, v_genesis);
  v_at := pg_catalog.clock_timestamp();

  IF v_actor_uid IS NOT NULL THEN
    v_actor_type := 'HUMAN';
  -- pg_has_role() is true for superusers for every role, so exclude them:
  -- a superuser/owner session is SYSTEM, never WORKER.
  ELSIF NOT (SELECT r.rolsuper FROM pg_catalog.pg_roles r WHERE r.rolname = session_user)
        AND pg_catalog.pg_has_role(session_user, 'lfhe_worker', 'MEMBER') THEN
    v_actor_type := 'WORKER';
  ELSE
    v_actor_type := 'SYSTEM';
  END IF;

  v_hash := pg_catalog.encode(extensions.digest(pg_catalog.convert_to(
      lfhe.audit_canonical_v1(v_seq, v_at, v_actor_type, v_actor_uid, session_user::text,
        p_event_type, p_object_type, p_object_id, p_previous_state, p_new_state,
        coalesce(p_metadata, '{}'::jsonb), v_prev_hash),
      'UTF8'), 'sha256'), 'hex');

  INSERT INTO lfhe.audit_log (seq, occurred_at, actor_type, actor_user_id, actor_db_role,
    event_type, object_type, object_id, previous_state, new_state, metadata,
    previous_entry_hash, entry_hash)
  VALUES (v_seq, v_at, v_actor_type, v_actor_uid, session_user::text,
    p_event_type, p_object_type, p_object_id, p_previous_state, p_new_state,
    coalesce(p_metadata, '{}'::jsonb), v_prev_hash, v_hash);

  RETURN v_seq;
END $$;
REVOKE ALL ON FUNCTION lfhe.write_audit(text, text, text, jsonb, jsonb, jsonb)
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator;

-- ---------------------------------------------------------------------------
-- Immutability
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.audit_log_block_mutation()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  RAISE EXCEPTION 'lfhe.audit_log is append-only (% blocked)', TG_OP
    USING ERRCODE = 'insufficient_privilege';
END $$;
REVOKE ALL ON FUNCTION lfhe.audit_log_block_mutation() FROM PUBLIC;

CREATE TRIGGER audit_log_no_update_delete
  BEFORE UPDATE OR DELETE ON lfhe.audit_log
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_log_block_mutation();
CREATE TRIGGER audit_log_no_truncate
  BEFORE TRUNCATE ON lfhe.audit_log
  FOR EACH STATEMENT EXECUTE FUNCTION lfhe.audit_log_block_mutation();

REVOKE ALL ON lfhe.audit_log FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator;
GRANT SELECT ON lfhe.audit_log TO authenticated;
ALTER TABLE lfhe.audit_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY audit_log_read ON lfhe.audit_log FOR SELECT TO authenticated
  USING (lfhe.has_permission('AUDIT_READ'));

-- ---------------------------------------------------------------------------
-- Generic row-change audit trigger.
--   TG_ARGV[0] event on INSERT, [1] on UPDATE, [2] on DELETE ('-' = none),
--   [3] object_type. object_id = NEW/OLD.id.
-- SECURITY DEFINER so that it may call write_audit() regardless of which
-- application role performed the change.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.audit_row_change()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_event text;
  v_old   jsonb := CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN to_jsonb(OLD) END;
  v_new   jsonb := CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN to_jsonb(NEW) END;
BEGIN
  v_event := CASE TG_OP WHEN 'INSERT' THEN TG_ARGV[0] WHEN 'UPDATE' THEN TG_ARGV[1] ELSE TG_ARGV[2] END;
  IF v_event IS NULL OR v_event = '-' THEN
    RETURN NULL;
  END IF;
  PERFORM lfhe.write_audit(v_event, TG_ARGV[3],
    coalesce(v_new ->> 'id', v_old ->> 'id'), v_old, v_new, '{}'::jsonb);
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION lfhe.audit_row_change() FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator;

-- ---------------------------------------------------------------------------
-- Audit triggers for objects that already exist
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.audit_user_roles()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_row record := CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
BEGIN
  PERFORM lfhe.write_audit('USER_ROLE_CHANGED', 'user_role',
    v_row.user_id::text || ':' || v_row.role_code,
    CASE WHEN TG_OP = 'DELETE' THEN to_jsonb(OLD) END,
    CASE WHEN TG_OP = 'INSERT' THEN to_jsonb(NEW) END,
    jsonb_build_object('operation', CASE TG_OP WHEN 'INSERT' THEN 'GRANT' ELSE 'REVOKE' END));
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION lfhe.audit_user_roles() FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator;

CREATE TRIGGER user_roles_audit
  AFTER INSERT OR DELETE ON lfhe.user_roles
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_user_roles();

CREATE OR REPLACE FUNCTION lfhe.audit_role_permissions()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_row record := CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
BEGIN
  PERFORM lfhe.write_audit('PERMISSION_CHANGED', 'role_permission',
    v_row.role_code || ':' || v_row.permission_code,
    CASE WHEN TG_OP <> 'INSERT' THEN to_jsonb(OLD) END,
    CASE WHEN TG_OP <> 'DELETE' THEN to_jsonb(NEW) END, '{}'::jsonb);
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION lfhe.audit_role_permissions() FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator;

CREATE TRIGGER role_permissions_audit
  AFTER INSERT OR UPDATE OR DELETE ON lfhe.role_permissions
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_role_permissions();

CREATE OR REPLACE FUNCTION lfhe.audit_deployment_environment()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  PERFORM lfhe.write_audit('DEPLOYMENT_ENVIRONMENT_SET', 'deployment_environment',
    NEW.environment, NULL, to_jsonb(NEW), '{}'::jsonb);
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION lfhe.audit_deployment_environment() FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator;

CREATE TRIGGER deployment_environment_audit
  AFTER INSERT ON lfhe.deployment_environment
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_deployment_environment();
