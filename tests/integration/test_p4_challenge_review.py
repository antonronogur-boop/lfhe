"""P4-05 / P4-06 — M08 structured challenge + human disposition, human analytical review,
final analytic confidence, immutable MODIFY_AND_APPROVE (Phase 4 Addendum §13, §16, §19;
required tests 37–53) through the real M07/M08 bundles and ingestion; scripted model."""
import json

import psycopg
import pytest
from psycopg.types.json import Jsonb

from claims_support import make_model_run
from lfhe_orchestrator.assessment_pipeline import run_challenge
from lfhe_orchestrator.claim_inputs import InputBuildError
from lfhe_orchestrator.providers import FakeProvider
from p4_support import approve, create_baseline, pclaim
from pipeline_support import activate_real_prompts, model_configuration
from test_p4_assessments import NOW, assess, out, rejected, setup_event, st, version_of

pytestmark = pytest.mark.db
CONF_RAT = "Single official source, contradicted by a denial; analyst keeps moderate confidence."


@pytest.fixture(scope="module")
def m78(pg):
    return activate_real_prompts(pg, ("M02_CLAIM_EXTRACTOR", "M03_CLASSIFIER", "M07_INTELLIGENCE_ASSESSOR", "M08_CHALLENGER"))


@pytest.fixture
def analyst(make_user):
    return make_user("ANALYST")


def flag(ftype="OVERCONFIDENCE", sev="MAJOR", stmt="AS3", field=None, action="LOWER_CONFIDENCE",
         expl="The judgment rests on one official source contradicted by a denial.", evidence=()):
    return {"flag_type": ftype, "severity": sev, "affected_statement_local_id": stmt, "affected_field": field,
            "explanation": expl, "evidence_claim_ids": list(evidence), "recommended_action": action}


def chal(env, flags=None, counter="The denial may be accurate; the arrival could be a routine transit only.",
         result="CHALLENGED_WITH_FLAGS", **extra):
    r = {"assessment_version_id": env["task"]["assessment_version_id"],
         "assessment_version_hash": env["task"]["assessment_version_hash"], "challenge_result": result,
         "flags": [flag()] if flags is None else flags, "strongest_counterargument": counter,
         "confidence_challenge": "MODERATE is not supported by a single contradicted lineage.",
         "recommended_overall_action": "ANALYST_REVIEW"}
    r.update(extra)
    return json.dumps({"module": "M08_CHALLENGER", "status": "SUCCESS", "warnings": [], "human_review_required": True,
                       "result": r})


def draft(pg, analyst, **kw):
    e, vid, vh, claims = setup_event(pg, analyst)
    r = assess(pg, vid, vh, lambda m, env: out(env, claims=claims), **kw)
    assert r.outcome == "ASSESSMENT_RECORDED", r
    return version_of(pg, r.final_run_id), claims, (e, vid, vh)


def challenge(pg, v, responder):
    with pg.worker() as c:
        return run_challenge(c, str(v["id"]), v["content_hash"], model_configuration_id=model_configuration(pg),
                             provider=FakeProvider(responder), worker_id="p4-test")


def state(pg, version_id):
    with pg.admin() as x:
        return x.execute("SELECT state::text s FROM lfhe.assessment_version_states WHERE assessment_version_id=%s",
                         (version_id,)).fetchone()["s"]


def in_review(pg, analyst, **kw):
    v, claims, ev = draft(pg, analyst, **kw)
    assert challenge(pg, v, lambda m, env: chal(env)).outcome == "CHALLENGE_RECORDED"
    assert state(pg, v["id"]) == "IN_REVIEW"
    return v, claims, ev


def review(pg, user, v, decision, conf=None, rat=None, h=None):
    with pg.as_user(user) as c:
        return c.execute("SELECT lfhe.review_assessment(%s, %s, %s, %s, %s, 'analyst reviewed the draft') r",
                         (str(v["id"]), h or v["content_hash"], decision, conf, rat)).fetchone()["r"]


def ingest_direct(pg, v, result):
    run = make_model_run(pg, "M08_CHALLENGER", [("assessment_version", str(v["id"]))],
                         task_parameters={"report_mode": v["report_mode"], "information_cutoff": v["information_cutoff"].isoformat()})
    with pg.worker() as c:
        return c.execute("SELECT lfhe.ingest_challenge(%s::jsonb) r",
                         (Jsonb({"model_run_id": run, "output_status": "SUCCESS", "result": result}),)).fetchone()["r"]


def snapshot(pg, vid):
    with pg.admin() as x:
        return (dict(x.execute("SELECT content, content_hash, ai_recommended_confidence::text c FROM lfhe.assessment_versions "
                               "WHERE id=%s", (vid,)).fetchone()),
                [dict(r) for r in x.execute("SELECT statement_local_id, statement_text, statement_type::text t "
                                            "FROM lfhe.assessment_statements WHERE assessment_version_id=%s ORDER BY 1", (vid,))])


# --- 37, 38, 39, 40 ------------------------------------------------------------------------
def test_m08_flags_are_bound_to_exact_version_and_never_mutate_m07(pg, m78, analyst):
    v, claims, _ = draft(pg, analyst)
    before = snapshot(pg, v["id"])
    seen = {}

    def responder(m, env):
        seen["env"] = env
        return chal(env, flags=[flag(), flag("CONTRADICTORY_EVIDENCE", "WARNING", None, "STATEMENT_SET", "ADD_CAVEAT",
                                             "The denial must stay visible next to the arrival report.",
                                             [claims[1]["claim_id"]])])
    r = challenge(pg, v, responder)
    assert r.outcome == "CHALLENGE_RECORDED", r
    assert [i["object_type"] for i in seen["env"]["inputs"]] == ["assessment_version"]
    assert seen["env"]["task"]["information_cutoff"] == v["information_cutoff"].isoformat()
    assert snapshot(pg, v["id"]) == before
    with pg.admin() as x:
        cr = x.execute("SELECT * FROM lfhe.challenge_runs WHERE model_run_id=%s", (r.final_run_id,)).fetchone()
        assert (str(cr["assessment_version_id"]), cr["assessment_version_hash"]) == (str(v["id"]), v["content_hash"])
        flags = x.execute("SELECT f.*, f.flag_type::text ft, f.severity::text sv, f.recommended_action::text ra, "
                          "f.affected_field::text af, s.statement_local_id sl FROM lfhe.challenge_flags f "
                          "LEFT JOIN lfhe.assessment_statements s ON s.id=f.affected_statement_id "
                          "WHERE challenge_run_id=%s ORDER BY flag_no", (cr["id"],)).fetchall()
        assert [(f["ft"], f["sv"], f["sl"], f["af"], f["ra"]) for f in flags] == [
            ("OVERCONFIDENCE", "MAJOR", "AS3", None, "LOWER_CONFIDENCE"),
            ("CONTRADICTORY_EVIDENCE", "WARNING", None, "STATEMENT_SET", "ADD_CAVEAT")]
        assert all(len(f["explanation"]) >= 10 for f in flags)
        assert [str(c) for c in flags[1]["evidence_claim_ids"]] == [claims[1]["claim_id"]]
        cols = {c["column_name"] for c in x.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='lfhe' "
                                                    "AND table_name IN ('challenge_runs','challenge_flags')")}
        assert not cols & {"final_analytic_confidence", "ai_recommended_confidence", "confidence"}
        for sql in ("UPDATE lfhe.challenge_flags SET severity='INFO' WHERE challenge_run_id=%s",
                    "DELETE FROM lfhe.challenge_runs WHERE id=%s"):
            with pytest.raises(psycopg.Error):
                x.execute(sql, (cr["id"],))
    assert state(pg, v["id"]) == "IN_REVIEW"
    # the worker cannot write assessment content directly
    with pg.worker() as c, pytest.raises(psycopg.Error):
        c.execute("UPDATE lfhe.assessment_statements SET statement_text='x' WHERE assessment_version_id=%s", (v["id"],))


def test_m08_output_that_modifies_or_finalises_is_rejected_and_binding_is_exact(pg, m78, analyst):
    v, claims, _ = draft(pg, analyst)
    base = json.loads(chal({"task": {"assessment_version_id": str(v["id"]), "assessment_version_hash": v["content_hash"]}}))["result"]
    # schema layer: extra keys never pass
    assert challenge(pg, v, lambda m, env: chal(env, final_analytic_confidence="LOW")).outcome == "SCHEMA_VALIDATION_FAILED"
    for key, val in (("final_analytic_confidence", "LOW"), ("assessment_statements", []), ("ai_recommended_confidence", "LOW")):
        r = ingest_direct(pg, v, dict(base, **{key: val}))
        assert "M08_MAY_NOT_MODIFY_ASSESSMENT" in r["rejection_reasons"], key
    assert "ASSESSMENT_VERSION_HASH_MISMATCH" in ingest_direct(pg, v, dict(base, assessment_version_hash="0" * 64))["rejection_reasons"]
    r = ingest_direct(pg, v, dict(base, assessment_version_id="00000000-0000-4000-8000-000000000009"))
    assert r["rejection_reasons"] == ["ASSESSMENT_VERSION_NOT_SUPPLIED"]
    assert "FLAG_TARGET_REQUIRED" in ingest_direct(pg, v, dict(base, flags=[flag(stmt=None)]))["rejection_reasons"]
    assert any(x.startswith("FLAG_TARGET_UNKNOWN") for x in ingest_direct(pg, v, dict(base, flags=[flag(stmt="AS99")]))["rejection_reasons"])
    assert any(x.startswith("EVIDENCE_NOT_SUPPLIED") for x in ingest_direct(
        pg, v, dict(base, flags=[flag(evidence=["00000000-0000-4000-8000-00000000000a"])]))["rejection_reasons"])
    assert "STRONGEST_COUNTERARGUMENT_REQUIRED" in ingest_direct(pg, v, dict(base, strongest_counterargument=" "))["rejection_reasons"]
    assert state(pg, v["id"]) == "DRAFT"           # nothing above changed workflow state
    with pg.admin() as x:
        assert x.execute("SELECT count(*) n FROM lfhe.challenge_runs WHERE assessment_version_id=%s", (v["id"],)).fetchone()["n"] == 0


# --- 41, 42, 43, 44 ------------------------------------------------------------------------
def test_inflation_omitted_contradiction_and_context_contamination_are_flaggable(pg, m78, analyst):
    prior = pclaim(pg, "In 2025 the air force said Fort Aster hosted fighter aircraft only.", "Fort Aster hosted fighter aircraft only")
    b = create_baseline(pg, analyst, "BL-CH-1", [("Fort Aster hosted fighter aircraft only in 2025.", [("claim", prior["claim_id"])])])
    approve(pg, analyst, "baseline", b)
    v, claims, _ = draft(pg, analyst, baseline_code="BL-CH-1")
    counter = "The single ministry lineage plus a denial supports at most LOW confidence; transit is as likely."
    flags = [flag("OVERCONFIDENCE", "MAJOR", None, "AI_RECOMMENDED_CONFIDENCE", "LOWER_CONFIDENCE"),
             flag("UNSUPPORTED_STATEMENT", "CRITICAL", "AS3", None, "REMOVE_UNSUPPORTED_STATEMENT"),
             flag("CONTRADICTORY_EVIDENCE", "MAJOR", "AS1", None, "ADD_CAVEAT", evidence=[claims[1]["claim_id"]]),
             flag("BASELINE_ERROR", "WARNING", None, "BASELINE", "RECHECK_BASELINE"),
             flag("HINDSIGHT_CONTAMINATION", "WARNING", None, "REFERENCE_CONTEXT", "RECHECK_DATE"),
             flag("CIRCULAR_REPORTING", "MAJOR", "AS3", None, "RECHECK_LINEAGE")]
    seen = {}

    def responder(m, env):
        seen["ctx"] = [c["object_type"] for c in env["context"]]
        return chal(env, flags=flags, counter=counter)
    r = challenge(pg, v, responder)
    assert r.outcome == "CHALLENGE_RECORDED", r
    assert "baseline_version" in seen["ctx"] and "event_version" in seen["ctx"]
    with pg.admin() as x:
        cr = x.execute("SELECT * FROM lfhe.challenge_runs WHERE model_run_id=%s", (r.final_run_id,)).fetchone()
        assert cr["strongest_counterargument"] == counter
        got = [f["t"] for f in x.execute("SELECT flag_type::text t FROM lfhe.challenge_flags WHERE challenge_run_id=%s "
                                          "ORDER BY flag_no", (cr["id"],))]
    assert got == [f["flag_type"] for f in flags]
    # the draft's own confidence is untouched by the challenge
    with pg.admin() as x:
        assert x.execute("SELECT ai_recommended_confidence::text c FROM lfhe.assessment_versions WHERE id=%s",
                         (v["id"],)).fetchone()["c"] == "MODERATE"


# --- 45, 46 --------------------------------------------------------------------------------
def test_disposition_is_human_only_and_separate_from_model_output(pg, m78, analyst, make_user):
    v, claims, _ = in_review(pg, analyst)
    with pg.admin() as x:
        f = x.execute("SELECT f.id FROM lfhe.challenge_flags f JOIN lfhe.challenge_runs r ON r.id=f.challenge_run_id "
                      "WHERE r.assessment_version_id=%s", (v["id"],)).fetchone()["id"]
    sql = "SELECT lfhe.dispose_challenge_flag(%s, 'ACCEPTED', 'accepted: lower the confidence') r"
    with pg.worker() as c, pytest.raises(psycopg.Error):
        c.execute(sql, (f,))
    with pg.as_service_role() as c, pytest.raises(psycopg.Error):
        c.execute(sql, (f,))
    with pg.as_user(make_user("VIEWER")) as c, pytest.raises(psycopg.Error):
        c.execute(sql, (f,))
    with pg.as_user(make_user("REVIEWER")) as c:
        c.execute("SELECT lfhe.dispose_challenge_flag(%s, 'ACKNOWLEDGED', 'reviewer notes the flag') r", (f,))
    with pg.as_user(analyst) as c:
        d = c.execute(sql, (f,)).fetchone()["r"]
        with pytest.raises(psycopg.Error):
            c.execute("SELECT lfhe.dispose_challenge_flag(%s, 'IGNORED', 'not a disposition') r", (f,))
    with pg.admin() as x:
        rows = x.execute("SELECT disposition, actor_user_id FROM lfhe.challenge_flag_dispositions WHERE flag_id=%s ORDER BY seq",
                         (f,)).fetchall()
        assert [r["disposition"] for r in rows] == ["ACKNOWLEDGED", "ACCEPTED"] and str(rows[1]["actor_user_id"]) == str(analyst)
        cols = {c["column_name"] for c in x.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='lfhe' "
                                                    "AND table_name='challenge_flags'")}
        assert "disposition" not in cols
        assert x.execute("SELECT count(*) n FROM lfhe.audit_log WHERE event_type='CHALLENGER_FLAG_DISPOSITIONED' "
                         "AND object_id=%s", (str(f),)).fetchone()["n"] == 2
        with pytest.raises(psycopg.Error):
            x.execute("UPDATE lfhe.challenge_flag_dispositions SET disposition='REJECTED' WHERE id=%s", (d,))


# --- 47, 50, 51, 53 + challenge precedes review ----------------------------------------------
def test_approve_is_version_hash_bound_and_final_confidence_is_human_only(pg, m78, analyst, make_user):
    v0, _, _ = draft(pg, analyst)
    with pytest.raises(psycopg.Error, match="ASSESSMENT_NOT_CHALLENGED"):
        review(pg, analyst, v0, "APPROVE", "LOW", CONF_RAT)
    v, _, _ = in_review(pg, analyst)
    with pytest.raises(psycopg.Error, match="VERSION_HASH_MISMATCH"):
        review(pg, analyst, v, "APPROVE", "LOW", CONF_RAT, h="f" * 64)
    with pytest.raises(psycopg.Error, match="FINAL_CONFIDENCE_AND_RATIONALE_REQUIRED"):
        review(pg, analyst, v, "APPROVE", "LOW", "too short")
    with pytest.raises(psycopg.Error, match="FINAL_CONFIDENCE_AND_RATIONALE_REQUIRED"):
        review(pg, analyst, v, "APPROVE", None, CONF_RAT)
    with pytest.raises(psycopg.Error):                       # REVIEWER lacks FINAL_CONFIDENCE_SET
        review(pg, make_user("REVIEWER"), v, "APPROVE", "LOW", CONF_RAT)
    with pytest.raises(psycopg.Error):
        review(pg, analyst, v, "REJECT", "LOW", None)        # confidence only through approval
    for conn in (pg.worker, pg.as_service_role):
        with conn() as c, pytest.raises(psycopg.Error):
            c.execute("SELECT lfhe.review_assessment(%s, %s, 'APPROVE', 'LOW', %s, 'machine approval')",
                      (str(v["id"]), v["content_hash"], CONF_RAT))
    a = review(pg, analyst, v, "APPROVE", "LOW", CONF_RAT)
    assert state(pg, v["id"]) == "APPROVED"
    with pg.admin() as x:
        row = x.execute("SELECT * FROM lfhe.assessment_version_states WHERE assessment_version_id=%s", (v["id"],)).fetchone()
        assert (row["final_analytic_confidence"], row["ai_recommended_confidence"], str(row["approved_by"])) == ("LOW", "MODERATE", str(analyst))
        assert x.execute("SELECT content_hash FROM lfhe.analytical_approvals WHERE id=%s", (a,)).fetchone()["content_hash"] == v["content_hash"]
        types = {r["event_type"] for r in x.execute("SELECT event_type FROM lfhe.audit_log WHERE object_id=%s", (str(v["id"]),))}
        assert {"ASSESSMENT_APPROVED", "FINAL_CONFIDENCE_SET"} <= types
        with pytest.raises(psycopg.Error):
            x.execute("UPDATE lfhe.analytical_approvals SET final_analytic_confidence='HIGH' WHERE id=%s", (a,))
    with pytest.raises(psycopg.Error, match="ASSESSMENT_NOT_IN_REVIEW"):     # no double approval
        review(pg, analyst, v, "APPROVE", "HIGH", CONF_RAT)


def test_reject_escalate_and_reprocessing_are_recorded_without_confidence(pg, m78, analyst):
    for decision, expected in (("REJECT", "REJECTED"), ("REQUEST_REPROCESSING", "REPROCESSING_REQUESTED"), ("ESCALATE", "ESCALATED")):
        v, _, _ = in_review(pg, analyst)
        review(pg, analyst, v, decision)
        assert state(pg, v["id"]) == expected
    review(pg, analyst, v, "APPROVE", "MODERATE", CONF_RAT)      # an escalated version may still be decided
    assert state(pg, v["id"]) == "APPROVED"


# --- 48, 49, 52, 53 --------------------------------------------------------------------------
def test_modify_and_approve_creates_new_version_and_old_one_is_unchanged(pg, m78, analyst):
    v, claims, _ = in_review(pg, analyst)
    before = snapshot(pg, v["id"])
    stmts = [st("AS1", "KNOWN_FACT", "The air force reported that 4 tanker aircraft arrived at Fort Aster.", claims=[claims[0]],
                attr=True, attr_text="The air force reported"),
             st("AS2", "ALTERNATIVE_EXPLANATION", "The arrival may be a routine transit; a spokesman denied it.",
                claims=[claims[0]], contra=[claims[1]], evidence=False, attr=False),
             st("AS3", "ANALYTIC_JUDGMENT", "Northland may be testing tanker support at Fort Aster.", claims=[claims[0]],
                premises=["AS1"], evidence=True, attr=False)]
    p = {"assessment_statements": stmts, "derived_summary": {"text": "", "source_statement_ids": []}, "indicators_to_watch": []}

    def modify(payload, h=None, conf="LOW", rat=CONF_RAT, user=analyst):
        with pg.as_user(user) as c:
            return c.execute("SELECT lfhe.modify_and_approve_assessment(%s, %s, %s::jsonb, %s, %s, 'analyst revised AS2/AS3') r",
                             (str(v["id"]), h or v["content_hash"], json.dumps(payload), conf, rat)).fetchone()["r"]
    bad = dict(p, assessment_statements=[st("AS1", "KNOWN_FACT", "4 tankers arrived at Fort Aster.", attr=False)])
    with pytest.raises(psycopg.Error, match="STATEMENT_PROVENANCE_INVALID"):
        modify(bad)
    with pytest.raises(psycopg.Error, match="VERSION_HASH_MISMATCH"):
        modify(p, h="a" * 64)
    with pytest.raises(psycopg.Error, match="FINAL_CONFIDENCE_AND_RATIONALE_REQUIRED"):
        modify(p, rat="")
    with pg.worker() as c, pytest.raises(psycopg.Error):
        c.execute("SELECT lfhe.modify_and_approve_assessment(%s, %s, %s::jsonb, 'LOW', %s, 'machine')",
                  (str(v["id"]), v["content_hash"], json.dumps(p), CONF_RAT))
    res = modify(p)
    new = res["assessment_version_id"]
    assert new != str(v["id"]) and snapshot(pg, v["id"]) == before
    assert (state(pg, v["id"]), state(pg, new)) == ("SUPERSEDED", "APPROVED")
    with pg.admin() as x:
        nv = x.execute("SELECT * FROM lfhe.assessment_versions WHERE id=%s", (new,)).fetchone()
        assert (nv["origin"], nv["version_no"], str(nv["previous_version_id"]), nv["content_hash"]) == \
            ("HUMAN", 2, str(v["id"]), res["content_hash"])
        assert (str(nv["event_version_id"]), nv["event_version_hash"]) == (str(v["event_version_id"]), v["event_version_hash"])
        ap = x.execute("SELECT * FROM lfhe.analytical_approvals WHERE assessment_version_id=%s", (new,)).fetchone()
        assert (ap["decision"], str(ap["modified_from_version_id"]), ap["final_analytic_confidence"]) == \
            ("MODIFY_AND_APPROVE", str(v["id"]), "LOW")
        assert x.execute("SELECT statement_text FROM lfhe.assessment_statements WHERE assessment_version_id=%s AND "
                         "statement_local_id='AS3'", (new,)).fetchone()["statement_text"].startswith("Northland may be testing")
        assert x.execute("SELECT count(*) n FROM lfhe.audit_log WHERE event_type='ASSESSMENT_MODIFIED' AND object_id=%s",
                         (new,)).fetchone()["n"] == 1
    with pytest.raises(psycopg.Error, match="REVIEW_STALE"):
        review(pg, analyst, v, "APPROVE", "LOW", CONF_RAT)


def test_later_approved_version_supersedes_without_deleting_and_previous_is_asof(pg, m78, analyst):
    v1, claims, (e, vid, vh) = in_review(pg, analyst)
    review(pg, analyst, v1, "APPROVE", "LOW", CONF_RAT)
    seen = {}

    def responder(m, env):
        seen["ctx"] = [c["object_type"] for c in env["context"]]
        return out(env, claims=claims)
    r = assess(pg, vid, vh, responder, previous_assessment_version_id=str(v1["id"]))
    assert r.outcome == "ASSESSMENT_RECORDED", r
    assert "assessment_version" in seen["ctx"]
    v2 = version_of(pg, r.final_run_id)
    assert (v2["assessment_id"], v2["version_no"]) == (v1["assessment_id"], 2)
    assert state(pg, v1["id"]) == "APPROVED"                    # a draft does not supersede
    assert challenge(pg, v2, lambda m, env: chal(env)).outcome == "CHALLENGE_RECORDED"
    review(pg, analyst, v2, "APPROVE", "MODERATE", CONF_RAT)
    assert (state(pg, v1["id"]), state(pg, v2["id"])) == ("SUPERSEDED", "APPROVED")
    with pg.admin() as x:
        assert x.execute("SELECT count(*) n FROM lfhe.analytical_approvals WHERE assessment_version_id IN (%s,%s)",
                         (v1["id"], v2["id"])).fetchone()["n"] == 2
        assert x.execute("SELECT count(*) n FROM lfhe.assessment_versions WHERE assessment_id=%s",
                         (v1["assessment_id"],)).fetchone()["n"] == 2
    with pg.worker() as w:
        q = "SELECT lfhe.assessment_version_approved_asof(%s, 'LIVE', %s) r"
        assert w.execute(q, (v2["id"], NOW())).fetchone()["r"] is True
        assert w.execute(q, (v1["id"], NOW())).fetchone()["r"] is False     # superseded by a knowable later approval
    # an unapproved draft can never be supplied as the previous assessment
    v3, _, (_, vid3, vh3) = draft(pg, analyst)
    with pytest.raises(InputBuildError, match="PREVIOUS_ASSESSMENT_INELIGIBLE"):
        assess(pg, vid3, vh3, lambda m, env: out(env, claims=claims), previous_assessment_version_id=str(v3["id"]))
    with pytest.raises(InputBuildError, match="PREVIOUS_ASSESSMENT_INELIGIBLE"):          # superseded is not as-of approved
        assess(pg, vid, vh, lambda m, env: out(env, claims=claims), previous_assessment_version_id=str(v1["id"]))
