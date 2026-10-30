-- CR7-05 — report autopilot (PO decision 2026-10-30: "legyen human control, de ne minden egyes claimbe").
--
-- A human (EVENT_ACTION) switches the automatic analysis on for exactly ONE report (= one analysis context: mode +
-- information cutoff). While it is on, the worker chains the existing, unchanged pipeline steps for new claims of
-- that context (M05 → M06 → M07 → M08). The chain only ENQUEUES jobs that a human could request by hand; it never
-- approves, reviews, promotes, sets a state or a confidence. Every output is still a draft for human decisions.
-- * lfhe.report_autopilot           — the switch (one row per report; at most one report enabled at a time)
-- * lfhe.set_report_autopilot       — HUMAN_ONLY, audited REPORT_AUTOPILOT_SET
-- * lfhe.autopilot_context          — worker/read: the enabled report's mode and cutoff
-- * lfhe.autopilot_eligible_claims  — worker: claims of a batch that are cutoff-eligible and not rejected
-- No applied migration is modified; no permission is widened.

INSERT INTO lfhe.audit_event_types (code, spec_source) VALUES
  ('REPORT_AUTOPILOT_SET', 'CR7-05 (PO 2026-10-30)')
ON CONFLICT (code) DO NOTHING;

CREATE TABLE lfhe.report_autopilot (
  report_id   uuid PRIMARY KEY REFERENCES lfhe.reports(id),
  enabled     boolean NOT NULL,
  changed_by  uuid NOT NULL,
  reason      text NOT NULL CHECK (length(btrim(reason)) >= 5),
  changed_at  timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX report_autopilot_one_enabled ON lfhe.report_autopilot ((true)) WHERE enabled;

CREATE OR REPLACE FUNCTION lfhe.set_report_autopilot(p_report uuid, p_enabled boolean, p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v_actor uuid := lfhe.require_human_permission('EVENT_ACTION');
  v_rep   lfhe.reports;
  v_other uuid;
BEGIN
  IF p_reason IS NULL OR length(btrim(p_reason)) < 5 THEN
    RAISE EXCEPTION 'a reason of at least 5 characters is required' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  SELECT * INTO v_rep FROM lfhe.reports WHERE id = p_report;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'REPORT_NOT_FOUND: %', p_report USING ERRCODE = 'no_data_found';
  END IF;
  IF p_enabled THEN
    SELECT report_id INTO v_other FROM lfhe.report_autopilot WHERE enabled AND report_id <> p_report;
    IF FOUND THEN                                   -- exactly one analysis context at a time: switch the other off first
      RAISE EXCEPTION 'AUTOPILOT_ALREADY_ON_FOR_ANOTHER_REPORT: switch it off for report % first', v_other
        USING ERRCODE = 'object_not_in_prerequisite_state';
    END IF;
  END IF;
  INSERT INTO lfhe.report_autopilot (report_id, enabled, changed_by, reason)
  VALUES (p_report, p_enabled, v_actor, btrim(p_reason))
  ON CONFLICT (report_id) DO UPDATE SET enabled = EXCLUDED.enabled, changed_by = EXCLUDED.changed_by,
                                         reason = EXCLUDED.reason, changed_at = now();
  PERFORM lfhe.write_audit('REPORT_AUTOPILOT_SET', 'report', p_report::text, NULL,
    pg_catalog.jsonb_build_object('enabled', p_enabled, 'report_code', v_rep.code, 'report_mode', v_rep.report_mode::text,
                                  'information_cutoff', v_rep.information_cutoff, 'reason', btrim(p_reason)), '{}'::jsonb);
  RETURN pg_catalog.jsonb_build_object('report_id', p_report, 'enabled', p_enabled);
END $$;
COMMENT ON FUNCTION lfhe.set_report_autopilot(uuid, boolean, text) IS 'HUMAN_ONLY';

CREATE OR REPLACE FUNCTION lfhe.autopilot_context()
RETURNS TABLE (report_id uuid, report_mode text, information_cutoff timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT r.id, r.report_mode::text, r.information_cutoff
  FROM lfhe.report_autopilot a JOIN lfhe.reports r ON r.id = a.report_id WHERE a.enabled
$$;

CREATE OR REPLACE FUNCTION lfhe.autopilot_eligible_claims(p_claims uuid[], p_mode text, p_cutoff timestamptz)
RETURNS uuid[] LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT coalesce(array_agg(c.id ORDER BY c.id), '{}')
  FROM lfhe.claims c JOIN lfhe.claim_state st ON st.claim_id = c.id
  WHERE c.id = ANY (coalesce(p_claims, '{}'))
    AND st.review_state NOT IN ('REJECTED', 'REPROCESSING_REQUESTED')
    AND lfhe.claim_cutoff_eligible(c.id, p_mode, p_cutoff)
$$;

REVOKE ALL ON FUNCTION lfhe.set_report_autopilot(uuid, boolean, text), lfhe.autopilot_context(),
  lfhe.autopilot_eligible_claims(uuid[], text, timestamptz)
  FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT EXECUTE ON FUNCTION lfhe.set_report_autopilot(uuid, boolean, text) TO authenticated;
GRANT EXECUTE ON FUNCTION lfhe.autopilot_context() TO lfhe_worker, authenticated;
GRANT EXECUTE ON FUNCTION lfhe.autopilot_eligible_claims(uuid[], text, timestamptz) TO lfhe_worker;

REVOKE ALL ON lfhe.report_autopilot FROM PUBLIC, anon, authenticated, service_role, lfhe_worker, lfhe_evaluator, lfhe_registrar;
GRANT SELECT ON lfhe.report_autopilot TO authenticated, lfhe_worker;
ALTER TABLE lfhe.report_autopilot ENABLE ROW LEVEL SECURITY;
CREATE POLICY report_autopilot_read_human ON lfhe.report_autopilot FOR SELECT TO authenticated
  USING (lfhe.has_permission('CLAIM_READ'));
CREATE POLICY report_autopilot_read_worker ON lfhe.report_autopilot FOR SELECT TO lfhe_worker USING (true);
