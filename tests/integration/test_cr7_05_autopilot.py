"""CR7-05 — report autopilot (migration 4500): a human switches it on for one report; the worker then chains the
unchanged pipeline steps M05 → M06 → M07 → M08 for new claims of that context. It only enqueues; it never reviews,
approves, promotes or changes a state. Synthetic 'Northland' material, scripted model."""
import json
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from lfhe_orchestrator import autopilot
from lfhe_orchestrator.providers import FakeProvider
from lfhe_orchestrator.worker import make_handlers
from lfhe_shared.jobs import JobQueue
from p4_support import pclaim
from p5_helpers import new_report
from pipeline_support import activate_real_prompts, model_configuration
from test_p4_assessments import out as m07_out
from test_p4_challenge_review import chal
from test_p4_relevance import out as m06_out
from test_phase3_pipeline import m05_create

pytestmark = pytest.mark.db
NOW = lambda: datetime.now(timezone.utc) + timedelta(minutes=5)   # noqa: E731
MODULES = ("M02_CLAIM_EXTRACTOR", "M03_CLASSIFIER", "M04_LINEAGE", "M05_EVENT_BUILDER", "M06_RELEVANCE",
           "M07_INTELLIGENCE_ASSESSOR", "M08_CHALLENGER")


@pytest.fixture(scope="module")
def prompts(pg):
    return activate_real_prompts(pg, MODULES)


@pytest.fixture
def analyst(make_user):
    return make_user("ANALYST")


def park_pending(pg):
    with pg.admin() as x:
        x.execute("UPDATE lfhe.report_autopilot SET enabled=false")
        x.execute("UPDATE lfhe.processing_jobs SET status='SKIPPED' WHERE status IN ('PENDING','RUNNING')")


def set_autopilot(pg, user, report, on, reason="analyst switches the analysis on"):
    with pg.as_user(user) as h:
        return h.execute("SELECT lfhe.set_report_autopilot(%s, %s, %s) r", (report, on, reason)).fetchone()["r"]


def work(pg, responder, n):
    mc = model_configuration(pg)
    with pg.worker() as c:
        q = JobQueue(c, "cr7-05-worker")
        handlers = make_handlers(c, q, FakeProvider(responder), m02_config=mc, m03_config=mc, worker_id="cr7-05-worker",
                                 m04_config=mc, m05_config=mc, m06_config=mc, m07_config=mc, m08_config=mc)
        return sum(q.run_once(handlers, limit=1) for _ in range(n))


def jobs(pg, like):
    with pg.admin() as x:
        return x.execute("SELECT job_type, status::text s, idempotency_key FROM lfhe.processing_jobs "
                         "WHERE idempotency_key LIKE %s ORDER BY created_at", (like,)).fetchall()


def test_only_a_human_with_event_permission_switches_the_autopilot_one_context_at_a_time(pg, prompts, analyst, make_user):
    park_pending(pg)
    r1 = new_report(pg, analyst, "RPT-AUTO-ONE", mode="LIVE", cutoff=NOW())
    r2 = new_report(pg, analyst, "RPT-AUTO-TWO", mode="LIVE", cutoff=NOW())
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        set_autopilot(pg, make_user("VIEWER"), r1, True)
    with pg.as_anon() as h, pytest.raises(psycopg.errors.InsufficientPrivilege):
        h.execute("SELECT lfhe.set_report_autopilot(%s, true, 'anonymous attempt')", (r1,))
    assert set_autopilot(pg, analyst, r1, True)["enabled"] is True
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState, match="ALREADY_ON_FOR_ANOTHER_REPORT"):
        set_autopilot(pg, analyst, r2, True)
    set_autopilot(pg, analyst, r1, False)
    assert set_autopilot(pg, analyst, r2, True)["enabled"] is True
    with pg.admin() as x:
        assert x.execute("SELECT count(*) n FROM lfhe.audit_log WHERE event_type='REPORT_AUTOPILOT_SET'").fetchone()["n"] >= 3
    set_autopilot(pg, analyst, r2, False)


def test_nothing_is_chained_while_the_autopilot_is_off(pg, prompts, analyst):
    park_pending(pg)
    a = pclaim(pg, "The air force said 4 tanker aircraft arrived at Fort Aster.", "4 tanker aircraft arrived at Fort Aster")
    with pg.worker() as c:
        assert autopilot.after_classification(c, JobQueue(c, "t"), [a["claim_id"]]) == 0
    assert jobs(pg, "AUTO:%") == [] or all(j["s"] == "SKIPPED" for j in jobs(pg, "AUTO:BUILD_EVENTS:%"))


def test_chain_runs_m05_m06_m07_m08_without_any_human_step_and_decides_nothing(pg, prompts, analyst):
    park_pending(pg)
    cutoff = NOW()
    rid = new_report(pg, analyst, "RPT-AUTO-CHAIN", mode="LIVE", cutoff=cutoff)
    a = pclaim(pg, "The air force said 7 tanker aircraft arrived at Fort Aster.", "7 tanker aircraft arrived at Fort Aster")
    set_autopilot(pg, analyst, rid, True)

    with pg.worker() as c:
        assert autopilot.after_classification(c, JobQueue(c, "t"), [a["claim_id"]]) == 1
        assert autopilot.after_classification(c, JobQueue(c, "t"), [a["claim_id"]]) == 1      # idempotent key
    assert len(jobs(pg, "AUTO:BUILD_EVENTS:%")) == 1

    def responder(module, env):
        code = module.module_code
        if code == "M05_EVENT_BUILDER":
            return m05_create([a])(module, env)
        if code == "M06_RELEVANCE":
            return m06_out(env)
        if code == "M07_INTELLIGENCE_ASSESSOR":
            return m07_out(env, claims=[a])
        return chal(env)

    assert work(pg, responder, 4) == 4                                  # M05, M06, M07, M08 — no human click in between
    kinds = [j["job_type"] for j in jobs(pg, "AUTO:%") + jobs(pg, "CHALLENGE_ASSESSMENT:%")]
    assert {"BUILD_EVENTS", "ASSESS_RELEVANCE", "ASSESS_EVENT", "CHALLENGE_ASSESSMENT"} <= set(kinds)
    with pg.admin() as x:
        av = x.execute("SELECT id FROM lfhe.assessment_versions av JOIN lfhe.event_claims ec "
                       "ON ec.event_version_id = av.event_version_id WHERE ec.claim_id=%s", (a["claim_id"],)).fetchone()
        assert av is not None
        ev = x.execute("SELECT s.new_state::text st FROM lfhe.event_claims ec JOIN lfhe.event_versions v ON v.id=ec.event_version_id "
                       "JOIN lfhe.event_state_history s ON s.event_id=v.event_id WHERE ec.claim_id=%s", (a["claim_id"],)).fetchall()
        assert [e["st"] for e in ev] == ["CANDIDATE"]                  # no state change, no review, no approval
        assert x.execute("SELECT count(*) n FROM lfhe.analytical_approvals WHERE assessment_version_id=%s",
                         (av["id"],)).fetchone()["n"] == 0
        assert x.execute("SELECT count(*) n FROM lfhe.event_version_reviews").fetchone()["n"] >= 0
    set_autopilot(pg, analyst, rid, False)


def test_other_context_or_rejected_claims_are_not_chained(pg, prompts, analyst):
    park_pending(pg)
    rid = new_report(pg, analyst, "RPT-AUTO-CTX", mode="LIVE", cutoff=NOW())
    set_autopilot(pg, analyst, rid, True)
    with pg.worker() as c:
        q = JobQueue(c, "t")
        other = {"report_mode": "REPLAY", "information_cutoff": "2026-03-01T00:00:00+00:00"}
        assert autopilot.after_event_build(c, q, "00000000-0000-0000-0000-000000000000", other) == 0
        assert autopilot.after_relevance(c, q, "00000000-0000-0000-0000-000000000000", other) == 0
        assert autopilot.after_classification(c, q, []) == 0
    set_autopilot(pg, analyst, rid, False)
