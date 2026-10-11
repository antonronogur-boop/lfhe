-- ============================================================================
-- P1-06  Source Registry (DS §7, §28, §30; Control Gate 0 K-04)
--
-- Governance encoded in the database:
--   * a new source is inactive, unapproved and METADATA_ONLY by default;
--   * automated collection requires active = true AND an approved method
--     (DS §7) — enforced by CHECK constraint;
--   * changing collection_method or collection_config revokes approval and
--     deactivates the source (re-approval required);
--   * BROWSER_AUTOMATION cannot be approved in Phase 1 (no adapter);
--   * collection_config may not carry credentials / headers / cookies
--     (no access-control bypass, no secrets in the database config).
-- All writes go through HUMAN_ONLY functions; every change is audited.
-- ============================================================================

CREATE TABLE lfhe.sources (
  id                          uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  name                        text NOT NULL UNIQUE CHECK (length(btrim(name)) BETWEEN 2 AND 200),
  canonical_domain            text NOT NULL
                                CHECK (canonical_domain ~ '^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$'),
  owner_organisation          text,
  owner_country               text CHECK (owner_country ~ '^[A-Z]{2}$'),
  source_tier                 smallint CHECK (source_tier BETWEEN 1 AND 4),
  source_type                 text NOT NULL CHECK (source_type IN (
                                'OFFICIAL_GOVERNMENT', 'OFFICIAL_MILITARY', 'INTERNATIONAL_ORGANISATION',
                                'INDUSTRY', 'WIRE_SERVICE', 'MEDIA', 'THINK_TANK', 'OTHER')),
  official_status             text NOT NULL DEFAULT 'NON_OFFICIAL'
                                CHECK (official_status IN ('OFFICIAL', 'SEMI_OFFICIAL', 'NON_OFFICIAL')),
  primary_language            text NOT NULL CHECK (primary_language ~ '^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$'),
  additional_languages        text[] NOT NULL DEFAULT '{}',
  geographic_focus            text[] NOT NULL DEFAULT '{}',
  topic_focus                 text[] NOT NULL DEFAULT '{}',
  collection_priority         smallint NOT NULL DEFAULT 3 CHECK (collection_priority BETWEEN 1 AND 5),
  collection_method           lfhe.collection_method NOT NULL,
  collection_config           jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(collection_config) = 'object'),
  collection_frequency        interval NOT NULL DEFAULT interval '1 hour'
                                CHECK (collection_frequency >= interval '5 minutes'),
  collection_method_approved  boolean NOT NULL DEFAULT false,
  collection_method_approved_by uuid REFERENCES auth.users(id),
  collection_method_approved_at timestamptz,
  retention_mode              lfhe.retention_mode NOT NULL DEFAULT 'METADATA_ONLY',
  terms_notes                 text,
  reliability_prior           text CHECK (reliability_prior IN ('A', 'B', 'C', 'D', 'E', 'F')),
  bias_profile                text,
  independence_group          text,
  active                      boolean NOT NULL DEFAULT false,
  last_verified_at            timestamptz,
  access_restrictions         text,
  analyst_notes               text,
  created_at                  timestamptz NOT NULL DEFAULT now(),
  created_by                  uuid REFERENCES auth.users(id),
  updated_at                  timestamptz NOT NULL DEFAULT now(),
  updated_by                  uuid REFERENCES auth.users(id),

  CONSTRAINT sources_active_requires_approved_method
    CHECK (NOT active OR collection_method_approved),
  CONSTRAINT sources_browser_automation_not_approvable
    CHECK (NOT (collection_method = 'BROWSER_AUTOMATION' AND collection_method_approved)),
  CONSTRAINT sources_approval_fields_consistent
    CHECK (collection_method_approved = (collection_method_approved_at IS NOT NULL)),
  CONSTRAINT sources_config_has_no_credentials
    CHECK (NOT (collection_config ?| ARRAY['headers', 'auth', 'authorization', 'cookies', 'cookie',
                                          'password', 'token', 'api_key', 'apikey', 'secret']))
);

-- ---------------------------------------------------------------------------
-- Audit: one source change may produce several catalogue events.
-- The calling function passes a human reason via the transaction-local
-- setting lfhe.audit_reason.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.audit_sources()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_meta jsonb := jsonb_strip_nulls(jsonb_build_object(
    'reason', nullif(pg_catalog.current_setting('lfhe.audit_reason', true), '')));
  v_old jsonb;
  v_new jsonb;
BEGIN
  IF TG_OP = 'INSERT' THEN
    PERFORM lfhe.write_audit('SOURCE_CREATED', 'source', NEW.id::text, NULL, to_jsonb(NEW), v_meta);
    RETURN NULL;
  END IF;

  IF NEW.collection_method_approved IS DISTINCT FROM OLD.collection_method_approved THEN
    PERFORM lfhe.write_audit(
      CASE WHEN NEW.collection_method_approved THEN 'SOURCE_COLLECTION_METHOD_APPROVED'
           ELSE 'SOURCE_COLLECTION_METHOD_REVOKED' END,
      'source', NEW.id::text,
      jsonb_build_object('collection_method', OLD.collection_method, 'collection_method_approved', OLD.collection_method_approved),
      jsonb_build_object('collection_method', NEW.collection_method, 'collection_method_approved', NEW.collection_method_approved),
      v_meta);
  END IF;

  IF NEW.active IS DISTINCT FROM OLD.active THEN
    PERFORM lfhe.write_audit(
      CASE WHEN NEW.active THEN 'SOURCE_ACTIVATED' ELSE 'SOURCE_DEACTIVATED' END,
      'source', NEW.id::text,
      jsonb_build_object('active', OLD.active), jsonb_build_object('active', NEW.active), v_meta);
  END IF;

  -- Any other content change.
  v_old := to_jsonb(OLD) - ARRAY['active', 'collection_method_approved', 'collection_method_approved_by',
                                  'collection_method_approved_at', 'updated_at', 'updated_by'];
  v_new := to_jsonb(NEW) - ARRAY['active', 'collection_method_approved', 'collection_method_approved_by',
                                  'collection_method_approved_at', 'updated_at', 'updated_by'];
  IF v_old IS DISTINCT FROM v_new THEN
    PERFORM lfhe.write_audit('SOURCE_UPDATED', 'source', NEW.id::text, v_old, v_new, v_meta);
  END IF;
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION lfhe.audit_sources() FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator;

CREATE TRIGGER sources_audit
  AFTER INSERT OR UPDATE ON lfhe.sources
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_sources();

CREATE OR REPLACE FUNCTION lfhe.sources_block_delete()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  RAISE EXCEPTION 'sources are never deleted; deactivate instead'
    USING ERRCODE = 'insufficient_privilege';
END $$;
REVOKE ALL ON FUNCTION lfhe.sources_block_delete() FROM PUBLIC;

CREATE TRIGGER sources_no_delete
  BEFORE DELETE ON lfhe.sources
  FOR EACH ROW EXECUTE FUNCTION lfhe.sources_block_delete();

-- ---------------------------------------------------------------------------
-- HUMAN_ONLY write functions
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.create_source(p jsonb)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('SOURCE_CREATE');
  v_id    uuid;
  v_unknown text[];
BEGIN
  SELECT array_agg(k) INTO v_unknown FROM jsonb_object_keys(p) k
  WHERE k NOT IN ('name', 'canonical_domain', 'owner_organisation', 'owner_country', 'source_tier',
                  'source_type', 'official_status', 'primary_language', 'additional_languages',
                  'geographic_focus', 'topic_focus', 'collection_priority', 'collection_method',
                  'collection_config', 'collection_frequency', 'retention_mode', 'terms_notes',
                  'reliability_prior', 'bias_profile', 'independence_group', 'access_restrictions',
                  'analyst_notes');
  IF v_unknown IS NOT NULL THEN
    RAISE EXCEPTION 'create_source: field(s) not allowed: %', v_unknown USING ERRCODE = 'invalid_parameter_value';
  END IF;

  INSERT INTO lfhe.sources (
    name, canonical_domain, owner_organisation, owner_country, source_tier, source_type,
    official_status, primary_language, additional_languages, geographic_focus, topic_focus,
    collection_priority, collection_method, collection_config, collection_frequency,
    retention_mode, terms_notes, reliability_prior, bias_profile, independence_group,
    access_restrictions, analyst_notes, created_by, updated_by)
  VALUES (
    btrim(p ->> 'name'), lower(p ->> 'canonical_domain'), p ->> 'owner_organisation',
    upper(p ->> 'owner_country'), (p ->> 'source_tier')::smallint, p ->> 'source_type',
    coalesce(p ->> 'official_status', 'NON_OFFICIAL'), p ->> 'primary_language',
    coalesce(ARRAY(SELECT jsonb_array_elements_text(p -> 'additional_languages')), '{}'),
    coalesce(ARRAY(SELECT jsonb_array_elements_text(p -> 'geographic_focus')), '{}'),
    coalesce(ARRAY(SELECT jsonb_array_elements_text(p -> 'topic_focus')), '{}'),
    coalesce((p ->> 'collection_priority')::smallint, 3),
    (p ->> 'collection_method')::lfhe.collection_method,
    coalesce(p -> 'collection_config', '{}'::jsonb),
    coalesce((p ->> 'collection_frequency')::interval, interval '1 hour'),
    coalesce((p ->> 'retention_mode')::lfhe.retention_mode, 'METADATA_ONLY'),
    p ->> 'terms_notes', p ->> 'reliability_prior', p ->> 'bias_profile',
    p ->> 'independence_group', p ->> 'access_restrictions', p ->> 'analyst_notes',
    v_actor, v_actor)
  RETURNING id INTO v_id;
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.create_source(jsonb) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.update_source(p_id uuid, p jsonb, p_reason text DEFAULT NULL)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor  uuid := lfhe.require_human_permission('SOURCE_UPDATE');
  v_old    lfhe.sources%ROWTYPE;
  v_unknown text[];
  v_method lfhe.collection_method;
  v_config jsonb;
  v_reapproval boolean;
BEGIN
  SELECT array_agg(k) INTO v_unknown FROM jsonb_object_keys(p) k
  WHERE k NOT IN ('name', 'canonical_domain', 'owner_organisation', 'owner_country', 'source_tier',
                  'source_type', 'official_status', 'primary_language', 'additional_languages',
                  'geographic_focus', 'topic_focus', 'collection_priority', 'collection_method',
                  'collection_config', 'collection_frequency', 'retention_mode', 'terms_notes',
                  'reliability_prior', 'bias_profile', 'independence_group', 'access_restrictions',
                  'analyst_notes', 'last_verified_at');
  IF v_unknown IS NOT NULL THEN
    RAISE EXCEPTION 'update_source: field(s) not allowed: %', v_unknown USING ERRCODE = 'invalid_parameter_value';
  END IF;

  SELECT * INTO v_old FROM lfhe.sources WHERE id = p_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'unknown source %', p_id USING ERRCODE = 'no_data_found';
  END IF;

  v_method := coalesce((p ->> 'collection_method')::lfhe.collection_method, v_old.collection_method);
  v_config := coalesce(p -> 'collection_config', v_old.collection_config);
  v_reapproval := v_method IS DISTINCT FROM v_old.collection_method
               OR v_config IS DISTINCT FROM v_old.collection_config;

  PERFORM pg_catalog.set_config('lfhe.audit_reason',
    coalesce(p_reason, '') || CASE WHEN v_reapproval AND v_old.collection_method_approved
      THEN ' [collection method/config changed: approval revoked, source deactivated]' ELSE '' END, true);

  UPDATE lfhe.sources SET
    name                 = coalesce(btrim(p ->> 'name'), name),
    canonical_domain     = coalesce(lower(p ->> 'canonical_domain'), canonical_domain),
    owner_organisation   = CASE WHEN p ? 'owner_organisation' THEN p ->> 'owner_organisation' ELSE owner_organisation END,
    owner_country        = CASE WHEN p ? 'owner_country' THEN upper(p ->> 'owner_country') ELSE owner_country END,
    source_tier          = CASE WHEN p ? 'source_tier' THEN (p ->> 'source_tier')::smallint ELSE source_tier END,
    source_type          = coalesce(p ->> 'source_type', source_type),
    official_status      = coalesce(p ->> 'official_status', official_status),
    primary_language     = coalesce(p ->> 'primary_language', primary_language),
    additional_languages = CASE WHEN p ? 'additional_languages'
                             THEN ARRAY(SELECT jsonb_array_elements_text(p -> 'additional_languages')) ELSE additional_languages END,
    geographic_focus     = CASE WHEN p ? 'geographic_focus'
                             THEN ARRAY(SELECT jsonb_array_elements_text(p -> 'geographic_focus')) ELSE geographic_focus END,
    topic_focus          = CASE WHEN p ? 'topic_focus'
                             THEN ARRAY(SELECT jsonb_array_elements_text(p -> 'topic_focus')) ELSE topic_focus END,
    collection_priority  = coalesce((p ->> 'collection_priority')::smallint, collection_priority),
    collection_method    = v_method,
    collection_config    = v_config,
    collection_frequency = coalesce((p ->> 'collection_frequency')::interval, collection_frequency),
    retention_mode       = coalesce((p ->> 'retention_mode')::lfhe.retention_mode, retention_mode),
    terms_notes          = CASE WHEN p ? 'terms_notes' THEN p ->> 'terms_notes' ELSE terms_notes END,
    reliability_prior    = CASE WHEN p ? 'reliability_prior' THEN p ->> 'reliability_prior' ELSE reliability_prior END,
    bias_profile         = CASE WHEN p ? 'bias_profile' THEN p ->> 'bias_profile' ELSE bias_profile END,
    independence_group   = CASE WHEN p ? 'independence_group' THEN p ->> 'independence_group' ELSE independence_group END,
    access_restrictions  = CASE WHEN p ? 'access_restrictions' THEN p ->> 'access_restrictions' ELSE access_restrictions END,
    analyst_notes        = CASE WHEN p ? 'analyst_notes' THEN p ->> 'analyst_notes' ELSE analyst_notes END,
    last_verified_at     = CASE WHEN p ? 'last_verified_at' THEN (p ->> 'last_verified_at')::timestamptz ELSE last_verified_at END,
    collection_method_approved    = CASE WHEN v_reapproval THEN false ELSE collection_method_approved END,
    collection_method_approved_by = CASE WHEN v_reapproval THEN NULL ELSE collection_method_approved_by END,
    collection_method_approved_at = CASE WHEN v_reapproval THEN NULL ELSE collection_method_approved_at END,
    active               = CASE WHEN v_reapproval THEN false ELSE active END,
    updated_at           = now(),
    updated_by           = v_actor
  WHERE id = p_id;
END $$;
COMMENT ON FUNCTION lfhe.update_source(uuid, jsonb, text) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.set_collection_method_approval(p_id uuid, p_approved boolean, p_reason text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('SOURCE_APPROVE_COLLECTION_METHOD');
BEGIN
  IF p_reason IS NULL OR length(btrim(p_reason)) < 5 THEN
    RAISE EXCEPTION 'a reason (terms / legal basis) is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  PERFORM pg_catalog.set_config('lfhe.audit_reason', p_reason, true);
  UPDATE lfhe.sources SET
    collection_method_approved    = p_approved,
    collection_method_approved_by = CASE WHEN p_approved THEN v_actor END,
    collection_method_approved_at = CASE WHEN p_approved THEN now() END,
    active                        = CASE WHEN p_approved THEN active ELSE false END,
    updated_at = now(), updated_by = v_actor
  WHERE id = p_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'unknown source %', p_id USING ERRCODE = 'no_data_found';
  END IF;
END $$;
COMMENT ON FUNCTION lfhe.set_collection_method_approval(uuid, boolean, text) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.set_source_active(p_id uuid, p_active boolean, p_reason text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('SOURCE_ACTIVATE');
  v_src   lfhe.sources%ROWTYPE;
BEGIN
  IF p_reason IS NULL OR length(btrim(p_reason)) < 5 THEN
    RAISE EXCEPTION 'a reason is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  SELECT * INTO v_src FROM lfhe.sources WHERE id = p_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'unknown source %', p_id USING ERRCODE = 'no_data_found';
  END IF;
  IF p_active AND NOT v_src.collection_method_approved THEN
    RAISE EXCEPTION 'source % cannot be activated: collection method not approved', p_id
      USING ERRCODE = 'check_violation';
  END IF;
  PERFORM pg_catalog.set_config('lfhe.audit_reason', p_reason, true);
  UPDATE lfhe.sources SET active = p_active, updated_at = now(), updated_by = v_actor WHERE id = p_id;
END $$;
COMMENT ON FUNCTION lfhe.set_source_active(uuid, boolean, text) IS 'HUMAN_ONLY';

REVOKE ALL ON FUNCTION lfhe.create_source(jsonb) FROM PUBLIC, anon, service_role, lfhe_worker, lfhe_evaluator;
REVOKE ALL ON FUNCTION lfhe.update_source(uuid, jsonb, text) FROM PUBLIC, anon, service_role, lfhe_worker, lfhe_evaluator;
REVOKE ALL ON FUNCTION lfhe.set_collection_method_approval(uuid, boolean, text) FROM PUBLIC, anon, service_role, lfhe_worker, lfhe_evaluator;
REVOKE ALL ON FUNCTION lfhe.set_source_active(uuid, boolean, text) FROM PUBLIC, anon, service_role, lfhe_worker, lfhe_evaluator;
GRANT EXECUTE ON FUNCTION lfhe.create_source(jsonb), lfhe.update_source(uuid, jsonb, text),
  lfhe.set_collection_method_approval(uuid, boolean, text), lfhe.set_source_active(uuid, boolean, text)
  TO authenticated;

-- ---------------------------------------------------------------------------
-- Privileges: read-only for humans with SOURCE_READ and for workers.
-- ---------------------------------------------------------------------------
REVOKE ALL ON lfhe.sources FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator;
GRANT SELECT ON lfhe.sources TO authenticated, lfhe_worker;
ALTER TABLE lfhe.sources ENABLE ROW LEVEL SECURITY;
CREATE POLICY sources_read_human ON lfhe.sources FOR SELECT TO authenticated
  USING (lfhe.has_permission('SOURCE_READ'));
CREATE POLICY sources_read_worker ON lfhe.sources FOR SELECT TO lfhe_worker
  USING (true);

-- Sources eligible for automated collection (DS §7).
CREATE VIEW lfhe.collectable_sources WITH (security_invoker = true) AS
  SELECT * FROM lfhe.sources
  WHERE active AND collection_method_approved AND collection_method <> 'BROWSER_AUTOMATION';
GRANT SELECT ON lfhe.collectable_sources TO lfhe_worker, authenticated;
