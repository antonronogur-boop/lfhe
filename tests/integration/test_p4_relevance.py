"""P4-02 — M06 relevance (Phase 4 Addendum §4, required tests 1–9) through the real
M06 bundle, the real input builder and real ingestion; the model is scripted."""
import json
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from claims_support import make_model_run
from lfhe_orchestrator.assessment_inputs import build_m06_inputs
from lfhe_orchestrator.assessment_pipeline import run_relevance
from lfhe_orchestrator.claim_inputs import InputBuildError
from lfhe_orchestrator.providers import FakeProvider
from p4_support import CUT_DT, PRE, POST, approve, create_baseline, head, human_event, pclaim
from pipeline_support import activate_real_prompts, model_configuration
from psycopg.types.json import Jsonb

pytestmark = pytest.mark.db
NOW = lambda: datetime.now(timezone.utc) + timedelta(minutes=5)   # noqa: E731
GOOD = ("Northland's new long-range air-defence radars at Fort Aster extend surveillance over the eastern "
        "flank approaches relevant to Hungarian and NATO air-policing and warning requirements.")
NOT_EST = "No material HU/NATO relevance established from supplied evidence: the claims concern a domestic parade only."


@pytest.fixture(scope="module")
def m06(pg):
    return activate_real_prompts(pg, ("M02_CLAIM_EXTRACTOR", "M03_CLASSIFIER", "M06_RELEVANCE"))


@pytest.fixture
def analyst(make_user):
    return make_user("ANALYST")


def event(pg, analyst, when=PRE):
    c = pclaim(pg, "The air force said 6 long-range radars were installed at Fort Aster.",
               "6 long-range radars were installed at Fort Aster", when, claim_type="DEPLOYMENT")
    e = human_event(pg, analyst, [c], title="Radars installed at Fort Aster")
    h = head(pg, e)
    return e, str(h["head_version_id"]), h["head_content_hash"], c


def out(env, **kw):
    ev = env["inputs"][0]["content"]
    r = {"event_id": ev["event_id"], "event_version_id": ev["event_version_id"],
         "baseline_version_id": env["task"]["baseline_version_id"], "previous_assessment_version_id": None,
         "military_significance": 4, "novelty_change": 3, "hu_nato_relevance_score": 4, "strategic_relevance": 3,
         "time_sensitivity": 2, "applicable_pir_ids": ["PIR_01", "PIR_07"], "recommendation": None,
         "automatic_assessment_recommended": True, "retain_for_manual_review": True,
         "hu_nato_dimensions": ["AIR_DEFENCE", "EASTERN_FLANK_POSTURE"],
         "hu_nato_evidence_claim_ids": [ev["claims"][0]["claim_id"]], "hu_nato_relevance_rationale": GOOD,
         "executive_relevance": "New sensor coverage near the eastern flank.", "reasoning_summary": "Radars installed.",
         "relevance_uncertainty": None}
    extra = kw.pop("_extra", {})
    r.update(kw)
    r.update(extra)
    return json.dumps({"module": "M06_RELEVANCE", "status": "SUCCESS", "warnings": [], "human_review_required": False,
                       "result": r})


def score(pg, vid, vh, responder, mode="LIVE", cutoff=None, baseline_code=None):
    with pg.worker() as c:
        return run_relevance(c, vid, vh, report_mode=mode, information_cutoff=cutoff or NOW(),
                             model_configuration_id=model_configuration(pg), provider=FakeProvider(responder),
                             worker_id="p4-test", baseline_code=baseline_code)


def result_of(pg, run_id):
    with pg.admin() as x:
        return x.execute("SELECT *, hu_nato_dimensions::text[] AS hu_nato_dimensions FROM lfhe.relevance_results "
                         "WHERE model_run_id=%s", (run_id,)).fetchone()


# --- 1, 2: closed scores, no publishing --------------------------------------------------
def test_scores_are_0_to_5_and_m06_cannot_publish(pg, m06, analyst):
    with pg.admin() as x:
        report_rows_before = x.execute("SELECT (SELECT count(*) FROM lfhe.report_candidate_pool) + (SELECT count(*) FROM "
                                       "lfhe.report_selection_decisions) + (SELECT count(*) FROM lfhe.report_versions) n").fetchone()["n"]
    e, vid, vh, _ = event(pg, analyst)
    bad = score(pg, vid, vh, lambda m, env: out(env, military_significance=6))
    assert bad.outcome == "SCHEMA_VALIDATION_FAILED" and len(bad.model_run_ids) == 2      # 1 + repair
    pub = score(pg, vid, vh, lambda m, env: out(env, _extra={"publish": True, "report_candidate": True}))
    assert pub.outcome == "SCHEMA_VALIDATION_FAILED"                                      # 2: no such capability
    ok = score(pg, vid, vh, lambda m, env: out(env))
    r = result_of(pg, ok.final_run_id)
    assert ok.outcome == "RELEVANCE_RECORDED" and float(r["priority_score"]) == round(0.25 * 4 + 0.2 * 3 + 0.25 * 4 + 0.2 * 3 + 0.1 * 2, 2)
    with pg.admin() as x:
        with pytest.raises(psycopg.errors.CheckViolation):
            x.execute("INSERT INTO lfhe.relevance_results SELECT (jsonb_populate_record(NULL::lfhe.relevance_results, "
                      "to_jsonb(r) || '{\"id\": \"00000000-0000-4000-8000-0000000000aa\", \"military_significance\": 9}')).* "
                      "FROM lfhe.relevance_results r WHERE id=%s", (r["id"],))
        # M06 has no path into report selection (Phase 5 forward form of this Phase 4 check, SD5-09):
        # its run wrote no report row, and the worker cannot write selection / version tables.
        assert x.execute("SELECT (SELECT count(*) FROM lfhe.report_candidate_pool) + (SELECT count(*) FROM "
                         "lfhe.report_selection_decisions) + (SELECT count(*) FROM lfhe.report_versions) n").fetchone()["n"] \
            == report_rows_before
    with pg.worker() as w:
        for t in ("report_candidate_pool", "report_selection_decisions", "report_selection_sets", "report_versions"):
            assert not w.execute("SELECT has_table_privilege(current_user, %s, 'INSERT') p", (f"lfhe.{t}",)).fetchone()["p"], t


# --- 3, 4, 5: low score never hides; manual promotion / request is human + audited -------
def test_low_score_stays_visible_and_manually_assessable(pg, m06, analyst, make_user):
    e, vid, vh, _ = event(pg, analyst)
    low = score(pg, vid, vh, lambda m, env: out(env, military_significance=0, novelty_change=0, hu_nato_relevance_score=0,
                                                strategic_relevance=0, time_sensitivity=0, applicable_pir_ids=[],
                                                automatic_assessment_recommended=False, recommendation="BACKGROUND_ONLY",
                                                hu_nato_dimensions=[], hu_nato_evidence_claim_ids=[],
                                                hu_nato_relevance_rationale=NOT_EST))
    assert low.outcome == "RELEVANCE_RECORDED" and float(result_of(pg, low.final_run_id)["priority_score"]) == 0
    viewer = make_user("VIEWER")
    with pg.as_user(viewer) as v:                                                        # 3: still visible
        row = v.execute("SELECT * FROM lfhe.event_relevance_queue WHERE event_id=%s", (e,)).fetchone()
        assert row and float(row["priority_score"]) == 0
        assert v.execute("SELECT count(*) n FROM lfhe.event_versions WHERE event_id=%s", (e,)).fetchone()["n"] == 1
    for conn in (pg.worker, pg.as_service_role, pg.as_anon, lambda: pg.as_user(viewer),
                 lambda: pg.as_user(make_user("ADMIN"))):
        with conn() as x, pytest.raises(psycopg.errors.InsufficientPrivilege):
            x.execute("SELECT lfhe.promote_event_version(%s, %s, 'REQUEST_ASSESSMENT', 'not allowed')", (vid, vh))
    with pg.as_user(analyst) as h:                                                       # 4, 5
        req = h.execute("SELECT lfhe.promote_event_version(%s, %s, 'REQUEST_ASSESSMENT', 'analyst wants an assessment')",
                        (vid, vh)).fetchone()["promote_event_version"]
        h.execute("SELECT lfhe.promote_event_version(%s, %s, 'PROMOTE', 'analyst promotes despite low score')", (vid, vh))
        with pytest.raises(psycopg.errors.SerializationFailure, match="VERSION_HASH_MISMATCH"):
            h.execute("SELECT lfhe.promote_event_version(%s, %s, 'PROMOTE', 'stale hash given')", (vid, "0" * 64))
    with pg.admin() as x:
        ev = {r["event_type"] for r in x.execute("SELECT event_type FROM lfhe.audit_log WHERE object_id=%s", (vid,))}
        assert {"MANUAL_ASSESSMENT_REQUESTED", "EVENT_MANUALLY_PROMOTED"} <= ev
        assert x.execute("SELECT manually_promoted_or_requested m FROM lfhe.event_relevance_queue WHERE event_id=%s",
                         (e,)).fetchone()["m"]
    assert req


# --- 6, 7: PIR-07 rationale --------------------------------------------------------------
@pytest.mark.parametrize("kw, reason", [
    ({"hu_nato_relevance_rationale": "Important for NATO."}, "HU_NATO_RATIONALE_GENERIC"),
    ({"hu_nato_relevance_rationale": "This is strategically significant"}, "HU_NATO_RATIONALE_GENERIC"),
    ({"hu_nato_dimensions": []}, "HU_NATO_DIMENSION_REQUIRED"),
    ({"hu_nato_evidence_claim_ids": []}, "HU_NATO_EVIDENCE_REQUIRED"),
    ({"hu_nato_evidence_claim_ids": ["00000000-0000-4000-8000-000000000001"]}, "HU_NATO_EVIDENCE_NOT_IN_EVENT_VERSION"),
    ({"hu_nato_relevance_score": 0, "hu_nato_dimensions": [], "hu_nato_evidence_claim_ids": [],
      "hu_nato_relevance_rationale": "n/a"}, "HU_NATO_NOT_ESTABLISHED_STATEMENT_REQUIRED"),
])
def test_recommended_event_needs_concrete_hu_nato_rationale(pg, m06, analyst, kw, reason):
    e, vid, vh, _ = event(pg, analyst)
    r = score(pg, vid, vh, lambda m, env: out(env, **kw))
    assert r.outcome == "OUTPUT_REJECTED" and any(x.startswith(reason) for x in r.rejection_reasons), r
    assert result_of(pg, r.final_run_id) is None


def test_not_established_is_a_valid_result(pg, m06, analyst):
    e, vid, vh, _ = event(pg, analyst)
    r = score(pg, vid, vh, lambda m, env: out(env, hu_nato_relevance_score=0, hu_nato_dimensions=[],
                                              hu_nato_evidence_claim_ids=[], hu_nato_relevance_rationale=NOT_EST))
    res = result_of(pg, r.final_run_id)
    assert r.outcome == "RELEVANCE_RECORDED" and res["hu_nato_relevance_established"] is False
    good = result_of(pg, score(pg, vid, vh, lambda m, env: out(env)).final_run_id)
    assert good["hu_nato_relevance_established"] and set(good["hu_nato_dimensions"]) == {"AIR_DEFENCE", "EASTERN_FLANK_POSTURE"}


# --- 8: invalid PIR / taxonomy ID fails closed ------------------------------------------
def test_invalid_pir_fails_closed(pg, m06, analyst):
    e, vid, vh, _ = event(pg, analyst)
    assert score(pg, vid, vh, lambda m, env: out(env, applicable_pir_ids=["PIR_09"])).outcome == "SCHEMA_VALIDATION_FAILED"
    run = make_model_run(pg, "M06_RELEVANCE", [("event_version", vid)],
                         task_parameters={"report_mode": "LIVE", "information_cutoff": NOW().isoformat()})
    payload = json.loads(out({"task": {"baseline_version_id": None}, "inputs": [{"content": {
        "event_id": e, "event_version_id": vid, "claims": [{"claim_id": "00000000-0000-4000-8000-000000000002"}]}}]},
        applicable_pir_ids=["TOPIC_C_UAS"], hu_nato_relevance_score=0, hu_nato_dimensions=[],
        hu_nato_evidence_claim_ids=[], hu_nato_relevance_rationale=NOT_EST))["result"]
    with pg.worker() as c:
        r = c.execute("SELECT lfhe.ingest_relevance(%s::jsonb) r", (Jsonb({"model_run_id": run, "output_status": "SUCCESS",
                                                                              "result": payload}),)).fetchone()["r"]
    assert r["outcome"] == "OUTPUT_REJECTED" and "PIR_ID_UNKNOWN:TOPIC_C_UAS" in r["rejection_reasons"]


# --- 9: M06 cannot change event / claim status ------------------------------------------
def test_m06_changes_no_event_or_claim_state(pg, m06, analyst):
    e, vid, vh, c = event(pg, analyst)
    with pg.admin() as x:
        before = (head(pg, e), x.execute("SELECT claim_status FROM lfhe.claim_state WHERE claim_id=%s",
                                         (c["claim_id"],)).fetchone())
    score(pg, vid, vh, lambda m, env: out(env, recommendation="EXCLUDE_FROM_AUTOMATIC_ASSESSMENT",
                                          automatic_assessment_recommended=False))
    with pg.admin() as x:
        after = (head(pg, e), x.execute("SELECT claim_status FROM lfhe.claim_state WHERE claim_id=%s",
                                        (c["claim_id"],)).fetchone())
    assert before == after


# --- inputs: exact eligible version + hash; as-of baseline -------------------------------
def test_inputs_require_exact_eligible_version_and_supply_only_asof_baseline(pg, m06, analyst):
    e, vid, vh, c = event(pg, analyst)
    with pg.worker() as w:
        with pytest.raises(InputBuildError) as err:
            build_m06_inputs(w, vid, "0" * 64, report_mode="LIVE", information_cutoff=NOW())
        assert err.value.code == "EVENT_VERSION_HASH_MISMATCH"
    late_e, late_vid, late_vh, _ = event(pg, analyst, POST)
    with pg.worker() as w, pytest.raises(InputBuildError) as err:
        build_m06_inputs(w, late_vid, late_vh, report_mode="REPLAY", information_cutoff=CUT_DT)
    assert err.value.code == "EVENT_VERSION_NOT_ELIGIBLE"
    v1 = create_baseline(pg, analyst, "BL-M06-1", [("6 radars at Fort Aster", [("claim", c["claim_id"])])])
    approve(pg, analyst, "baseline", v1)
    with pg.worker() as w:
        x = build_m06_inputs(w, vid, vh, report_mode="REPLAY", information_cutoff=CUT_DT, baseline_code="BL-M06-1")
        none = build_m06_inputs(w, vid, vh, report_mode="REPLAY", information_cutoff=CUT_DT, baseline_code="BL-NONE")
    assert x.task["baseline_version_id"] == v1 and [i.object_id for i in x.context] == [v1]
    assert none.task["baseline_status"] == "BASELINE_UNAVAILABLE" and none.context == []
    r = score(pg, vid, vh, lambda m, env: out(env, baseline_version_id=v1))          # baseline not supplied → reject
    assert "BASELINE_NOT_SUPPLIED_OR_INELIGIBLE" in r.rejection_reasons
    ok = score(pg, vid, vh, lambda m, env: out(env), mode="REPLAY", cutoff=CUT_DT, baseline_code="BL-M06-1")
    assert ok.outcome == "RELEVANCE_RECORDED" and str(result_of(pg, ok.final_run_id)["baseline_version_id"]) == v1


def test_validate_and_override_are_human_only_and_audited(pg, m06, analyst, make_user):
    e, vid, vh, _ = event(pg, analyst)
    res = result_of(pg, score(pg, vid, vh, lambda m, env: out(env)).final_run_id)
    for conn in (pg.worker, pg.as_service_role, lambda: pg.as_user(make_user("VIEWER"))):
        with conn() as x, pytest.raises(psycopg.errors.InsufficientPrivilege):
            x.execute("SELECT lfhe.decide_relevance(%s, 'VALIDATE', NULL, 'not allowed')", (res["id"],))
    with pg.as_user(analyst) as h:
        h.execute("SELECT lfhe.decide_relevance(%s, 'VALIDATE', NULL, 'rationale checked')", (res["id"],))
        h.execute("SELECT lfhe.decide_relevance(%s, 'OVERRIDE', %s::jsonb, 'analyst lowers priority')",
                  (res["id"], json.dumps({"priority_score": 1.5, "automatic_assessment_recommended": False})))
        with pytest.raises(psycopg.errors.InvalidParameterValue):
            h.execute("SELECT lfhe.decide_relevance(%s, 'OVERRIDE', %s::jsonb, 'bad override value')",
                      (res["id"], json.dumps({"priority_score": 9})))
    with pg.admin() as x:
        ev = {r["event_type"] for r in x.execute("SELECT event_type FROM lfhe.audit_log WHERE object_id=%s", (vid,))}
        assert {"EXECUTIVE_RELEVANCE_VALIDATED", "RELEVANCE_SCORE_OVERRIDDEN"} <= ev
        q = x.execute("SELECT latest_override FROM lfhe.event_relevance_queue WHERE event_id=%s", (e,)).fetchone()
    assert q["latest_override"]["priority_score"] == 1.5
