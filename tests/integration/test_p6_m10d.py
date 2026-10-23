"""P6-02 — M10-D deterministic QA engine (Phase 6 Addendum §8, §26; acceptance behaviours 1–18).

Corrupted states that the Phase 5 write path can never produce are created through the owner-only
internal writer (p6_helpers.write_version_unvalidated) or owner-level tampering, to prove that M10-D
fails closed on them. Synthetic material only."""
import json
from datetime import datetime, timezone

import psycopg
import pytest

from lfhe_orchestrator.providers import FakeProvider
from lfhe_orchestrator.qa_pipeline import run_m10d
from m10s_auditor import auditor
from p4_support import approve, create_baseline, create_rc, pclaim
from p5_helpers import CONF_RAT, new_report, run_m09, select
from p6_helpers import (activate, codes, drafted, findings, first_statement, park_jobs, qa, request_qa, run_qa,
                        write_version_unvalidated)
from pipeline_support import model_configuration

pytestmark = pytest.mark.db
EARLY = datetime(2026, 1, 20, tzinfo=timezone.utc)            # after PRE evidence, before KNOW context


@pytest.fixture(scope="module")
def p6(pg):
    yield activate(pg)
    park_jobs(pg)


@pytest.fixture
def analyst(make_user):
    return make_user("ANALYST")


def d_codes(pg, q):
    return codes(pg, q.deterministic_qa_run_id)


def mutated(pg, analyst, d, fn):
    return write_version_unvalidated(pg, d.rv, fn, user=analyst)


# --- 1, 2, 3, 18 --------------------------------------------------------------------------------
def test_m10d_binds_exact_version_rejects_wrong_hash_and_missing_objects_and_uses_no_model(pg, p6, analyst):
    d = drafted(pg, analyst, "RPT-P6D-1")
    with pg.admin() as x:
        runs_before = x.execute("SELECT count(*) n FROM lfhe.model_runs").fetchone()["n"]
    req = request_qa(pg, analyst, d.rv)
    with pg.worker() as w:
        r = run_m10d(w, str(d.rv["id"]), d.rv["report_version_hash"], req)                              # 1
        with pytest.raises(psycopg.Error, match="VERSION_HASH_MISMATCH"):
            run_m10d(w, str(d.rv["id"]), "0" * 64, req)                                                  # 2
        with pytest.raises(psycopg.Error, match="REPORT_VERSION_NOT_FOUND"):
            run_m10d(w, "00000000-0000-4000-8000-000000000001", d.rv["report_version_hash"], req)        # 3
        with pytest.raises(psycopg.Error, match="QA_REQUEST_NOT_FOR_VERSION"):
            run_m10d(w, str(d.rv["id"]), d.rv["report_version_hash"], "00000000-0000-4000-8000-000000000002")
    with pytest.raises(psycopg.Error, match="VERSION_HASH_MISMATCH"):
        with pg.as_user(analyst) as h:
            h.execute("SELECT lfhe.request_report_qa(%s, %s, 'analyst submits for QA')", (str(d.rv["id"]), "f" * 64))
    with pg.admin() as x:
        run = x.execute("SELECT * FROM lfhe.qa_runs WHERE id=%s", (r["qa_run_id"],)).fetchone()
        assert (str(run["report_version_id"]), run["report_version_hash"], run["kind"], run["status"]) == \
            (str(d.rv["id"]), d.rv["report_version_hash"], "D", "COMPLETED")
        assert run["model_run_id"] is None and run["prompt_version_id"] is None and run["engine_version"] == "lfhe-m10d/1.0.0"
        assert x.execute("SELECT count(*) n FROM lfhe.model_runs").fetchone()["n"] == runs_before      # 18
        with pytest.raises(psycopg.Error):                                                               # FK binding
            x.execute("INSERT INTO lfhe.qa_runs (report_id, report_version_id, report_version_hash, qa_request_id, kind, status, "
                      "engine_version) VALUES (%s, %s, %s, %s, 'D', 'COMPLETED', 'x')",
                      (d.rid, str(d.rv["id"]), "0" * 64, req))
    rows = findings(pg, r["qa_run_id"])
    assert r["critical"] == 0 and r["fail"] == 0 and r["warning"] == 0
    with pg.admin() as x:
        d_checks = {c["check_id"] for c in x.execute("SELECT check_id FROM lfhe.qa_checks WHERE layer='D'")}
    assert {f["check_id"] for f in rows} == d_checks and all(f["status"] == "PASS" for f in rows)      # full coverage visible
    assert all(set(f) >= {"check_id", "status", "severity", "affected_object_id", "affected_statement_id", "details",
                          "evidence_refs", "recommended_action"} for f in rows)


# --- 4, 7, 8, 15, 16, 17 ------------------------------------------------------------------------
def test_m10d_fails_closed_on_corrupted_content(pg, p6, analyst, make_user):
    d = drafted(pg, analyst, "RPT-P6D-2")

    def no_mapping(c):
        return c                                                    # + an unmapped statement row inserted below

    def conf(c):
        first_statement(c)["final_analytic_confidence"] = "HIGH"                     # approved: LOW
        return c

    def lik(c):
        for s in c["key_judgments"][0]["statements"]:
            if s["likelihood_term"]:
                s["likelihood_term"] = "ALMOST_CERTAIN" if s["likelihood_term"] != "ALMOST_CERTAIN" else "REMOTE_CHANCE"
                return c
        first_statement(c)["likelihood_term"] = "LIKELY"
        return c

    def four_kjs(c):
        base = c["key_judgments"][0]
        c["key_judgments"] = [dict(base, item_local_id=f"K{i}", statements=[
            dict(s, report_statement_local_id=f"RS{i}{n}") for n, s in enumerate(base["statements"], 1)]) for i in range(1, 5)]
        return c

    def indep(c):
        s = first_statement(c)
        s["text"] = s["text"].rstrip(".") + ", independently confirmed by multiple sources."
        return c

    def marking(c):
        s = first_statement(c)
        s["text"] = "NATO SECRET " + s["text"]
        return c

    expected = {no_mapping: ("QA-01", "MISSING_REQUIRED_PROVENANCE"),                               # 4
                conf: ("QA-08", "UNAUTHORISED_CONFIDENCE_CHANGE"),                                   # 7
                lik: ("QA-08", "UNAUTHORISED_LIKELIHOOD_CHANGE"),                                    # 8
                four_kjs: ("STRUCTURE", "REPORT_STRUCTURE_INVALID"),                                 # 15
                indep: ("QA-05", "FALSE_INDEPENDENT_CONFIRMATION"),                                  # 16
                marking: ("QA-14", "PROHIBITED_INFORMATION")}                                        # 17
    for fn, code in expected.items():
        bad = mutated(pg, analyst, d, fn)
        if fn is no_mapping:
            with pg.admin() as x:
                x.execute("""INSERT INTO lfhe.report_item_statements (report_item_id, statement_no, report_statement_local_id,
                               statement_role, statement_text, editorial_transform, contested, author_type, user_id)
                             SELECT i.id, 99, 'RS99', 'KEY_JUDGMENT', 'Unmapped sentence.', 'PARAPHRASE', false, 'HUMAN', %s
                             FROM lfhe.report_items i WHERE i.report_version_id = %s LIMIT 1""", (str(analyst), str(bad["id"])))
        q = qa(pg, analyst, bad)
        assert code in d_codes(pg, q), (fn.__name__, d_codes(pg, q))
        assert q.status == "FAIL", fn.__name__
        crit = [f for f in findings(pg, q.deterministic_qa_run_id) if (f["check_id"], f["finding_code"]) == code]
        assert all(f["status"] == "FAIL" and f["sev"] == "CRITICAL" for f in crit)
    # 17: the OSINT-boundary failure blocks release eligibility
    with pg.as_user(make_user("RELEASE_AUTHORITY")) as h:
        el = h.execute("SELECT lfhe.release_eligibility(%s, %s, NULL) r", (str(bad["id"]), bad["report_version_hash"])).fetchone()["r"]
    assert el["eligible"] is False and "QA_ACCEPTABLE" in el["failed"] and "NO_CRITICAL_FINDING" in el["failed"]


# --- 5, 12, 13 ----------------------------------------------------------------------------------
def test_m10d_post_cutoff_evidence_baseline_and_reference_context(pg, p6, analyst):
    from test_p4_assessments import assess, default_statements, out as m07_out, setup_event, st, version_of
    from test_p4_challenge_review import chal, challenge, review
    e, vid, vh, claims = setup_event(pg, analyst)
    prior = pclaim(pg, "The air force said 2 tanker aircraft were based at Fort Aster.", "2 tanker aircraft were based at Fort Aster")
    bl = create_baseline(pg, analyst, "BL-P6D-1", [("2 tankers at Fort Aster", [("claim", prior["claim_id"])])])
    approve(pg, analyst, "baseline", bl)
    rc = create_rc(pg, analyst, "RC-P6D-1", [prior], text="Fort Aster is Northland's main tanker base.")
    approve(pg, analyst, "rc", rc)
    stmts = default_statements(claims) + [
        st("AS6", "KNOWN_FACT", "Per reference context, Fort Aster is Northland's main tanker base.", prov="APPROVED_REFERENCE_CONTEXT",
           rcs=[rc], attr_text="Per reference context")]
    r = assess(pg, vid, vh, lambda m, env: m07_out(env, json.loads(json.dumps(stmts))), baseline_code="BL-P6D-1",
               reference_context_codes=["RC-P6D-1"])
    assert r.outcome == "ASSESSMENT_RECORDED", r
    av = version_of(pg, r.final_run_id)
    challenge(pg, av, lambda m, env: chal(env))
    review(pg, analyst, av, "APPROVE", "LOW", CONF_RAT)
    d = drafted(pg, analyst, "RPT-P6D-3", assessment=(av, claims, (e, vid, vh)))
    ok = qa(pg, analyst, d.rv)
    assert ok.status == "PASS", (d_codes(pg, ok), ok.fail_reasons)
    # the same content in a REPLAY report whose cutoff precedes the baseline / context knowledge_as_of
    early = new_report(pg, analyst, "RPT-P6D-3E", mode="REPLAY", cutoff=EARLY)
    bad = write_version_unvalidated(pg, d.rv, lambda c: c, user=analyst, report_id=early)
    q = qa(pg, analyst, bad)
    got = d_codes(pg, q)
    assert ("QA-04", "POST_CUTOFF_EVIDENCE") in got                                                    # 5
    assert ("D21", "POST_CUTOFF_EVIDENCE") in got                                                      # 12
    assert ("D22", "POST_CUTOFF_EVIDENCE") in got                                                      # 13
    assert ("QA-17", "POST_CUTOFF_EVIDENCE") in got and q.status == "FAIL"


# --- 6, 9, 10, 11, 14 ---------------------------------------------------------------------------
def test_m10d_unapproved_unpinned_untraceable_ungrounded_and_unvalidated(pg, p6, analyst, make_user):
    from test_p4_assessments import assess, out as m07_out, version_of
    from test_p4_challenge_review import chal, challenge, review
    # 6: a later approved version of the same assessment supersedes the cited one as of the cutoff
    d = drafted(pg, analyst, "RPT-P6D-4")
    e, vid, vh = d.event
    r2 = assess(pg, vid, vh, lambda m, env: m07_out(env, claims=d.claims), previous_assessment_version_id=str(d.av["id"]))
    v2 = version_of(pg, r2.final_run_id)
    challenge(pg, v2, lambda m, env: chal(env))
    review(pg, analyst, v2, "APPROVE", "MODERATE", CONF_RAT)
    q = qa(pg, analyst, d.rv)
    assert ("QA-10", "UNAPPROVED_ASSESSMENT") in d_codes(pg, q) and q.status == "FAIL"

    # 9: an item whose candidate is not in the pinned selection set
    d9 = drafted(pg, analyst, "RPT-P6D-5")
    other = drafted(pg, analyst, "RPT-P6D-5B")
    with pg.admin() as x:
        x.execute("""INSERT INTO lfhe.report_items (report_version_id, section, item_no, item_local_id, source_candidate_id,
                       pinned_assessment_version_id, pinned_assessment_version_hash)
                     SELECT %s, 'SIGNIFICANT_DEVELOPMENT', 9, 'ROGUE', i.source_candidate_id, i.pinned_assessment_version_id,
                            i.pinned_assessment_version_hash FROM lfhe.report_items i WHERE i.report_version_id = %s LIMIT 1""",
                  (str(d9.rv["id"]), str(other.rv["id"])))
    q9 = qa(pg, analyst, d9.rv)
    assert ("QA-11", "UNPINNED_REQUIRED_VERSION") in d_codes(pg, q9) and q9.status == "FAIL"

    # 10: a MODEL version whose authoring run did not succeed
    d10 = drafted(pg, analyst, "RPT-P6D-6")
    sid, sh = d10.rv["selection_set_id"], d10.rv["selection_set_hash"]
    bad_run = run_m09(pg, str(sid), sh, lambda m, env: "not json")
    with pg.admin() as x:
        content = x.execute("SELECT lfhe.report_version_content(%s) c", (str(d10.rv["id"]),)).fetchone()["c"]
        vid10 = x.execute("SELECT lfhe.p5_write_report_version(%s, %s, %s::jsonb, '{}', 'WITHIN_LIMIT', 'MODEL', %s, NULL, '[]') i",
                          (d10.rid, str(sid), json.dumps(content), bad_run.final_run_id)).fetchone()["i"]
        v10 = x.execute("SELECT * FROM lfhe.report_versions WHERE id=%s", (vid10,)).fetchone()
    q10 = qa(pg, analyst, v10)
    assert ("QA-12", "MISSING_REQUIRED_PROVENANCE") in d_codes(pg, q10) and q10.status == "FAIL"

    # 11: original-language grounding no longer verifies (simulated storage tampering by the owner)
    d11 = drafted(pg, analyst, "RPT-P6D-7")
    cid = d11.claims[0]["claim_id"]
    with pg.admin(autocommit=False) as x:
        x.execute("SET LOCAL session_replication_role = replica")
        x.execute("""UPDATE lfhe.claims SET span_exact_text = span_exact_text || ' (altered)',
                       evidence_span_original = jsonb_set(evidence_span_original, '{exact_text}',
                                                          to_jsonb(span_exact_text || ' (altered)')) WHERE id = %s""", (cid,))
        x.commit()
    q11 = qa(pg, analyst, d11.rv)
    assert ("D18", "MISSING_REQUIRED_PROVENANCE") in d_codes(pg, q11) and q11.status == "FAIL"

    # 14: a cited claim becomes high-impact; its human validation is missing
    d14 = drafted(pg, analyst, "RPT-P6D-8")
    with pg.as_user(analyst) as h:
        h.execute("SELECT lfhe.mark_claim_high_impact(%s, true, '{}', 'analyst marks the arrival as high impact')",
                  (d14.claims[0]["claim_id"],))
    q14 = qa(pg, analyst, d14.rv)
    assert ("D20", "HIGH_IMPACT_VALIDATION_MISSING") in d_codes(pg, q14) and q14.status == "FAIL"


def test_m10d_stale_version_and_semantic_run_cannot_rescue_a_deterministic_failure(pg, p6, analyst):
    d = drafted(pg, analyst, "RPT-P6D-9")
    req = request_qa(pg, analyst, d.rv)
    newer = write_version_unvalidated(pg, d.rv, lambda c: c, user=analyst)                  # d.rv is now stale
    q = run_qa(pg, d.rv, req, auditor(findings=[]))
    assert ("D23", "VERSION_NOT_CURRENT") in d_codes(pg, q) and q.status == "FAIL"
    with pytest.raises(psycopg.Error, match="REPORT_VERSION_STALE"):
        request_qa(pg, analyst, d.rv)
    assert newer["version_no"] == d.rv["version_no"] + 1
    assert FakeProvider and model_configuration
