"""Phase 6 test support: drafted report versions (real Phase 4/5 chain), QA via the real M10-D
engine + M10 bundle with the rule-based M10-S stand-in, human approvals, release PDF (real headless
Chromium) and release. All material is synthetic ('Northland'); nothing here is benchmark material."""
from __future__ import annotations

import json
from dataclasses import dataclass

from lfhe_orchestrator.providers import FakeProvider
from lfhe_orchestrator.qa_pipeline import run_report_qa
from lfhe_orchestrator.report_pdf import render_release_pdf
from lfhe_orchestrator.report_render import render_and_record
from lfhe_shared.storage import LocalObjectStore
from m10s_auditor import auditor
from p5_helpers import P5_MODULES, approved_assessment, m09, new_report, run_m09, select, version_of_run
from pipeline_support import activate_real_prompts, model_configuration

P6_MODULES = P5_MODULES + ("M10_QA_AUDITOR",)
P6_JOB_TYPES = ("EDIT_REPORT", "RENDER_REPORT", "RUN_REPORT_QA", "RENDER_RELEASE_PDF")
RAT = "reviewed the exact version and its QA findings"


def activate(pg):
    return activate_real_prompts(pg, P6_MODULES)


def park_jobs(pg):
    with pg.admin() as x:
        x.execute("UPDATE lfhe.processing_jobs SET status='SKIPPED' WHERE status='PENDING' AND job_type = ANY(%s)",
                  (list(P6_JOB_TYPES),))


@dataclass
class Drafted:
    rv: dict
    rid: str
    av: dict
    claims: list
    event: tuple


def drafted(pg, analyst, code, *, responder=None, render=True, assessment=None, **kw) -> Drafted:
    """Approved assessment → report → selection → M09 draft (+ preview render)."""
    v, claims, ev = assessment or approved_assessment(pg, analyst, **kw)
    rid = new_report(pg, analyst, code)
    sid, sh = select(pg, analyst, rid, [(v["id"], "KEY_JUDGMENT", 1)])
    r = run_m09(pg, sid, sh, responder or (lambda m, env: m09(env)))
    assert r.outcome == "REPORT_VERSION_RECORDED", r
    rv = version_of_run(pg, r.final_run_id)
    if render:
        with pg.worker() as w:
            render_and_record(w, str(rv["id"]), rv["report_version_hash"], worker_id="p6-test")
    return Drafted(rv, rid, v, claims, ev)


def request_qa(pg, user, rv, reason="analyst submits the draft for QA"):
    with pg.as_user(user) as h:
        return h.execute("SELECT lfhe.request_report_qa(%s, %s, %s) r", (str(rv["id"]), rv["report_version_hash"], reason)
                         ).fetchone()["r"]["qa_request_id"]


def run_qa(pg, rv, request_id, responder=None):
    with pg.worker() as w:
        return run_report_qa(w, str(rv["id"]), rv["report_version_hash"], str(request_id),
                             model_configuration_id=model_configuration(pg), provider=FakeProvider(responder or auditor()),
                             worker_id="p6-test")


def qa(pg, user, rv, responder=None):
    return run_qa(pg, rv, request_qa(pg, user, rv), responder)


def findings(pg, run_id, *, status=None):
    with pg.admin() as x:
        q = "SELECT *, severity::text AS sev FROM lfhe.qa_check_results WHERE qa_run_id=%s" + (" AND status=%s" if status else "")
        return x.execute(q + " ORDER BY finding_no", (str(run_id), status) if status else (str(run_id),)).fetchall()


def codes(pg, run_id):
    return {(f["check_id"], f["finding_code"]) for f in findings(pg, run_id) if f["status"] != "PASS"}


def acknowledge(pg, user, rv, qa_result, finding, rationale="warning reviewed against the evidence; acceptable"):
    with pg.as_user(user) as h:
        return h.execute("SELECT lfhe.acknowledge_qa_warning(%s, %s, %s, %s, %s) r",
                         (str(rv["id"]), rv["report_version_hash"], str(qa_result), str(finding), rationale)).fetchone()["r"]


def content(pg, user, rv, qa_result, decision="APPROVE", rationale=RAT):
    with pg.as_user(user) as h:
        return h.execute("SELECT lfhe.decide_report_content(%s, %s, %s, %s, %s) r",
                         (str(rv["id"]), rv["report_version_hash"], str(qa_result), decision, rationale)).fetchone()["r"]


def security(pg, user, rv, review, status="APPROVED", rationale="handling reviewed: OSINT-only, releasable"):
    with pg.as_user(user) as h:
        return h.execute("SELECT lfhe.decide_security_review(%s, %s, %s, %s, %s) r",
                         (str(rv["id"]), rv["report_version_hash"], str(review), status, rationale)).fetchone()["r"]


def store(tmp_path):
    return LocalObjectStore(tmp_path / "objects")


def make_pdf(pg, rv, objstore):
    with pg.worker() as w:
        return render_release_pdf(w, str(rv["id"]), rv["report_version_hash"], store=objstore, worker_id="p6-test")


def release(pg, user, rv, pdf_id, rationale="all release conditions verified; release approved"):
    with pg.as_user(user) as h:
        return h.execute("SELECT lfhe.release_report(%s, %s, %s, %s) r",
                         (str(rv["id"]), rv["report_version_hash"], str(pdf_id), rationale)).fetchone()["r"]


def eligibility(pg, user, rv, pdf_id=None):
    with pg.as_user(user) as h:
        return h.execute("SELECT lfhe.release_eligibility(%s, %s, %s) r",
                         (str(rv["id"]), rv["report_version_hash"], str(pdf_id) if pdf_id else None)).fetchone()["r"]


def workflow(pg, rv):
    with pg.admin() as x:
        return x.execute("SELECT * FROM lfhe.report_version_workflow WHERE report_version_id=%s", (str(rv["id"]),)).fetchone()


def write_version_unvalidated(pg, rv, content_mutator, *, user, report_id=None):
    """TEST-ONLY corrupted state: write a new version through the owner-only internal writer,
    bypassing the Phase 5 validator (no application role can do this). Used to prove that M10
    fails closed on content that should never have existed."""
    with pg.admin() as x:
        c = x.execute("SELECT lfhe.report_version_content(%s) c", (str(rv["id"]),)).fetchone()["c"]
        c = content_mutator(json.loads(json.dumps(c)))
        removed = [str(r) for r in rv["canonical_json"].get("human_removals") or []]
        vid = x.execute("SELECT lfhe.p5_write_report_version(%s, %s, %s::jsonb, %s::uuid[], 'WITHIN_LIMIT', 'HUMAN', NULL, %s, '[]') id",
                        (str(report_id or rv["report_id"]), str(rv["selection_set_id"]), json.dumps(c), removed, str(user))
                        ).fetchone()["id"]
        new = x.execute("SELECT * FROM lfhe.report_versions WHERE id=%s", (vid,)).fetchone()
    with pg.worker() as w:
        render_and_record(w, str(new["id"]), new["report_version_hash"], worker_id="p6-test")
    return new


def first_statement(content_obj, section="key_judgments"):
    return content_obj[section][0]["statements"][0]


def through_security(pg, analyst, reviewer, secrev, code, **kw):
    """Draft → QA PASS → content APPROVE → security APPROVED. Returns (drafted, qa_outcome, content_res, security_res)."""
    d = drafted(pg, analyst, code, **kw)
    rv = d.rv
    q = qa(pg, analyst, rv)
    assert q.status == "PASS", (q.status, q.fail_reasons, codes(pg, q.deterministic_qa_run_id), codes(pg, q.semantic_qa_run_id))
    c = content(pg, reviewer, rv, q.qa_result_id)
    s = security(pg, secrev, rv, c["security_review_id"])
    return d, q, c, s


__all__ = ["Drafted", "P6_MODULES", "RAT", "acknowledge", "activate", "codes", "content", "drafted", "eligibility", "findings",
           "first_statement", "make_pdf", "park_jobs", "qa", "release", "request_qa", "run_qa", "security", "store",
           "through_security", "workflow", "write_version_unvalidated"]
