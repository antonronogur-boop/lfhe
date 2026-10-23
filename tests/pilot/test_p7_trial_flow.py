"""Regression of the P7-03 real-provider trial FLOW with the real AnthropicProvider adapter and a stubbed
HTTP transport answering with the deterministic test responders. Proves the trial wiring (M07 → M08 →
human approval → M09 → M10-D + M10-S → pilot binding → §26 checks → export) without a provider call.
This is NOT real-provider evidence: the stubbed runs are labelled with the stub model identifier."""
import json

import httpx
import pytest

import test_p7_provider_trial as trial
from lfhe_orchestrator.providers import AnthropicProvider
from m10s_auditor import auditor
from p5_helpers import m09
from test_p4_assessments import out as m07_out
from test_p4_challenge_review import chal

pytestmark = pytest.mark.db
p7 = trial.p7
CLAIMS: list = []


def handler(req: httpx.Request) -> httpx.Response:
    body = json.loads(req.content)
    env = json.loads(body["messages"][0]["content"].split("<lfhe_task_envelope>\n", 1)[1].rsplit("\n</lfhe_task_envelope>", 1)[0])
    text = {"M07_INTELLIGENCE_ASSESSOR": lambda: m07_out(env, None, claims=CLAIMS[-1]), "M08_CHALLENGER": lambda: chal(env),
            "M09_EXECUTIVE_EDITOR": lambda: m09(env), "M10_QA_AUDITOR": lambda: auditor()(None, env)}[env["module_code"]]()
    return httpx.Response(200, json={"id": "msg_stub", "model": body["model"], "stop_reason": "end_turn",
                                     "usage": {"input_tokens": 10, "output_tokens": 5}, "content": [{"type": "text", "text": text}]})


def test_trial_flow_with_stubbed_transport(pg, p7, make_user, monkeypatch, tmp_path):
    setup = trial.setup_event

    def recording_setup(*a, **k):
        r = setup(*a, **k)
        CLAIMS.append(r[3])
        return r
    monkeypatch.setattr(trial, "setup_event", recording_setup)
    monkeypatch.setenv("LFHE_P7_PROVIDER", "anthropic")
    monkeypatch.setenv("LFHE_P7_MODEL", "stub-transport-1")
    monkeypatch.setenv("LFHE_P7_TRIAL_OUT", str(tmp_path / "trial.json"))
    monkeypatch.setattr(AnthropicProvider, "from_environment",
                        classmethod(lambda cls, transport=None: cls("stub-key-not-a-secret", transport=httpx.MockTransport(handler))))
    trial.test_real_provider_trial(pg, p7, make_user)
    d = json.loads((tmp_path / "trial.json").read_text())
    assert d["steps"]["M07"]["outcome"] == "ASSESSMENT_RECORDED" and d["steps"]["M10"]["status"] == "PASS"
    assert sorted(r["module_code"] for r in d["runs"]) == ["M07_INTELLIGENCE_ASSESSOR", "M08_CHALLENGER", "M09_EXECUTIVE_EDITOR",
                                                            "M10_QA_AUDITOR"]
    assert all(r["admissible"] and r["model"] == "stub-transport-1" for r in d["runs"])
    assert set(d["metrics"]["modules"]) == {"M07_INTELLIGENCE_ASSESSOR", "M08_CHALLENGER", "M09_EXECUTIVE_EDITOR", "M10_QA_AUDITOR"}
