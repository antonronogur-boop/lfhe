"""P4-07 — persistent trends (human/manual path) and indicators (Phase 4 Addendum §17–§18;
required tests 54–59)."""
import json
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from p4_support import head, human_event, pclaim, POST
from test_p4_assessments import assess, out, setup_event, version_of
from test_p4_challenge_review import CONF_RAT, chal, challenge, review, state

pytestmark = pytest.mark.db
JUST_NOW = lambda: (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()   # noqa: E731
CONCRETE = "More than 4 tanker aircraft visible on the Fort Aster apron in commercial imagery."
VAGUE = "Monitor the situation for any changes."


@pytest.fixture(scope="module")
def m78(pg):
    from pipeline_support import activate_real_prompts
    return activate_real_prompts(pg, ("M02_CLAIM_EXTRACTOR", "M03_CLASSIFIER", "M07_INTELLIGENCE_ASSESSOR", "M08_CHALLENGER"))


@pytest.fixture
def analyst(make_user):
    return make_user("ANALYST")


def second_event(pg, analyst, when=None):
    kw = {"when": when} if when else {}
    c = pclaim(pg, "The air force said 2 more tanker aircraft arrived at Fort Aster.", "2 more tanker aircraft arrived at Fort Aster", **kw)
    e = human_event(pg, analyst, [c], title="Second tanker arrival at Fort Aster")
    h = head(pg, e)
    return e, str(h["head_version_id"]), h["head_content_hash"], c


def trend(pg, user, code, evs, asof=None, ass=(), **kw):
    p = {"code": code, "title": "Tanker build-up at Fort Aster", "description": "Synthetic Northland trend.",
         "direction": kw.pop("direction", "increasing tanker presence"), "velocity": kw.pop("velocity", "not established"),
         "uncertainty": kw.pop("uncertainty", "Two official reports only; no independent imagery."),
         "knowledge_as_of": asof or JUST_NOW(),
         "event_versions": [{"event_version_id": v, "content_hash": h} for v, h in evs],
         "assessment_versions": [{"assessment_version_id": str(a["id"]), "content_hash": a["content_hash"]} for a in ass]}
    p.update(kw)
    with pg.as_user(user) as c:
        return str(c.execute("SELECT lfhe.create_trend_version(%s::jsonb, 'analyst links two arrivals') v",
                             (json.dumps(p),)).fetchone()["v"])


def approved_assessment(pg, analyst, indicators):
    e, vid, vh, claims = setup_event(pg, analyst)
    r = assess(pg, vid, vh, lambda m, env: out(env, claims=claims, indicators=indicators))
    assert r.outcome == "ASSESSMENT_RECORDED", r
    v = version_of(pg, r.final_run_id)
    assert challenge(pg, v, lambda m, env: chal(env)).outcome == "CHALLENGE_RECORDED"
    return v, claims, (e, vid, vh)


def indicator(pg, user, code, v, **p):
    body = {"code": code, "assessment_version_id": str(v["id"]), "assessment_version_hash": v["content_hash"]}
    body.update(p)
    with pg.as_user(user) as c:
        return str(c.execute("SELECT lfhe.create_indicator_version(%s::jsonb, 'analyst makes indicator') v",
                             (json.dumps(body),)).fetchone()["v"])


def ind(local, text, cond, stmts=("AS3",), claims=()):
    return {"indicator_local_id": local, "indicator_text": text, "observable_condition": cond,
            "related_statement_local_ids": list(stmts), "supporting_claim_ids": [c["claim_id"] for c in claims]}


# --- 54, 55, 56, 57 ------------------------------------------------------------------------
def test_trend_is_separate_versioned_and_preserves_exact_event_versions(pg, m78, analyst, make_user):
    e1, v1, h1, _ = setup_event(pg, analyst, contra=False)
    e2, v2, h2, _ = second_event(pg, analyst)
    with pytest.raises(psycopg.Error, match="TREND_REQUIRES_MULTIPLE_EVENTS"):
        trend(pg, analyst, "TR-ASTER-1", [(v1, h1)])
    with pytest.raises(psycopg.Error, match="TREND_REQUIRES_MULTIPLE_EVENTS"):       # same event twice is still one event
        trend(pg, analyst, "TR-ASTER-1", [(v1, h1), (v1, h1)])
    with pytest.raises(psycopg.Error, match="VERSION_HASH_MISMATCH"):
        trend(pg, analyst, "TR-ASTER-1", [(v1, h1), (v2, "0" * 64)])
    with pytest.raises(psycopg.Error, match="TREND_UNCERTAINTY_REQUIRED"):
        trend(pg, analyst, "TR-ASTER-1", [(v1, h1), (v2, h2)], uncertainty="")
    with pytest.raises(psycopg.Error, match="TREND_DIRECTION_AND_VELOCITY_REQUIRED"):
        trend(pg, analyst, "TR-ASTER-1", [(v1, h1), (v2, h2)], velocity="")
    for conn in (pg.worker, pg.as_service_role):
        with conn() as c, pytest.raises(psycopg.Error):
            c.execute("SELECT lfhe.create_trend_version('{}'::jsonb, 'machine trend')")
    with pg.as_user(make_user("VIEWER")) as c, pytest.raises(psycopg.Error):
        c.execute("SELECT lfhe.create_trend_version('{}'::jsonb, 'viewer trend')")
    t1 = trend(pg, analyst, "TR-ASTER-1", [(v1, h1), (v2, h2)])
    t2 = trend(pg, analyst, "TR-ASTER-1", [(v1, h1), (v2, h2)], direction="stable", uncertainty="Re-read: second arrival may be a rotation.")
    with pg.admin() as x:
        rows = x.execute("SELECT id, version_no, previous_version_id, content, content_hash FROM lfhe.trend_versions "
                         "WHERE id IN (%s,%s) ORDER BY version_no", (t1, t2)).fetchall()
        assert [r["version_no"] for r in rows] == [1, 2] and str(rows[1]["previous_version_id"]) == t1
        assert rows[0]["content"]["direction"] == "increasing tanker presence" and rows[0]["content"]["velocity"] == "not established"
        mem = {(str(r["event_version_id"]), r["event_version_hash"]) for r in
               x.execute("SELECT * FROM lfhe.trend_events WHERE trend_version_id=%s", (t1,))}
        assert mem == {(v1, h1), (v2, h2)}
        # trend and event are separate objects; trend ids are not event ids
        assert x.execute("SELECT count(*) n FROM lfhe.events WHERE id IN (SELECT trend_id FROM lfhe.trend_versions WHERE id=%s)",
                         (t1,)).fetchone()["n"] == 0
        for sql in ("UPDATE lfhe.trend_versions SET content = content || '{\"direction\":\"x\"}' WHERE id=%s",
                    "DELETE FROM lfhe.trend_events WHERE trend_version_id=%s", "DELETE FROM lfhe.trend_versions WHERE id=%s"):
            with pytest.raises(psycopg.Error):
                x.execute(sql, (t1,))
        assert x.execute("SELECT count(*) n FROM lfhe.audit_log WHERE event_type='TREND_VERSION_CREATED' AND object_id IN (%s,%s)",
                         (t1, t2)).fetchone()["n"] == 2
    with pg.worker() as w:
        tid = w.execute("SELECT trend_id FROM lfhe.trend_versions WHERE id=%s", (t1,)).fetchone()["trend_id"]
        assert str(w.execute("SELECT lfhe.trend_asof(%s, 'LIVE', now() + interval '1 minute') r", (tid,)).fetchone()["r"]) == t2


def test_trend_knowledge_bound_and_cutoff(pg, m78, analyst):
    e1, v1, h1, _ = setup_event(pg, analyst, contra=False)
    e2, v2, h2, _ = second_event(pg, analyst, when=POST)
    with pytest.raises(psycopg.Error, match="EVIDENCE_POSTDATES_KNOWLEDGE_AS_OF"):
        trend(pg, analyst, "TR-ASTER-2", [(v1, h1), (v2, h2)], asof="2026-03-01T00:00:00+00:00")
    t = trend(pg, analyst, "TR-ASTER-2", [(v1, h1), (v2, h2)])
    with pg.worker() as w:
        q = "SELECT lfhe.trend_version_usable(%s, %s, %s) r"
        assert w.execute(q, (t, "LIVE", datetime.now(timezone.utc) + timedelta(minutes=1))).fetchone()["r"] is True
        assert w.execute(q, (t, "REPLAY", "2026-03-01T00:00:00+00:00")).fetchone()["r"] is False


# --- 58, 59 --------------------------------------------------------------------------------
def test_indicator_is_bound_to_approved_assessment_and_claim_evidence(pg, m78, analyst, make_user):
    v, claims, (e, vid, vh) = approved_assessment(pg, analyst, [ind("IND1", "Additional tanker arrivals", CONCRETE)])
    with pytest.raises(psycopg.Error, match="INDICATOR_ASSESSMENT_NOT_APPROVED"):
        indicator(pg, analyst, "IND-ASTER-1", v, indicator_text="Additional tanker arrivals", observable_condition=CONCRETE,
                  related_statement_local_ids=["AS3"])
    review(pg, analyst, v, "APPROVE", "LOW", CONF_RAT)
    with pg.admin() as x:
        prop = str(x.execute("SELECT id FROM lfhe.assessment_indicator_proposals WHERE assessment_version_id=%s",
                             (v["id"],)).fetchone()["id"])
    with pytest.raises(psycopg.Error, match="VERSION_HASH_MISMATCH"):
        indicator(pg, analyst, "IND-ASTER-1", dict(v, content_hash="1" * 64), source_proposal_id=prop)
    other = pclaim(pg, "A ministry said fighters left Fort Aster.", "fighters left Fort Aster")
    with pytest.raises(psycopg.Error, match="EVIDENCE_NOT_SUPPLIED"):
        indicator(pg, analyst, "IND-ASTER-1", v, source_proposal_id=prop, supporting_claim_ids=[other["claim_id"]])
    with pytest.raises(psycopg.Error, match="INDICATOR_REFERENCES_UNKNOWN_STATEMENT"):
        indicator(pg, analyst, "IND-ASTER-1", v, source_proposal_id=prop, related_statement_local_ids=["AS77"])
    for conn in (pg.worker, pg.as_service_role):
        with conn() as c, pytest.raises(psycopg.Error):
            c.execute("SELECT lfhe.create_indicator_version('{}'::jsonb, 'machine indicator')")
    i1 = indicator(pg, analyst, "IND-ASTER-1", v, source_proposal_id=prop, supporting_claim_ids=[claims[0]["claim_id"]])
    with pg.admin() as x:
        iv = x.execute("SELECT * FROM lfhe.indicator_versions WHERE id=%s", (i1,)).fetchone()
        assert (str(iv["assessment_version_id"]), iv["assessment_version_hash"], str(iv["source_proposal_id"]), iv["human_corrected"]) == \
            (str(v["id"]), v["content_hash"], prop, False)
        assert [str(r["claim_id"]) for r in x.execute("SELECT claim_id FROM lfhe.indicator_claims WHERE indicator_version_id=%s", (i1,))] \
            == [claims[0]["claim_id"]]
        assert len(iv["content"]["related_statement_ids"]) == 1
        with pytest.raises(psycopg.Error):
            x.execute("UPDATE lfhe.indicator_versions SET human_corrected=true WHERE id=%s", (i1,))
        assert x.execute("SELECT count(*) n FROM lfhe.audit_log WHERE event_type='INDICATOR_VERSION_CREATED' AND object_id=%s",
                         (i1,)).fetchone()["n"] == 1
    with pg.worker() as w:
        assert w.execute("SELECT lfhe.indicator_version_usable(%s, 'LIVE', now() + interval '1 minute') r", (i1,)).fetchone()["r"] is True


def test_vague_indicator_needs_human_correction_and_operational_is_rejected(pg, m78, analyst):
    v, claims, _ = approved_assessment(pg, analyst, [ind("IND1", "Watch Fort Aster", VAGUE)])
    review(pg, analyst, v, "APPROVE", "LOW", CONF_RAT)
    with pg.admin() as x:
        prop = str(x.execute("SELECT id FROM lfhe.assessment_indicator_proposals WHERE assessment_version_id=%s",
                             (v["id"],)).fetchone()["id"])
    with pytest.raises(psycopg.Error, match="INDICATOR_REQUIRES_HUMAN_CORRECTION: INDICATOR_VAGUE"):
        indicator(pg, analyst, "IND-ASTER-2", v, source_proposal_id=prop)
    with pytest.raises(psycopg.Error, match="INDICATOR_INVALID: INDICATOR_VAGUE"):        # a correction that is still vague
        indicator(pg, analyst, "IND-ASTER-2", v, source_proposal_id=prop, observable_condition="Watch for any further developments.")
    with pytest.raises(psycopg.Error, match="OPERATIONAL_RECOMMENDATION_PROHIBITED"):
        indicator(pg, analyst, "IND-ASTER-2", v, source_proposal_id=prop,
                  observable_condition="If 6 tankers arrive, we recommend a strike on the Fort Aster apron.")
    i = indicator(pg, analyst, "IND-ASTER-2", v, source_proposal_id=prop, observable_condition=CONCRETE)
    with pg.admin() as x:
        iv = x.execute("SELECT human_corrected, content FROM lfhe.indicator_versions WHERE id=%s", (i,)).fetchone()
    assert iv["human_corrected"] is True and iv["content"]["observable_condition"] == CONCRETE
    with pg.worker() as w:
        assert w.execute("SELECT lfhe.p4_indicator_problems('Tanker count', %s) r", (CONCRETE,)).fetchone()["r"] == []
        assert w.execute("SELECT lfhe.p4_indicator_problems('x', 'short') r").fetchone()["r"] == ["INDICATOR_NOT_OBSERVABLE"]
