-- LFHÉ Phase 6 — CR6-01 (PO decision 2026-10-23, docs/specs/PO_Decision_2026-10-23_CG6_Targeted_Correction_CR6-01.md):
-- the release manifest preserves `baseline_version_ids` (Module Prompt Pack delta-audit PG-07).
-- Forward-only; 3800 and 3900 are applied and unchanged. Manifest provenance only — no new baseline semantics.
--
-- * lfhe.p6_required_baseline_versions(version): the distinct baseline versions actually used by the report's
--   analytical chain — the baseline_version_id of every assessment version pinned by a report item or cited by a
--   report statement source, plus every baseline_version cited as evidence by a cited assessment statement.
--   Sorted by id text (deterministic). Derived only from stored, approved analytical objects; nothing inferred.
-- * lfhe.p6_build_manifest: identical to 3900 plus the field `baseline_version_ids` (included in JCS / SHA-256).
-- * lfhe.p6_manifest_problems: the 3900 completeness list plus `baseline_version_ids`, and fail-closed checks that
--   the listed ids are canonical (uuid, sorted, distinct), equal to the required set (missing / not in the chain),
--   exist, and are usable under the existing cutoff rules for the version's own mode / cutoff. It runs inside
--   lfhe.release_report, so any problem aborts the release transaction (MANIFEST_INCOMPLETE).

CREATE OR REPLACE FUNCTION lfhe.p6_required_baseline_versions(p_version uuid)
RETURNS uuid[] LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  WITH avs AS (
    SELECT i.pinned_assessment_version_id AS av FROM lfhe.report_items i
    WHERE i.report_version_id = p_version AND i.pinned_assessment_version_id IS NOT NULL
    UNION
    SELECT x.assessment_version_id FROM lfhe.report_statement_sources x
    JOIN lfhe.report_item_statements st ON st.id = x.report_item_statement_id
    JOIN lfhe.report_items i ON i.id = st.report_item_id
    WHERE i.report_version_id = p_version),
  ids AS (
    SELECT v.baseline_version_id AS id FROM lfhe.assessment_versions v JOIN avs ON avs.av = v.id
    WHERE v.baseline_version_id IS NOT NULL
    UNION
    SELECT e.object_id FROM lfhe.report_statement_sources x
    JOIN lfhe.report_item_statements st ON st.id = x.report_item_statement_id
    JOIN lfhe.report_items i ON i.id = st.report_item_id
    JOIN lfhe.assessment_statement_evidence e ON e.statement_id = x.assessment_statement_id AND e.object_type = 'baseline_version'
    WHERE i.report_version_id = p_version)
  SELECT coalesce(ARRAY(SELECT id FROM ids ORDER BY id::text), '{}')
$$;

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
    'baseline_version_ids', pg_catalog.to_jsonb(lfhe.p6_required_baseline_versions(v.id)::text[]),
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

CREATE OR REPLACE FUNCTION lfhe.p6_manifest_problems(p jsonb)
RETURNS text[] LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_out   text[];
  v       lfhe.report_versions;
  v_ids   jsonb := p -> 'baseline_version_ids';
  v_given text[];
  v_req   text[];
  x       text;
BEGIN
  v_out := ARRAY(SELECT k FROM pg_catalog.unnest(ARRAY[
      '{manifest_schema_version}', '{report,report_id}', '{report,report_mode}', '{report,information_cutoff}',
      '{report_version,report_version_id}', '{report_version,report_version_hash}', '{selection_set,id}', '{selection_set,hash}',
      '{qa,deterministic_qa_run_id}', '{qa,semantic_qa_run_id}', '{qa,combined_qa_status}', '{qa,m10s_model_run_id}',
      '{qa,m10_prompt_version_id}', '{qa,m10_prompt_hash}', '{content_approval_id}', '{security_review_id}', '{release_decision_id}',
      '{released_by}', '{release_timestamp}', '{rendering,template_version}', '{rendering,template_hash}', '{rendering,renderer_version}',
      '{rendering,renderer_hash}', '{pdf,pdf_artifact_id}', '{pdf,pdf_sha256}', '{pdf,byte_size}', '{pdf,mime_type}',
      '{warning_acknowledgement_ids}', '{analytical_provenance}', '{baseline_version_ids}']) k
    WHERE p #> k::text[] IS NULL OR p #> k::text[] = 'null'::jsonb
       OR (k = '{analytical_provenance}' AND pg_catalog.jsonb_array_length(p -> 'analytical_provenance') = 0)
    ORDER BY 1);
  -- CR6-01: baseline_version_ids — canonical, exactly the chain's baselines, existing, cutoff-eligible
  IF v_ids IS NULL OR v_ids = 'null'::jsonb THEN
    RETURN v_out;
  END IF;
  IF pg_catalog.jsonb_typeof(v_ids) <> 'array' OR EXISTS (
       SELECT 1 FROM pg_catalog.jsonb_array_elements(v_ids) e
       WHERE pg_catalog.jsonb_typeof(e) <> 'string' OR (e #>> '{}') !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') THEN
    RETURN v_out || 'BASELINE_VERSION_IDS_INVALID'::text;
  END IF;
  v_given := ARRAY(SELECT e FROM pg_catalog.jsonb_array_elements_text(v_ids) WITH ORDINALITY t(e, o) ORDER BY o);
  IF v_given IS DISTINCT FROM ARRAY(SELECT DISTINCT e FROM pg_catalog.unnest(v_given) e ORDER BY e) THEN
    v_out := v_out || 'BASELINE_VERSION_IDS_NOT_CANONICAL'::text;
  END IF;
  SELECT * INTO v FROM lfhe.report_versions WHERE id::text = p #>> '{report_version,report_version_id}';
  IF v.id IS NULL THEN
    RETURN v_out || 'BASELINE_CHAIN_UNRESOLVABLE'::text;
  END IF;
  v_req := lfhe.p6_required_baseline_versions(v.id)::text[];
  FOREACH x IN ARRAY v_req LOOP
    IF NOT (x = ANY (v_given)) THEN
      v_out := v_out || ('BASELINE_VERSION_MISSING:' || x);
    END IF;
  END LOOP;
  FOREACH x IN ARRAY v_given LOOP
    IF NOT EXISTS (SELECT 1 FROM lfhe.baseline_versions b WHERE b.id::text = x) THEN
      v_out := v_out || ('BASELINE_VERSION_UNKNOWN:' || x);
    ELSIF NOT (x = ANY (v_req)) THEN
      v_out := v_out || ('BASELINE_VERSION_NOT_IN_CHAIN:' || x);
    ELSIF NOT lfhe.baseline_version_usable(x::uuid, v.report_mode::text, v.information_cutoff) THEN
      v_out := v_out || ('BASELINE_VERSION_NOT_ELIGIBLE:' || x);
    END IF;
  END LOOP;
  RETURN v_out;
END $$;

REVOKE ALL ON FUNCTION lfhe.p6_required_baseline_versions(uuid), lfhe.p6_build_manifest(uuid), lfhe.p6_manifest_problems(jsonb)
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
