"""Phase 7 (P7-01, P7-07) — pilot instrumentation and reproducible metrics (Baseline §25 tests 1–8,
10–14, 16–18). Synthetic 'Northland' material only; the model is the deterministic test double, so
nothing here is evidence of real-provider quality (§14)."""
import json
from decimal import Decimal

import psycopg
import pytest

from lfhe_pilot.capacity import (Comparison, CostAssumption, MissingAssumption, capacity, capacity_value, cash_saving,
                                 evidence_class)
from lfhe_pilot.export import ExportRejected, build_export, export_problems
from lfhe_pilot.metrics import cycle_metrics
from lfhe_shared.audit import verify_chain
from p6_helpers import activate, content, drafted, make_pdf, park_jobs, qa, release, security, store

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def p7(pg):
    yield activate(pg)
    park_jobs(pg)


def authoritative_fingerprint(pg):
    """md5 of every non-pilot lfhe table (the audit log is checked separately by chain verification)."""
    with pg.admin() as x:
        tables = [r["t"] for r in x.execute(
            "SELECT c.relname t FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='lfhe' "
            "AND c.relkind='r' AND c.relname NOT LIKE 'pilot\\_%%' AND c.relname <> 'audit_log' ORDER BY 1")]
        return {t: x.execute(f"SELECT md5(coalesce(string_agg(r::text, '|' ORDER BY r::text), '')) h FROM lfhe.{t} r").fetchone()["h"]
                for t in tables}


def call(pg, user, sql, args=()):
    with pg.as_user(user) as h:
        return h.execute(sql, args).fetchone()


def new_cycle(pg, lead, analyst, code, rid, *, mode="LIVE", boundary="SYNTHETIC"):
    with pg.admin() as x:
        r = x.execute("SELECT report_mode::text m, information_cutoff c FROM lfhe.reports WHERE id=%s", (rid,)).fetchone()
    cid = call(pg, lead, "SELECT lfhe.pilot_create_cycle(%s::jsonb) id", (json.dumps({
        "code": code, "pilot_mode": mode, "information_cutoff": r["c"].isoformat(), "data_boundary": boundary,
        "input_scope": "synthetic Northland corpus, one event", "analyst_user_id": str(analyst),
        "provider_setup": "test double (fake provider)"}),))["id"]
    return str(cid), r


def released_report(pg, analyst, rev, sec, ra, code, tmp_path, *, cycle=None):
    d = drafted(pg, analyst, code)
    if cycle:
        call(pg, analyst, "SELECT lfhe.pilot_start_timer(%s, 'QA_RESOLUTION') id", (cycle,))
    q = qa(pg, analyst, d.rv)
    assert q.status == "PASS", q
    if cycle:
        call(pg, analyst, "SELECT lfhe.pilot_stop_timer(%s) n", (cycle,))
    c = content(pg, rev, d.rv, q.qa_result_id)
    security(pg, sec, d.rv, c["security_review_id"])
    pdf = make_pdf(pg, d.rv, store(tmp_path))
    release(pg, ra, d.rv, pdf["pdf_artifact_id"])
    return d


def test_pilot_cycle_end_to_end_measurement_is_traceable_and_never_touches_analytical_state(pg, p7, make_user, tmp_path):
    analyst, rev, sec, ra, lead = (make_user(r) for r in ("ANALYST", "REVIEWER", "SECURITY_REVIEWER", "RELEASE_AUTHORITY", "PILOT_LEAD"))
    d = drafted(pg, analyst, "RPT-P7-1")
    cid, rep = new_cycle(pg, lead, analyst, "P7C-T1", d.rid)
    before = authoritative_fingerprint(pg)
    # analyst timing: server clock only; starting a new stage closes the open one
    call(pg, analyst, "SELECT lfhe.pilot_start_timer(%s, 'REPORT_EDIT') id", (cid,))
    call(pg, analyst, "SELECT lfhe.pilot_start_timer(%s, 'QA_RESOLUTION') id", (cid,))
    call(pg, analyst, "SELECT lfhe.pilot_stop_timer(%s) n", (cid,))
    call(pg, lead, "SELECT lfhe.pilot_bind_report(%s, %s) r", (cid, d.rid))
    call(pg, analyst, "SELECT lfhe.pilot_record_ux_finding(%s::jsonb) id", (json.dumps({
        "cycle_id": cid, "area": "QA_VIEW", "severity": "MINOR", "finding_class": "USABILITY_DEFECT",
        "title": "Finding list needs scrolling", "description": "the QA finding list is long and needs scrolling", "route": "/reports/[id]"}),))
    call(pg, analyst, "SELECT lfhe.pilot_record_workload(%s, %s::jsonb)", (cid, json.dumps(
        {"mental": 40, "physical": 5, "temporal": 30, "performance": 20, "effort": 35, "frustration": 10})))
    call(pg, lead, "SELECT lfhe.pilot_record_comparator(%s, %s::jsonb) id", (cid, json.dumps({
        "method": "MATCHED_MANUAL_CONTROL", "baseline_analyst_seconds": 7200, "baseline_basis": "TIMED_MEASUREMENT",
        "comparable_scope": True, "reference": "synthetic manual control (test)"})))
    assert authoritative_fingerprint(pg) == before                                   # test 1 (before the report moves on)

    # test 7: completeness is reported, never filled — the report is not released yet, runs not bound
    missing = call(pg, lead, "SELECT lfhe.pilot_cycle_missing_metrics(%s) m", (cid,))["m"]
    assert "MODEL_RUNS_NOT_BOUND" in missing and any(m.startswith("REPORT_NOT_AT_TERMINAL_STATE") for m in missing)
    with pytest.raises(psycopg.errors.CheckViolation, match="PILOT_MEASUREMENT_INCOMPLETE"):
        call(pg, lead, "SELECT lfhe.pilot_close_cycle(%s, 'COMPLETED', 'trying to close early') r", (cid,))

    q = qa(pg, analyst, d.rv)
    c = content(pg, rev, d.rv, q.qa_result_id)
    security(pg, sec, d.rv, c["security_review_id"])
    release(pg, ra, d.rv, make_pdf(pg, d.rv, store(tmp_path))["pdf_artifact_id"])
    # test 8: provider metrics bind to the exact model runs of the chain (M07, M08, M09, M10-S)
    n = call(pg, lead, "SELECT lfhe.pilot_bind_model_runs(%s, NULL, 'REPORT_CHAIN') n", (cid,))["n"]
    with pg.admin() as x:
        bound = {r["module_code"]: r for r in x.execute("SELECT * FROM lfhe.pilot_model_run_metrics WHERE cycle_id=%s", (cid,))}
        chain = x.execute("SELECT lfhe.pilot_report_chain_model_runs(%s) r", (d.rid,)).fetchone()["r"]
        m09 = x.execute("SELECT created_by_model_run_id r FROM lfhe.report_versions WHERE id=%s", (str(d.rv["id"]),)).fetchone()["r"]
        m10 = x.execute("SELECT model_run_id r FROM lfhe.qa_runs WHERE id=%s", (str(q.semantic_qa_run_id),)).fetchone()["r"]
    assert n == len(chain) >= 4 and {"M07_INTELLIGENCE_ASSESSOR", "M08_CHALLENGER", "M09_EXECUTIVE_EDITOR", "M10_QA_AUDITOR"} <= set(bound)
    assert str(bound["M09_EXECUTIVE_EDITOR"]["model_run_id"]) == str(m09) and m10 in chain
    assert all(r["prompt_content_hash"] and r["model_config_hash"] and r["latency_ms"] is not None for r in bound.values())
    assert all(r["model_cost"] is None for r in bound.values())                       # no price recorded → cost unknown, not 0
    with pytest.raises(psycopg.Error, match="PILOT_MODEL_RUN_UNKNOWN"):
        call(pg, lead, "SELECT lfhe.pilot_bind_model_runs(%s, ARRAY['00000000-0000-4000-8000-0000000000aa']::uuid[], 'TRIAL') n", (cid,))

    res = call(pg, lead, "SELECT lfhe.pilot_close_cycle(%s, 'COMPLETED', 'all measurements recorded for the test cycle') r", (cid,))["r"]
    assert res["terminal_state"] == "RELEASED"
    with pytest.raises(psycopg.Error, match="PILOT_CYCLE_NOT_OPEN"):
        call(pg, analyst, "SELECT lfhe.pilot_start_timer(%s, 'OTHER') id", (cid,))
    with pg.admin() as x, pytest.raises(psycopg.Error, match="closed and immutable"):
        x.execute("UPDATE lfhe.pilot_cycles SET closure_note='edited' WHERE id=%s", (cid,))

    # P7-07 reproducible metrics
    with pg.admin() as x:
        m1, m2 = cycle_metrics(x, cid), cycle_metrics(x, cid)
    assert m1 == m2 and m1["missing"] == []                                            # test 12: deterministic
    assert m1["cycle"]["mode"] == "LIVE" and m1["comparator"]["method"] == "MATCHED_MANUAL_CONTROL"   # tests 4, 14
    assert set(m1["effort"]["analyst_seconds_by_stage"]) == {"REPORT_EDIT", "QA_RESOLUTION"} and m1["effort"]["timing_complete"]
    assert m1["throughput"]["final_report_items"] >= 1 and m1["throughput"]["assessments"] == 1
    assert m1["provenance"] == {"released": True, "manifest_problems": [], "complete": True}
    assert m1["provider"]["real_provider_runs"] == 0                                    # test double ≠ real-provider evidence
    assert m1["qa"]["final_status"] == "PASS" and set(m1["qa"]) >= {"D", "S"}           # D and S separately measurable
    assert m1["ux"]["by_severity"] == {"MINOR": 1} and m1["workload"]["raw_tlx"] == Decimal("23.33").__float__()
    with pg.admin() as x:
        assert verify_chain(x).ok                                                         # test 17


def test_mode_and_cutoff_must_match_the_report_and_timing_is_ordered(pg, p7, make_user):
    analyst, lead = make_user("ANALYST"), make_user("PILOT_LEAD")
    live = drafted(pg, analyst, "RPT-P7-2")
    cid, rep = new_cycle(pg, lead, analyst, "P7C-T2", live.rid, mode="REPLAY", boundary="AUTHORISED_PUBLIC_REPLAY")
    with pytest.raises(psycopg.errors.CheckViolation, match="PILOT_MODE_OR_CUTOFF_MISMATCH"):   # tests 3, 4
        call(pg, lead, "SELECT lfhe.pilot_bind_report(%s, %s) r", (cid, live.rid))
    with pytest.raises(psycopg.errors.CheckViolation):                                    # LIVE cycles cannot claim replay material
        new_cycle(pg, lead, analyst, "P7C-T2B", live.rid, mode="LIVE", boundary="AUTHORISED_PUBLIC_REPLAY")
    # tests 5, 6: timing is server-clock, ordered; no negative or rewritten segment is possible
    sid = call(pg, analyst, "SELECT lfhe.pilot_start_timer(%s, 'REPORT_EDIT') id", (cid,))["id"]
    call(pg, analyst, "SELECT lfhe.pilot_stop_timer(%s) n", (cid,))
    with pg.admin() as x:
        s = x.execute("SELECT * FROM lfhe.pilot_timing_segments WHERE id=%s", (sid,)).fetchone()
        assert s["ended_at"] >= s["started_at"]
        with pytest.raises(psycopg.Error, match="only be closed, once"):
            x.execute("UPDATE lfhe.pilot_timing_segments SET ended_at = started_at - interval '1 hour' WHERE id=%s", (sid,))
        with pytest.raises(psycopg.errors.CheckViolation):
            x.execute("INSERT INTO lfhe.pilot_timing_segments (cycle_id, user_id, stage, started_at, ended_at, end_reason) "
                      "VALUES (%s, %s, 'OTHER', now(), now() - interval '1 minute', 'STOPPED')", (cid, str(analyst)))
    fns = call(pg, analyst, "SELECT array_agg(p.proname::text) f FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
                            "WHERE n.nspname='lfhe' AND p.proname LIKE 'pilot\\_%%' AND pg_get_function_arguments(p.oid) ~ 'interval|seconds'")["f"]
    assert fns is None                                                                     # no API takes a typed-in duration


def test_explicit_cost_assumptions_and_separated_cash_semantics(pg, p7, make_user):
    lead, analyst = make_user("PILOT_LEAD"), make_user("ANALYST")
    with pg.admin() as x:                                                                 # test 11: nothing seeded
        assert x.execute("SELECT count(*) n FROM lfhe.pilot_cost_assumptions").fetchone()["n"] == 0
        assert x.execute("SELECT count(*) n FROM lfhe.pilot_provider_prices").fetchone()["n"] == 0
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        call(pg, analyst, "SELECT lfhe.pilot_record_cost_assumption(%s::jsonb) id", (json.dumps({
            "code": "COST-X", "currency": "EUR", "loaded_hourly_cost": 50, "weekly_work_hours": 40,
            "working_weeks_per_year": 46, "basis": "analyst cannot set economics"}),))
    call(pg, lead, "SELECT lfhe.pilot_record_cost_assumption(%s::jsonb) id", (json.dumps({
        "code": "COST-TEST-1", "currency": "EUR", "loaded_hourly_cost": "60.00", "weekly_work_hours": "40",
        "working_weeks_per_year": "46", "basis": "synthetic test assumption, not a real rate"}),))
    with pytest.raises(psycopg.errors.CheckViolation):
        call(pg, lead, "SELECT lfhe.pilot_record_cost_assumption(%s::jsonb) id", (json.dumps({
            "code": "COST-BAD", "currency": "EUR", "loaded_hourly_cost": 0, "weekly_work_hours": 40,
            "working_weeks_per_year": 46, "basis": "zero cost is not an assumption"}),))
    with pg.admin() as x, pytest.raises(psycopg.Error, match="append-only"):
        x.execute("UPDATE lfhe.pilot_cost_assumptions SET loaded_hourly_cost = 1")

    a = CostAssumption("COST-TEST-1", "EUR", Decimal("60.00"), Decimal("40"), Decimal("46"))
    ctrl = Comparison("MATCHED_MANUAL_CONTROL", "TIMED_MEASUREMENT", True)
    r = capacity(Decimal("10"), Decimal("6"), ctrl, a, cycles_per_week=1)                 # test 12
    assert (r.analyst_hours_saved, r.capacity_release_percent, r.weekly_fte_equivalent, r.capacity_value,
            r.annual_capacity_value) == (Decimal("4"), Decimal("40.00"), Decimal("0.1000"), Decimal("240.00"), Decimal("11040.00"))
    assert r == capacity(Decimal("10"), Decimal("6"), ctrl, a, cycles_per_week=1)
    assert r.cash_saving is None and "not a cash saving" in r.semantics                   # test 13
    cash = cash_saving([{"category": "AVOIDED_OVERTIME", "amount": "120", "currency": "EUR"}])
    assert cash["EUR"]["AVOIDED_OVERTIME"] == Decimal("120.00") and cash["EUR"]["ACTUAL_CASH_SAVING"] == Decimal("0.00")
    with pytest.raises(MissingAssumption):
        capacity_value(4, None)
    with pytest.raises(MissingAssumption):
        CostAssumption("COST-NONE", "EUR", Decimal("0"), Decimal("40"), Decimal("46"))
    obs = capacity(Decimal("10"), Decimal("6"), Comparison("PRIOR_DOCUMENTED_MANUAL_WORKFLOW", "DOCUMENTED_RECORD", True), a,
                   cycles_per_week=1)
    assert obs.evidence_class == "OBSERVATIONAL" and obs.annual_capacity_value is None     # §9: never upgraded to controlled
    assert evidence_class(Comparison("NONE", None, False)) == "NO_COMPARATOR"
    assert not capacity(Decimal("10"), Decimal("6"), Comparison("NONE", None, False), a).claimable


def test_pilot_rbac_and_human_only_controls_unchanged(pg, p7, make_user):
    viewer, analyst, lead, admin = make_user("VIEWER"), make_user("ANALYST"), make_user("PILOT_LEAD"), make_user("ADMIN")
    with pg.admin() as x:
        human = {r["proname"] for r in x.execute(
            "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='lfhe' "
            "AND p.proname LIKE 'pilot\\_%%' AND obj_description(p.oid,'pg_proc')='HUMAN_ONLY'")}
        assert len(human) == 16
        for t in [r["relname"] for r in x.execute("SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                                                  "WHERE n.nspname='lfhe' AND relkind='r' AND relname LIKE 'pilot\\_%%'")]:
            assert x.execute("SELECT relrowsecurity r FROM pg_class WHERE oid=%s::regclass", (f"lfhe.{t}",)).fetchone()["r"]
            for role in ("authenticated", "service_role", "anon", "lfhe_worker", "lfhe_evaluator", "lfhe_registrar"):
                for priv in ("INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                    assert not x.execute("SELECT has_table_privilege(%s, %s, %s) ok", (role, f"lfhe.{t}", priv)).fetchone()["ok"]
            assert not x.execute("SELECT has_table_privilege('lfhe_worker', %s, 'SELECT') ok", (f"lfhe.{t}",)).fetchone()["ok"]
        # test 16: no pilot role gained analytical / QA / approval / security / release authority
        perms = {r["p"] for r in x.execute("SELECT permission_code p FROM lfhe.role_permissions WHERE role_code='PILOT_LEAD'")}
        assert perms.isdisjoint({"CLAIM_REVIEW", "EVENT_ACTION", "ASSESSMENT_REVIEW", "FINAL_CONFIDENCE_SET", "REPORT_EDIT",
                                 "REPORT_CONTENT_APPROVE", "QA_WARNING_ACKNOWLEDGE", "SECURITY_REVIEW", "RELEASE_DECIDE"})
        rows = x.execute("SELECT role_code, permission_code FROM lfhe.role_permissions WHERE permission_code IN "
                         "('QA_WARNING_ACKNOWLEDGE', 'REPORT_CONTENT_APPROVE', 'SECURITY_REVIEW', 'RELEASE_DECIDE')").fetchall()
    assert sorted((r["permission_code"], r["role_code"]) for r in rows) == [
        ("QA_WARNING_ACKNOWLEDGE", "REVIEWER"), ("RELEASE_DECIDE", "RELEASE_AUTHORITY"),
        ("REPORT_CONTENT_APPROVE", "REVIEWER"), ("SECURITY_REVIEW", "SECURITY_REVIEWER")]
    body = json.dumps({"code": "P7C-RBAC", "pilot_mode": "LIVE", "information_cutoff": "2026-01-01T00:00:00Z",
                       "data_boundary": "SYNTHETIC", "input_scope": "synthetic Northland corpus", "analyst_user_id": str(analyst),
                       "provider_setup": "fake"})
    for u in (viewer, analyst, admin):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            call(pg, u, "SELECT lfhe.pilot_create_cycle(%s::jsonb) id", (body,))
    for conn in (pg.worker, pg.as_service_role, pg.as_anon):
        with conn() as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("SELECT lfhe.pilot_create_cycle(%s::jsonb)", (body,))
    with pytest.raises(psycopg.Error, match="PILOT_ANALYST_INVALID"):
        call(pg, lead, "SELECT lfhe.pilot_create_cycle(%s::jsonb) id", (body.replace(str(analyst), str(viewer)),))
    cid = call(pg, lead, "SELECT lfhe.pilot_create_cycle(%s::jsonb) id", (body,))["id"]
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        call(pg, viewer, "SELECT lfhe.pilot_start_timer(%s, 'OTHER') id", (str(cid),))
    with pg.as_user(viewer) as h:
        assert h.execute("SELECT count(*) n FROM lfhe.pilot_cycles").fetchone()["n"] == 0     # no PILOT_READ
    with pg.as_user(analyst) as h:
        assert h.execute("SELECT count(*) n FROM lfhe.pilot_cycles").fetchone()["n"] >= 1


def test_export_is_reproducible_and_clean(pg, p7, make_user, tmp_path):
    analyst, rev, sec, ra, lead = (make_user(r) for r in ("ANALYST", "REVIEWER", "SECURITY_REVIEWER", "RELEASE_AUTHORITY", "PILOT_LEAD"))
    with pg.admin() as x:
        doc1 = build_export(x, cycle_codes=["P7C-T1"], cost_assumption_code="COST-TEST-1", cycles_per_week=1,
                            generated_at="2026-10-23T00:00:00Z")
        doc2 = build_export(x, cycle_codes=["P7C-T1"], cost_assumption_code="COST-TEST-1", cycles_per_week=1,
                            generated_at="2026-10-23T00:00:00Z")
    assert doc1 == doc2 and export_problems(doc1) == []                                   # tests 12, 18
    cap = doc1["cycles"][0]["capacity"]
    assert cap["computed"] and cap["evidence_class"] == "CONTROLLED" and cap["cash_saving"] is None
    assert export_problems({"x": {"api_key": "a"}}) and export_problems({"note": "postgresql://u:" + "x" * 8 + "@h/db"})
    with pytest.raises(ExportRejected):
        with pg.admin() as x:
            x.execute("SELECT 1")
            from lfhe_pilot import export as ex
            orig = ex.cycle_metrics
            ex.cycle_metrics = lambda conn, cid: {**orig(conn, cid), "provider_setup_token": "x"}
            try:
                ex.build_export(x, cycle_codes=["P7C-T1"], generated_at="t")
            finally:
                ex.cycle_metrics = orig
