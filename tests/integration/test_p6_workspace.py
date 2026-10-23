"""P6-08 — the QA / release workspace reads (acceptance behaviours 86–90, 92): everything the
`/reports/[id]?view=qa|release` panels show is readable by an authorised human under RLS, comes from
the database (never recomputed client-side) and carries the exact version / hash."""
import pytest

from conftest import REPO_ROOT
from p6_helpers import activate, content, drafted, eligibility, make_pdf, park_jobs, qa, release, security, store, write_version_unvalidated

pytestmark = pytest.mark.db
WEB = REPO_ROOT / "apps" / "web"


@pytest.fixture(scope="module")
def p6(pg):
    yield activate(pg)
    park_jobs(pg)


def test_workspace_reads_qa_findings_checklist_and_released_view(pg, p6, make_user, tmp_path):
    a, rev, sec, ra, viewer = (make_user(r) for r in ("ANALYST", "REVIEWER", "SECURITY_REVIEWER", "RELEASE_AUTHORITY", "VIEWER"))
    d = drafted(pg, a, "RPT-P6W-1")
    warn = write_version_unvalidated(pg, d.rv, lambda c: (c["key_judgments"].append(dict(
        c["key_judgments"][0], item_local_id="KJDUP", statements=[dict(s, report_statement_local_id=f"RS{80 + n}")
                                                                  for n, s in enumerate(c["key_judgments"][0]["statements"])])), c)[1], user=a)
    q = qa(pg, a, warn)
    with pg.as_user(rev) as h:                                                                          # 86, 87
        wf = h.execute("SELECT * FROM lfhe.report_version_workflow WHERE report_version_id=%s", (str(warn["id"]),)).fetchone()
        res = h.execute("SELECT * FROM lfhe.qa_results WHERE id=%s", (q.qa_result_id,)).fetchone()
        fs = h.execute("SELECT * FROM lfhe.qa_check_results WHERE qa_run_id IN (%s, %s) AND status <> 'PASS'",
                       (q.deterministic_qa_run_id, q.semantic_qa_run_id)).fetchall()
        runs = h.execute("SELECT kind, status, model_run_id FROM lfhe.qa_runs WHERE id IN (%s, %s)",
                         (q.deterministic_qa_run_id, q.semantic_qa_run_id)).fetchall()
    assert wf["workflow_state"] == "QA_PASSED_WITH_WARNINGS" and wf["report_version_hash"] == warn["report_version_hash"]
    assert res["report_version_hash"] == warn["report_version_hash"] and res["status"] == "PASS_WITH_WARNINGS"
    assert fs and all(f["evidence_refs"] for f in fs if f["layer"] == "S")
    stmt_refs = {r["object_id"] for f in fs for r in f["evidence_refs"] if r["object_type"] == "report_item_statement"}
    with pg.as_user(rev) as h:
        stmts = h.execute("SELECT st.id FROM lfhe.report_item_statements st JOIN lfhe.report_items i ON i.id = st.report_item_id "
                          "WHERE i.report_version_id=%s", (str(warn["id"]),)).fetchall()
    assert stmt_refs <= {str(s["id"]) for s in stmts}                                                   # 87: provenance resolvable
    assert {r["kind"] for r in runs} == {"D", "S"}
    # 89: the checklist the UI shows is the database evaluation for that caller
    good = write_version_unvalidated(pg, d.rv, lambda c: c, user=a)
    q2 = qa(pg, a, good)
    c = content(pg, rev, good, q2.qa_result_id)
    security(pg, sec, good, c["security_review_id"])
    pdf = make_pdf(pg, good, store(tmp_path))
    for user, expected in ((ra, True), (viewer, False)):
        el = eligibility(pg, user, good, pdf["pdf_artifact_id"])
        assert el["eligible"] is expected and (expected or el["failed"] == ["CALLER_HUMAN_RELEASE_AUTHORITY"])
    r = release(pg, ra, good, pdf["pdf_artifact_id"])
    with pg.as_user(viewer) as h:                                                                       # 90: released view
        rel = h.execute("SELECT * FROM lfhe.report_releases WHERE id=%s", (r["report_release_id"],)).fetchone()
        man = h.execute("SELECT manifest_hash, manifest_json FROM lfhe.release_manifests WHERE id=%s", (r["release_manifest_id"],)).fetchone()
        art = h.execute("SELECT pdf_sha256, octet_length(pdf_bytes) n FROM lfhe.release_pdf_artifacts WHERE id=%s",
                        (pdf["pdf_artifact_id"],)).fetchone()
        wf2 = h.execute("SELECT workflow_state, manifest_hash, pdf_sha256, released_by FROM lfhe.report_version_workflow "
                        "WHERE report_version_id=%s", (str(good["id"]),)).fetchone()
    assert rel["state"] == "RELEASED" and rel["manifest_hash"] == man["manifest_hash"] == wf2["manifest_hash"]
    assert rel["pdf_sha256"] == art["pdf_sha256"] == wf2["pdf_sha256"] and art["n"] > 1000 and str(wf2["released_by"]) == str(ra)
    with pg.as_user(make_user()) as h:                                                                  # no role → nothing visible
        assert h.execute("SELECT count(*) n FROM lfhe.report_releases").fetchone()["n"] == 0


def test_workspace_code_never_touches_benchmark_material_and_calls_only_human_only_rpcs():
    import re
    files = [WEB / "app" / "reports" / "release-actions.ts", WEB / "app" / "reports" / "[id]" / "release-panels.tsx",
             WEB / "app" / "reports" / "[id]" / "pdf" / "[artifact]" / "route.ts", WEB / "lib" / "release.ts"]
    for f in files:
        src = f.read_text()
        assert not re.search(r"gs-0\d\d|gold[ _-]?standard|answer[ _-]?key", src, re.I), f                 # 92
        assert "service_role" not in src and "SERVICE_ROLE" not in src, f
    rpcs = set(re.findall(r'"(\w+)"', (WEB / "app" / "reports" / "release-actions.ts").read_text())) & {
        "request_report_qa", "acknowledge_qa_warning", "decide_report_content", "decide_security_review", "request_release_pdf",
        "decide_release", "release_report", "run_m10d", "record_qa_result", "record_release_pdf", "ingest_qa_semantic"}
    assert rpcs == {"request_report_qa", "acknowledge_qa_warning", "decide_report_content", "decide_security_review",
                    "request_release_pdf", "decide_release", "release_report"}
