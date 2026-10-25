"""P7-05 controlled benchmarks P7-BM-01 and P7-BM-02 (Baseline §10 D, §22–§23; tests 9, 10, 19).

P7-BM-01 reuses the Phase 4–6 test chain (its 'clean' base turned out to contain genuine fixture defects, so its
false-alarm figure is invalid — CG7 report 2026-10-25). P7-BM-02 uses the internally consistent base of
tests/pilot/bm02_fixture.py with the same error classes; its labels are in evaluation/p7-bm-02/benchmark.json.

Seeded synthetic report versions are built through the real chain in the throw-away harness (never in
DEV: seeded corrupt versions must not enter the DEV analytical tables). Labels come from the
evaluator-only file evaluation/p7-bm-01/benchmark.json, are recorded through the HUMAN_ONLY
PILOT_EVALUATE functions and scored in aggregate by lfhe.pilot_benchmark_outcomes, D and S separately.

Default provider: the rule-based M10-S stand-in (TEST DOUBLE — regression of the measurement path).
With LFHE_P7_PROVIDER=anthropic the same cases are audited by the real provider (P7-03 / CG7 #19);
the result is written to $LFHE_P7_BENCHMARK_OUT."""
import json
from datetime import datetime, timezone

import psycopg
import pytest

from p7_support import ROOT, output_diagnostics, provider_and_config, provider_label, real_provider_requested, write_json
from lfhe_orchestrator.qa_pipeline import run_report_qa
from lfhe_pilot.export import benchmark_scores, export_problems
from p5_helpers import content_of, edit, new_report
from p6_helpers import activate, drafted, park_jobs, request_qa, write_version_unvalidated
from test_phase6_acceptance import MUTATIONS as BM01_MUTATIONS
import bm02_fixture

pytestmark = pytest.mark.db


def load(name):
    return json.loads((ROOT / "evaluation" / name / "benchmark.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def p7(pg):
    yield activate(pg)
    park_jobs(pg)


def call(pg, user, sql, args=()):
    with pg.as_user(user) as h:
        return h.execute(sql, args).fetchone()


def test_p7_bm_01(pg, p7, make_user):
    def base(a):
        d = drafted(pg, a, "RPT-P7BM-BASE")
        return d.rv, d.rid
    run_benchmark(pg, make_user, load("p7-bm-01"), base, BM01_MUTATIONS, "LFHE_P7_BENCHMARK_OUT", "RPT-P7BM-EARLY")


def test_p7_bm_02(pg, p7, make_user):
    def base(a):
        rv, rid, _, _ = bm02_fixture.build_base(pg, a, "RPT-P7BM2-BASE")
        return rv, rid
    out = run_benchmark(pg, make_user, load("p7-bm-02"), base, bm02_fixture.MUTATIONS, "LFHE_P7_BENCHMARK02_OUT",
                        "RPT-P7BM2-EARLY")
    if not real_provider_requested():          # the consistent base is clean for both layers; expected statuses hold
        assert all(v["expected"] == v["got"] for v in out["statuses"].values()), out["statuses"]
        assert out["scores"]["D"]["false_positives_on_clean_cases"] == 0 == out["scores"]["S"]["false_positives_on_clean_cases"]


def run_benchmark(pg, make_user, BENCH, base_factory, MUTATIONS, out_env, early_code, *, stand_in_s_exact=True):
    a, ev = make_user("ANALYST"), make_user("PILOT_LEAD")
    provider, config = provider_and_config(pg)
    base_rv, base_rid = base_factory(a)
    early = new_report(pg, a, early_code, mode="REPLAY", cutoff=datetime(2026, 1, 5, tzinfo=timezone.utc))
    base_content = content_of(pg, base_rv["id"])
    bid = call(pg, ev, "SELECT lfhe.pilot_record_benchmark(%s::jsonb) id", (json.dumps(
        {"code": BENCH["code"], "description": BENCH["description"][:900], "material": BENCH["material"]}),))["id"]
    runs, statuses = [], {}
    for case in BENCH["cases"]:
        fn = MUTATIONS[case["mutation"]]
        if case["write"] == "base":
            v = base_rv
        elif case["write"] == "edit":
            with pg.admin() as x:
                latest = x.execute("SELECT * FROM lfhe.report_versions WHERE report_id=%s ORDER BY version_no DESC LIMIT 1",
                                   (base_rid,)).fetchone()
            r = edit(pg, a, latest, fn(json.loads(json.dumps(base_content))), f"benchmark seeded edit {case['case_code']}")
            with pg.admin() as x:
                v = x.execute("SELECT * FROM lfhe.report_versions WHERE id=%s", (r["report_version_id"],)).fetchone()
        elif case["write"] == "replay_early":
            v = write_version_unvalidated(pg, base_rv, fn, user=a, report_id=early)
        else:
            v = write_version_unvalidated(pg, base_rv, fn, user=a)
            if case["mutation"] == "unmapped_statement":
                with pg.admin() as x:
                    x.execute("""INSERT INTO lfhe.report_item_statements (report_item_id, statement_no, report_statement_local_id,
                                   statement_role, statement_text, editorial_transform, contested, author_type, user_id)
                                 SELECT i.id, 99, 'RS99', 'KEY_JUDGMENT', 'An unmapped sentence.', 'PARAPHRASE', false, 'HUMAN', %s
                                 FROM lfhe.report_items i WHERE i.report_version_id = %s LIMIT 1""", (str(a), str(v["id"])))
        cid = call(pg, ev, "SELECT lfhe.pilot_record_benchmark_case(%s, %s, %s, %s) id",
                   (bid, case["case_code"], str(v["id"]), v["report_version_hash"]))["id"]
        for label in case["labels"]:
            call(pg, ev, "SELECT lfhe.pilot_record_benchmark_label(%s, %s::jsonb) id", (cid, json.dumps(label)))
        with pg.worker() as w:
            q = run_report_qa(w, str(v["id"]), v["report_version_hash"], request_qa(pg, a, v, "benchmark QA request"),
                              model_configuration_id=config, provider=provider, worker_id="p7-benchmark")
        statuses[case["case_code"]] = {"expected": case["expected_status"], "got": q.status}
        with pg.admin() as x:
            mr = x.execute("SELECT model_run_id FROM lfhe.qa_runs WHERE id=%s", (str(q.semantic_qa_run_id),)).fetchone()
        if mr and mr["model_run_id"]:
            runs.append(str(mr["model_run_id"]))
            with pg.admin() as x:
                st = x.execute("SELECT status::text s, error_code e FROM lfhe.model_runs WHERE id=%s", (mr["model_run_id"],)).fetchone()
            statuses[case["case_code"]]["m10s_run"] = {"status": st["s"], "error_code": st["e"]}

    # test 10: model / deterministic findings can never be recorded as benchmark truth
    any_case = call(pg, ev, "SELECT id FROM lfhe.pilot_benchmark_cases WHERE benchmark_id=%s LIMIT 1", (bid,))["id"]
    for kind in ("MODEL_FINDING", "DETERMINISTIC_FINDING"):
        with pytest.raises(psycopg.errors.CheckViolation, match="PILOT_LABEL_KIND_NOT_TRUTH"):
            call(pg, ev, "SELECT lfhe.pilot_record_benchmark_label(%s, %s::jsonb) id", (any_case, json.dumps(
                {"label_kind": kind, "expected_layer": "S", "expected_check_id": "QA-01", "critical": False, "note": "from a finding"})))
    with pytest.raises(psycopg.errors.CheckViolation, match="PILOT_LABEL_FROM_FINDING"):
        call(pg, ev, "SELECT lfhe.pilot_record_benchmark_label(%s, %s::jsonb) id", (any_case, json.dumps(
            {"label_kind": "BENCHMARK_LABEL", "expected_layer": "S", "expected_check_id": "QA-01", "critical": False,
             "note": "copied", "qa_check_result_id": "00000000-0000-4000-8000-000000000001"})))
    # labels are evaluator-only: analyst and worker see nothing
    with pg.as_user(a) as h:
        assert h.execute("SELECT count(*) n FROM lfhe.pilot_benchmark_labels").fetchone()["n"] == 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            h.execute("SELECT * FROM lfhe.pilot_benchmark_outcomes(%s)", (bid,))
    with pg.worker() as w, pytest.raises(psycopg.errors.InsufficientPrivilege):
        w.execute("SELECT count(*) FROM lfhe.pilot_benchmark_labels")

    # test 9: no label content reached any provider input
    notes = {lb["note"] for c in BENCH["cases"] for lb in c["labels"]} | {c["case_code"] for c in BENCH["cases"]} | {BENCH["code"]}
    assert provider.texts and not [n for n in notes for t in provider.texts if n in t]

    with pg.admin() as x:
        scores = benchmark_scores(x, BENCH["code"])
        # evaluator-side per-case breakdown (P7-08 analysis): outcome counts per layer, the missed labels, and the model's
        # non-PASS S findings (check, code, status, severity, shortened details) — synthetic material only
        per_case = {}
        for r in x.execute("SELECT * FROM lfhe.pilot_benchmark_outcomes(%s)", (bid,)):
            c = per_case.setdefault(r["case_code"], {"counts": {}, "missed": []})
            key = f"{r['layer']}:{r['kind']}"
            c["counts"][key] = c["counts"].get(key, 0) + 1
            if r["kind"] == "FALSE_NEGATIVE":
                c["missed"].append({"layer": r["layer"], "check_id": r["check_id"], "finding_code": r["finding_code"],
                                    "critical": r["critical"]})
        for code, st in statuses.items():
            q = x.execute("""SELECT q.semantic_qa_run_id s FROM lfhe.qa_results q JOIN lfhe.pilot_benchmark_cases c
                               ON c.report_version_id = q.report_version_id WHERE c.benchmark_id=%s AND c.case_code=%s
                             ORDER BY q.result_no DESC LIMIT 1""", (bid, code)).fetchone()
            per_case.setdefault(code, {"counts": {}, "missed": []})["s_findings"] = [
                {"check_id": f["check_id"], "finding_code": f["finding_code"], "status": f["status"], "severity": f["sev"],
                 "details": f["details"][:240]}
                for f in x.execute("SELECT check_id, finding_code, status, severity::text sev, details FROM lfhe.qa_check_results "
                                   "WHERE qa_run_id=%s AND status <> 'PASS' ORDER BY finding_no", (q["s"],))] if q and q["s"] else []
    run_states = [v.get("m10s_run", {}).get("status") for v in statuses.values()]
    if not real_provider_requested():
        evidence = "TEST_DOUBLE_REGRESSION"
    elif all(s == "SUCCEEDED" for s in run_states):
        evidence = "REAL_PROVIDER"
    else:
        evidence = "REAL_PROVIDER_RUNS_FAILED — not a measurement of M10-S quality"   # failures stay failures (§26)
    diagnostics = [d for d in (output_diagnostics(pg, r) for r in runs[:3]) if d]
    doc = {"benchmark": BENCH["code"], "provider": provider_label(), "scores": scores, "statuses": statuses,
                                         "schema_failure_diagnostics": diagnostics, "per_case": per_case,
                                         "m10s_model_runs": runs, "m10s_run_status_counts":
                                         {s: run_states.count(s) for s in sorted(set(map(str, run_states)))},
                                         "evidence_class": evidence}
    write_json(out_env, doc)
    assert export_problems(scores) == []                                                    # test 19: aggregate only
    assert scores["cases"] == len(BENCH["cases"]) and scores["cases_without_qa_result"] == 0
    assert set(scores) >= {"D", "S"}                                                         # D and S separately measurable
    assert scores["D"]["critical_misses"] == 0                                               # deterministic layer is provider-independent
    if not real_provider_requested() and stand_in_s_exact:
        assert scores["S"]["false_negatives"] == 0                                          # stand-in regression only
    return doc
