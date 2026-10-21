-- LFHÉ Phase 5 (P5-07) — deterministic report preview renders. Baseline: Phase 5 Addendum §20;
-- CG0 C.9 (canonical JSON → deterministic HTML template; PDF via headless Chromium); K-09.
--
-- * A render is a PREVIEW of one exact report_version_id + report_version_hash, produced by the
--   worker from canonical_json + template_version + renderer_version only. It is never QA-approved,
--   security-approved or released (status is fixed to PREVIEW) and is never authoritative on its own.
-- * template_version, template_sha256, renderer_version and html_sha256 are persisted so Phase 6
--   can bind them into the release manifest (K-09). Re-rendering the same version with the same
--   template / renderer must give the same bytes (RENDER_NONDETERMINISTIC otherwise).
-- * PDF is not produced in Phase 5 (SD5-10); the HTML carries the print layout foundation.

INSERT INTO lfhe.audit_event_types (code, spec_source) VALUES
  ('REPORT_PREVIEW_RENDERED', 'Phase 5 impl.')
ON CONFLICT (code) DO NOTHING;

CREATE TABLE lfhe.report_renders (
  id                   uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  report_version_id    uuid NOT NULL,
  report_version_hash  text NOT NULL,
  render_format        text NOT NULL CHECK (render_format = 'HTML'),
  template_version     text NOT NULL CHECK (template_version ~ '^[A-Z0-9_-]{3,60}/[0-9]+\.[0-9]+\.[0-9]+$'),
  template_sha256      text NOT NULL CHECK (template_sha256 ~ '^[0-9a-f]{64}$'),
  renderer_version     text NOT NULL CHECK (renderer_version ~ '^[a-z0-9_-]{3,60}/[0-9]+\.[0-9]+\.[0-9]+$'),
  content              text NOT NULL,
  content_sha256       text NOT NULL,
  status               text NOT NULL DEFAULT 'PREVIEW' CHECK (status = 'PREVIEW'),
  worker_id            text NOT NULL,
  created_at           timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (report_version_id, report_version_hash) REFERENCES lfhe.report_versions (id, report_version_hash),
  UNIQUE (report_version_id, render_format, template_version, renderer_version),
  CHECK (content_sha256 = pg_catalog.encode(extensions.digest(pg_catalog.convert_to(content, 'UTF8'), 'sha256'), 'hex'))
);
CREATE TRIGGER report_renders_immutable BEFORE UPDATE OR DELETE ON lfhe.report_renders
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();
CREATE TRIGGER report_renders_audit AFTER INSERT ON lfhe.report_renders
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_p5_objects('REPORT_PREVIEW_RENDERED', 'report_version', 'report_version_id');

-- worker: p {report_version_id, report_version_hash, template_version, template_sha256, renderer_version, content, worker_id}
CREATE OR REPLACE FUNCTION lfhe.record_report_render(p jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_sha  text := pg_catalog.encode(extensions.digest(pg_catalog.convert_to(p ->> 'content', 'UTF8'), 'sha256'), 'hex');
  v_old  lfhe.report_renders;
  v_id   uuid;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM lfhe.report_versions WHERE id::text = p ->> 'report_version_id'
                 AND report_version_hash = p ->> 'report_version_hash') THEN
    RAISE EXCEPTION 'VERSION_HASH_MISMATCH: report version %', p ->> 'report_version_id' USING ERRCODE = 'serialization_failure';
  END IF;
  IF pg_catalog.strpos(p ->> 'content', p ->> 'report_version_hash') = 0 THEN
    RAISE EXCEPTION 'RENDER_NOT_BOUND_TO_VERSION' USING ERRCODE = 'check_violation';
  END IF;
  SELECT * INTO v_old FROM lfhe.report_renders WHERE report_version_id::text = p ->> 'report_version_id' AND render_format = 'HTML'
    AND template_version = p ->> 'template_version' AND renderer_version = p ->> 'renderer_version';
  IF FOUND THEN
    IF v_old.content_sha256 <> v_sha OR v_old.template_sha256 <> p ->> 'template_sha256' THEN
      RAISE EXCEPTION 'RENDER_NONDETERMINISTIC: % differs from the recorded render', v_old.id USING ERRCODE = 'check_violation';
    END IF;
    RETURN pg_catalog.jsonb_build_object('render_id', v_old.id, 'content_sha256', v_sha, 'new', false);
  END IF;
  INSERT INTO lfhe.report_renders (report_version_id, report_version_hash, render_format, template_version, template_sha256,
    renderer_version, content, content_sha256, worker_id)
  VALUES ((p ->> 'report_version_id')::uuid, p ->> 'report_version_hash', 'HTML', p ->> 'template_version', p ->> 'template_sha256',
    p ->> 'renderer_version', p ->> 'content', v_sha, p ->> 'worker_id')
  RETURNING id INTO v_id;
  RETURN pg_catalog.jsonb_build_object('render_id', v_id, 'content_sha256', v_sha, 'new', true);
END $$;

REVOKE ALL ON FUNCTION lfhe.record_report_render(jsonb) FROM PUBLIC, anon, authenticated, service_role, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.record_report_render(jsonb) TO lfhe_worker;
REVOKE ALL ON lfhe.report_renders FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT SELECT ON lfhe.report_renders TO authenticated, lfhe_worker;
ALTER TABLE lfhe.report_renders ENABLE ROW LEVEL SECURITY;
CREATE POLICY report_renders_read_human ON lfhe.report_renders FOR SELECT TO authenticated USING (lfhe.has_permission('CLAIM_READ'));
CREATE POLICY report_renders_read_worker ON lfhe.report_renders FOR SELECT TO lfhe_worker USING (true);
