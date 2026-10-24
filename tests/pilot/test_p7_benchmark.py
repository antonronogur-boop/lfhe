"""P7-05 controlled benchmark P7-BM-01 (Baseline §10 D, §22–§23; tests 9, 10, 19).

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

from p7_support import ROOT, provider_and_config, provider_label, real_provider_requested, write_json
from lfhe_orchestrator.qa_pipeline import run_report_qa
from lfhe_pilot.export import benchmark_scores, export_problems
from p5_helpers import content_of, edit, new_report
from p6_helpers import activate, drafted, park_jobs, request_qa, write_version_unvalidated
from test_phase6_acceptance import MUTATIONS

pytestmark = pytest.mark.db
BENCH = json.loads((ROOT / "evaluation" / "p7-bm-01" / "benchmark.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def p7(pg):
    yield activate(pg)
    park_jobs(pg)


def call(pg, user, sql, args=()):
    with pg.as_user(user) as h:
        return h.execute(sql, args).fetchone()


def test_p7_bm_01(pg, p7, make_user):
    a, ev = make_user("ANALYST"), make_user("PILOT_LEAD")
    provider, config = provider_and_config(pg)
    base = drafted(pg, a, "RPT-P7BM-BASE")
    early = new_report(pg, a, "RPT-P7BM-EARLY", mode="REPLAY", cutoff=datetime(2026, 1, 5, tzinfo=timezone.utc))
    base_content = content_of(pg, base.rv["id"])
    bid = call(pg, ev, "SELECT lfhe.pilot_record_benchmark(%s::jsonb) id", (json.dumps(
        {"code": BENCH["code"], "description": BENCH["description"][:900], "material": BENCH["material"]}),))["id"]
    runs, statuses = [], {}
    for case in BENCH["cases"]:
        fn = MUTATIONS[case["mutation"]]
        if case["write"] == "base":
            v = base.rv
        elif case["write"] == "edit":
            with pg.admin() as x:
                latest = x.execute("SELECT * FROM lfhe.report_versions WHERE report_id=%s ORDER BY version_no DESC LIMIT 1",
                                   (base.rid,)).fetchone()
            r = edit(pg, a, latest, fn(json.loads(json.dumps(base_content))), f"benchmark seeded edit {case['case_code']}")
            with pg.admin() as x:
                v = x.execute("SELECT * FROM lfhe.report_versions WHERE id=%s", (r["report_version_id"],)).fetchone()
        elif case["write"] == "replay_early":
            v = write_version_unvalidated(pg, base.rv, fn, user=a, report_id=early)
        else:
            v = write_version_unvalidated(pg, base.rv, fn, user=a)
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
    assert export_problems(scores) == []                                                    # test 19: aggregate only
    assert scores["cases"] == len(BENCH["cases"]) and scores["cases_without_qa_result"] == 0
    assert set(scores) >= {"D", "S"}                                                         # D and S separately measurable
    assert scores["D"]["critical_misses"] == 0                                               # deterministic layer is provider-independent
    if not real_provider_requested():
        assert scores["S"]["false_negatives"] == 0                                          # stand-in regression only
    run_states = [v.get("m10s_run", {}).get("status") for v in statuses.values()]
    if not real_provider_requested():
        evidence = "TEST_DOUBLE_REGRESSION"
    elif all(s == "SUCCEEDED" for s in run_states):
        evidence = "REAL_PROVIDER"
    else:
        evidence = "REAL_PROVIDER_RUNS_FAILED — not a measurement of M10-S quality"   # failures stay failures (§26)
    write_json("LFHE_P7_BENCHMARK_OUT", {"provider": provider_label(), "scores": scores, "statuses": statuses,
                                         "m10s_model_runs": runs, "m10s_run_status_counts":
                                         {s: run_states.count(s) for s in sorted(set(map(str, run_states)))},
                                         "evidence_class": evidence})
