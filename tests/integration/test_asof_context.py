"""CG3-01 — as-of (knowledge-bound) lineage and event context (migration 2300).

Timeline used throughout (all processing happens *now*, i.e. after the cutoff):
  PRE  = evidence publicly available before the cutoff
  CUT  = REPLAY information_cutoff
  POST = evidence publicly available after the cutoff (but before now)
"""
import json
from datetime import datetime

import psycopg
import pytest

from lfhe_orchestrator.event_inputs import build_m04_inputs, build_m05_inputs
from lineage_support import (candidate_event, grounded_claim, head, ingest_events, ingest_lineage, lineage_run,
                             proposal, proposals, rel, version_claims)
from claims_support import make_model_run

pytestmark = pytest.mark.db
PRE, CUT, POST = "2026-01-10T08:00:00+00:00", "2026-03-01T00:00:00+00:00", "2026-05-10T08:00:00+00:00"
CUT_DT = datetime.fromisoformat(CUT)


@pytest.fixture
def analyst(make_user):
    return make_user("ANALYST")


def claim(pg, text, exact, when, **kw):
    kw.setdefault("claim_type", "DEPLOYMENT")
    return grounded_claim(pg, text, exact, available_at=when, **kw)


def human_event(pg, user, claims, *, title, description="Synthetic as-of event.", locations=(), roles=None, etype="DEPLOYMENT"):
    with pg.as_user(user) as h:
        return str(h.execute("SELECT lfhe.create_event(%s::jsonb, 'as-of test: analyst creates') AS e", (json.dumps({
            "title": title, "description": description, "event_type": etype, "locations": list(locations),
            "claims": [{"claim_id": c["claim_id"], "role": (roles or {}).get(c["claim_id"], "SUPPORTS")} for c in claims]}),)
        ).fetchone()["e"])


def human_update(pg, user, event, claims, *, title, description, locations=()):
    with pg.as_user(user) as h:
        return str(h.execute("SELECT lfhe.update_event(%s, %s, %s::jsonb, 'as-of test: later reporting') AS v", (
            event, str(head(pg, event)["head_version_id"]), json.dumps({
                "title": title, "description": description, "event_type": "DEPLOYMENT", "locations": list(locations),
                "claims": [{"claim_id": c["claim_id"], "role": "SUPPORTS"} for c in claims]}))).fetchone()["v"])


def m05_context(pg, probe, mode="REPLAY", cutoff=CUT_DT):
    with pg.worker() as c:
        x = build_m05_inputs(c, [probe["claim_id"]], report_mode=mode, information_cutoff=cutoff)
    return {i.content["event_id"]: i for i in x.context if i.object_type == "event_version"}, x


def asof(pg, event, mode="REPLAY", cutoff=CUT):
    with pg.worker() as c:
        return c.execute("SELECT * FROM lfhe.event_asof(%s, %s, %s)", (event, mode, cutoff)).fetchone()


# --- 1–3: v1 from pre-cutoff evidence, v2 adds post-cutoff claim and new fields -----
def test_replay_sees_only_the_cutoff_eligible_version_never_later_fields(pg, analyst):
    a = claim(pg, "Northland deployed 4 jets to Fort Aster.", "Northland deployed 4 jets to Fort Aster", PRE,
              locations=["Fort Aster"])
    event = human_event(pg, analyst, [a], title="Jets to Fort Aster (v1)", description="Initial report.",
                        locations=["Fort Aster"])
    v1 = str(head(pg, event)["head_version_id"])
    b = claim(pg, "Northland moved the jets on to Port Brill.", "Northland moved the jets on to Port Brill", POST,
              locations=["Port Brill"])
    v2 = human_update(pg, analyst, event, [a, b], title="Jets relocated to Port Brill (v2)",
                      description="LATER-ONLY description.", locations=["Port Brill"])
    probe = claim(pg, "Northland jets were seen at Fort Aster.", "Northland jets were seen at Fort Aster", PRE,
                  locations=["Fort Aster"])
    ctx, x = m05_context(pg, probe)
    item = ctx[event]
    assert item.object_id == v1 and item.content["version_no"] == 1
    assert item.content["title"] == "Jets to Fort Aster (v1)" and item.content["locations"] == ["Fort Aster"]
    assert {c["claim_id"] for c in item.content["claims"]} == {a["claim_id"]}
    blob = json.dumps([i.content for i in x.context] + [i.content for i in x.inputs])
    for later in ("(v2)", "LATER-ONLY", "Port Brill", b["claim_id"], v2):
        assert later not in blob
    # LIVE now sees the current head
    live, _ = m05_context(pg, probe, mode="LIVE", cutoff=datetime.fromisoformat("2100-01-01T00:00:00+00:00"))
    assert live[event].object_id == v2


# --- 4: later CONFIRMED / REJECTED does not leak backwards; 7: later processing on eligible evidence does
def test_later_state_does_not_leak_backwards_but_later_processing_on_eligible_evidence_counts(pg, analyst):
    a = claim(pg, "Northland stationed 2 tankers at Fort Aster.", "Northland stationed 2 tankers at Fort Aster", PRE)
    e_late = human_event(pg, analyst, [a], title="Tankers at Fort Aster")
    b = claim(pg, "Officials confirmed the tankers left Fort Aster.", "Officials confirmed the tankers left Fort Aster", POST)
    human_update(pg, analyst, e_late, [a, b], title="Tankers left Fort Aster", description="Confirmed later.")
    with pg.as_user(analyst) as h:
        h.execute("SELECT lfhe.set_event_state(%s, 'ACTIVE', 'CONFIRMED', 'confirmed with the later report')", (e_late,))
    assert asof(pg, e_late)["state"] == "ACTIVE"                       # CONFIRMED was bound to v2 (post-cutoff)
    assert asof(pg, e_late, "LIVE", "2100-01-01")["state"] == "CONFIRMED"
    with pg.as_user(analyst) as h:
        h.execute("SELECT lfhe.reject_event(%s, 'CONFIRMED', 'rejected after the later report')", (e_late,))
    r = asof(pg, e_late)
    assert r["state"] == "ACTIVE" and r["is_open"]                     # REJECTED does not leak backwards
    # 7: a decision taken now (after the cutoff) on cutoff-eligible evidence only is usable in REPLAY
    c = claim(pg, "Northland stationed 3 drones at Fort Aster.", "Northland stationed 3 drones at Fort Aster", PRE)
    e_ok = human_event(pg, analyst, [c], title="Drones at Fort Aster")
    with pg.as_user(analyst) as h:
        h.execute("SELECT lfhe.set_event_state(%s, 'ACTIVE', 'CONFIRMED', 'confirmed on the pre-cutoff report')", (e_ok,))
    assert asof(pg, e_ok)["state"] == "CONFIRMED"


# --- 5: a later MERGE / SUPERSEDE does not alter the earlier replay context -----------
def test_later_merge_and_supersede_do_not_alter_the_replay(pg, analyst):
    a = claim(pg, "Northland flew 2 patrols over Fort Aster.", "Northland flew 2 patrols over Fort Aster", PRE)
    late = claim(pg, "A later report says the patrols were one sortie.", "the patrols were one sortie", POST)
    target = human_event(pg, analyst, [a], title="Patrols over Fort Aster")
    source = human_event(pg, analyst, [late], title="One sortie (later report)")
    heads = {e: str(head(pg, e)["head_version_id"]) for e in (target, source)}
    with pg.as_user(analyst) as h:
        merged = str(h.execute("SELECT lfhe.merge_events(%s, ARRAY[%s]::uuid[], %s::jsonb, 'same flights') AS v",
                               (target, source, json.dumps(heads))).fetchone()["v"])
    r = asof(pg, target)
    assert r["version_id"] != merged and str(r["version_id"]) == heads[target] and r["is_open"]
    assert asof(pg, source) is None                                     # known only from post-cutoff evidence
    old = human_event(pg, analyst, [claim(pg, "Northland tested a radar at Fort Aster.", "Northland tested a radar at Fort Aster", PRE)],
                      title="Radar test at Fort Aster")
    repl = human_event(pg, analyst, [claim(pg, "The radar test was a full trial, a later report says.", "The radar test was a full trial", POST)],
                       title="Radar trial (consolidated, later)")
    with pg.as_user(analyst) as h:
        h.execute("SELECT lfhe.supersede_event(%s, %s, %s::jsonb, 'consolidated later')",
                  (old, repl, json.dumps({e: str(head(pg, e)["head_version_id"]) for e in (old, repl)})))
    r = asof(pg, old)
    assert r["structural_status"] is None and r["is_open"]              # supersession not knowable at the cutoff
    assert asof(pg, old, "LIVE", "2100-01-01")["structural_status"] == "SUPERSEDED_BY"
    # positive control (item 7): a merge done now on pre-cutoff evidence only IS visible in replay
    p1 = human_event(pg, analyst, [claim(pg, "Northland based 5 trainers at Fort Aster.", "Northland based 5 trainers at Fort Aster", PRE)], title="Trainers A")
    p2 = human_event(pg, analyst, [claim(pg, "5 Northland trainers are based at Fort Aster.", "5 Northland trainers are based at Fort Aster", PRE)], title="Trainers B")
    with pg.as_user(analyst) as h:
        h.execute("SELECT lfhe.merge_events(%s, ARRAY[%s]::uuid[], %s::jsonb, 'same basing')",
                  (p1, p2, json.dumps({e: str(head(pg, e)["head_version_id"]) for e in (p1, p2)})))
    assert asof(pg, p2)["structural_status"] == "MERGED_INTO" and not asof(pg, p2)["is_open"]


# --- 6: lineage established with later evidence stays out of earlier replays ----------
def test_lineage_from_later_evidence_is_not_used_in_an_earlier_replay(pg, analyst):
    p = claim(pg, "The Northland air staff said 6 radars were installed.", "6 radars were installed", PRE)
    q = claim(pg, "A newspaper, citing the air staff, says 6 radars were installed.", "6 radars were installed", PRE)
    x = claim(pg, "A later wire story traces the radar report to the air staff.", "traces the radar report to the air staff", POST)
    run = lineage_run(pg, [p, q, x])                    # the model saw post-cutoff evidence
    ingest_lineage(pg, run, [rel(q, "DERIVED_REPORTING", parent_claim=p)])
    [prop] = proposals(pg, run)
    with pg.as_user(analyst) as h:
        h.execute("SELECT lfhe.decide_lineage_proposal(%s, true, 'traced by the later wire story')", (prop["id"],))
    with pg.worker() as c:
        replay = c.execute("SELECT lfhe.independence_summary_asof(%s::uuid[], 'REPLAY', %s) s",
                           ([p["claim_id"], q["claim_id"]], CUT)).fetchone()["s"]
        live = c.execute("SELECT lfhe.independence_summary_asof(%s::uuid[], 'LIVE', '2100-01-01') s",
                         ([p["claim_id"], q["claim_id"]],)).fetchone()["s"]
        m04 = build_m04_inputs(c, [p["claim_id"], q["claim_id"]], report_mode="REPLAY", information_cutoff=CUT_DT)
        m05 = build_m05_inputs(c, [p["claim_id"], q["claim_id"]], report_mode="REPLAY", information_cutoff=CUT_DT)
    assert replay["claims_with_unknown_lineage"] == 2 and replay["distinct_groups_upper_bound"] == 2
    assert live["distinct_groups_upper_bound"] == 1
    assert not [i for i in m04.context if i.object_type == "claim_lineage"]
    groups = {i.content["claim_id"]: i.content["independence_group"] for i in m05.inputs}
    assert groups[p["claim_id"]] != groups[q["claim_id"]]               # computed from the eligible lineage set only
    # the same dependence derived from pre-cutoff evidence only IS usable (processing after the cutoff)
    p2 = claim(pg, "The Northland air staff said 7 radars were installed.", "7 radars were installed", PRE)
    q2 = claim(pg, "Citing the air staff, a blog says 7 radars were installed.", "7 radars were installed", PRE)
    run2 = lineage_run(pg, [p2, q2])
    ingest_lineage(pg, run2, [rel(q2, "DERIVED_REPORTING", parent_claim=p2)])
    with pg.as_user(analyst) as h:
        h.execute("SELECT lfhe.decide_lineage_proposal(%s, true, 'the blog cites the statement')", (proposals(pg, run2)[0]["id"],))
    with pg.worker() as c:
        s = c.execute("SELECT lfhe.independence_summary_asof(%s::uuid[], 'REPLAY', %s) s",
                      ([p2["claim_id"], q2["claim_id"]], CUT)).fetchone()["s"]
    assert s["distinct_groups_upper_bound"] == 1


def test_human_recorded_lineage_needs_a_declared_evidence_bound_for_replay(pg, analyst):
    p = claim(pg, "The ministry said 8 drones were bought.", "8 drones were bought", PRE)
    q = claim(pg, "Quoting the ministry, a site says 8 drones were bought.", "8 drones were bought", PRE)
    late = claim(pg, "A later audit links the drone story to the ministry.", "links the drone story to the ministry", POST)
    spec = {"child_claim_id": q["claim_id"], "relationship_type": "DERIVED_REPORTING", "parent_claim_id": p["claim_id"]}

    def record(basis):
        with pg.as_user(analyst) as h:
            lid = h.execute("SELECT lfhe.record_claim_lineage(%s::jsonb, 'analyst read both texts') AS id",
                            (json.dumps({**spec, **({"evidence_basis": basis} if basis is not None else {})}),)).fetchone()["id"]
        with pg.worker() as c:
            out = c.execute("SELECT lfhe.lineage_usable(%s, 'REPLAY', %s) r", (lid, CUT)).fetchone()["r"]
        with pg.as_user(analyst) as h:
            h.execute("SELECT lfhe.retract_claim_lineage(%s, 'reset for the next case')", (lid,))
        return out
    assert record(None) is False                                         # no provable bound → fail closed in REPLAY
    assert record([{"object_type": "claim", "object_id": p["claim_id"]},
                   {"object_type": "claim", "object_id": q["claim_id"]}]) is True
    assert record([{"object_type": "claim", "object_id": late["claim_id"]}]) is False
    with pg.as_user(analyst) as h, pytest.raises(psycopg.errors.CheckViolation, match="EVIDENCE_BASIS_INVALID"):
        h.execute("SELECT lfhe.record_claim_lineage(%s::jsonb, 'bad basis given')", (json.dumps(
            {**spec, "evidence_basis": [{"object_type": "event", "object_id": p["claim_id"]}]}),))


def test_replay_ingestion_accepts_only_the_asof_version_and_never_materialises_on_a_later_head(pg, analyst):
    a = claim(pg, "Northland parked 3 bombers at Fort Aster.", "Northland parked 3 bombers at Fort Aster", PRE)
    event = human_event(pg, analyst, [a], title="Bombers at Fort Aster")
    v1 = str(head(pg, event)["head_version_id"])
    b = claim(pg, "The bombers later flew to Port Brill.", "The bombers later flew to Port Brill", POST)
    v2 = human_update(pg, analyst, event, [a, b], title="Bombers moved", description="Later.")
    n = claim(pg, "Northland bombers were photographed at Fort Aster.", "Northland bombers were photographed at Fort Aster", PRE)

    def run(ctx_version):
        return make_model_run(pg, "M05_EVENT_BUILDER", [("claim", n["claim_id"])], context=[("event_version", ctx_version)],
                              task_parameters={"report_mode": "REPLAY", "information_cutoff": CUT})
    ok = ingest_events(pg, run(v1), [proposal("KEEP_SEPARATE", related=[event])])
    assert ok["outcome"] == "PROPOSALS_RECORDED"
    leaked = ingest_events(pg, run(v2), [proposal("KEEP_SEPARATE", related=[event])])
    assert any(r.startswith("EVENT_NOT_IN_MODEL_RUN_CONTEXT_OR_STALE") for r in leaked["rejection_reasons"])
    upd = ingest_events(pg, run(v1), [proposal("UPDATE_EXISTING_EVENT", target=event, target_version=v2, claims=[n],
                                               event_candidate=candidate_event([n], event_type="DEPLOYMENT"))])
    assert "UPDATE_TARGET_VERSION_NOT_SUPPLIED" in upd["rejection_reasons"]
    assert set(version_claims(pg, head(pg, event)["head_version_id"])) == {a["claim_id"], b["claim_id"]}
