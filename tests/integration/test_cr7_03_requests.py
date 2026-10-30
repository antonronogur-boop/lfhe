"""CR7-03 — human, audited request path for existing pipeline jobs (migration 4300).

The requests are made through the real HUMAN_ONLY functions with a human session; the jobs are processed by the
unchanged worker handlers (make_handlers) with a scripted model, so the payload the database builds is proven to be
the payload the closed pipeline reads. Synthetic 'Northland' material only."""
import json
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from psycopg.types.json import Jsonb

from lfhe_orchestrator.providers import FakeProvider
from lfhe_orchestrator.worker import make_handlers
from lfhe_shared.jobs import JobQueue
from lineage_support import grounded_claim, head
from p4_support import CUT, POST, PRE, human_event, pclaim
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


def request(pg, user, job_type, params, reason="analyst requests the pipeline step"):
    with pg.as_user(user) as h:
        return h.execute("SELECT lfhe.request_workflow_job(%s, %s::jsonb, %s) AS r",
                         (job_type, json.dumps(params), reason)).fetchone()["r"]


def park_pending(pg):
    with pg.admin() as x:                      # the test DB is shared: park unrelated pending jobs
        x.execute("UPDATE lfhe.processing_jobs SET status='SKIPPED' WHERE status IN ('PENDING','RUNNING')")


def work(pg, responder, n=1):
    mc = model_configuration(pg)
    with pg.worker() as c:
        q = JobQueue(c, "cr7-03-worker")
        handlers = make_handlers(c, q, FakeProvider(responder), m02_config=mc, m03_config=mc, worker_id="cr7-03-worker",
                                 m04_config=mc, m05_config=mc, m06_config=mc, m07_config=mc, m08_config=mc)
        done = 0
        for _ in range(n):
            done += q.run_once(handlers, limit=1)
        return done


def job(pg, job_id):
    with pg.admin() as x:
        return x.execute("SELECT * FROM lfhe.processing_jobs WHERE id=%s", (job_id,)).fetchone()


def test_only_humans_with_the_step_permission_can_request(pg, prompts, make_user):
    c = pclaim(pg, "The air force said 2 radars were installed at Fort Aster.", "2 radars were installed at Fort Aster")
    params = {"claim_ids": [c["claim_id"]], "report_mode": "LIVE", "information_cutoff": NOW().isoformat()}
    for role in ("VIEWER", "ADMIN", "REVIEWER", "SECURITY_REVIEWER", "RELEASE_AUTHORITY", "PILOT_LEAD"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            request(pg, make_user(role), "BUILD_EVENTS", params)
    for conn in (pg.as_service_role, pg.as_anon, pg.worker):
        with conn() as h, pytest.raises(psycopg.errors.InsufficientPrivilege):
            h.execute("SELECT lfhe.request_workflow_job('BUILD_EVENTS', %s::jsonb, 'machine tries to request')",
                      (json.dumps(params),))
    with pytest.raises(psycopg.errors.InvalidParameterValue):
        request(pg, make_user("ANALYST"), "EDIT_REPORT", params)          # report jobs keep their own human paths
    with pytest.raises(psycopg.errors.InvalidParameterValue):
        request(pg, make_user("ANALYST"), "BUILD_EVENTS", params, reason="no")


def test_extract_request_uses_the_worker_key_and_is_idempotent(pg, prompts, analyst):
    c = grounded_claim(pg, "The navy said 3 drones were tested near Port Vale.", "3 drones were tested near Port Vale")
    tr = c["rep_id"]
    park_pending(pg)
    r1 = request(pg, analyst, "EXTRACT_CLAIMS", {"text_representation_id": tr})
    r2 = request(pg, analyst, "EXTRACT_CLAIMS", {"text_representation_id": tr})
    assert r1["outcome"] == "ENQUEUED" and r2["outcome"] == "ALREADY_ACTIVE" and r1["job_id"] == r2["job_id"]
    assert r1["idempotency_key"] == f"EXTRACT_CLAIMS:{tr}:{prompts['M02_CLAIM_EXTRACTOR']}"
    with pg.worker() as w:      # the closed worker bulk path sees the same key: no second extraction job
        w.execute("SELECT lfhe.enqueue_pending_claim_extractions(500)")
        assert w.execute("SELECT count(*) n FROM lfhe.processing_jobs WHERE job_type='EXTRACT_CLAIMS' AND object_id=%s",
                         (tr,)).fetchone()["n"] == 1
    with pg.admin() as x:
        reqs = x.execute("SELECT * FROM lfhe.workflow_job_requests WHERE object_id=%s ORDER BY seq", (tr,)).fetchall()
        assert [r["requested_by"] for r in reqs] == [analyst, analyst]
        audited = x.execute("SELECT count(*) n FROM lfhe.audit_log WHERE event_type='WORKFLOW_JOB_REQUESTED' "
                            "AND object_id=%s", (r1["job_id"],)).fetchone()["n"]
        assert audited == 2
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            x.execute("UPDATE lfhe.workflow_job_requests SET reason='rewritten history' WHERE object_id=%s", (tr,))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            x.execute("DELETE FROM lfhe.workflow_job_requests WHERE object_id=%s", (tr,))


def test_build_events_request_respects_cutoff_and_runs_through_the_worker(pg, prompts, analyst):
    late = pclaim(pg, "The air force said 6 jets landed at Fort Aster.", "6 jets landed at Fort Aster", when=POST)
    with pytest.raises(psycopg.errors.CheckViolation, match="CLAIM_NOT_CUTOFF_ELIGIBLE"):
        request(pg, analyst, "BUILD_EVENTS", {"claim_ids": [late["claim_id"]], "report_mode": "REPLAY",
                                              "information_cutoff": CUT})
    a = pclaim(pg, "The air force said 4 tanker aircraft arrived at Base North.", "4 tanker aircraft arrived at Base North",
               when=PRE)
    park_pending(pg)
    r = request(pg, analyst, "BUILD_EVENTS", {"claim_ids": [a["claim_id"]], "report_mode": "REPLAY",
                                              "information_cutoff": CUT})
    assert r["outcome"] == "ENQUEUED" and r["job_status"] == "PENDING"
    j = job(pg, r["job_id"])
    assert j["payload"]["report_mode"] == "REPLAY" and datetime.fromisoformat(j["payload"]["information_cutoff"]) \
        == datetime.fromisoformat(CUT)
    assert work(pg, m05_create([a])) == 1
    assert job(pg, r["job_id"])["status"] == "HUMAN_REVIEW"            # M05 proposals always end in human review
    with pg.admin() as x:
        ev = x.execute("SELECT e.id, s.new_state::text st FROM lfhe.event_claims ec JOIN lfhe.event_versions v "
                       "ON v.id = ec.event_version_id JOIN lfhe.events e ON e.id = v.event_id "
                       "JOIN lfhe.event_state_history s ON s.event_id = e.id WHERE ec.claim_id=%s", (a["claim_id"],)).fetchall()
        assert [e["st"] for e in ev] == ["CANDIDATE"]                 # nothing beyond a candidate without a human
    with pg.as_user(analyst) as h:
        st = h.execute("SELECT display_status FROM lfhe.workflow_job_request_status WHERE request_id=%s",
                       (r["request_id"],)).fetchone()
        assert st["display_status"] == "NEEDS_HUMAN_REVIEW"
    with pg.as_anon() as h, pytest.raises(psycopg.errors.InsufficientPrivilege):
        h.execute("SELECT * FROM lfhe.workflow_job_request_status")


def test_assessment_request_requires_m06_recommendation_or_audited_manual_request(pg, prompts, analyst):
    c = pclaim(pg, "The air force said 4 tanker aircraft arrived at Fort Aster.", "4 tanker aircraft arrived at Fort Aster")
    e = human_event(pg, analyst, [c], title="Tanker arrival at Fort Aster")
    h = head(pg, e)
    vid, vh = str(h["head_version_id"]), h["head_content_hash"]
    ctx = {"event_version_id": vid, "event_version_hash": vh, "report_mode": "LIVE", "information_cutoff": NOW().isoformat()}
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState, match="MANUAL_ASSESSMENT_REQUEST_REQUIRED"):
        request(pg, analyst, "ASSESS_EVENT", ctx)
    with pytest.raises(psycopg.errors.CheckViolation, match="HASH_MISMATCH"):
        request(pg, analyst, "ASSESS_RELEVANCE", dict(ctx, event_version_hash="0" * 64))
    park_pending(pg)
    rel = request(pg, analyst, "ASSESS_RELEVANCE", ctx)
    assert work(pg, lambda m, env: m06_out(env)) == 1 and job(pg, rel["job_id"])["status"] == "SUCCESS"
    a = request(pg, analyst, "ASSESS_EVENT", ctx)                         # M06 now recommends assessment
    assert a["outcome"] == "ENQUEUED"
    assert request(pg, analyst, "ASSESS_EVENT", ctx)["outcome"] == "ALREADY_ACTIVE"
    assert work(pg, lambda m, env: m07_out(env, claims=[c])) == 1
    assert job(pg, a["job_id"])["status"] == "SUCCESS"
    assert request(pg, analyst, "ASSESS_EVENT", ctx)["outcome"] == "ALREADY_COMPLETED"
    with pg.admin() as x:
        av = x.execute("SELECT id, content_hash FROM lfhe.assessment_versions WHERE event_version_id=%s", (vid,)).fetchone()
        chained = x.execute("SELECT status::text s FROM lfhe.processing_jobs WHERE idempotency_key=%s",
                            (f"CHALLENGE_ASSESSMENT:{av['id']}",)).fetchone()
        assert chained["s"] == "PENDING"                               # the closed M07 → M08 chain is unchanged
        # nothing is approved by a request
        assert x.execute("SELECT count(*) n FROM lfhe.analytical_approvals WHERE assessment_version_id=%s",
                         (av["id"],)).fetchone()["n"] == 0
    ch = request(pg, analyst, "CHALLENGE_ASSESSMENT", {"assessment_version_id": str(av["id"]),
                                                       "assessment_version_hash": av["content_hash"]})
    assert ch["outcome"] == "ALREADY_ACTIVE"                          # same key as the worker's chain: no 2nd challenge
    assert work(pg, lambda m, env: chal(env)) == 1


def test_manual_promotion_unlocks_assessment_without_m06(pg, prompts, analyst):
    c = pclaim(pg, "The air force said 2 jets arrived at Fort Aster.", "2 jets arrived at Fort Aster")
    e = human_event(pg, analyst, [c], title="Jet arrival at Fort Aster")
    h = head(pg, e)
    vid, vh = str(h["head_version_id"]), h["head_content_hash"]
    with pg.as_user(analyst) as hu:
        hu.execute("SELECT lfhe.promote_event_version(%s, %s, 'REQUEST_ASSESSMENT', 'analyst requests assessment despite no score')",
                   (vid, vh))
    r = request(pg, analyst, "ASSESS_EVENT", {"event_version_id": vid, "event_version_hash": vh, "report_mode": "LIVE",
                                              "information_cutoff": NOW().isoformat()})
    assert r["outcome"] == "ENQUEUED"


def test_permanent_failure_can_be_re_requested_once_per_failure(pg, prompts, analyst):
    c = pclaim(pg, "The air force said 5 radars were moved to Fort Aster.", "5 radars were moved to Fort Aster")
    params = {"claim_ids": [c["claim_id"]], "report_mode": "LIVE", "information_cutoff": NOW().isoformat()}
    r1 = request(pg, analyst, "BUILD_EVENTS", params)
    with pg.admin() as x:                                    # simulate max_attempts exhausted under fail_job
        x.execute("UPDATE lfhe.processing_jobs SET status='FAILED', attempt_count=max_attempts, completed_at=now(), "
                  "last_error='PERMANENT: provider unavailable' WHERE id=%s", (r1["job_id"],))
    with pg.as_user(analyst) as h:
        st = h.execute("SELECT display_status, last_error FROM lfhe.workflow_job_request_status WHERE request_id=%s",
                       (r1["request_id"],)).fetchone()
        assert st["display_status"] == "FAILED" and "provider unavailable" in st["last_error"]
    r2 = request(pg, analyst, "BUILD_EVENTS", params, reason="analyst retries after provider outage")
    assert r2["outcome"] == "REQUEUED_AFTER_FAILURE" and r2["job_id"] != r1["job_id"]
    assert r2["idempotency_key"] == r1["idempotency_key"] + ":retry:1"
    r3 = request(pg, analyst, "BUILD_EVENTS", params)
    assert r3["outcome"] == "ALREADY_ACTIVE" and r3["job_id"] == r2["job_id"]
    with pg.admin() as x:
        assert x.execute("SELECT count(*) n FROM lfhe.processing_jobs WHERE idempotency_key LIKE %s",
                         (r1["idempotency_key"] + "%",)).fetchone()["n"] == 2


def test_requests_without_active_prompt_fail_clearly(pg, analyst, make_user):
    # a fresh database state for the module is not available in the shared DB; check the guard via a fake module
    with pg.admin() as x:
        assert x.execute("SELECT lfhe.current_prompt_version('M99_UNKNOWN') v").fetchone()["v"] is None
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState, match="PROMPT_NOT_ACTIVE"):
            x.execute("SELECT lfhe.cr7_03_prompt('M99_UNKNOWN')")


def test_cr7_04_rejected_m07_can_be_re_requested_and_shows_why(pg, prompts, analyst):
    c = pclaim(pg, "A blog said 3 radars are at Fort Aster.", "3 radars are at Fort Aster")
    e = human_event(pg, analyst, [c], title="Radars at Fort Aster (blog)")
    h = head(pg, e)
    vid, vh = str(h["head_version_id"]), h["head_content_hash"]
    with pg.as_user(analyst) as hu:
        hu.execute("SELECT lfhe.promote_event_version(%s, %s, 'REQUEST_ASSESSMENT', 'analyst requests assessment')", (vid, vh))
    ctx = {"event_version_id": vid, "event_version_hash": vh, "report_mode": "LIVE", "information_cutoff": NOW().isoformat()}
    park_pending(pg)
    from test_p4_assessments import st
    lie = [st("AS1", "KNOWN_FACT", "3 radars are at Fort Aster.", claims=[c], attr=False)]
    ok = [st("AS1", "KNOWN_FACT", "A blog said 3 radars are at Fort Aster.", claims=[c], attr_text="A blog said")]
    a = request(pg, analyst, "ASSESS_EVENT", ctx)
    assert a["outcome"] == "ENQUEUED"
    assert work(pg, lambda m, env: m07_out(env, lie)) == 1
    assert job(pg, a["job_id"])["status"] == "HUMAN_REVIEW"
    with pg.as_user(analyst) as hu:                          # the UI can now show WHY
        d = hu.execute("SELECT outcome, rejection_reasons FROM lfhe.job_rejection_detail WHERE job_id=%s",
                       (a["job_id"],)).fetchall()
    assert any(r["outcome"] == "OUTPUT_REJECTED" and "ATTRIBUTION_CONTRADICTS_WORKFLOW_STATE:AS1" in r["rejection_reasons"]
               for r in d)
    r2 = request(pg, analyst, "ASSESS_EVENT", ctx, reason="analyst re-requests after the rejected output")
    assert r2["outcome"] == "REQUEUED_AFTER_REJECTION" and r2["job_id"] != a["job_id"]
    assert request(pg, analyst, "ASSESS_EVENT", ctx)["outcome"] == "ALREADY_ACTIVE"
    assert work(pg, lambda m, env: m07_out(env, ok)) == 1
    assert job(pg, r2["job_id"])["status"] == "SUCCESS"
    assert request(pg, analyst, "ASSESS_EVENT", ctx)["outcome"] == "ALREADY_COMPLETED"   # recorded → no more re-runs
