-- ============================================================================
-- P1-04  Authentication and RBAC foundation
--
-- * roles / permissions / role_permissions: explicit, data-driven matrix
--   (Enforcement Addendum G-11). Phase-introduced permissions for later
--   phases are seeded now so the matrix is reviewable as a whole; no function
--   uses them until their phase.
-- * user_roles keyed on auth.users (Supabase Auth).
-- * Human-authority guard: lfhe.require_human_permission().
--
-- SECURITY DEFINER HARDENING (PO guardrail 2) — every definer function:
--   - SET search_path = pg_catalog, pg_temp (no user-writable schema);
--   - schema-qualifies every object it touches;
--   - has EXECUTE revoked from PUBLIC, anon, service_role, lfhe_worker and
--     granted only to the roles that need it;
--   - verifies identity + permission inside the function;
--   - rejects worker sessions and non-'authenticated' roles explicitly.
-- Functions carrying COMMENT 'HUMAN_ONLY' are checked by a meta-test.
-- ============================================================================

-- Fix-forward for 20261011000100: per-schema ALTER DEFAULT PRIVILEGES cannot
-- remove PostgreSQL's *global* default EXECUTE-to-PUBLIC on functions, so
-- every lfhe function must REVOKE explicitly. Enforced by
-- tests/security/test_security_definer_hardening.py.
REVOKE ALL ON FUNCTION lfhe.deployment_environment_immutable() FROM PUBLIC;

CREATE TABLE lfhe.roles (
  code        text PRIMARY KEY CHECK (code ~ '^[A-Z][A-Z_]*$'),
  description text NOT NULL
);

CREATE TABLE lfhe.permissions (
  code             text PRIMARY KEY CHECK (code ~ '^[A-Z][A-Z_]*$'),
  description      text NOT NULL,
  phase_introduced smallint NOT NULL CHECK (phase_introduced BETWEEN 1 AND 7)
);

CREATE TABLE lfhe.role_permissions (
  role_code       text NOT NULL REFERENCES lfhe.roles(code),
  permission_code text NOT NULL REFERENCES lfhe.permissions(code),
  PRIMARY KEY (role_code, permission_code)
);

CREATE TABLE lfhe.user_roles (
  user_id    uuid NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
  role_code  text NOT NULL REFERENCES lfhe.roles(code),
  granted_at timestamptz NOT NULL DEFAULT now(),
  granted_by uuid REFERENCES auth.users(id),
  PRIMARY KEY (user_id, role_code)
);

INSERT INTO lfhe.roles (code, description) VALUES
  ('ADMIN',             'Technical and configuration administration; user-role management'),
  ('ANALYST',           'Processes sources, claims, events and assessments'),
  ('REVIEWER',          'Higher-level approval as authorised; source activation governance'),
  ('SECURITY_REVIEWER', 'Human security / handling review (Phase 6)'),
  ('RELEASE_AUTHORITY', 'Human release decision (Phase 6)'),
  ('VIEWER',            'Read-only access');

INSERT INTO lfhe.permissions (code, description, phase_introduced) VALUES
  ('USER_ROLE_MANAGE',                 'Grant / revoke user roles', 1),
  ('SOURCE_READ',                      'Read the source registry', 1),
  ('SOURCE_CREATE',                    'Create a source (inactive)', 1),
  ('SOURCE_UPDATE',                    'Edit source metadata and collection configuration', 1),
  ('SOURCE_APPROVE_COLLECTION_METHOD', 'Approve / revoke a source''s collection method', 1),
  ('SOURCE_ACTIVATE',                  'Activate / deactivate automated collection', 1),
  ('ARTICLE_READ',                     'Read articles and snapshots', 1),
  ('PROMPT_ACTIVATE',                  'Activate a registered prompt version in this environment', 1),
  ('AUDIT_READ',                       'Read the audit log', 1),
  ('SYSTEM_READ',                      'Read jobs, collection runs, errors and model runs', 1),
  ('CLAIM_REVIEW',                     'Human claim review (Phase 2)', 2),
  ('EVENT_ACTION',                     'Execute human EVENT_ACTION decisions (Phase 3)', 3),
  ('ASSESSMENT_REVIEW',                'Issue REVIEW_DECISION on assessments (Phase 4)', 4),
  ('FINAL_CONFIDENCE_SET',             'Finalise analytic confidence (Phase 4)', 4),
  ('REPORT_EDIT',                      'Select and edit report content (Phase 5)', 5),
  ('REPORT_CONTENT_APPROVE',           'Approve report content version (Phase 6)', 6),
  ('QA_WARNING_ACKNOWLEDGE',           'Acknowledge PASS_WITH_WARNINGS (Phase 6)', 6),
  ('SECURITY_REVIEW',                  'Security / handling review decision (Phase 6)', 6),
  ('RELEASE_DECIDE',                   'Human RELEASE_DECISION (Phase 6)', 6);

INSERT INTO lfhe.role_permissions (role_code, permission_code)
SELECT r, p FROM (VALUES
  ('ADMIN', 'USER_ROLE_MANAGE'), ('ADMIN', 'SOURCE_READ'), ('ADMIN', 'SOURCE_CREATE'),
  ('ADMIN', 'SOURCE_UPDATE'), ('ADMIN', 'SOURCE_APPROVE_COLLECTION_METHOD'),
  ('ADMIN', 'SOURCE_ACTIVATE'), ('ADMIN', 'ARTICLE_READ'), ('ADMIN', 'PROMPT_ACTIVATE'),
  ('ADMIN', 'AUDIT_READ'), ('ADMIN', 'SYSTEM_READ'),

  ('ANALYST', 'SOURCE_READ'), ('ANALYST', 'SOURCE_CREATE'), ('ANALYST', 'SOURCE_UPDATE'),
  ('ANALYST', 'ARTICLE_READ'), ('ANALYST', 'SYSTEM_READ'), ('ANALYST', 'CLAIM_REVIEW'),
  ('ANALYST', 'EVENT_ACTION'), ('ANALYST', 'ASSESSMENT_REVIEW'),
  ('ANALYST', 'FINAL_CONFIDENCE_SET'), ('ANALYST', 'REPORT_EDIT'),

  ('REVIEWER', 'SOURCE_READ'), ('REVIEWER', 'SOURCE_APPROVE_COLLECTION_METHOD'),
  ('REVIEWER', 'SOURCE_ACTIVATE'), ('REVIEWER', 'ARTICLE_READ'), ('REVIEWER', 'AUDIT_READ'),
  ('REVIEWER', 'ASSESSMENT_REVIEW'), ('REVIEWER', 'REPORT_CONTENT_APPROVE'),
  ('REVIEWER', 'QA_WARNING_ACKNOWLEDGE'),

  ('SECURITY_REVIEWER', 'SOURCE_READ'), ('SECURITY_REVIEWER', 'ARTICLE_READ'),
  ('SECURITY_REVIEWER', 'SECURITY_REVIEW'),

  ('RELEASE_AUTHORITY', 'SOURCE_READ'), ('RELEASE_AUTHORITY', 'ARTICLE_READ'),
  ('RELEASE_AUTHORITY', 'RELEASE_DECIDE'),

  ('VIEWER', 'SOURCE_READ'), ('VIEWER', 'ARTICLE_READ')
) AS m(r, p);

-- ---------------------------------------------------------------------------
-- Identity helpers
-- ---------------------------------------------------------------------------

-- The caller is a signed-in human using a PostgREST-style 'authenticated'
-- session, and is NOT a worker login. Returns the user id or NULL.
CREATE OR REPLACE FUNCTION lfhe.current_human_user()
RETURNS uuid LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_claims jsonb := nullif(pg_catalog.current_setting('request.jwt.claims', true), '')::jsonb;
  v_uid    uuid;
BEGIN
  IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'authenticated' THEN
    RETURN NULL;
  END IF;
  IF v_claims IS NULL OR v_claims ->> 'role' IS DISTINCT FROM 'authenticated' THEN
    RETURN NULL;
  END IF;
  IF pg_catalog.pg_has_role(session_user, 'lfhe_worker', 'MEMBER') THEN
    RETURN NULL;
  END IF;
  v_uid := auth.uid();
  IF v_uid IS NULL OR NOT EXISTS (SELECT 1 FROM auth.users u WHERE u.id = v_uid) THEN
    RETURN NULL;
  END IF;
  RETURN v_uid;
END $$;

CREATE OR REPLACE FUNCTION lfhe.user_has_permission(p_user uuid, p_permission text)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
  SELECT EXISTS (
    SELECT 1
    FROM lfhe.user_roles ur
    JOIN lfhe.role_permissions rp ON rp.role_code = ur.role_code
    WHERE ur.user_id = p_user AND rp.permission_code = p_permission
  )
$$;

-- For RLS policies and the UI: does the current human caller hold p_permission?
CREATE OR REPLACE FUNCTION lfhe.has_permission(p_permission text)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
  SELECT coalesce(lfhe.user_has_permission(lfhe.current_human_user(), p_permission), false)
$$;

CREATE OR REPLACE FUNCTION lfhe.my_permissions()
RETURNS SETOF text LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
  SELECT DISTINCT rp.permission_code
  FROM lfhe.user_roles ur
  JOIN lfhe.role_permissions rp ON rp.role_code = ur.role_code
  WHERE ur.user_id = lfhe.current_human_user()
  ORDER BY 1
$$;

-- Raise unless the caller is a human holding p_permission. Returns the user id.
-- Called only from inside other hardened functions.
CREATE OR REPLACE FUNCTION lfhe.require_human_permission(p_permission text)
RETURNS uuid LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_uid uuid := lfhe.current_human_user();
BEGIN
  IF v_uid IS NULL THEN
    RAISE EXCEPTION 'human authentication required (role=%, session=%)',
      coalesce(pg_catalog.current_setting('role', true), 'none'), session_user
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF NOT lfhe.user_has_permission(v_uid, p_permission) THEN
    RAISE EXCEPTION 'permission % required', p_permission
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN v_uid;
END $$;

REVOKE ALL ON FUNCTION lfhe.current_human_user() FROM PUBLIC, anon, service_role, lfhe_worker;
REVOKE ALL ON FUNCTION lfhe.user_has_permission(uuid, text) FROM PUBLIC, anon, service_role, lfhe_worker, authenticated;
REVOKE ALL ON FUNCTION lfhe.require_human_permission(text) FROM PUBLIC, anon, service_role, lfhe_worker, authenticated;
REVOKE ALL ON FUNCTION lfhe.has_permission(text) FROM PUBLIC, anon, service_role, lfhe_worker;
REVOKE ALL ON FUNCTION lfhe.my_permissions() FROM PUBLIC, anon, service_role, lfhe_worker;
GRANT EXECUTE ON FUNCTION lfhe.current_human_user(), lfhe.has_permission(text), lfhe.my_permissions() TO authenticated;

-- ---------------------------------------------------------------------------
-- Role management (human-only)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.grant_user_role(p_user uuid, p_role text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('USER_ROLE_MANAGE');
BEGIN
  IF NOT EXISTS (SELECT 1 FROM auth.users u WHERE u.id = p_user) THEN
    RAISE EXCEPTION 'unknown user %', p_user;
  END IF;
  INSERT INTO lfhe.user_roles (user_id, role_code, granted_by)
  VALUES (p_user, p_role, v_actor)
  ON CONFLICT (user_id, role_code) DO NOTHING;
END $$;
COMMENT ON FUNCTION lfhe.grant_user_role(uuid, text) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.revoke_user_role(p_user uuid, p_role text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('USER_ROLE_MANAGE');
BEGIN
  IF p_role = 'ADMIN' AND (
       SELECT count(*) FROM lfhe.user_roles WHERE role_code = 'ADMIN' AND user_id <> p_user
     ) = 0 THEN
    RAISE EXCEPTION 'cannot revoke the last ADMIN';
  END IF;
  DELETE FROM lfhe.user_roles WHERE user_id = p_user AND role_code = p_role;
END $$;
COMMENT ON FUNCTION lfhe.revoke_user_role(uuid, text) IS 'HUMAN_ONLY';

REVOKE ALL ON FUNCTION lfhe.grant_user_role(uuid, text) FROM PUBLIC, anon, service_role, lfhe_worker;
REVOKE ALL ON FUNCTION lfhe.revoke_user_role(uuid, text) FROM PUBLIC, anon, service_role, lfhe_worker;
GRANT EXECUTE ON FUNCTION lfhe.grant_user_role(uuid, text), lfhe.revoke_user_role(uuid, text) TO authenticated;

-- Operator bootstrap (first ADMIN) — owner only, never granted to any role.
CREATE OR REPLACE FUNCTION lfhe.bootstrap_grant_role(p_user uuid, p_role text)
RETURNS void LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  INSERT INTO lfhe.user_roles (user_id, role_code, granted_by)
  VALUES (p_user, p_role, NULL)
  ON CONFLICT (user_id, role_code) DO NOTHING;
END $$;
REVOKE ALL ON FUNCTION lfhe.bootstrap_grant_role(uuid, text) FROM PUBLIC, anon, authenticated, service_role, lfhe_worker;

-- ---------------------------------------------------------------------------
-- Table privileges and RLS: read-only for humans; no direct writes for anyone
-- except through the definer functions above.
-- ---------------------------------------------------------------------------
REVOKE ALL ON lfhe.roles, lfhe.permissions, lfhe.role_permissions, lfhe.user_roles
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker;
GRANT SELECT ON lfhe.roles, lfhe.permissions, lfhe.role_permissions, lfhe.user_roles TO authenticated;

ALTER TABLE lfhe.roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE lfhe.permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE lfhe.role_permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE lfhe.user_roles ENABLE ROW LEVEL SECURITY;

CREATE POLICY roles_read ON lfhe.roles FOR SELECT TO authenticated
  USING (lfhe.current_human_user() IS NOT NULL);
CREATE POLICY permissions_read ON lfhe.permissions FOR SELECT TO authenticated
  USING (lfhe.current_human_user() IS NOT NULL);
CREATE POLICY role_permissions_read ON lfhe.role_permissions FOR SELECT TO authenticated
  USING (lfhe.current_human_user() IS NOT NULL);
CREATE POLICY user_roles_read ON lfhe.user_roles FOR SELECT TO authenticated
  USING (user_id = lfhe.current_human_user() OR lfhe.has_permission('USER_ROLE_MANAGE'));
