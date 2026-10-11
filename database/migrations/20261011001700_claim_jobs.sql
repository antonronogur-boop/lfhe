-- ============================================================================
-- P2-05  Claim-pipeline jobs
--
-- * job types EXTRACT_CLAIMS (object: text_representation) and
--   CLASSIFY_CLAIMS (object: claim_extraction_result = the M02 model run).
-- * lfhe.enqueue_pending_claim_extractions(limit): enqueues EXTRACT_CLAIMS for
--   original-language text representations (language known, not
--   METADATA_ONLY) that have no extraction result from the ACTIVE M02 prompt
--   version. Idempotency key binds text representation + prompt version, so
--   re-running never duplicates; a new activated prompt version yields new
--   (separately traceable) extraction jobs. Without an active M02 version it
--   enqueues nothing (fail closed).
-- ============================================================================

ALTER TABLE lfhe.processing_jobs DROP CONSTRAINT processing_jobs_job_type_check;
ALTER TABLE lfhe.processing_jobs ADD CONSTRAINT processing_jobs_job_type_check
  CHECK (job_type IN ('COLLECT_SOURCE', 'EXTRACT_CLAIMS', 'CLASSIFY_CLAIMS'));

CREATE OR REPLACE FUNCTION lfhe.enqueue_pending_claim_extractions(p_limit integer DEFAULT 50)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_pv  uuid := lfhe.current_prompt_version('M02_CLAIM_EXTRACTOR');
  v_rep record;
  v_n   integer := 0;
BEGIN
  IF v_pv IS NULL THEN
    RETURN 0;
  END IF;
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
    LIMIT greatest(p_limit, 1)
  LOOP
    PERFORM lfhe.enqueue_job('EXTRACT_CLAIMS', 'text_representation', v_rep.id::text,
      'EXTRACT_CLAIMS:' || v_rep.id::text || ':' || v_pv::text,
      pg_catalog.jsonb_build_object('prompt_version_id', v_pv), 100::smallint, 3, NULL);
    v_n := v_n + 1;
  END LOOP;
  RETURN v_n;
END $$;
REVOKE ALL ON FUNCTION lfhe.enqueue_pending_claim_extractions(integer)
  FROM PUBLIC, anon, authenticated, service_role, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.enqueue_pending_claim_extractions(integer) TO lfhe_worker;

-- Review flag for claims from source text that contains instruction-like
-- content (possible prompt injection, TB-2). Extends the closed list; the
-- claims CHECK constraint reads this function.
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
    'MODEL_REQUESTED_HUMAN_REVIEW', 'SOURCE_CONTAINS_INSTRUCTION_LIKE_TEXT']::text[]
$$;
REVOKE ALL ON FUNCTION lfhe.claim_review_flags() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION lfhe.claim_review_flags() TO authenticated, lfhe_worker;
