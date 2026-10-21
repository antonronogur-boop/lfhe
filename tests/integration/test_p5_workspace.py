"""P5-08 — analyst report workspace server-side behaviour (required tests 50–55): the exact
reads and HUMAN_ONLY calls the Next.js workspace performs, executed as real `authenticated`
sessions under RLS. The pure UI logic is covered by apps/web/tests/reports.test.ts."""
import json
import re

import psycopg
import pytest

from conftest import REPO_ROOT
from p5_helpers import activate, approved_assessment, m09, new_report, run_m09, select, version_of_run

pytestmark = pytest.mark.db
GS = re.compile(r"gs-0\d\d|gold[ _-]?standard|answer[ _-]?key|expected_(claims|events|assessment)", re.IGNORECASE)


@pytest.fixture(scope="module")
def p5(pg):
    return activate(pg)


def test_workspace_reads_actions_and_provenance(pg, p5, make_user):
    analyst, viewer = make_user("ANALYST"), make_user("VIEWER")
    v, claims, _ = approved_assessment(pg, analyst)
    rid = new_report(pg, analyst, "RPT-UI-1")
    # 50: authorised analyst (and a reader) can view the pool with confidence / state context
    for who in (analyst, viewer):
        with pg.as_user(who) as h:
            rows = h.execute("SELECT * FROM lfhe.report_candidate_state WHERE report_id=%s", (rid,)).fetchall()
            assert str(v["id"]) in {str(r["object_id"]) for r in rows}
            st = h.execute("SELECT final_analytic_confidence, state FROM lfhe.assessment_version_states WHERE assessment_version_id=%s",
                           (v["id"],)).fetchone()
            assert (st["final_analytic_confidence"], st["state"]) == ("LOW", "APPROVED")
    with pg.as_anon() as h, pytest.raises(psycopg.errors.InsufficientPrivilege):
        h.execute("SELECT count(*) n FROM lfhe.report_candidate_state")
    # 51 / 54: selection only through guarded server-side functions; VIEWER refused
    cand = next(r for r in rows if str(r["object_id"]) == str(v["id"]))
    with pg.as_user(viewer) as h:
        for sql, args in (("SELECT lfhe.decide_report_candidate(%s, %s, 'INCLUDE', 'KEY_JUDGMENT', 1, NULL, 'viewer tries')",
                           (cand["candidate_id"], cand["object_hash"])),
                          ("SELECT lfhe.freeze_report_selection(%s, 'viewer tries')", (rid,)),
                          ("SELECT lfhe.refresh_report_candidates(%s)", (rid,)),
                          ("SELECT lfhe.create_report('{}'::jsonb, 'viewer tries')", ())):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                h.execute(sql, args)
        with pytest.raises(psycopg.Error):
            h.execute("INSERT INTO lfhe.report_selection_decisions (report_id, candidate_id, candidate_object_hash, decision, "
                      "actor_user_id, reason) VALUES (%s, %s, %s, 'EXCLUDE', %s, 'direct write')",
                      (rid, cand["candidate_id"], cand["object_hash"], str(viewer)))
    sid, sh = select(pg, analyst, rid, [(v["id"], "KEY_JUDGMENT", 1)])
    rv = version_of_run(pg, run_m09(pg, sid, sh, lambda m, env: m09(env)).final_run_id)
    with pg.as_user(viewer) as h:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            h.execute("SELECT lfhe.edit_report_version(%s, %s, '{}'::jsonb, 'viewer edit')", (rv["id"], rv["report_version_hash"]))
        # 52: provenance resolves report statement → assessment statement → evidence → claim, as the UI reads it
        srcs = h.execute("""SELECT x.assessment_statement_id, a.statement_text, a.assessment_version_id
                            FROM lfhe.report_statement_sources x JOIN lfhe.report_item_statements s ON s.id = x.report_item_statement_id
                            JOIN lfhe.report_items i ON i.id = s.report_item_id
                            JOIN lfhe.assessment_statements a ON a.id = x.assessment_statement_id
                            WHERE i.report_version_id = %s""", (rv["id"],)).fetchall()
        assert srcs and {str(r["assessment_version_id"]) for r in srcs} == {str(v["id"])}
        ev = h.execute("""SELECT e.object_id FROM lfhe.assessment_statement_evidence e WHERE e.object_type='claim'
                          AND e.statement_id = ANY(%s::uuid[])""", ([str(r["assessment_statement_id"]) for r in srcs],)).fetchall()
        claim_ids = {str(r["object_id"]) for r in ev}
        assert claim_ids <= {c["claim_id"] for c in claims} and claim_ids
        assert h.execute("SELECT count(*) n FROM lfhe.claims WHERE id = ANY(%s::uuid[])", (list(claim_ids),)).fetchone()["n"] == len(claim_ids)
        canon = h.execute("SELECT canonical_json FROM lfhe.report_versions WHERE id=%s", (rv["id"],)).fetchone()["canonical_json"]
        assert {s for sec in canon["sections"] for it in sec["items"] for st in it["statements"] for s in st["sources"]} == \
            {str(r["assessment_statement_id"]) for r in srcs}
    # 53: version comparison reads two immutable versions of the same report
    with pg.as_user(analyst) as h:
        c = h.execute("SELECT canonical_json FROM lfhe.report_versions WHERE id=%s", (rv["id"],)).fetchone()["canonical_json"]
    content = {s["section"]: s for s in c["sections"]}
    kj = content["KEY_JUDGMENT"]["items"][0]
    edit_payload = {"key_judgments": [{"item_local_id": kj["item_local_id"], "source_candidate_id": kj["source_candidate_id"],
                                       "statements": [{"report_statement_local_id": st["report_statement_local_id"], "text": st["text"],
                                                       "statement_role": st["statement_role"], "source_assessment_statement_ids": st["sources"],
                                                       "final_analytic_confidence": st["final_analytic_confidence"],
                                                       "likelihood_term": st["likelihood_term"],
                                                       "editorial_transform": st["editorial_transform"]} for st in reversed(kj["statements"])]}]}
    with pg.as_user(analyst) as h:
        res = h.execute("SELECT lfhe.edit_report_version(%s, %s, %s::jsonb, 'analyst reorders') r",
                        (rv["id"], rv["report_version_hash"], json.dumps(edit_payload))).fetchone()["r"]
        both = h.execute("SELECT id, version_no, report_version_hash FROM lfhe.report_versions WHERE report_id=%s ORDER BY version_no",
                         (rid,)).fetchall()
    assert [b["version_no"] for b in both] == [1, 2] and str(both[1]["id"]) == res["report_version_id"]
    assert both[0]["report_version_hash"] != both[1]["report_version_hash"]


def test_workspace_code_never_touches_gold_standard_material():
    """55: the workspace reads only database objects; no GS / answer-key path or marker in its code."""
    hits = []
    for root in (REPO_ROOT / "apps" / "web" / "app", REPO_ROOT / "apps" / "web" / "lib"):
        for f in root.rglob("*"):
            if f.is_file() and f.suffix in {".ts", ".tsx"}:
                for n, line in enumerate(f.read_text().splitlines(), 1):
                    if GS.search(line):
                        hits.append(f"{f.relative_to(REPO_ROOT)}:{n}")
    assert hits == []
    src = (REPO_ROOT / "apps" / "web" / "app" / "reports" / "[id]" / "page.tsx").read_text()
    assert "readFile" not in src and "fs" not in re.findall(r'from "([^"]+)"', src)
    assert 'sandbox=""' in src                                            # preview iframe cannot run scripts
