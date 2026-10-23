"""P6-04 / P6-05 — combined QA, warning acknowledgement, human content approval, human security review
(Phase 6 Addendum §13, §14, §16–§18, §29; acceptance behaviours 38–56)."""
import psycopg
import pytest

from m10s_auditor import _f, audit_output
from p5_helpers import content_of, edit
from p6_helpers import (acknowledge, activate, codes, content, drafted, eligibility, findings, park_jobs, qa, security,
                        workflow, write_version_unvalidated)

pytestmark = pytest.mark.db
IP = psycopg.errors.InsufficientPrivilege


@pytest.fixture(scope="module")
def p6(pg):
    yield activate(pg)
    park_jobs(pg)


@pytest.fixture
def people(make_user):
    return {r: make_user(r) for r in ("ANALYST", "REVIEWER", "SECURITY_REVIEWER", "RELEASE_AUTHORITY", "ADMIN", "VIEWER")}


def dup_items(c):
    it = c["key_judgments"][0]
    c["key_judgments"].append(dict(it, item_local_id="KJDUP", statements=[
        dict(s, report_statement_local_id=f"RS{60 + n}") for n, s in enumerate(it["statements"])]))
    return c


def audit_rows(pg, event, version_id):
    with pg.admin() as x:
        return x.execute("SELECT * FROM lfhe.audit_log WHERE event_type=%s AND object_id=%s ORDER BY seq",
                         (event, str(version_id))).fetchall()


# --- 38, 39, 40, 42, 43, 44, 45, 46, 47, 50 ------------------------------------------------------
def test_combined_status_warning_acknowledgement_and_reruns(pg, p6, people):
    a, rev = people["ANALYST"], people["REVIEWER"]
    d = drafted(pg, a, "RPT-P6A-1")
    clean = qa(pg, a, d.rv)
    assert clean.status == "PASS"                                                                      # 38
    warn_v = write_version_unvalidated(pg, d.rv, dup_items, user=a)
    q1 = qa(pg, a, warn_v)
    assert q1.status == "PASS_WITH_WARNINGS"                                                           # 39
    warnings = [f for run in (q1.deterministic_qa_run_id, q1.semantic_qa_run_id) for f in findings(pg, run, status="WARNING")]
    assert warnings and all(f["sev"] in ("WARNING", "MAJOR") for f in warnings)
    with pg.admin() as x:
        res = x.execute("SELECT * FROM lfhe.qa_results WHERE id=%s", (q1.qa_result_id,)).fetchone()
    assert sorted(map(str, res["warning_finding_ids"])) == sorted(str(f["id"]) for f in warnings) and not res["release_blocked"]
    # 50: PASS_WITH_WARNINGS cannot be content-approved before every warning is acknowledged
    with pytest.raises(psycopg.Error, match="WARNINGS_NOT_ACKNOWLEDGED"):
        content(pg, rev, warn_v, q1.qa_result_id)
    # 42: only REVIEWER (QA_WARNING_ACKNOWLEDGE) acknowledges
    for role in ("ANALYST", "SECURITY_REVIEWER", "RELEASE_AUTHORITY", "ADMIN", "VIEWER"):
        with pytest.raises(IP):
            acknowledge(pg, people[role], warn_v, q1.qa_result_id, warnings[0]["id"])
    for conn in (pg.worker, pg.as_service_role, pg.as_anon):
        with conn() as c, pytest.raises(IP):
            c.execute("SELECT lfhe.acknowledge_qa_warning(%s, %s, %s, %s, 'automated acknowledgement attempt')",
                      (str(warn_v["id"]), warn_v["report_version_hash"], q1.qa_result_id, str(warnings[0]["id"])))
    # 43: bound to the exact version / hash / result / finding
    with pytest.raises(psycopg.Error, match="VERSION_HASH_MISMATCH"):
        acknowledge(pg, rev, dict(warn_v, report_version_hash="0" * 64), q1.qa_result_id, warnings[0]["id"])
    clean_finding = findings(pg, clean.deterministic_qa_run_id)[0]
    with pytest.raises(psycopg.Error, match="FINDING_NOT_IN_QA_RESULT"):
        acknowledge(pg, rev, warn_v, q1.qa_result_id, clean_finding["id"])
    ack_ids = [acknowledge(pg, rev, warn_v, q1.qa_result_id, f["id"]) for f in warnings]
    with pytest.raises(psycopg.Error, match="WARNING_ALREADY_ACKNOWLEDGED"):
        acknowledge(pg, rev, warn_v, q1.qa_result_id, warnings[0]["id"])
    with pg.admin() as x:
        rows = x.execute("SELECT * FROM lfhe.warning_acknowledgements WHERE id = ANY(%s::uuid[])", (ack_ids,)).fetchall()
        assert all((str(r["report_version_id"]), r["report_version_hash"], str(r["qa_result_id"])) ==
                   (str(warn_v["id"]), warn_v["report_version_hash"], q1.qa_result_id) for r in rows)
        with pytest.raises(psycopg.Error):                        # composite FK: an acknowledgement cannot point at another version
            x.execute("INSERT INTO lfhe.warning_acknowledgements (qa_result_id, qa_check_result_id, report_version_id, "
                      "report_version_hash, acknowledged_by, rationale) VALUES (%s, %s, %s, %s, %s, 'forged acknowledgement')",
                      (q1.qa_result_id, str(warnings[0]["id"]), str(d.rv["id"]), d.rv["report_version_hash"], str(rev)))
    assert workflow(pg, warn_v)["workflow_state"] == "WARNING_ACKNOWLEDGED"
    # 45 / 46: a rerun creates a new authoritative result; earlier acknowledgements do not carry over
    q2 = qa(pg, a, warn_v)
    assert q2.status == "PASS_WITH_WARNINGS" and q2.qa_result_id != q1.qa_result_id
    with pytest.raises(psycopg.Error, match="QA_RESULT_STALE"):
        content(pg, rev, warn_v, q1.qa_result_id)
    with pytest.raises(psycopg.Error, match="WARNINGS_NOT_ACKNOWLEDGED"):
        content(pg, rev, warn_v, q2.qa_result_id)
    with pytest.raises(psycopg.Error, match="QA_RESULT_STALE"):
        acknowledge(pg, rev, warn_v, q1.qa_result_id, warnings[0]["id"])
    with pg.admin() as x:
        assert x.execute("SELECT count(*) n FROM lfhe.qa_results WHERE report_version_id=%s", (str(warn_v["id"]),)).fetchone()["n"] == 2
        assert x.execute("SELECT count(*) n FROM lfhe.qa_runs WHERE report_version_id=%s", (str(warn_v["id"]),)).fetchone()["n"] == 4
    # 47: a rerun that changes the authoritative status is audited
    q3 = qa(pg, a, warn_v, lambda m, env: audit_output(env, extra=[_f("QA-01", "FAIL", "CRITICAL", "UNSUPPORTED_FACT",
                                                                    "scripted semantic failure")]))
    assert q3.status == "FAIL"                                                                         # 40
    changed = audit_rows(pg, "QA_RESULT_CHANGED_BY_RERUN", warn_v["id"])
    assert changed and changed[-1]["new_state"]["status"] == "FAIL" and changed[-1]["previous_state"]["status"] == "PASS_WITH_WARNINGS"
    # 44: a FAIL / CRITICAL finding can never be acknowledged into eligibility
    crit = [f for f in findings(pg, q3.semantic_qa_run_id) if f["sev"] == "CRITICAL"][0]
    with pytest.raises(psycopg.Error, match="NOT_ACKNOWLEDGEABLE"):
        acknowledge(pg, rev, warn_v, q3.qa_result_id, crit["id"])
    assert eligibility(pg, people["RELEASE_AUTHORITY"], warn_v)["eligible"] is False


# --- 48, 49, 51, 52, 53, 54, 55 ------------------------------------------------------------------
def test_content_approval_and_security_review_are_human_role_bound_and_ordered(pg, p6, people):
    a, rev, sec = people["ANALYST"], people["REVIEWER"], people["SECURITY_REVIEWER"]
    d = drafted(pg, a, "RPT-P6A-2")
    bad = write_version_unvalidated(pg, d.rv, lambda c: (c["key_judgments"][0]["statements"][0].__setitem__(
        "final_analytic_confidence", "HIGH"), c)[1], user=a)
    qf = qa(pg, a, bad)
    assert qf.status == "FAIL"
    with pytest.raises(psycopg.Error, match="CONTENT_APPROVAL_QA_FAILED"):                             # 48
        content(pg, rev, bad, qf.qa_result_id)
    good = write_version_unvalidated(pg, d.rv, lambda c: c, user=a)
    q = qa(pg, a, good)
    assert q.status == "PASS"
    with pg.admin() as x:
        assert x.execute("SELECT count(*) n FROM lfhe.security_reviews WHERE report_version_id=%s",
                         (str(good["id"]),)).fetchone()["n"] == 0                                       # 53: nothing to review yet
    for role in ("ANALYST", "ADMIN", "SECURITY_REVIEWER", "RELEASE_AUTHORITY", "VIEWER"):              # 51, 52
        with pytest.raises(IP):
            content(pg, people[role], good, q.qa_result_id)
    for conn in (pg.worker, pg.as_service_role, pg.as_anon):
        with conn() as c, pytest.raises(IP):
            c.execute("SELECT lfhe.decide_report_content(%s, %s, %s, 'APPROVE', 'automated approval attempt')",
                      (str(good["id"]), good["report_version_hash"], q.qa_result_id))
    with pytest.raises(psycopg.Error, match="SECURITY_REVIEW_NOT_PENDING_FOR_VERSION"):               # 53
        security(pg, sec, good, "00000000-0000-4000-8000-000000000003")
    c = content(pg, rev, good, q.qa_result_id)                                                         # 49
    assert c["decision"] == "APPROVE" and c["security_review_id"]
    with pytest.raises(psycopg.Error, match="CONTENT_ALREADY_DECIDED"):
        content(pg, rev, good, q.qa_result_id, "REJECT")
    assert workflow(pg, good)["workflow_state"] == "SECURITY_REVIEW_PENDING"
    for role in ("ANALYST", "REVIEWER", "RELEASE_AUTHORITY", "ADMIN", "VIEWER"):                       # 55
        with pytest.raises(IP):
            security(pg, people[role], good, c["security_review_id"])
    for conn in (pg.worker, pg.as_service_role, pg.as_anon):
        with conn() as cc, pytest.raises(IP):
            cc.execute("SELECT lfhe.decide_security_review(%s, %s, %s, 'APPROVED', 'automated approval attempt')",
                       (str(good["id"]), good["report_version_hash"], c["security_review_id"]))
    with pg.as_user(sec) as h, pytest.raises(psycopg.Error):
        h.execute("INSERT INTO lfhe.security_reviews (report_id, report_version_id, report_version_hash, content_approval_id, "
                  "status, reviewer_user_id, rationale) VALUES (%s, %s, %s, %s, 'APPROVED', %s, 'direct write attempt')",
                  (d.rid, str(good["id"]), good["report_version_hash"], c["content_approval_id"], str(sec)))
    s = security(pg, sec, good, c["security_review_id"])                                               # 54
    assert s["status"] == "APPROVED" and s["release_pdf_job_id"]
    with pytest.raises(psycopg.Error, match="SECURITY_REVIEW_NOT_PENDING_FOR_VERSION"):
        security(pg, sec, good, s["security_review_id"], "REJECTED")
    with pytest.raises(psycopg.Error, match="SECURITY_REVIEW_ALREADY_DECIDED"):
        security(pg, sec, good, c["security_review_id"], "REJECTED")
    assert workflow(pg, good)["workflow_state"] == "SECURITY_APPROVED"
    for ev in ("REPORT_CONTENT_DECIDED", "SECURITY_REVIEW_OPENED", "SECURITY_REVIEW_DECIDED"):
        rows = audit_rows(pg, ev, good["id"])
        assert rows and all(r["actor_type"] == "HUMAN" or ev == "SECURITY_REVIEW_OPENED" for r in rows)
    with pg.admin() as x:
        for t in ("content_approvals", "security_reviews"):
            with pytest.raises(psycopg.Error):
                x.execute(f"UPDATE lfhe.{t} SET rationale = 'rewritten rationale text' WHERE report_version_id=%s", (str(good["id"]),))


# --- 56: a new version makes every earlier decision inapplicable (kept, never deleted) -----------
def test_new_version_invalidates_qa_content_and_security_decisions(pg, p6, people):
    a, rev, sec = people["ANALYST"], people["REVIEWER"], people["SECURITY_REVIEWER"]
    d = drafted(pg, a, "RPT-P6A-3")
    q = qa(pg, a, d.rv)
    c = content(pg, rev, d.rv, q.qa_result_id)
    s = security(pg, sec, d.rv, c["security_review_id"])
    cc = content_of(pg, d.rv["id"])
    cc["key_judgments"][0]["statements"][-1]["text"] = cc["key_judgments"][0]["statements"][-1]["text"].rstrip(".") + " at the base."
    cc["key_judgments"][0]["statements"][-1]["editorial_transform"] = "PARAPHRASE"
    v2 = edit(pg, a, d.rv, cc, "analyst refines a sentence after QA")
    with pg.admin() as x:
        r2 = x.execute("SELECT * FROM lfhe.report_versions WHERE id=%s", (v2["report_version_id"],)).fetchone()
        kept = x.execute("SELECT (SELECT count(*) FROM lfhe.qa_results WHERE report_version_id=%(v)s) q, "
                         "(SELECT count(*) FROM lfhe.content_approvals WHERE report_version_id=%(v)s) c, "
                         "(SELECT count(*) FROM lfhe.security_reviews WHERE report_version_id=%(v)s) s", {"v": str(d.rv["id"])}).fetchone()
    assert kept == {"q": 1, "c": 1, "s": 2}                                                            # history kept
    assert workflow(pg, r2)["workflow_state"] == "DRAFT_VERSION" and workflow(pg, r2)["qa_result_id"] is None
    assert workflow(pg, d.rv)["workflow_state"] == "SUPERSEDED"
    el = eligibility(pg, people["RELEASE_AUTHORITY"], d.rv)
    assert el["eligible"] is False and "VERSION_CURRENT" in el["failed"]
    with pytest.raises(psycopg.Error, match="REPORT_VERSION_STALE"):
        content(pg, rev, d.rv, q.qa_result_id, "REJECT")
    assert audit_rows(pg, "QA_INVALIDATED_BY_REPORT_CHANGE", d.rv["id"])
    assert audit_rows(pg, "SECURITY_APPROVAL_INVALIDATED", d.rv["id"])
    q2 = qa(pg, a, r2)                                                                                 # QA starts from zero
    assert q2.status == "PASS" and codes(pg, q2.deterministic_qa_run_id) == set()
    assert s["status"] == "APPROVED"
