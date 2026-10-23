-- LFHÉ Phase 6 (P6-05 … P6-07) — human content approval, human security / handling review, release
-- PDF artifacts, deterministic release eligibility, human release decision, atomic release
-- manifest + RELEASED, post-release correction path.
-- Baseline: Phase 6 Addendum §5 (DC6-01 … DC6-06), §6, §7, §17–§24, §26, §29–§31; CG0 E.17–E.19,
-- G (RELEASED protection); Prompt Pack v1.2 §49–§54.
--
-- * Every record is bound by composite FK to the exact (report_version_id, report_version_hash);
--   report_versions are never modified (DC6-01). The workflow state is derived (report_version_workflow).
-- * content_approvals   HUMAN_ONLY (REPORT_CONTENT_APPROVE): APPROVE only on the CURRENT qa_result
--                       with PASS, or PASS_WITH_WARNINGS with every warning acknowledged; FAIL never.
-- * security_reviews    PENDING is opened deterministically by a content APPROVE; the decision
--                       (APPROVED / RETURN_FOR_REVISION / REJECTED) is HUMAN_ONLY (SECURITY_REVIEW).
-- * release_pdf_artifacts  worker-recorded, immutable PDF bytes + SHA-256, bound to version / hash,
--                       template version / hash, renderer version / hash and the preview render.
-- * release_decisions / release_manifests / report_releases  HUMAN_ONLY (RELEASE_DECIDE). RELEASED
--                       exists only as a report_releases row, written together with the APPROVE
--                       decision and the manifest by lfhe.release_report in ONE transaction, after
--                       the deterministic eligibility checklist is re-evaluated inside it. A guard
--                       trigger refuses any insert that does not come from that function.
-- * Corrections: a new version after a release emits REPORT_CORRECTION_CREATED; the released
--   version, its PDF and manifest stay immutable; the new version needs the full sequence again.

INSERT INTO lfhe.audit_event_types (code, spec_source) VALUES
  ('REPORT_CONTENT_DECIDED', 'Phase 6 impl. (content approval human decision, Addendum §17)'),
  ('SECURITY_REVIEW_OPENED', 'Phase 6 impl.'),
  ('RELEASE_PDF_RECORDED', 'Phase 6 impl.'),
  ('RELEASE_PDF_REQUESTED', 'Phase 6 impl.')
ON CONFLICT (code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------
CREATE TABLE lfhe.content_approvals (
  seq                          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id                           uuid NOT NULL UNIQUE DEFAULT pg_catalog.gen_random_uuid(),
  report_id                    uuid NOT NULL REFERENCES lfhe.reports(id),
  report_version_id            uuid NOT NULL,
  report_version_hash          text NOT NULL,
  qa_result_id                 uuid NOT NULL,
  qa_status                    text NOT NULL CHECK (qa_status IN ('PASS', 'PASS_WITH_WARNINGS', 'FAIL')),
  decision                     text NOT NULL CHECK (decision IN ('APPROVE', 'RETURN_FOR_REVISION', 'REJECT')),
  warning_acknowledgement_ids  uuid[] NOT NULL DEFAULT '{}',
  reviewer_user_id             uuid NOT NULL,
  rationale                    text NOT NULL CHECK (length(btrim(rationale)) >= 10),
  created_at                   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (qa_result_id),
  UNIQUE (id, report_version_id, report_version_hash),
  FOREIGN KEY (qa_result_id, report_version_id, report_version_hash) REFERENCES lfhe.qa_results (id, report_version_id, report_version_hash),
  CHECK (decision <> 'APPROVE' OR qa_status IN ('PASS', 'PASS_WITH_WARNINGS'))
);

CREATE TABLE lfhe.security_reviews (
  seq                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id                   uuid NOT NULL UNIQUE DEFAULT pg_catalog.gen_random_uuid(),
  report_id            uuid NOT NULL REFERENCES lfhe.reports(id),
  report_version_id    uuid NOT NULL,
  report_version_hash  text NOT NULL,
  content_approval_id  uuid NOT NULL,
  status               lfhe.security_review_status NOT NULL,
  pending_review_id    uuid UNIQUE REFERENCES lfhe.security_reviews(id),
  reviewer_user_id     uuid,
  rationale            text,
  created_at           timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id, report_version_id, report_version_hash),
  FOREIGN KEY (content_approval_id, report_version_id, report_version_hash)
    REFERENCES lfhe.content_approvals (id, report_version_id, report_version_hash),
  CHECK ((status = 'PENDING') = (pending_review_id IS NULL)),
  CHECK ((status = 'PENDING') = (reviewer_user_id IS NULL AND rationale IS NULL)),
  CHECK (status = 'PENDING' OR length(btrim(rationale)) >= 10)
);
CREATE UNIQUE INDEX security_reviews_one_pending ON lfhe.security_reviews (content_approval_id) WHERE status = 'PENDING';

CREATE TABLE lfhe.release_pdf_artifacts (
  id                   uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  report_id            uuid NOT NULL REFERENCES lfhe.reports(id),
  report_version_id    uuid NOT NULL,
  report_version_hash  text NOT NULL,
  preview_render_id    uuid NOT NULL REFERENCES lfhe.report_renders(id),
  source_html          text NOT NULL,
  source_html_sha256   text NOT NULL,
  template_version     text NOT NULL,
  template_hash        text NOT NULL CHECK (template_hash ~ '^[0-9a-f]{64}$'),
  renderer_version     text NOT NULL CHECK (renderer_version ~ '^[a-z0-9_-]{3,60}/[0-9]+\.[0-9]+\.[0-9]+$'),
  renderer_hash        text NOT NULL CHECK (renderer_hash ~ '^[0-9a-f]{64}$'),
  renderer_identity    jsonb NOT NULL,
  storage_key          text NOT NULL,
  mime_type            text NOT NULL CHECK (mime_type = 'application/pdf'),
  byte_size            integer NOT NULL CHECK (byte_size > 0),
  pdf_sha256           text NOT NULL CHECK (pdf_sha256 ~ '^[0-9a-f]{64}$'),
  pdf_bytes            bytea NOT NULL,
  worker_id            text NOT NULL,
  created_at           timestamptz NOT NULL DEFAULT now(),
  UNIQUE (report_version_id, pdf_sha256),
  UNIQUE (id, report_version_id, report_version_hash),
  UNIQUE (id, pdf_sha256),
  FOREIGN KEY (report_version_id, report_version_hash) REFERENCES lfhe.report_versions (id, report_version_hash),
  CHECK (pdf_sha256 = pg_catalog.encode(extensions.digest(pdf_bytes, 'sha256'), 'hex')),
  CHECK (byte_size = pg_catalog.octet_length(pdf_bytes)),
  CHECK (substring(pdf_bytes FROM 1 FOR 5) = '\x255044462d'::bytea),
  CHECK (storage_key = 'release-pdf/sha256/' || substr(pdf_sha256, 1, 2) || '/' || substr(pdf_sha256, 3, 2) || '/' || pdf_sha256),
  CHECK (source_html_sha256 = pg_catalog.encode(extensions.digest(pg_catalog.convert_to(source_html, 'UTF8'), 'sha256'), 'hex')),
  CHECK (pg_catalog.strpos(source_html, report_version_hash) > 0)
);

CREATE TABLE lfhe.release_decisions (
  seq                          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id                           uuid NOT NULL UNIQUE DEFAULT pg_catalog.gen_random_uuid(),
  report_id                    uuid NOT NULL REFERENCES lfhe.reports(id),
  report_version_id            uuid NOT NULL,
  report_version_hash          text NOT NULL,
  decision                     lfhe.release_decision NOT NULL,
  qa_result_id                 uuid,
  deterministic_qa_run_id      uuid,
  semantic_qa_run_id           uuid,
  qa_status                    text,
  warning_acknowledgement_ids  uuid[] NOT NULL DEFAULT '{}',
  content_approval_id          uuid,
  security_review_id           uuid,
  pdf_artifact_id              uuid,
  eligibility                  jsonb NOT NULL,
  decided_by                   uuid NOT NULL,
  rationale                    text NOT NULL CHECK (length(btrim(rationale)) >= 10),
  created_at                   timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  UNIQUE (id, report_version_id, report_version_hash),
  FOREIGN KEY (report_version_id, report_version_hash) REFERENCES lfhe.report_versions (id, report_version_hash),
  FOREIGN KEY (qa_result_id, report_version_id, report_version_hash) REFERENCES lfhe.qa_results (id, report_version_id, report_version_hash),
  FOREIGN KEY (content_approval_id, report_version_id, report_version_hash)
    REFERENCES lfhe.content_approvals (id, report_version_id, report_version_hash),
  FOREIGN KEY (security_review_id, report_version_id, report_version_hash)
    REFERENCES lfhe.security_reviews (id, report_version_id, report_version_hash),
  FOREIGN KEY (pdf_artifact_id, report_version_id, report_version_hash)
    REFERENCES lfhe.release_pdf_artifacts (id, report_version_id, report_version_hash),
  CHECK (decision <> 'APPROVE_FOR_RELEASE' OR (qa_result_id IS NOT NULL AND deterministic_qa_run_id IS NOT NULL
         AND semantic_qa_run_id IS NOT NULL AND qa_status IN ('PASS', 'PASS_WITH_WARNINGS') AND content_approval_id IS NOT NULL
         AND security_review_id IS NOT NULL AND pdf_artifact_id IS NOT NULL AND (eligibility ->> 'eligible')::boolean))
);
CREATE UNIQUE INDEX release_decisions_one_release ON lfhe.release_decisions (report_version_id) WHERE decision = 'APPROVE_FOR_RELEASE';

CREATE TABLE lfhe.release_manifests (
  id                   uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  release_decision_id  uuid NOT NULL UNIQUE,
  report_version_id    uuid NOT NULL,
  report_version_hash  text NOT NULL,
  manifest_json        jsonb NOT NULL,
  manifest_hash        text NOT NULL,
  created_at           timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id, manifest_hash),
  FOREIGN KEY (release_decision_id, report_version_id, report_version_hash)
    REFERENCES lfhe.release_decisions (id, report_version_id, report_version_hash),
  CHECK (manifest_hash = lfhe.jcs_sha256(manifest_json))
);

-- RELEASED (the only representation of the released state; DC6-01)
CREATE TABLE lfhe.report_releases (
  id                   uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  report_id            uuid NOT NULL REFERENCES lfhe.reports(id),
  report_version_id    uuid NOT NULL UNIQUE,
  report_version_hash  text NOT NULL,
  state                text NOT NULL DEFAULT 'RELEASED' CHECK (state = 'RELEASED'),
  release_decision_id  uuid NOT NULL UNIQUE,
  release_manifest_id  uuid NOT NULL UNIQUE,
  manifest_hash        text NOT NULL,
  pdf_artifact_id      uuid NOT NULL,
  pdf_sha256           text NOT NULL,
  released_by          uuid NOT NULL,
  released_at          timestamptz NOT NULL,
  FOREIGN KEY (report_version_id, report_version_hash) REFERENCES lfhe.report_versions (id, report_version_hash),
  FOREIGN KEY (release_decision_id, report_version_id, report_version_hash)
    REFERENCES lfhe.release_decisions (id, report_version_id, report_version_hash),
  FOREIGN KEY (release_manifest_id, manifest_hash) REFERENCES lfhe.release_manifests (id, manifest_hash),
  FOREIGN KEY (pdf_artifact_id, pdf_sha256) REFERENCES lfhe.release_pdf_artifacts (id, pdf_sha256)
);

DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['content_approvals', 'security_reviews', 'release_pdf_artifacts', 'release_decisions',
                           'release_manifests', 'report_releases'] LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON lfhe.%I FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation()',
                   t || '_immutable', t);
  END LOOP;
END $$;
CREATE TRIGGER report_releases_no_truncate BEFORE TRUNCATE ON lfhe.report_releases
  FOR EACH STATEMENT EXECUTE FUNCTION lfhe.block_mutation();
CREATE TRIGGER release_manifests_no_truncate BEFORE TRUNCATE ON lfhe.release_manifests
  FOR EACH STATEMENT EXECUTE FUNCTION lfhe.block_mutation();
CREATE TRIGGER release_pdf_artifacts_no_truncate BEFORE TRUNCATE ON lfhe.release_pdf_artifacts
  FOR EACH STATEMENT EXECUTE FUNCTION lfhe.block_mutation();

-- RELEASED / manifest / APPROVE_FOR_RELEASE rows may only be written inside lfhe.release_report,
-- which sets a transaction-local token naming the exact version / hash being released.
CREATE OR REPLACE FUNCTION lfhe.p6_release_guard()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  IF TG_TABLE_NAME = 'release_decisions' THEN
    IF (pg_catalog.to_jsonb(NEW) ->> 'decision') <> 'APPROVE_FOR_RELEASE' THEN
      RETURN NEW;
    END IF;
  END IF;
  IF coalesce(pg_catalog.current_setting('lfhe.p6_release_tx', true), '')
       IS DISTINCT FROM NEW.report_version_id::text || ':' || NEW.report_version_hash THEN
    RAISE EXCEPTION 'RELEASED_WRITE_PROHIBITED: % rows are written only by lfhe.release_report', TG_TABLE_NAME
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION lfhe.p6_release_guard() FROM PUBLIC;
CREATE TRIGGER release_decisions_guard BEFORE INSERT ON lfhe.release_decisions FOR EACH ROW EXECUTE FUNCTION lfhe.p6_release_guard();
CREATE TRIGGER release_manifests_guard BEFORE INSERT ON lfhe.release_manifests FOR EACH ROW EXECUTE FUNCTION lfhe.p6_release_guard();
CREATE TRIGGER report_releases_guard BEFORE INSERT ON lfhe.report_releases FOR EACH ROW EXECUTE FUNCTION lfhe.p6_release_guard();

-- ---------------------------------------------------------------------------
-- Current-chain helpers (all deterministic)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.p6_current_content_approval(p_version uuid)
RETURNS lfhe.content_approvals LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT c.* FROM lfhe.content_approvals c
  WHERE c.qa_result_id = (lfhe.p6_current_qa_result(p_version)).id
$$;

CREATE OR REPLACE FUNCTION lfhe.p6_current_security_review(p_content_approval uuid)
RETURNS lfhe.security_reviews LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT s.* FROM lfhe.security_reviews s WHERE s.content_approval_id = p_content_approval ORDER BY s.seq DESC LIMIT 1
$$;

CREATE OR REPLACE FUNCTION lfhe.p6_renderer_identity_ok(p_pdf lfhe.release_pdf_artifacts)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT EXISTS (SELECT 1 FROM lfhe.report_renders rr WHERE rr.id = p_pdf.preview_render_id
                 AND rr.report_version_id = p_pdf.report_version_id AND rr.report_version_hash = p_pdf.report_version_hash
                 AND rr.template_version = p_pdf.template_version AND rr.template_sha256 = p_pdf.template_hash)
     AND p_pdf.renderer_hash = lfhe.jcs_sha256(p_pdf.renderer_identity)
     AND (p_pdf.renderer_identity ->> 'renderer_version') = p_pdf.renderer_version
     AND (p_pdf.renderer_identity ->> 'template_version') = p_pdf.template_version
$$;

-- The deterministic release-eligibility checklist (Addendum §20). Pure read; p_actor is the caller
-- whose RELEASE_DECIDE authority is evaluated (NULL = not a human).
CREATE OR REPLACE FUNCTION lfhe.p6_release_checklist(p_version uuid, p_hash text, p_pdf uuid, p_actor uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v      lfhe.report_versions;
  q      lfhe.qa_results;
  d      lfhe.qa_runs;
  s      lfhe.qa_runs;
  ca     lfhe.content_approvals;
  sr     lfhe.security_reviews;
  f      lfhe.release_pdf_artifacts;
  v_ck   jsonb := '[]';
  v_un   uuid[];
  v_acks uuid[];
  v_ok   boolean;
BEGIN
  SELECT * INTO v FROM lfhe.report_versions WHERE id = p_version;
  v_ck := v_ck || pg_catalog.jsonb_build_object('code', 'VERSION_EXISTS', 'ok', v.id IS NOT NULL);
  v_ck := v_ck || pg_catalog.jsonb_build_object('code', 'HASH_MATCHES', 'ok', v.id IS NOT NULL AND v.report_version_hash = p_hash
                                                AND lfhe.jcs_sha256(v.canonical_json) = v.report_version_hash);
  v_ck := v_ck || pg_catalog.jsonb_build_object('code', 'VERSION_CURRENT', 'ok', coalesce(lfhe.p6_is_latest_version(p_version), false));
  v_ck := v_ck || pg_catalog.jsonb_build_object('code', 'NOT_ALREADY_RELEASED',
                                                'ok', NOT EXISTS (SELECT 1 FROM lfhe.report_releases x WHERE x.report_version_id = p_version));
  q := lfhe.p6_current_qa_result(p_version);
  SELECT * INTO d FROM lfhe.qa_runs WHERE id = q.deterministic_qa_run_id;
  SELECT * INTO s FROM lfhe.qa_runs WHERE id = q.semantic_qa_run_id;
  v_ck := v_ck || pg_catalog.jsonb_build_object('code', 'QA_BOUND_TO_VERSION', 'ok', q.id IS NOT NULL AND q.report_version_hash = p_hash,
                                                'qa_result_id', q.id);
  v_ck := v_ck || pg_catalog.jsonb_build_object('code', 'M10D_COMPLETE', 'ok', d.status IS NOT DISTINCT FROM 'COMPLETED');
  v_ck := v_ck || pg_catalog.jsonb_build_object('code', 'M10S_COMPLETE', 'ok', s.status IS NOT DISTINCT FROM 'COMPLETED');
  v_un := CASE WHEN q.id IS NULL THEN '{}' ELSE lfhe.p6_unacknowledged_warnings(q.id) END;
  v_ck := v_ck || pg_catalog.jsonb_build_object('code', 'QA_ACCEPTABLE',
            'ok', q.status IS NOT DISTINCT FROM 'PASS' OR (q.status IS NOT DISTINCT FROM 'PASS_WITH_WARNINGS' AND cardinality(v_un) = 0),
            'qa_status', q.status, 'unacknowledged_warnings', pg_catalog.to_jsonb(v_un));
  v_ck := v_ck || pg_catalog.jsonb_build_object('code', 'NO_CRITICAL_FINDING',
            'ok', q.id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM lfhe.qa_check_results x WHERE x.qa_run_id IN (q.deterministic_qa_run_id,
                  q.semantic_qa_run_id) AND (x.severity = 'CRITICAL' OR x.status = 'FAIL')));
  ca := lfhe.p6_current_content_approval(p_version);
  v_acks := ARRAY(SELECT a.id FROM lfhe.warning_acknowledgements a WHERE a.qa_result_id = q.id ORDER BY a.id);
  v_ck := v_ck || pg_catalog.jsonb_build_object('code', 'CONTENT_APPROVED',
            'ok', ca.decision IS NOT DISTINCT FROM 'APPROVE' AND ca.report_version_hash = p_hash
                  AND ca.warning_acknowledgement_ids @> v_acks AND v_acks @> ca.warning_acknowledgement_ids,
            'content_approval_id', ca.id);
  sr := CASE WHEN ca.id IS NULL THEN NULL ELSE lfhe.p6_current_security_review(ca.id) END;
  v_ck := v_ck || pg_catalog.jsonb_build_object('code', 'SECURITY_APPROVED', 'ok', sr.status IS NOT DISTINCT FROM 'APPROVED'
                                                AND sr.report_version_hash = p_hash, 'security_review_id', sr.id);
  SELECT * INTO f FROM lfhe.release_pdf_artifacts WHERE id = p_pdf;
  v_ck := v_ck || pg_catalog.jsonb_build_object('code', 'PDF_EXISTS', 'ok', f.id IS NOT NULL, 'pdf_artifact_id', f.id);
  v_ck := v_ck || pg_catalog.jsonb_build_object('code', 'PDF_BOUND_TO_VERSION', 'ok', f.report_version_id IS NOT DISTINCT FROM p_version
                                                AND f.report_version_hash IS NOT DISTINCT FROM p_hash
                                                AND pg_catalog.strpos(f.source_html, p_version::text) > 0);
  v_ck := v_ck || pg_catalog.jsonb_build_object('code', 'PDF_HASH_VALID', 'ok', f.id IS NOT NULL
                                                AND pg_catalog.encode(extensions.digest(f.pdf_bytes, 'sha256'), 'hex') = f.pdf_sha256
                                                AND pg_catalog.octet_length(f.pdf_bytes) = f.byte_size, 'pdf_sha256', f.pdf_sha256);
  v_ck := v_ck || pg_catalog.jsonb_build_object('code', 'TEMPLATE_RENDERER_RESOLVE', 'ok', f.id IS NOT NULL AND lfhe.p6_renderer_identity_ok(f));
  v_ok := s.id IS NOT NULL AND EXISTS (SELECT 1 FROM lfhe.model_runs m JOIN lfhe.prompt_versions pv ON pv.id = m.prompt_version_id
                                       WHERE m.id = s.model_run_id AND m.status = 'SUCCEEDED' AND pv.content_hash = m.prompt_content_hash)
          AND (v.origin = 'HUMAN' OR EXISTS (SELECT 1 FROM lfhe.model_runs m WHERE m.id = v.created_by_model_run_id AND m.status = 'SUCCEEDED'));
  v_ck := v_ck || pg_catalog.jsonb_build_object('code', 'MODEL_PROVENANCE_RESOLVES', 'ok', v_ok);
  v_ok := v.id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM lfhe.report_statement_sources x JOIN lfhe.report_item_statements st ON st.id = x.report_item_statement_id
            JOIN lfhe.report_items i ON i.id = st.report_item_id
            WHERE i.report_version_id = v.id AND NOT lfhe.assessment_version_approved_asof(x.assessment_version_id, v.report_mode::text,
                                                                                            v.information_cutoff))
          AND EXISTS (SELECT 1 FROM lfhe.report_items i WHERE i.report_version_id = v.id);
  v_ck := v_ck || pg_catalog.jsonb_build_object('code', 'ANALYTICAL_PROVENANCE_RESOLVES', 'ok', v_ok);
  v_ck := v_ck || pg_catalog.jsonb_build_object('code', 'MANIFEST_INPUTS_COMPLETE', 'ok', v.id IS NOT NULL AND q.id IS NOT NULL
                                                AND ca.id IS NOT NULL AND sr.id IS NOT NULL AND f.id IS NOT NULL
                                                AND v.selection_set_id IS NOT NULL);
  v_ck := v_ck || pg_catalog.jsonb_build_object('code', 'CALLER_HUMAN_RELEASE_AUTHORITY',
                                                'ok', p_actor IS NOT NULL AND lfhe.user_has_permission(p_actor, 'RELEASE_DECIDE'));
  RETURN pg_catalog.jsonb_build_object(
    'eligible', NOT EXISTS (SELECT 1 FROM pg_catalog.jsonb_array_elements(v_ck) x WHERE NOT (x ->> 'ok')::boolean),
    'failed', (SELECT coalesce(pg_catalog.jsonb_agg(x ->> 'code'), '[]') FROM pg_catalog.jsonb_array_elements(v_ck) x
               WHERE NOT (x ->> 'ok')::boolean),
    'checks', v_ck,
    'refs', pg_catalog.jsonb_build_object('qa_result_id', q.id, 'deterministic_qa_run_id', q.deterministic_qa_run_id,
              'semantic_qa_run_id', q.semantic_qa_run_id, 'qa_status', q.status, 'warning_acknowledgement_ids', pg_catalog.to_jsonb(v_acks),
              'content_approval_id', ca.id, 'security_review_id', sr.id, 'pdf_artifact_id', f.id));
END $$;

-- UI / API read: the checklist exactly as the release transaction evaluates it, for the caller
CREATE OR REPLACE FUNCTION lfhe.release_eligibility(p_version uuid, p_hash text, p_pdf uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  IF NOT lfhe.has_permission('CLAIM_READ') THEN
    RAISE EXCEPTION 'permission CLAIM_READ required' USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN lfhe.p6_release_checklist(p_version, p_hash, p_pdf, lfhe.current_human_user());
END $$;

-- canonical release manifest (Addendum §23 + K-09); built from stored rows only
CREATE OR REPLACE FUNCTION lfhe.p6_build_manifest(p_decision uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  rd lfhe.release_decisions;
  v  lfhe.report_versions;
  r  lfhe.reports;
  q  lfhe.qa_results;
  d  lfhe.qa_runs;
  s  lfhe.qa_runs;
  m  lfhe.model_runs;
  f  lfhe.release_pdf_artifacts;
  m9 lfhe.model_runs;
BEGIN
  SELECT * INTO rd FROM lfhe.release_decisions WHERE id = p_decision;
  SELECT * INTO v FROM lfhe.report_versions WHERE id = rd.report_version_id;
  SELECT * INTO r FROM lfhe.reports WHERE id = v.report_id;
  SELECT * INTO q FROM lfhe.qa_results WHERE id = rd.qa_result_id;
  SELECT * INTO d FROM lfhe.qa_runs WHERE id = q.deterministic_qa_run_id;
  SELECT * INTO s FROM lfhe.qa_runs WHERE id = q.semantic_qa_run_id;
  SELECT * INTO m FROM lfhe.model_runs WHERE id = s.model_run_id;
  SELECT * INTO f FROM lfhe.release_pdf_artifacts WHERE id = rd.pdf_artifact_id;
  SELECT * INTO m9 FROM lfhe.model_runs WHERE id = v.created_by_model_run_id;
  RETURN pg_catalog.jsonb_build_object(
    'format', 'lfhe-release-manifest/1', 'manifest_schema_version', '1.0.0',
    'report', pg_catalog.jsonb_build_object('report_id', r.id, 'code', r.code, 'title', r.title, 'cycle_label', r.cycle_label,
                                            'report_mode', r.report_mode, 'information_cutoff', lfhe.p5_ts(r.information_cutoff)),
    'report_version', pg_catalog.jsonb_build_object('report_version_id', v.id, 'report_version_hash', v.report_version_hash,
                                                    'version_no', v.version_no, 'origin', v.origin,
                                                    'previous_report_version_id', v.previous_report_version_id,
                                                    'authoring_model_run_id', v.created_by_model_run_id,
                                                    'authoring_prompt_version_id', m9.prompt_version_id,
                                                    'authoring_prompt_hash', m9.prompt_content_hash),
    'selection_set', pg_catalog.jsonb_build_object('id', v.selection_set_id, 'hash', v.selection_set_hash),
    'analytical_provenance', (SELECT coalesce(pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
         'section', i.section, 'item_local_id', i.item_local_id,
         'assessment_version', CASE WHEN i.pinned_assessment_version_id IS NULL THEN NULL ELSE pg_catalog.jsonb_build_object(
            'id', i.pinned_assessment_version_id, 'hash', i.pinned_assessment_version_hash,
            'analytical_approval_id', (SELECT a.id FROM lfhe.analytical_approvals a WHERE a.assessment_version_id = i.pinned_assessment_version_id
                                       AND a.decision IN ('APPROVE', 'MODIFY_AND_APPROVE'))) END,
         'event_version', CASE WHEN i.pinned_event_version_id IS NULL THEN NULL
                               ELSE pg_catalog.jsonb_build_object('id', i.pinned_event_version_id, 'hash', i.pinned_event_version_hash) END,
         'indicator_version', CASE WHEN i.pinned_indicator_version_id IS NULL THEN NULL
                               ELSE pg_catalog.jsonb_build_object('id', i.pinned_indicator_version_id, 'hash', i.pinned_indicator_version_hash) END,
         'trend_version', CASE WHEN i.pinned_trend_version_id IS NULL THEN NULL
                               ELSE pg_catalog.jsonb_build_object('id', i.pinned_trend_version_id, 'hash', i.pinned_trend_version_hash) END)
         ORDER BY i.section, i.item_no), '[]') FROM lfhe.report_items i WHERE i.report_version_id = v.id),
    'qa', pg_catalog.jsonb_build_object('qa_result_id', q.id, 'combined_qa_status', q.status,
            'deterministic_qa_run_id', d.id, 'deterministic_engine_version', d.engine_version,
            'semantic_qa_run_id', s.id, 'm10s_model_run_id', m.id, 'm10_prompt_version_id', m.prompt_version_id,
            'm10_prompt_semver', m.prompt_semver, 'm10_prompt_hash', m.prompt_content_hash, 'm10_module_version', m.module_version,
            'm10_model_configuration_hash', m.model_config_hash),
    'warning_acknowledgement_ids', (SELECT coalesce(pg_catalog.jsonb_agg(x ORDER BY x), '[]') FROM pg_catalog.unnest(rd.warning_acknowledgement_ids) x),
    'content_approval_id', rd.content_approval_id,
    'security_review_id', rd.security_review_id,
    'release_decision_id', rd.id,
    'released_by', rd.decided_by,
    'release_timestamp', lfhe.p5_ts(rd.created_at),
    'rendering', pg_catalog.jsonb_build_object('template_version', f.template_version, 'template_hash', f.template_hash,
            'renderer_version', f.renderer_version, 'renderer_hash', f.renderer_hash, 'preview_render_id', f.preview_render_id,
            'source_html_sha256', f.source_html_sha256),
    'pdf', pg_catalog.jsonb_build_object('pdf_artifact_id', f.id, 'pdf_sha256', f.pdf_sha256, 'byte_size', f.byte_size,
            'mime_type', f.mime_type, 'storage_key', f.storage_key));
END $$;

-- final manifest completeness (D25 at the release gate): every required reference present
CREATE OR REPLACE FUNCTION lfhe.p6_manifest_problems(p jsonb)
RETURNS text[] LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
  SELECT ARRAY(SELECT k FROM pg_catalog.unnest(ARRAY[
      '{manifest_schema_version}', '{report,report_id}', '{report,report_mode}', '{report,information_cutoff}',
      '{report_version,report_version_id}', '{report_version,report_version_hash}', '{selection_set,id}', '{selection_set,hash}',
      '{qa,deterministic_qa_run_id}', '{qa,semantic_qa_run_id}', '{qa,combined_qa_status}', '{qa,m10s_model_run_id}',
      '{qa,m10_prompt_version_id}', '{qa,m10_prompt_hash}', '{content_approval_id}', '{security_review_id}', '{release_decision_id}',
      '{released_by}', '{release_timestamp}', '{rendering,template_version}', '{rendering,template_hash}', '{rendering,renderer_version}',
      '{rendering,renderer_hash}', '{pdf,pdf_artifact_id}', '{pdf,pdf_sha256}', '{pdf,byte_size}', '{pdf,mime_type}',
      '{warning_acknowledgement_ids}', '{analytical_provenance}']) k
    WHERE p #> k::text[] IS NULL OR p #> k::text[] = 'null'::jsonb
       OR (k = '{analytical_provenance}' AND pg_catalog.jsonb_array_length(p -> 'analytical_provenance') = 0)
    ORDER BY 1)
$$;

-- ---------------------------------------------------------------------------
-- HUMAN_ONLY (REPORT_CONTENT_APPROVE): content decision on the current QA result
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.decide_report_content(p_version uuid, p_hash text, p_qa_result uuid, p_decision text,
                                                      p_rationale text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('REPORT_CONTENT_APPROVE');
  v       lfhe.report_versions;
  q       lfhe.qa_results;
  v_acks  uuid[];
  v_id    uuid;
  v_sr    uuid;
BEGIN
  IF p_decision IS NULL OR p_decision NOT IN ('APPROVE', 'RETURN_FOR_REVISION', 'REJECT') THEN
    RAISE EXCEPTION 'CONTENT_DECISION_UNKNOWN: %', p_decision USING ERRCODE = 'invalid_parameter_value';
  END IF;
  IF p_rationale IS NULL OR length(btrim(p_rationale)) < 10 THEN
    RAISE EXCEPTION 'a rationale (>= 10 characters) is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  v := lfhe.p5_require_latest_version(p_version, p_hash);
  q := lfhe.p6_current_qa_result(v.id);
  IF q.id IS NULL OR q.id <> p_qa_result THEN
    RAISE EXCEPTION 'QA_RESULT_STALE: % is not the current QA result of version %', p_qa_result, v.id
      USING ERRCODE = 'serialization_failure';
  END IF;
  IF EXISTS (SELECT 1 FROM lfhe.content_approvals c WHERE c.qa_result_id = q.id) THEN
    RAISE EXCEPTION 'CONTENT_ALREADY_DECIDED for QA result %', q.id USING ERRCODE = 'unique_violation';
  END IF;
  IF p_decision = 'APPROVE' THEN
    IF q.status = 'FAIL' THEN
      RAISE EXCEPTION 'CONTENT_APPROVAL_QA_FAILED: QA result % is FAIL (%)', q.id, array_to_string(q.fail_reasons, ', ')
        USING ERRCODE = 'check_violation';
    END IF;
    IF cardinality(lfhe.p6_unacknowledged_warnings(q.id)) > 0 THEN
      RAISE EXCEPTION 'WARNINGS_NOT_ACKNOWLEDGED: % warning(s) of QA result % need acknowledgement',
        cardinality(lfhe.p6_unacknowledged_warnings(q.id)), q.id USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  v_acks := ARRAY(SELECT a.id FROM lfhe.warning_acknowledgements a WHERE a.qa_result_id = q.id ORDER BY a.id);
  INSERT INTO lfhe.content_approvals (report_id, report_version_id, report_version_hash, qa_result_id, qa_status, decision,
    warning_acknowledgement_ids, reviewer_user_id, rationale)
  VALUES (v.report_id, v.id, v.report_version_hash, q.id, q.status, p_decision, v_acks, v_actor, p_rationale)
  RETURNING id INTO v_id;
  PERFORM lfhe.write_audit('REPORT_CONTENT_DECIDED', 'report_version', v.id::text, NULL,
    pg_catalog.jsonb_build_object('content_approval_id', v_id, 'decision', p_decision, 'qa_result_id', q.id, 'qa_status', q.status,
                                  'warning_acknowledgement_ids', pg_catalog.to_jsonb(v_acks),
                                  'report_version_hash', v.report_version_hash, 'rationale', p_rationale), '{}');
  IF p_decision = 'APPROVE' THEN
    INSERT INTO lfhe.security_reviews (report_id, report_version_id, report_version_hash, content_approval_id, status)
    VALUES (v.report_id, v.id, v.report_version_hash, v_id, 'PENDING') RETURNING id INTO v_sr;
    PERFORM lfhe.write_audit('SECURITY_REVIEW_OPENED', 'report_version', v.id::text, NULL,
      pg_catalog.jsonb_build_object('security_review_id', v_sr, 'content_approval_id', v_id, 'status', 'PENDING',
                                    'report_version_hash', v.report_version_hash), '{}');
  END IF;
  RETURN pg_catalog.jsonb_build_object('content_approval_id', v_id, 'decision', p_decision, 'security_review_id', v_sr);
END $$;
COMMENT ON FUNCTION lfhe.decide_report_content(uuid, text, uuid, text, text) IS 'HUMAN_ONLY';

-- ---------------------------------------------------------------------------
-- HUMAN_ONLY (SECURITY_REVIEW): decide the PENDING security / handling review
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.decide_security_review(p_version uuid, p_hash text, p_review uuid, p_status text, p_rationale text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('SECURITY_REVIEW');
  v       lfhe.report_versions;
  pr      lfhe.security_reviews;
  ca      lfhe.content_approvals;
  v_id    uuid;
  v_job   uuid;
BEGIN
  IF p_status IS NULL OR p_status NOT IN ('APPROVED', 'RETURN_FOR_REVISION', 'REJECTED') THEN
    RAISE EXCEPTION 'SECURITY_STATUS_UNKNOWN: %', p_status USING ERRCODE = 'invalid_parameter_value';
  END IF;
  IF p_rationale IS NULL OR length(btrim(p_rationale)) < 10 THEN
    RAISE EXCEPTION 'a rationale (>= 10 characters) is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  v := lfhe.p5_require_latest_version(p_version, p_hash);
  SELECT * INTO pr FROM lfhe.security_reviews WHERE id = p_review;
  IF NOT FOUND OR pr.status <> 'PENDING' OR pr.report_version_id <> v.id OR pr.report_version_hash <> v.report_version_hash THEN
    RAISE EXCEPTION 'SECURITY_REVIEW_NOT_PENDING_FOR_VERSION: %', p_review USING ERRCODE = 'check_violation';
  END IF;
  ca := lfhe.p6_current_content_approval(v.id);
  IF ca.id IS DISTINCT FROM pr.content_approval_id OR ca.decision <> 'APPROVE' THEN
    RAISE EXCEPTION 'CONTENT_APPROVAL_NOT_CURRENT: the security review belongs to a superseded content approval'
      USING ERRCODE = 'serialization_failure';
  END IF;
  IF EXISTS (SELECT 1 FROM lfhe.security_reviews x WHERE x.pending_review_id = pr.id) THEN
    RAISE EXCEPTION 'SECURITY_REVIEW_ALREADY_DECIDED' USING ERRCODE = 'unique_violation';
  END IF;
  INSERT INTO lfhe.security_reviews (report_id, report_version_id, report_version_hash, content_approval_id, status,
    pending_review_id, reviewer_user_id, rationale)
  VALUES (v.report_id, v.id, v.report_version_hash, ca.id, p_status::lfhe.security_review_status, pr.id, v_actor, p_rationale)
  RETURNING id INTO v_id;
  PERFORM lfhe.write_audit('SECURITY_REVIEW_DECIDED', 'report_version', v.id::text,
    pg_catalog.jsonb_build_object('security_review_id', pr.id, 'status', 'PENDING'),
    pg_catalog.jsonb_build_object('security_review_id', v_id, 'status', p_status, 'content_approval_id', ca.id,
                                  'report_version_hash', v.report_version_hash, 'rationale', p_rationale), '{}');
  IF p_status = 'APPROVED' THEN
    v_job := lfhe.enqueue_job('RENDER_RELEASE_PDF', 'report_version', v.id::text, 'RENDER_RELEASE_PDF:' || v_id,
      pg_catalog.jsonb_build_object('report_version_hash', v.report_version_hash, 'security_review_id', v_id), 80::smallint, 3);
  END IF;
  RETURN pg_catalog.jsonb_build_object('security_review_id', v_id, 'status', p_status, 'release_pdf_job_id', v_job);
END $$;
COMMENT ON FUNCTION lfhe.decide_security_review(uuid, text, uuid, text, text) IS 'HUMAN_ONLY';

-- ---------------------------------------------------------------------------
-- Release PDF (worker records; RELEASE_DECIDE human may request a re-render)
-- p: {report_version_id, report_version_hash, preview_render_id, source_html, template_version, template_hash,
--     renderer_version, renderer_identity{}, storage_key, pdf_base64, worker_id}
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.record_release_pdf(p jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v      lfhe.report_versions;
  rr     lfhe.report_renders;
  v_b    bytea;
  v_sha  text;
  v_old  lfhe.release_pdf_artifacts;
  v_id   uuid;
BEGIN
  SELECT * INTO v FROM lfhe.report_versions WHERE id::text = p ->> 'report_version_id';
  IF NOT FOUND OR v.report_version_hash IS DISTINCT FROM p ->> 'report_version_hash' THEN
    RAISE EXCEPTION 'VERSION_HASH_MISMATCH: report version %', p ->> 'report_version_id' USING ERRCODE = 'serialization_failure';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM lfhe.security_reviews s WHERE s.report_version_id = v.id AND s.report_version_hash = v.report_version_hash
                 AND s.status = 'APPROVED') THEN
    RAISE EXCEPTION 'NO_RELEASE_CANDIDATE: version % has no approved security review', v.id USING ERRCODE = 'check_violation';
  END IF;
  SELECT * INTO rr FROM lfhe.report_renders WHERE id::text = p ->> 'preview_render_id';
  IF NOT FOUND OR rr.report_version_id <> v.id OR rr.report_version_hash <> v.report_version_hash
     OR rr.template_version IS DISTINCT FROM p ->> 'template_version' OR rr.template_sha256 IS DISTINCT FROM p ->> 'template_hash' THEN
    RAISE EXCEPTION 'PDF_RENDER_BINDING_INVALID: preview render / template does not belong to version %', v.id
      USING ERRCODE = 'check_violation';
  END IF;
  IF pg_catalog.strpos(p ->> 'source_html', v.id::text) = 0 OR pg_catalog.strpos(p ->> 'source_html', v.report_version_hash) = 0 THEN
    RAISE EXCEPTION 'RENDER_NOT_BOUND_TO_VERSION' USING ERRCODE = 'check_violation';
  END IF;
  IF (p -> 'renderer_identity' ->> 'renderer_version') IS DISTINCT FROM p ->> 'renderer_version'
     OR (p -> 'renderer_identity' ->> 'template_version') IS DISTINCT FROM p ->> 'template_version' THEN
    RAISE EXCEPTION 'RENDERER_IDENTITY_INVALID' USING ERRCODE = 'check_violation';
  END IF;
  v_b := pg_catalog.decode(p ->> 'pdf_base64', 'base64');
  v_sha := pg_catalog.encode(extensions.digest(v_b, 'sha256'), 'hex');
  SELECT * INTO v_old FROM lfhe.release_pdf_artifacts WHERE report_version_id = v.id AND pdf_sha256 = v_sha;
  IF FOUND THEN
    RETURN pg_catalog.jsonb_build_object('pdf_artifact_id', v_old.id, 'pdf_sha256', v_sha, 'new', false);
  END IF;
  INSERT INTO lfhe.release_pdf_artifacts (report_id, report_version_id, report_version_hash, preview_render_id, source_html,
    source_html_sha256, template_version, template_hash, renderer_version, renderer_hash, renderer_identity, storage_key, mime_type,
    byte_size, pdf_sha256, pdf_bytes, worker_id)
  VALUES (v.report_id, v.id, v.report_version_hash, rr.id, p ->> 'source_html',
    pg_catalog.encode(extensions.digest(pg_catalog.convert_to(p ->> 'source_html', 'UTF8'), 'sha256'), 'hex'),
    p ->> 'template_version', p ->> 'template_hash', p ->> 'renderer_version', lfhe.jcs_sha256(p -> 'renderer_identity'),
    p -> 'renderer_identity', p ->> 'storage_key', 'application/pdf', pg_catalog.octet_length(v_b), v_sha, v_b, p ->> 'worker_id')
  RETURNING id INTO v_id;
  RETURN pg_catalog.jsonb_build_object('pdf_artifact_id', v_id, 'pdf_sha256', v_sha, 'new', true);
END $$;

CREATE OR REPLACE FUNCTION lfhe.request_release_pdf(p_version uuid, p_hash text, p_reason text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('RELEASE_DECIDE');
  v       lfhe.report_versions;
  sr      lfhe.security_reviews;
  v_job   uuid;
BEGIN
  IF p_reason IS NULL OR length(btrim(p_reason)) < 5 THEN
    RAISE EXCEPTION 'a reason is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  v := lfhe.p5_require_latest_version(p_version, p_hash);
  sr := lfhe.p6_current_security_review((lfhe.p6_current_content_approval(v.id)).id);
  IF sr.status IS DISTINCT FROM 'APPROVED' THEN
    RAISE EXCEPTION 'NO_RELEASE_CANDIDATE: version % has no current approved security review', v.id USING ERRCODE = 'check_violation';
  END IF;
  v_job := lfhe.enqueue_job('RENDER_RELEASE_PDF', 'report_version', v.id::text,
    'RENDER_RELEASE_PDF:' || sr.id || ':' || pg_catalog.gen_random_uuid(),
    pg_catalog.jsonb_build_object('report_version_hash', v.report_version_hash, 'security_review_id', sr.id), 80::smallint, 3);
  PERFORM lfhe.write_audit('RELEASE_PDF_REQUESTED', 'report_version', v.id::text, NULL,
    pg_catalog.jsonb_build_object('job_id', v_job, 'report_version_hash', v.report_version_hash, 'reason', p_reason), '{}');
  RETURN v_job;
END $$;
COMMENT ON FUNCTION lfhe.request_release_pdf(uuid, text, text) IS 'HUMAN_ONLY';

-- ---------------------------------------------------------------------------
-- HUMAN_ONLY (RELEASE_DECIDE): RETURN_FOR_REVISION / REJECT_RELEASE (never creates RELEASED)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.decide_release(p_version uuid, p_hash text, p_decision text, p_rationale text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('RELEASE_DECIDE');
  v       lfhe.report_versions;
  v_ck    jsonb;
  v_id    uuid;
BEGIN
  IF p_decision IS NULL OR p_decision NOT IN ('RETURN_FOR_REVISION', 'REJECT_RELEASE') THEN
    RAISE EXCEPTION 'RELEASE_DECISION_NOT_ALLOWED_HERE: % (APPROVE_FOR_RELEASE only through lfhe.release_report)', p_decision
      USING ERRCODE = 'invalid_parameter_value';
  END IF;
  IF p_rationale IS NULL OR length(btrim(p_rationale)) < 10 THEN
    RAISE EXCEPTION 'a rationale (>= 10 characters) is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  v := lfhe.p5_require_latest_version(p_version, p_hash);
  IF EXISTS (SELECT 1 FROM lfhe.report_releases x WHERE x.report_version_id = v.id) THEN
    RAISE EXCEPTION 'REPORT_VERSION_RELEASED' USING ERRCODE = 'check_violation';
  END IF;
  v_ck := lfhe.p6_release_checklist(v.id, v.report_version_hash, NULL, v_actor);
  IF (v_ck -> 'refs' ->> 'security_review_id') IS NULL
     OR (SELECT status FROM lfhe.security_reviews WHERE id = (v_ck -> 'refs' ->> 'security_review_id')::uuid) <> 'APPROVED' THEN
    RAISE EXCEPTION 'NO_RELEASE_CANDIDATE: version % has no current approved security review', v.id USING ERRCODE = 'check_violation';
  END IF;
  INSERT INTO lfhe.release_decisions (report_id, report_version_id, report_version_hash, decision, qa_result_id,
    deterministic_qa_run_id, semantic_qa_run_id, qa_status, warning_acknowledgement_ids, content_approval_id, security_review_id,
    eligibility, decided_by, rationale)
  VALUES (v.report_id, v.id, v.report_version_hash, p_decision::lfhe.release_decision, (v_ck -> 'refs' ->> 'qa_result_id')::uuid,
    (v_ck -> 'refs' ->> 'deterministic_qa_run_id')::uuid, (v_ck -> 'refs' ->> 'semantic_qa_run_id')::uuid, v_ck -> 'refs' ->> 'qa_status',
    ARRAY(SELECT x::uuid FROM pg_catalog.jsonb_array_elements_text(v_ck -> 'refs' -> 'warning_acknowledgement_ids') x),
    (v_ck -> 'refs' ->> 'content_approval_id')::uuid, (v_ck -> 'refs' ->> 'security_review_id')::uuid, v_ck, v_actor, p_rationale)
  RETURNING id INTO v_id;
  PERFORM lfhe.write_audit(CASE p_decision WHEN 'REJECT_RELEASE' THEN 'REPORT_RELEASE_REJECTED' ELSE 'RELEASE_RETURNED_FOR_REVISION' END,
    'report_version', v.id::text, NULL,
    pg_catalog.jsonb_build_object('release_decision_id', v_id, 'decision', p_decision, 'report_version_hash', v.report_version_hash,
                                  'rationale', p_rationale), '{}');
  RETURN v_id;
END $$;
COMMENT ON FUNCTION lfhe.decide_release(uuid, text, text, text) IS 'HUMAN_ONLY';

-- ---------------------------------------------------------------------------
-- HUMAN_ONLY (RELEASE_DECIDE): the ONLY path to RELEASED. One transaction:
-- re-check eligibility → APPROVE_FOR_RELEASE decision → manifest (JCS / SHA-256) → RELEASED.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.release_report(p_version uuid, p_hash text, p_pdf_artifact uuid, p_rationale text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor  uuid := lfhe.require_human_permission('RELEASE_DECIDE');
  v        lfhe.report_versions;
  v_ck     jsonb;
  v_dec    uuid;
  v_man    jsonb;
  v_mhash  text;
  v_mid    uuid;
  v_rel    uuid;
  v_probs  text[];
  f        lfhe.release_pdf_artifacts;
BEGIN
  IF p_rationale IS NULL OR length(btrim(p_rationale)) < 10 THEN
    RAISE EXCEPTION 'a rationale (>= 10 characters) is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  SELECT * INTO v FROM lfhe.report_versions WHERE id = p_version;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'RELEASE_NOT_ELIGIBLE: VERSION_EXISTS' USING ERRCODE = 'check_violation';
  END IF;
  PERFORM 1 FROM lfhe.reports WHERE id = v.report_id FOR UPDATE;
  v_ck := lfhe.p6_release_checklist(p_version, p_hash, p_pdf_artifact, v_actor);
  IF NOT (v_ck ->> 'eligible')::boolean THEN
    RAISE EXCEPTION 'RELEASE_NOT_ELIGIBLE: %', (SELECT string_agg(x, ', ') FROM pg_catalog.jsonb_array_elements_text(v_ck -> 'failed') x)
      USING ERRCODE = 'check_violation';
  END IF;
  SELECT * INTO f FROM lfhe.release_pdf_artifacts WHERE id = p_pdf_artifact;
  PERFORM pg_catalog.set_config('lfhe.p6_release_tx', v.id::text || ':' || v.report_version_hash, true);
  INSERT INTO lfhe.release_decisions (report_id, report_version_id, report_version_hash, decision, qa_result_id,
    deterministic_qa_run_id, semantic_qa_run_id, qa_status, warning_acknowledgement_ids, content_approval_id, security_review_id,
    pdf_artifact_id, eligibility, decided_by, rationale)
  VALUES (v.report_id, v.id, v.report_version_hash, 'APPROVE_FOR_RELEASE', (v_ck -> 'refs' ->> 'qa_result_id')::uuid,
    (v_ck -> 'refs' ->> 'deterministic_qa_run_id')::uuid, (v_ck -> 'refs' ->> 'semantic_qa_run_id')::uuid, v_ck -> 'refs' ->> 'qa_status',
    ARRAY(SELECT x::uuid FROM pg_catalog.jsonb_array_elements_text(v_ck -> 'refs' -> 'warning_acknowledgement_ids') x ORDER BY 1),
    (v_ck -> 'refs' ->> 'content_approval_id')::uuid, (v_ck -> 'refs' ->> 'security_review_id')::uuid, f.id, v_ck, v_actor, p_rationale)
  RETURNING id INTO v_dec;
  v_man := lfhe.p6_build_manifest(v_dec);
  v_probs := lfhe.p6_manifest_problems(v_man);
  IF cardinality(v_probs) > 0 THEN
    RAISE EXCEPTION 'MANIFEST_INCOMPLETE: %', array_to_string(v_probs, ', ') USING ERRCODE = 'check_violation';
  END IF;
  v_mhash := lfhe.jcs_sha256(v_man);
  INSERT INTO lfhe.release_manifests (release_decision_id, report_version_id, report_version_hash, manifest_json, manifest_hash)
  VALUES (v_dec, v.id, v.report_version_hash, v_man, v_mhash) RETURNING id INTO v_mid;
  IF (SELECT lfhe.jcs_sha256(manifest_json) FROM lfhe.release_manifests WHERE id = v_mid) <> v_mhash THEN
    RAISE EXCEPTION 'MANIFEST_HASH_MISMATCH' USING ERRCODE = 'check_violation';
  END IF;
  INSERT INTO lfhe.report_releases (report_id, report_version_id, report_version_hash, release_decision_id, release_manifest_id,
    manifest_hash, pdf_artifact_id, pdf_sha256, released_by, released_at)
  VALUES (v.report_id, v.id, v.report_version_hash, v_dec, v_mid, v_mhash, f.id, f.pdf_sha256, v_actor,
    (SELECT created_at FROM lfhe.release_decisions WHERE id = v_dec))
  RETURNING id INTO v_rel;
  PERFORM pg_catalog.set_config('lfhe.p6_release_tx', '', true);
  PERFORM lfhe.write_audit('REPORT_RELEASE_APPROVED', 'report_version', v.id::text, NULL,
    pg_catalog.jsonb_build_object('release_decision_id', v_dec, 'report_release_id', v_rel, 'report_version_hash', v.report_version_hash,
                                  'pdf_sha256', f.pdf_sha256, 'manifest_hash', v_mhash, 'rationale', p_rationale), '{}');
  PERFORM lfhe.write_audit('REPORT_RELEASE_MANIFEST_CREATED', 'release_manifest', v_mid::text, NULL,
    pg_catalog.jsonb_build_object('release_decision_id', v_dec, 'manifest_hash', v_mhash, 'report_version_id', v.id,
                                  'report_version_hash', v.report_version_hash), '{}');
  RETURN pg_catalog.jsonb_build_object('report_release_id', v_rel, 'release_decision_id', v_dec, 'release_manifest_id', v_mid,
    'manifest_hash', v_mhash, 'pdf_sha256', f.pdf_sha256, 'state', 'RELEASED');
END $$;
COMMENT ON FUNCTION lfhe.release_report(uuid, text, uuid, text) IS 'HUMAN_ONLY';

-- ---------------------------------------------------------------------------
-- Post-QA edits / corrections: a new version invalidates (never deletes) the previous chain
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.p6_new_version_audit()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_rel lfhe.report_releases;
BEGIN
  IF NEW.previous_report_version_id IS NULL THEN
    RETURN NULL;
  END IF;
  SELECT x.* INTO v_rel FROM lfhe.report_releases x JOIN lfhe.report_versions o ON o.id = x.report_version_id
  WHERE o.report_id = NEW.report_id AND o.version_no < NEW.version_no ORDER BY o.version_no DESC LIMIT 1;
  IF v_rel.id IS NOT NULL THEN
    PERFORM lfhe.write_audit('REPORT_CORRECTION_CREATED', 'report_version', NEW.id::text, NULL,
      pg_catalog.jsonb_build_object('report_version_hash', NEW.report_version_hash, 'released_report_version_id', v_rel.report_version_id,
                                    'released_report_version_hash', v_rel.report_version_hash, 'report_release_id', v_rel.id,
                                    'manifest_hash', v_rel.manifest_hash), '{}');
  END IF;
  IF EXISTS (SELECT 1 FROM lfhe.qa_results q WHERE q.report_version_id = NEW.previous_report_version_id) THEN
    PERFORM lfhe.write_audit('QA_INVALIDATED_BY_REPORT_CHANGE', 'report_version', NEW.previous_report_version_id::text, NULL,
      pg_catalog.jsonb_build_object('new_report_version_id', NEW.id, 'new_report_version_hash', NEW.report_version_hash), '{}');
  END IF;
  IF EXISTS (SELECT 1 FROM lfhe.security_reviews s WHERE s.report_version_id = NEW.previous_report_version_id AND s.status = 'APPROVED') THEN
    PERFORM lfhe.write_audit('SECURITY_APPROVAL_INVALIDATED', 'report_version', NEW.previous_report_version_id::text, NULL,
      pg_catalog.jsonb_build_object('new_report_version_id', NEW.id, 'new_report_version_hash', NEW.report_version_hash), '{}');
  END IF;
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION lfhe.p6_new_version_audit() FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
CREATE TRIGGER report_versions_p6_invalidation AFTER INSERT ON lfhe.report_versions
  FOR EACH ROW EXECUTE FUNCTION lfhe.p6_new_version_audit();

CREATE TRIGGER release_pdf_artifacts_audit AFTER INSERT ON lfhe.release_pdf_artifacts
  FOR EACH ROW EXECUTE FUNCTION lfhe.audit_p6_objects('RELEASE_PDF_RECORDED', 'report_version', 'report_version_id');

-- ---------------------------------------------------------------------------
-- Derived workflow state (DC6-01: a view, not a mutable status)
-- ---------------------------------------------------------------------------
CREATE VIEW lfhe.report_version_workflow WITH (security_invoker = true) AS
SELECT v.id AS report_version_id, v.report_id, v.version_no, v.report_version_hash,
       NOT EXISTS (SELECT 1 FROM lfhe.report_versions x WHERE x.report_id = v.report_id AND x.version_no > v.version_no) AS is_latest,
       q.id AS qa_result_id, q.status AS qa_status, q.deterministic_qa_run_id, q.semantic_qa_run_id,
       cardinality(q.warning_finding_ids) AS warnings_total,
       (SELECT count(*) FROM lfhe.warning_acknowledgements a WHERE a.qa_result_id = q.id) AS warnings_acknowledged,
       ca.id AS content_approval_id, ca.decision AS content_decision,
       sr.id AS security_review_id, sr.status::text AS security_status,
       rd.id AS release_decision_id, rd.decision::text AS release_decision,
       rel.id AS report_release_id, rel.released_at, rel.released_by, rel.manifest_hash, rel.pdf_sha256,
       (SELECT count(*) FROM lfhe.qa_requests r WHERE r.report_version_id = v.id) AS qa_requests,
       CASE
         WHEN rel.id IS NOT NULL THEN 'RELEASED'
         WHEN EXISTS (SELECT 1 FROM lfhe.report_versions x WHERE x.report_id = v.report_id AND x.version_no > v.version_no) THEN 'SUPERSEDED'
         WHEN rd.decision = 'REJECT_RELEASE' THEN 'RELEASE_REJECTED'
         WHEN rd.decision = 'RETURN_FOR_REVISION' THEN 'RELEASE_RETURNED_FOR_REVISION'
         WHEN sr.status = 'APPROVED' THEN 'SECURITY_APPROVED'
         WHEN sr.status = 'REJECTED' THEN 'SECURITY_REJECTED'
         WHEN sr.status = 'RETURN_FOR_REVISION' THEN 'SECURITY_RETURNED_FOR_REVISION'
         WHEN sr.status = 'PENDING' THEN 'SECURITY_REVIEW_PENDING'
         WHEN ca.decision = 'REJECT' THEN 'CONTENT_REJECTED'
         WHEN ca.decision = 'RETURN_FOR_REVISION' THEN 'CONTENT_RETURNED_FOR_REVISION'
         WHEN q.status = 'FAIL' THEN 'QA_FAILED'
         WHEN q.status = 'PASS' THEN 'QA_PASSED'
         WHEN q.status = 'PASS_WITH_WARNINGS' AND cardinality(lfhe.p6_unacknowledged_warnings(q.id)) = 0 THEN 'WARNING_ACKNOWLEDGED'
         WHEN q.status = 'PASS_WITH_WARNINGS' THEN 'QA_PASSED_WITH_WARNINGS'
         WHEN EXISTS (SELECT 1 FROM lfhe.qa_requests r WHERE r.report_version_id = v.id) THEN 'QA_RUNNING'
         ELSE 'DRAFT_VERSION' END AS workflow_state
FROM lfhe.report_versions v
LEFT JOIN LATERAL (SELECT * FROM lfhe.qa_results x WHERE x.report_version_id = v.id ORDER BY x.result_no DESC LIMIT 1) q ON true
LEFT JOIN lfhe.content_approvals ca ON ca.qa_result_id = q.id
LEFT JOIN LATERAL (SELECT * FROM lfhe.security_reviews x WHERE x.content_approval_id = ca.id ORDER BY x.seq DESC LIMIT 1) sr ON true
LEFT JOIN LATERAL (SELECT * FROM lfhe.release_decisions x WHERE x.report_version_id = v.id AND x.security_review_id = sr.id
                   ORDER BY x.seq DESC LIMIT 1) rd ON true
LEFT JOIN lfhe.report_releases rel ON rel.report_version_id = v.id;

-- ---------------------------------------------------------------------------
-- Grants / RLS
-- ---------------------------------------------------------------------------
REVOKE ALL ON FUNCTION lfhe.decide_report_content(uuid, text, uuid, text, text), lfhe.decide_security_review(uuid, text, uuid, text, text),
  lfhe.request_release_pdf(uuid, text, text), lfhe.decide_release(uuid, text, text, text), lfhe.release_report(uuid, text, uuid, text)
  FROM PUBLIC, anon, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.decide_report_content(uuid, text, uuid, text, text), lfhe.decide_security_review(uuid, text, uuid, text, text),
  lfhe.request_release_pdf(uuid, text, text), lfhe.decide_release(uuid, text, text, text), lfhe.release_report(uuid, text, uuid, text)
  TO authenticated;
REVOKE ALL ON FUNCTION lfhe.release_eligibility(uuid, text, uuid) FROM PUBLIC, anon, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.release_eligibility(uuid, text, uuid) TO authenticated;
REVOKE ALL ON FUNCTION lfhe.record_release_pdf(jsonb) FROM PUBLIC, anon, authenticated, service_role, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.record_release_pdf(jsonb) TO lfhe_worker;
REVOKE ALL ON FUNCTION lfhe.p6_current_content_approval(uuid), lfhe.p6_current_security_review(uuid),
  lfhe.p6_renderer_identity_ok(lfhe.release_pdf_artifacts), lfhe.p6_release_checklist(uuid, text, uuid, uuid),
  lfhe.p6_build_manifest(uuid), lfhe.p6_manifest_problems(jsonb)
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;

REVOKE ALL ON lfhe.content_approvals, lfhe.security_reviews, lfhe.release_pdf_artifacts, lfhe.release_decisions,
  lfhe.release_manifests, lfhe.report_releases, lfhe.report_version_workflow
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT SELECT ON lfhe.content_approvals, lfhe.security_reviews, lfhe.release_pdf_artifacts, lfhe.release_decisions,
  lfhe.release_manifests, lfhe.report_releases, lfhe.report_version_workflow TO authenticated, lfhe_worker;
DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['content_approvals', 'security_reviews', 'release_pdf_artifacts', 'release_decisions',
                           'release_manifests', 'report_releases'] LOOP
    EXECUTE format('ALTER TABLE lfhe.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY %I ON lfhe.%I FOR SELECT TO authenticated USING (lfhe.has_permission(''CLAIM_READ''))',
                   t || '_read_human', t);
    EXECUTE format('CREATE POLICY %I ON lfhe.%I FOR SELECT TO lfhe_worker USING (true)', t || '_read_worker', t);
  END LOOP;
END $$;
