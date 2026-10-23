"""P7-03 real-provider trial (Baseline §14, §26) and its regression with test doubles.

* test_provider_trial_checks_reject_test_doubles — always runs: the §26 admissibility checks classify a
  test-double run as NOT real-provider evidence, and a run of the real AnthropicProvider adapter (HTTP
  stubbed) as traceable through model_run, prompt hash, configuration hash and ingestion.
* test_real_provider_trial — runs only with LFHE_P7_PROVIDER=anthropic (secret-managed key): one synthetic
  'Northland' chain through real M07 → M08 → human approval → real M09 → M10-D + real M10-S, bound to a
  pilot cycle; writes provider metrics and admissibility to $LFHE_P7_TRIAL_OUT. Outcomes are recorded,
  not asserted: a failing provider stays a failure."""
import json
import os

import httpx
import pytest

from p7_support import provider_and_config, provider_label, real_provider_requested, write_json
from lfhe_orchestrator.assessment_pipeline import run_assessment, run_challenge
from lfhe_orchestrator.providers import AnthropicProvider
from lfhe_orchestrator.qa_pipeline import run_report_qa
from lfhe_orchestrator.report_pipeline import run_report_edit
from lfhe_orchestrator.report_render import render_and_record
from lfhe_pilot.metrics import provider_metrics
from lfhe_pilot.provider_trial import run_checks
from p5_helpers import CONF_RAT, new_report, now, select, version_of_run
from p6_helpers import activate, drafted, park_jobs, qa, request_qa
from psycopg.types.json import Jsonb
from test_p4_assessments import out as m07_out, setup_event, version_of
from test_p4_challenge_review import review

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def p7(pg):
    yield activate(pg)
    park_jobs(pg)


def test_provider_trial_checks_reject_test_doubles(pg, p7, make_user):
    a = make_user("ANALYST")
    d = drafted(pg, a, "RPT-P7TR-DOUBLE")
    with pg.admin() as x:
        r = run_checks(x, str(d.rv["created_by_model_run_id"]))
    assert not r["admissible"] and "TEST_DOUBLE_PROVIDER" in r["problems"] and "NO_PROVIDER_RESPONSE_ID" in r["problems"]
    assert r["ingestion_outcome"] == "REPORT_VERSION_RECORDED" and "PROMPT_NOT_TRACEABLE" not in r["problems"]

    # the real adapter's persistence path (HTTP stubbed — regression only, not provider evidence)
    e, vid, vh, claims = setup_event(pg, a)

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        env = json.loads(body["messages"][0]["content"].split("<lfhe_task_envelope>\n", 1)[1].rsplit("\n</lfhe_task_envelope>", 1)[0])
        return httpx.Response(200, json={"id": "msg_stub_1", "model": body["model"], "stop_reason": "end_turn",
                                         "usage": {"input_tokens": 1234, "output_tokens": 567},
                                         "content": [{"type": "text", "text": m07_out(env, None, claims=claims)}]})
    with pg.registrar() as c:
        cfg = str(c.execute("SELECT lfhe.register_model_configuration('anthropic', 'stub-model-1', %s::jsonb) id",
                            (Jsonb({"temperature": 0, "max_tokens": 8000}),)).fetchone()["id"])
    provider = AnthropicProvider("stub-key-not-a-secret", transport=httpx.MockTransport(handler))
    with pg.worker() as w:
        res = run_assessment(w, vid, vh, report_mode="LIVE", information_cutoff=now(), model_configuration_id=cfg,
                             provider=provider, worker_id="p7-trial-stub")
    assert res.outcome == "ASSESSMENT_RECORDED", res
    with pg.admin() as x:
        r = run_checks(x, str(res.final_run_id))
    assert r["admissible"] and r["provider"] == "anthropic" and r["model"] == "stub-model-1"
    assert (r["input_tokens"], r["output_tokens"]) == (1234, 567) and r["latency_ms"] is not None


@pytest.mark.skipif(not real_provider_requested(), reason="real provider not configured (LFHE_P7_PROVIDER=anthropic)")
def test_real_provider_trial(pg, p7, make_user):
    a, lead = make_user("ANALYST"), make_user("PILOT_LEAD")
    provider, cfg = provider_and_config(pg)
    out = {"provider": provider_label(), "steps": {}}
    cutoff = now()
    e, vid, vh, claims = setup_event(pg, a)
    with pg.worker() as w:
        r7 = run_assessment(w, vid, vh, report_mode="LIVE", information_cutoff=cutoff, model_configuration_id=cfg,
                            provider=provider, worker_id="p7-trial")
    out["steps"]["M07"] = {"outcome": r7.outcome, "rejections": list(getattr(r7, "rejection_reasons", []) or [])}
    runs = [str(r7.final_run_id)] + [str(x) for x in r7.model_run_ids or []]
    rid = None
    if r7.outcome == "ASSESSMENT_RECORDED":
        v = version_of(pg, r7.final_run_id)
        with pg.worker() as w:
            r8 = run_challenge(w, str(v["id"]), v["content_hash"], model_configuration_id=cfg, provider=provider, worker_id="p7-trial")
        out["steps"]["M08"] = {"outcome": r8.outcome}
        runs.append(str(r8.final_run_id))
        rv_ok = review(pg, a, v, "APPROVE", "LOW", CONF_RAT)
        out["steps"]["human_review"] = {"result": str(rv_ok)[:200]}
        rid = new_report(pg, a, "RPT-P7TR-REAL", cutoff=cutoff)
        sid, sh = select(pg, a, rid, [(v["id"], "KEY_JUDGMENT", 1)])
        with pg.worker() as w:
            r9 = run_report_edit(w, sid, sh, model_configuration_id=cfg, provider=provider, worker_id="p7-trial")
        out["steps"]["M09"] = {"outcome": r9.outcome, "rejections": list(getattr(r9, "rejection_reasons", []) or [])}
        runs.append(str(r9.final_run_id))
        if r9.outcome == "REPORT_VERSION_RECORDED":
            rv = version_of_run(pg, r9.final_run_id)
            with pg.worker() as w:
                render_and_record(w, str(rv["id"]), rv["report_version_hash"], worker_id="p7-trial")
                q = run_report_qa(w, str(rv["id"]), rv["report_version_hash"], request_qa(pg, a, rv, "real-provider trial QA"),
                                  model_configuration_id=cfg, provider=provider, worker_id="p7-trial")
            out["steps"]["M10"] = {"status": q.status, "fail_reasons": list(q.fail_reasons or [])}
    with pg.as_user(lead) as h:
        cid = str(h.execute("SELECT lfhe.pilot_create_cycle(%s::jsonb) id", (json.dumps({
            "code": "P7C-TRIAL-01", "pilot_mode": "LIVE", "information_cutoff": cutoff.isoformat(), "data_boundary": "SYNTHETIC",
            "input_scope": "synthetic Northland event, real-provider trial", "analyst_user_id": str(a),
            "provider_setup": provider_label()}),)).fetchone()["id"])
        if rid:
            h.execute("SELECT lfhe.pilot_bind_report(%s, %s)", (cid, rid))
            h.execute("SELECT lfhe.pilot_bind_model_runs(%s, NULL, 'REPORT_CHAIN')", (cid,))
        h.execute("SELECT lfhe.pilot_bind_model_runs(%s, %s::uuid[], 'TRIAL')", (cid, sorted(set(runs))))
    with pg.admin() as x:
        bound = [str(r["model_run_id"]) for r in x.execute("SELECT model_run_id FROM lfhe.pilot_cycle_model_runs WHERE cycle_id=%s", (cid,))]
        out["runs"] = [run_checks(x, r) for r in sorted(bound)]
        out["metrics"] = provider_metrics(x, cid)
    out["github_run"] = os.environ.get("GITHUB_RUN_ID")
    write_json("LFHE_P7_TRIAL_OUT", out)
    assert out["runs"] and all("TEST_DOUBLE_PROVIDER" not in r["problems"] for r in out["runs"])
