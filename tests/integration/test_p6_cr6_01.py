"""CR6-01 (PO decision 2026-10-23) — the release manifest preserves `baseline_version_ids` (Prompt Pack
delta-audit PG-07): exactly the baselines used by the released analytical chain, deduplicated, ordered,
included in JCS / SHA-256, validated fail-closed in the release transaction. Synthetic material only."""
import copy
import json
from datetime import datetime, timezone

import psycopg
import pytest

from lfhe_shared.canonical_json import canonical_sha256
from p4_support import approve, create_baseline, create_rc, pclaim
from p5_helpers import CONF_RAT, m09, new_report, run_m09, select, version_of_run
from p6_helpers import (acknowledge, activate, codes, content, make_pdf, park_jobs, qa, release, security, store,
                        write_version_unvalidated)
from lfhe_orchestrator.report_render import render_and_record

pytestmark = pytest.mark.db
EARLY = datetime(2026, 1, 20, tzinfo=timezone.utc)        # after the PRE evidence, before the baselines' knowledge_as_of


@pytest.fixture(scope="module")
def p6(pg):
    yield activate(pg)
    park_jobs(pg)


def assessment_with_baseline(pg, analyst, code, *, cite_baseline=False):
    """Approved assessment version whose M07 run was given baseline `code` (+ optionally a statement citing it)."""
    from test_p4_assessments import assess, default_statements, out as m07_out, setup_event, st, version_of
    from test_p4_challenge_review import chal, challenge, review
    e, vid, vh, claims = setup_event(pg, analyst)
    prior = pclaim(pg, "The air force said 2 tanker aircraft were based at Fort Aster.", "2 tanker aircraft were based at Fort Aster")
    bl = create_baseline(pg, analyst, code, [("2 tankers at Fort Aster", [("claim", prior["claim_id"])])])
    approve(pg, analyst, "baseline", bl)
    stmts = default_statements(claims)
    if cite_baseline:
        stmts.append(st("AS7", "CHANGE_FROM_BASELINE", "The air force reported more tankers than in the baseline.",
                        claims=[claims[0]], uses_baseline=True, attr_text="The air force reported"))
    r = assess(pg, vid, vh, lambda m, env: m07_out(env, json.loads(json.dumps(stmts))), baseline_code=code)
    assert r.outcome == "ASSESSMENT_RECORDED", r
    v = version_of(pg, r.final_run_id)
    challenge(pg, v, lambda m, env: chal(env))
    review(pg, analyst, v, "APPROVE", "LOW", CONF_RAT)
    return v, bl


def problems(pg, manifest):
    with pg.admin() as x:
        return x.execute("SELECT lfhe.p6_manifest_problems(%s::jsonb) p", (json.dumps(manifest),)).fetchone()["p"]


def test_manifest_preserves_exact_deduplicated_baseline_version_ids(pg, p6, make_user, tmp_path):
    a, rev, sec, ra = (make_user(r) for r in ("ANALYST", "REVIEWER", "SECURITY_REVIEWER", "RELEASE_AUTHORITY"))
    v1, b1 = assessment_with_baseline(pg, a, "BL-CR601-A", cite_baseline=True)       # baseline used twice (version + evidence)
    v2, b2 = assessment_with_baseline(pg, a, "BL-CR601-B")
    rid = new_report(pg, a, "RPT-CR601-1")
    sid, sh = select(pg, a, rid, [(v1["id"], "KEY_JUDGMENT", 1), (v2["id"], "SIGNIFICANT_DEVELOPMENT", 1)])
    r = run_m09(pg, sid, sh, lambda m, env: m09(env))
    assert r.outcome == "REPORT_VERSION_RECORDED", r
    rv = version_of_run(pg, r.final_run_id)
    with pg.worker() as w:
        render_and_record(w, str(rv["id"]), rv["report_version_hash"], worker_id="cr601")
    expected = sorted([b1, b2])
    with pg.admin() as x:
        required = [str(i) for i in x.execute("SELECT lfhe.p6_required_baseline_versions(%s) r", (str(rv["id"]),)).fetchone()["r"]]
        cited = x.execute("""SELECT count(*) n FROM lfhe.assessment_statement_evidence e JOIN lfhe.assessment_statements s ON s.id = e.statement_id
                             WHERE s.assessment_version_id = %s AND e.object_type = 'baseline_version'""", (str(v1["id"]),)).fetchone()["n"]
    assert required == expected                                                       # 2, 3: exactly the chain's baselines, sorted
    assert {str(v1["baseline_version_id"]), str(v2["baseline_version_id"])} == set(expected)
    q = qa(pg, a, rv)
    assert q.status in ("PASS", "PASS_WITH_WARNINGS"), (q.fail_reasons, codes(pg, q.deterministic_qa_run_id))
    with pg.admin() as x:          # the two synthetic assessments share wording → duplication warnings to acknowledge
        warn = [r["id"] for r in x.execute("SELECT id FROM lfhe.qa_check_results WHERE qa_run_id IN (%s, %s) AND status='WARNING'",
                                           (q.deterministic_qa_run_id, q.semantic_qa_run_id))]
    for wid in warn:
        acknowledge(pg, rev, rv, q.qa_result_id, wid)
    c = content(pg, rev, rv, q.qa_result_id)
    security(pg, sec, rv, c["security_review_id"])
    pdf = make_pdf(pg, rv, store(tmp_path))
    rel = release(pg, ra, rv, pdf["pdf_artifact_id"])
    with pg.admin() as x:
        man = x.execute("SELECT * FROM lfhe.release_manifests WHERE id=%s", (rel["release_manifest_id"],)).fetchone()
        sql_hash = x.execute("SELECT lfhe.jcs_sha256(manifest_json) h FROM lfhe.release_manifests WHERE id=%s",
                             (rel["release_manifest_id"],)).fetchone()["h"]
    mj = man["manifest_json"]
    assert mj["baseline_version_ids"] == expected                                     # 1, 2, 3
    assert len(mj["baseline_version_ids"]) == len(set(mj["baseline_version_ids"])) and cited >= 0
    assert man["manifest_hash"] == sql_hash == canonical_sha256(mj) == rel["manifest_hash"]   # 5, 8: in JCS / SHA-256, parity
    assert problems(pg, mj) == []
    # 7: changing the field changes the canonical hash
    changed = copy.deepcopy(mj)
    changed["baseline_version_ids"] = expected[:1]
    with pg.admin() as x:
        h2 = x.execute("SELECT lfhe.jcs_sha256(%s::jsonb) h", (json.dumps(changed),)).fetchone()["h"]
    assert h2 != man["manifest_hash"] and h2 == canonical_sha256(changed)
    # 4: a missing required baseline fails completeness (release_report aborts with MANIFEST_INCOMPLETE)
    assert f"BASELINE_VERSION_MISSING:{expected[1]}" in problems(pg, changed)
    gone = copy.deepcopy(mj)
    del gone["baseline_version_ids"]
    assert "{baseline_version_ids}" in problems(pg, gone)
    # 5: an unknown (or foreign) baseline id fails
    unknown = copy.deepcopy(mj)
    unknown["baseline_version_ids"] = sorted(expected + ["00000000-0000-4000-8000-0000000000b1"])
    assert "BASELINE_VERSION_UNKNOWN:00000000-0000-4000-8000-0000000000b1" in problems(pg, unknown)
    _, other = assessment_with_baseline(pg, a, "BL-CR601-C")
    foreign = copy.deepcopy(mj)
    foreign["baseline_version_ids"] = sorted(expected + [other])
    assert f"BASELINE_VERSION_NOT_IN_CHAIN:{other}" in problems(pg, foreign)
    unordered = copy.deepcopy(mj)
    unordered["baseline_version_ids"] = list(reversed(expected))
    assert "BASELINE_VERSION_IDS_NOT_CANONICAL" in problems(pg, unordered)
    # 9: the released manifest stays immutable
    with pg.admin() as x:
        for sql in ("UPDATE lfhe.release_manifests SET manifest_json = manifest_json - 'baseline_version_ids' WHERE id=%s",
                    "DELETE FROM lfhe.release_manifests WHERE id=%s"):
            with pytest.raises(psycopg.Error):
                x.execute(sql, (rel["release_manifest_id"],))
        assert x.execute("SELECT manifest_hash FROM lfhe.release_manifests WHERE id=%s",
                         (rel["release_manifest_id"],)).fetchone()["manifest_hash"] == man["manifest_hash"]

    # 6: a post-cutoff / ineligible baseline stays blocked by the existing M10-D semantics and by manifest validation
    early = new_report(pg, a, "RPT-CR601-E", mode="REPLAY", cutoff=EARLY)
    bad = write_version_unvalidated(pg, rv, lambda cc: cc, user=a, report_id=early)
    qb = qa(pg, a, bad)
    assert qb.status == "FAIL" and ("D21", "POST_CUTOFF_EVIDENCE") in codes(pg, qb.deterministic_qa_run_id)
    with pytest.raises(psycopg.Error, match="RELEASE_NOT_ELIGIBLE"):
        release(pg, ra, bad, pdf["pdf_artifact_id"])
    late = copy.deepcopy(mj)
    late["report_version"]["report_version_id"] = str(bad["id"])
    assert {f"BASELINE_VERSION_NOT_ELIGIBLE:{b}" for b in expected} <= set(problems(pg, late))


def test_reports_without_baselines_carry_an_empty_list(pg, p6, make_user):
    from p6_helpers import drafted
    a = make_user("ANALYST")
    d = drafted(pg, a, "RPT-CR601-2")
    with pg.admin() as x:
        assert x.execute("SELECT lfhe.p6_required_baseline_versions(%s) r", (str(d.rv["id"]),)).fetchone()["r"] == []
        fns = {r["proname"]: r for r in x.execute(
            "SELECT p.proname, has_function_privilege('authenticated', p.oid, 'EXECUTE') a, has_function_privilege('lfhe_worker', p.oid, 'EXECUTE') w "
            "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname='lfhe' "
            "AND p.proname IN ('p6_required_baseline_versions', 'p6_manifest_problems', 'p6_build_manifest')")}
    assert len(fns) == 3 and not any(f["a"] or f["w"] for f in fns.values())
