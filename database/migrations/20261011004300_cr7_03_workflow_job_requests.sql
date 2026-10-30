-- LFHÉ CR7-03 (PO decision 2026-10-30, docs/specs/PO_Decision_2026-10-30_CR7-03.md) — pilot operational path:
-- a human, audited request path for the existing pipeline jobs that had no production enqueuer.
--
-- Problem: the worker already processes EXTRACT_CLAIMS (M02), ANALYSE_LINEAGE (M04), BUILD_EVENTS (M05),
-- ASSESS_RELEVANCE (M06), ASSESS_EVENT (M07) and CHALLENGE_ASSESSMENT (M08), but only the worker itself
-- (lfhe.enqueue_pending_claim_extractions, the M07 → M08 chain) or the test harness could enqueue them, so
-- the claims → events → assessments path could not be operated on DEV.
--
-- What this migration adds (additive only; no Phase 1–6 object is altered):
-- * lfhe.request_workflow_job(job_type, params, reason) — HUMAN_ONLY. A signed-in human with the permission of
--   the corresponding human step requests one existing job type for one exact object. The payload is built
--   here in exactly the shape the closed worker handlers read; nothing is executed here, the worker runs the
--   unchanged pipeline (prompt / ingestion / human-review semantics unchanged).
-- * lfhe.request_pending_claim_extractions(limit, reason) — HUMAN_ONLY bulk variant of the M02 request using the
--   same selection and the same idempotency key as the closed worker function (no double extraction).
-- * lfhe.workflow_job_requests — append-only record of every human request (actor, reason, exact object,
--   mode / cutoff, outcome, job), audited as WORKFLOW_JOB_REQUESTED.
-- * lfhe.workflow_job_request_status — read view: request + current job status for the UI
--   (QUEUED / RUNNING / SUCCEEDED / NEEDS_HUMAN_REVIEW / FAILED / SKIPPED).
--
-- Rules preserved:
-- * Human-in-command: only a human session (lfhe.require_human_permission) can request; service_role,
--   lfhe_worker, anon cannot execute these functions. A request never approves, decides or changes any
--   analytical state.
-- * M07 regardless of M06 (Phase 4 §4.1): if no M06 result for the exact event version recommends assessment,
--   an explicit, audited human PROMOTE / REQUEST_ASSESSMENT decision (lfhe.promote_event_version) on that event
--   version is required first — the manual-promotion audit trail stays mandatory.
-- * Cutoff semantics: REPLAY / LIVE and the cutoff are explicit; claims / event versions must be cutoff-eligible
--   under the closed functions (lfhe.claim_cutoff_eligible, lfhe.event_version_eligible).
-- * Idempotency: a deterministic key per (job type, exact object, mode, cutoff, prompt version, options). A repeat
--   request while the job is QUEUED / RUNNING, or after it completed, does not create a second job (outcome
--   ALREADY_ACTIVE / ALREADY_COMPLETED). Only after a permanent FAILED job (max_attempts exhausted under the closed
--   back-off rules) may a human re-request, which creates one new job with key suffix ':retry:<n>'
--   (REQUEUED_AFTER_FAILURE). Automatic retries remain those of lfhe.fail_job.

INSERT INTO lfhe.audit_event_types (code, spec_source) VALUES
  ('WORKFLOW_JOB_REQUESTED', 'CR7-03 (PO 2026-10-30)')
ON CONFLICT (code) DO NOTHING;

CREATE TABLE lfhe.workflow_job_requests (
  seq                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id                  uuid NOT NULL UNIQUE DEFAULT pg_catalog.gen_random_uuid(),
  job_type            text NOT NULL CHECK (job_type IN ('EXTRACT_CLAIMS', 'ANALYSE_LINEAGE', 'BUILD_EVENTS',
                                                         'ASSESS_RELEVANCE', 'ASSESS_EVENT', 'CHALLENGE_ASSESSMENT')),
  object_type         text NOT NULL,
  object_id           text NOT NULL,
  job_id              uuid REFERENCES lfhe.processing_jobs(id),
  idempotency_key     text,
  outcome             text NOT NULL CHECK (outcome IN ('ENQUEUED', 'ALREADY_ACTIVE', 'ALREADY_COMPLETED',
                                                        'REQUEUED_AFTER_FAILURE')),
  report_mode         text CHECK (report_mode IS NULL OR report_mode IN ('LIVE', 'REPLAY')),
  information_cutoff  timestamptz,
  payload             jsonb NOT NULL DEFAULT '{}'::jsonb,
  requested_by        uuid NOT NULL,
  reason              text NOT NULL CHECK (length(btrim(reason)) >= 5),
  created_at          timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  CHECK ((report_mode IS NULL) = (information_cutoff IS NULL)),
  CHECK (job_id IS NOT NULL AND idempotency_key IS NOT NULL)
);
CREATE INDEX workflow_job_requests_object_idx ON lfhe.workflow_job_requests (job_type, object_type, object_id);
COMMENT ON TABLE lfhe.workflow_job_requests IS
  'CR7-03: append-only record of human requests for existing pipeline jobs (operational; not analytical evidence)';

CREATE TRIGGER workflow_job_requests_append_only BEFORE UPDATE OR DELETE ON lfhe.workflow_job_requests
  FOR EACH ROW EXECUTE FUNCTION lfhe.block_mutation();
CREATE TRIGGER workflow_job_requests_no_truncate BEFORE TRUNCATE ON lfhe.workflow_job_requests
  FOR EACH STATEMENT EXECUTE FUNCTION lfhe.block_mutation();

-- ---------------------------------------------------------------------------
-- Internal helpers (not executable by any API role)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lfhe.cr7_03_iso(p timestamptz)
RETURNS text LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
  -- the exact text the worker parses with datetime.fromisoformat()
  SELECT pg_catalog.to_char(p AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US') || '+00:00'
$$;

CREATE OR REPLACE FUNCTION lfhe.cr7_03_mode_cutoff(p jsonb, OUT report_mode text, OUT information_cutoff timestamptz)
LANGUAGE plpgsql STABLE SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  report_mode := p ->> 'report_mode';
  IF report_mode IS NULL OR report_mode NOT IN ('LIVE', 'REPLAY') THEN
    RAISE EXCEPTION 'REPORT_MODE_REQUIRED: report_mode must be LIVE or REPLAY' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  BEGIN
    information_cutoff := (p ->> 'information_cutoff')::timestamptz;
  EXCEPTION WHEN others THEN
    RAISE EXCEPTION 'CUTOFF_INVALID: %', coalesce(p ->> 'information_cutoff', 'null') USING ERRCODE = 'invalid_parameter_value';
  END;
  IF information_cutoff IS NULL THEN
    RAISE EXCEPTION 'CUTOFF_REQUIRED: information_cutoff is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
END $$;

CREATE OR REPLACE FUNCTION lfhe.cr7_03_prompt(p_module text)
RETURNS uuid LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v uuid := lfhe.current_prompt_version(p_module);
BEGIN
  IF v IS NULL THEN
    RAISE EXCEPTION 'PROMPT_NOT_ACTIVE: no active prompt version for % (register and activate it first)', p_module
      USING ERRCODE = 'object_not_in_prerequisite_state';
  END IF;
  RETURN v;
END $$;

-- Enqueue under the idempotency rules above and record the human request (one row, audited).
CREATE OR REPLACE FUNCTION lfhe.cr7_03_enqueue(p_actor uuid, p_job_type text, p_object_type text, p_object_id text,
                                               p_key text, p_payload jsonb, p_mode text, p_cutoff timestamptz,
                                               p_reason text, p_max_attempts integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_job      lfhe.processing_jobs;
  v_retries  integer;
  v_key      text := p_key;
  v_outcome  text;
  v_job_id   uuid;
  v_req      uuid;
BEGIN
  IF length(p_key) > 380 THEN
    RAISE EXCEPTION 'idempotency key too long' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  -- serialise concurrent requests for the same base key (no duplicate retry jobs)
  PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(p_key, 7303));
  SELECT * INTO v_job FROM lfhe.processing_jobs
   WHERE idempotency_key = p_key OR idempotency_key LIKE p_key || ':retry:%'
   ORDER BY created_at DESC, id DESC LIMIT 1;
  IF NOT FOUND THEN
    v_outcome := 'ENQUEUED';
  ELSIF v_job.status IN ('PENDING', 'RUNNING') THEN
    v_outcome := 'ALREADY_ACTIVE';
    v_job_id := v_job.id;
    v_key := v_job.idempotency_key;
  ELSIF v_job.status = 'FAILED' THEN
    SELECT count(*) INTO v_retries FROM lfhe.processing_jobs WHERE idempotency_key LIKE p_key || ':retry:%';
    v_key := p_key || ':retry:' || (v_retries + 1);
    v_outcome := 'REQUEUED_AFTER_FAILURE';
  ELSE                                              -- SUCCESS / HUMAN_REVIEW / SKIPPED: the run exists; no re-run
    v_outcome := 'ALREADY_COMPLETED';
    v_job_id := v_job.id;
    v_key := v_job.idempotency_key;
  END IF;
  IF v_job_id IS NULL THEN
    v_job_id := lfhe.enqueue_job(p_job_type, p_object_type, p_object_id, v_key, p_payload, 100::smallint,
                                 p_max_attempts, NULL);
  END IF;
  INSERT INTO lfhe.workflow_job_requests (job_type, object_type, object_id, job_id, idempotency_key, outcome,
                                          report_mode, information_cutoff, payload, requested_by, reason)
  VALUES (p_job_type, p_object_type, p_object_id, v_job_id, v_key, v_outcome, p_mode, p_cutoff, p_payload,
          p_actor, btrim(p_reason))
  RETURNING id INTO v_req;
  PERFORM lfhe.write_audit('WORKFLOW_JOB_REQUESTED', 'processing_job', v_job_id::text, NULL,
    pg_catalog.jsonb_build_object('request_id', v_req, 'job_type', p_job_type, 'object_type', p_object_type,
                                  'object_id', p_object_id, 'outcome', v_outcome, 'idempotency_key', v_key,
                                  'report_mode', p_mode, 'information_cutoff', p_cutoff, 'reason', btrim(p_reason)),
    '{}'::jsonb);
  RETURN pg_catalog.jsonb_build_object('request_id', v_req, 'job_id', v_job_id, 'outcome', v_outcome,
                                       'idempotency_key', v_key,
                                       'job_status', (SELECT status::text FROM lfhe.processing_jobs WHERE id = v_job_id));
END $$;

CREATE OR REPLACE FUNCTION lfhe.cr7_03_claim_ids(p jsonb)
RETURNS uuid[] LANGUAGE plpgsql STABLE SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v uuid[];
BEGIN
  IF pg_catalog.jsonb_typeof(p -> 'claim_ids') IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'CLAIM_IDS_REQUIRED' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  SELECT array_agg(DISTINCT x::uuid ORDER BY x::uuid) INTO v FROM pg_catalog.jsonb_array_elements_text(p -> 'claim_ids') x;
  IF v IS NULL OR cardinality(v) < 1 OR cardinality(v) > 100 THEN
    RAISE EXCEPTION 'CLAIM_IDS_REQUIRED: 1–100 claims' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  RETURN v;
END $$;

-- ---------------------------------------------------------------------------
-- HUMAN_ONLY request functions
-- ---------------------------------------------------------------------------
-- p (by job type):
--   EXTRACT_CLAIMS        {text_representation_id}                                          permission CLAIM_REVIEW
--   ANALYSE_LINEAGE       {claim_ids[], report_mode, information_cutoff}                   permission CLAIM_REVIEW
--   BUILD_EVENTS          {claim_ids[], report_mode, information_cutoff}                   permission EVENT_ACTION
--   ASSESS_RELEVANCE      {event_version_id, event_version_hash, report_mode, information_cutoff, baseline_code?}
--                                                                                          permission ASSESSMENT_REVIEW
--   ASSESS_EVENT          {event_version_id, event_version_hash, report_mode, information_cutoff, baseline_code?,
--                          reference_context_codes?[], previous_assessment_version_id?}    permission ASSESSMENT_REVIEW
--   CHALLENGE_ASSESSMENT  {assessment_version_id, assessment_version_hash}                 permission ASSESSMENT_REVIEW
CREATE OR REPLACE FUNCTION lfhe.request_workflow_job(p_job_type text, p jsonb, p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_perm     text := CASE p_job_type
                       WHEN 'EXTRACT_CLAIMS' THEN 'CLAIM_REVIEW' WHEN 'ANALYSE_LINEAGE' THEN 'CLAIM_REVIEW'
                       WHEN 'BUILD_EVENTS' THEN 'EVENT_ACTION' WHEN 'ASSESS_RELEVANCE' THEN 'ASSESSMENT_REVIEW'
                       WHEN 'ASSESS_EVENT' THEN 'ASSESSMENT_REVIEW' WHEN 'CHALLENGE_ASSESSMENT' THEN 'ASSESSMENT_REVIEW'
                     END;
  v_actor    uuid;
  v_mode     text;
  v_cutoff   timestamptz;
  v_pv       uuid;
  v_ids      uuid[];
  v_bad      uuid[];
  v_ver      lfhe.event_versions;
  v_av       lfhe.assessment_versions;
  v_tr       record;
  v_payload  jsonb;
  v_key      text;
  v_rc       jsonb;
  v_prev     uuid;
BEGIN
  IF v_perm IS NULL THEN
    RAISE EXCEPTION 'JOB_TYPE_NOT_REQUESTABLE: %', coalesce(p_job_type, 'null') USING ERRCODE = 'invalid_parameter_value';
  END IF;
  v_actor := lfhe.require_human_permission(v_perm);
  IF p_reason IS NULL OR length(btrim(p_reason)) < 5 THEN
    RAISE EXCEPTION 'a reason of at least 5 characters is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  p := coalesce(p, '{}'::jsonb);

  IF p_job_type = 'EXTRACT_CLAIMS' THEN
    v_pv := lfhe.cr7_03_prompt('M02_CLAIM_EXTRACTOR');
    SELECT t.id, t.is_original_language, t.language, s.retention_mode_applied::text AS retention INTO v_tr
      FROM lfhe.text_representations t JOIN lfhe.article_snapshots s ON s.id = t.snapshot_id
     WHERE t.id = (p ->> 'text_representation_id')::uuid;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'TEXT_REPRESENTATION_NOT_FOUND: %', p ->> 'text_representation_id' USING ERRCODE = 'no_data_found';
    ELSIF NOT v_tr.is_original_language THEN
      RAISE EXCEPTION 'NOT_ORIGINAL_LANGUAGE: only original-language text can be evidence' USING ERRCODE = 'check_violation';
    ELSIF v_tr.language IS NULL THEN
      RAISE EXCEPTION 'ORIGINAL_LANGUAGE_UNKNOWN' USING ERRCODE = 'check_violation';
    ELSIF v_tr.retention = 'METADATA_ONLY' THEN
      RAISE EXCEPTION 'METADATA_ONLY_SNAPSHOT: metadata-only sources cannot ground claims' USING ERRCODE = 'check_violation';
    END IF;
    -- identical key and payload to lfhe.enqueue_pending_claim_extractions (closed worker path)
    RETURN lfhe.cr7_03_enqueue(v_actor, 'EXTRACT_CLAIMS', 'text_representation', v_tr.id::text,
                               'EXTRACT_CLAIMS:' || v_tr.id::text || ':' || v_pv::text,
                               pg_catalog.jsonb_build_object('prompt_version_id', v_pv), NULL, NULL, p_reason, 3);

  ELSIF p_job_type IN ('ANALYSE_LINEAGE', 'BUILD_EVENTS') THEN
    v_pv := lfhe.cr7_03_prompt(CASE p_job_type WHEN 'ANALYSE_LINEAGE' THEN 'M04_LINEAGE' ELSE 'M05_EVENT_BUILDER' END);
    SELECT * INTO v_mode, v_cutoff FROM lfhe.cr7_03_mode_cutoff(p);
    v_ids := lfhe.cr7_03_claim_ids(p);
    SELECT array_agg(x) INTO v_bad FROM unnest(v_ids) x WHERE NOT EXISTS (SELECT 1 FROM lfhe.claims c WHERE c.id = x);
    IF v_bad IS NOT NULL THEN
      RAISE EXCEPTION 'CLAIM_NOT_FOUND: %', v_bad USING ERRCODE = 'no_data_found';
    END IF;
    SELECT array_agg(x) INTO v_bad FROM unnest(v_ids) x WHERE NOT lfhe.claim_cutoff_eligible(x, v_mode, v_cutoff);
    IF v_bad IS NOT NULL THEN
      RAISE EXCEPTION 'CLAIM_NOT_CUTOFF_ELIGIBLE: % under % %', v_bad, v_mode, v_cutoff USING ERRCODE = 'check_violation';
    END IF;
    v_payload := pg_catalog.jsonb_build_object('claim_ids', pg_catalog.to_jsonb(v_ids::text[]), 'report_mode', v_mode,
                                               'information_cutoff', lfhe.cr7_03_iso(v_cutoff));
    v_key := p_job_type || ':' || pg_catalog.md5(array_to_string(v_ids, ',')) || ':' || v_mode || ':'
             || lfhe.cr7_03_iso(v_cutoff) || ':' || v_pv::text;
    RETURN lfhe.cr7_03_enqueue(v_actor, p_job_type, 'claim_set', pg_catalog.md5(array_to_string(v_ids, ',')), v_key,
                               v_payload, v_mode, v_cutoff, p_reason, 3);

  ELSIF p_job_type IN ('ASSESS_RELEVANCE', 'ASSESS_EVENT') THEN
    v_pv := lfhe.cr7_03_prompt(CASE p_job_type WHEN 'ASSESS_RELEVANCE' THEN 'M06_RELEVANCE' ELSE 'M07_INTELLIGENCE_ASSESSOR' END);
    SELECT * INTO v_mode, v_cutoff FROM lfhe.cr7_03_mode_cutoff(p);
    SELECT * INTO v_ver FROM lfhe.event_versions WHERE id = (p ->> 'event_version_id')::uuid;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'EVENT_VERSION_NOT_FOUND: %', p ->> 'event_version_id' USING ERRCODE = 'no_data_found';
    ELSIF v_ver.content_hash IS DISTINCT FROM (p ->> 'event_version_hash') THEN
      RAISE EXCEPTION 'EVENT_VERSION_HASH_MISMATCH: the event version changed; reload' USING ERRCODE = 'check_violation';
    ELSIF NOT lfhe.event_version_eligible(v_ver.id, v_mode, v_cutoff) THEN
      RAISE EXCEPTION 'EVENT_VERSION_NOT_ELIGIBLE: % under % %', v_ver.id, v_mode, v_cutoff USING ERRCODE = 'check_violation';
    END IF;
    v_payload := pg_catalog.jsonb_build_object('event_version_hash', v_ver.content_hash, 'report_mode', v_mode,
                                               'information_cutoff', lfhe.cr7_03_iso(v_cutoff));
    IF nullif(btrim(p ->> 'baseline_code'), '') IS NOT NULL THEN
      v_payload := v_payload || pg_catalog.jsonb_build_object('baseline_code', btrim(p ->> 'baseline_code'));
    END IF;
    IF p_job_type = 'ASSESS_EVENT' THEN
      -- Phase 4 §4.1: without an M06 recommendation for this exact version, an audited human promotion is required
      IF NOT EXISTS (SELECT 1 FROM lfhe.relevance_results r WHERE r.event_version_id = v_ver.id
                       AND r.automatic_assessment_recommended)
         AND NOT EXISTS (SELECT 1 FROM lfhe.relevance_decisions d WHERE d.event_version_id = v_ver.id
                           AND d.action IN ('PROMOTE', 'REQUEST_ASSESSMENT')) THEN
        RAISE EXCEPTION 'MANUAL_ASSESSMENT_REQUEST_REQUIRED: no M06 recommendation for this event version; record an audited PROMOTE / REQUEST_ASSESSMENT decision first'
          USING ERRCODE = 'object_not_in_prerequisite_state';
      END IF;
      IF pg_catalog.jsonb_typeof(p -> 'reference_context_codes') = 'array'
         AND pg_catalog.jsonb_array_length(p -> 'reference_context_codes') > 0 THEN
        SELECT pg_catalog.jsonb_agg(DISTINCT x ORDER BY x) INTO v_rc FROM pg_catalog.jsonb_array_elements_text(p -> 'reference_context_codes') x;
        v_payload := v_payload || pg_catalog.jsonb_build_object('reference_context_codes', v_rc);
      END IF;
      IF nullif(p ->> 'previous_assessment_version_id', '') IS NOT NULL THEN
        v_prev := (p ->> 'previous_assessment_version_id')::uuid;
        IF NOT EXISTS (SELECT 1 FROM lfhe.assessment_versions a WHERE a.id = v_prev) THEN
          RAISE EXCEPTION 'PREVIOUS_ASSESSMENT_NOT_FOUND: %', v_prev USING ERRCODE = 'no_data_found';
        END IF;
        v_payload := v_payload || pg_catalog.jsonb_build_object('previous_assessment_version_id', v_prev::text);
      END IF;
    END IF;
    v_key := p_job_type || ':' || v_ver.id::text || ':' || v_mode || ':' || lfhe.cr7_03_iso(v_cutoff) || ':'
             || pg_catalog.md5(coalesce(v_payload ->> 'baseline_code', '') || '|' || coalesce((v_payload -> 'reference_context_codes')::text, '')
                               || '|' || coalesce(v_prev::text, '')) || ':' || v_pv::text;
    RETURN lfhe.cr7_03_enqueue(v_actor, p_job_type, 'event_version', v_ver.id::text, v_key, v_payload, v_mode, v_cutoff,
                               p_reason, 3);

  ELSE                                              -- CHALLENGE_ASSESSMENT
    PERFORM lfhe.cr7_03_prompt('M08_CHALLENGER');
    SELECT * INTO v_av FROM lfhe.assessment_versions WHERE id = (p ->> 'assessment_version_id')::uuid;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'ASSESSMENT_VERSION_NOT_FOUND: %', p ->> 'assessment_version_id' USING ERRCODE = 'no_data_found';
    ELSIF v_av.content_hash IS DISTINCT FROM (p ->> 'assessment_version_hash') THEN
      RAISE EXCEPTION 'ASSESSMENT_VERSION_HASH_MISMATCH: the assessment version changed; reload' USING ERRCODE = 'check_violation';
    END IF;
    -- same key as the worker's automatic M07 → M08 chain: never a second challenge for one version
    RETURN lfhe.cr7_03_enqueue(v_actor, 'CHALLENGE_ASSESSMENT', 'assessment_version', v_av.id::text,
                               'CHALLENGE_ASSESSMENT:' || v_av.id::text,
                               pg_catalog.jsonb_build_object('assessment_version_hash', v_av.content_hash), NULL, NULL,
                               p_reason, 3);
  END IF;
END $$;
COMMENT ON FUNCTION lfhe.request_workflow_job(text, jsonb, text) IS 'HUMAN_ONLY';

-- Bulk M02: the selection and key of lfhe.enqueue_pending_claim_extractions, one audited request row per job.
CREATE OR REPLACE FUNCTION lfhe.request_pending_claim_extractions(p_limit integer, p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('CLAIM_REVIEW');
  v_pv    uuid;
  v_rep   record;
  v_res   jsonb;
  v_out   jsonb := '[]'::jsonb;
BEGIN
  IF p_reason IS NULL OR length(btrim(p_reason)) < 5 THEN
    RAISE EXCEPTION 'a reason of at least 5 characters is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  v_pv := lfhe.cr7_03_prompt('M02_CLAIM_EXTRACTOR');
  FOR v_rep IN
    SELECT t.id FROM lfhe.text_representations t
    JOIN lfhe.article_snapshots s ON s.id = t.snapshot_id
    WHERE t.is_original_language AND t.language IS NOT NULL AND s.retention_mode_applied <> 'METADATA_ONLY'
      AND NOT EXISTS (SELECT 1 FROM lfhe.claim_extraction_results r JOIN lfhe.model_runs m ON m.id = r.model_run_id
                      WHERE r.text_representation_id = t.id AND m.prompt_version_id = v_pv
                        AND r.outcome NOT IN ('PROVIDER_ERROR', 'SCHEMA_VALIDATION_FAILED'))
      AND NOT EXISTS (SELECT 1 FROM lfhe.processing_jobs j
                      WHERE j.idempotency_key = 'EXTRACT_CLAIMS:' || t.id::text || ':' || v_pv::text)
    ORDER BY t.created_at
    LIMIT least(greatest(coalesce(p_limit, 50), 1), 200)
  LOOP
    v_res := lfhe.cr7_03_enqueue(v_actor, 'EXTRACT_CLAIMS', 'text_representation', v_rep.id::text,
                                 'EXTRACT_CLAIMS:' || v_rep.id::text || ':' || v_pv::text,
                                 pg_catalog.jsonb_build_object('prompt_version_id', v_pv), NULL, NULL, p_reason, 3);
    v_out := v_out || pg_catalog.jsonb_build_array(v_res);
  END LOOP;
  RETURN pg_catalog.jsonb_build_object('enqueued', pg_catalog.jsonb_array_length(v_out), 'requests', v_out);
END $$;
COMMENT ON FUNCTION lfhe.request_pending_claim_extractions(integer, text) IS 'HUMAN_ONLY';

-- ---------------------------------------------------------------------------
-- Read view for the UI: each human request with the current state of its job
-- ---------------------------------------------------------------------------
CREATE VIEW lfhe.workflow_job_request_status AS
SELECT r.id AS request_id, r.seq, r.job_type, r.object_type, r.object_id, r.outcome, r.report_mode, r.information_cutoff,
       r.requested_by, r.reason, r.created_at AS requested_at, r.job_id, j.status::text AS job_status,
       CASE j.status WHEN 'PENDING' THEN 'QUEUED' WHEN 'RUNNING' THEN 'RUNNING' WHEN 'SUCCESS' THEN 'SUCCEEDED'
                     WHEN 'HUMAN_REVIEW' THEN 'NEEDS_HUMAN_REVIEW' WHEN 'FAILED' THEN 'FAILED' ELSE 'SKIPPED' END AS display_status,
       j.attempt_count, j.max_attempts, j.next_attempt_at, j.started_at, j.completed_at, left(j.last_error, 500) AS last_error
FROM lfhe.workflow_job_requests r
JOIN lfhe.processing_jobs j ON j.id = r.job_id
WHERE lfhe.has_permission('CLAIM_READ');
COMMENT ON VIEW lfhe.workflow_job_request_status IS 'CR7-03: human job requests with the current job status (UI read model)';

-- ---------------------------------------------------------------------------
-- Grants / RLS
-- ---------------------------------------------------------------------------
REVOKE ALL ON FUNCTION lfhe.cr7_03_iso(timestamptz), lfhe.cr7_03_mode_cutoff(jsonb), lfhe.cr7_03_prompt(text),
  lfhe.cr7_03_enqueue(uuid, text, text, text, text, jsonb, text, timestamptz, text, integer), lfhe.cr7_03_claim_ids(jsonb)
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
REVOKE ALL ON FUNCTION lfhe.request_workflow_job(text, jsonb, text), lfhe.request_pending_claim_extractions(integer, text)
  FROM PUBLIC, anon, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.request_workflow_job(text, jsonb, text), lfhe.request_pending_claim_extractions(integer, text)
  TO authenticated;

REVOKE ALL ON lfhe.workflow_job_requests, lfhe.workflow_job_request_status
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT SELECT ON lfhe.workflow_job_requests, lfhe.workflow_job_request_status TO authenticated;
GRANT SELECT ON lfhe.workflow_job_requests TO lfhe_worker;
ALTER TABLE lfhe.workflow_job_requests ENABLE ROW LEVEL SECURITY;
CREATE POLICY workflow_job_requests_read_human ON lfhe.workflow_job_requests FOR SELECT TO authenticated
  USING (lfhe.has_permission('CLAIM_READ'));
CREATE POLICY workflow_job_requests_read_worker ON lfhe.workflow_job_requests FOR SELECT TO lfhe_worker USING (true);
