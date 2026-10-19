"""P3-02 — persistent events, M05 proposal materialisation and human structural
actions (Phase 3 Addendum §5–§11, §14; required tests 10–28)."""
import json

import psycopg
import pytest

from lineage_support import (candidate_event, event_run, grounded_claim, head, ingest_events, proposal,
                             version_claims)

pytestmark = pytest.mark.db

T1 = "The air force said on 3 October that 4 tanker aircraft arrived at Base North."
T2 = "Officials said 2 more tanker aircraft arrived at Base North on 5 October."
T3 = "The navy said 3 patrol drones were tested off the coast."
T4 = "A ministry spokesman denied that any tanker aircraft had arrived at Base North."


@pytest.fixture
def analyst(make_user):
    return make_user("ANALYST")


def c1(pg):
    return grounded_claim(pg, T1, "4 tanker aircraft arrived at Base North", event_date="2026-10-03",
                          event_date_confidence="MODERATE", locations=["Base North"])


def create(pg, claims, **cand):
    run = event_run(pg, claims)
    out = ingest_events(pg, run, [proposal("CREATE_NEW_EVENT", claims=claims,
                                           event_candidate=candidate_event(claims, **cand))])
    assert out["outcome"] == "PROPOSALS_RECORDED", out
    return out["materialised"][0]["event_id"], run


def heads_of(pg, *events):
    return {str(e): str(head(pg, e)["head_version_id"]) for e in events}


def human_event(pg, user, claims, title="Human event"):
    with pg.as_user(user) as h:
        return str(h.execute("SELECT lfhe.create_event(%s::jsonb, 'analyst created event') AS id",
                             (json.dumps(candidate_event(claims, title=title)),)).fetchone()["id"])


# --- test 10 -------------------------------------------------------------------
def test_create_new_event_materialises_only_a_candidate(pg):
    a = c1(pg)
    event, run = create(pg, [a], event_date_start="2026-10-03", event_date_confidence="MODERATE", locations=["Base North"])
    h = head(pg, event)
    assert h["state"] == "CANDIDATE" and h["origin"] == "AI" and h["head_version_no"] == 1 and h["head_pending_review"]
    with pg.admin() as x:
        v = x.execute("SELECT * FROM lfhe.event_versions WHERE id=%s", (h["head_version_id"],)).fetchone()
        assert v["origin"] == "AI" and str(v["created_by_model_run_id"]) == run
        with pytest.raises(psycopg.errors.CheckViolation):   # the worker can never write anything but the initial CANDIDATE
            x.execute("INSERT INTO lfhe.event_state_history (event_id, old_state, new_state, actor_type, reason) "
                      "VALUES (%s, 'CANDIDATE', 'ACTIVE', 'WORKER', 'promote')", (event,))
    with pg.worker() as w, pytest.raises(psycopg.errors.InsufficientPrivilege):
        w.execute("SELECT lfhe.set_event_state(%s, 'CANDIDATE', 'ACTIVE', 'worker promotes')", (event,))


# --- tests 11, 12, 14, 26 --------------------------------------------------------
def test_update_creates_a_new_immutable_version_and_keeps_the_old_one(pg):
    a = c1(pg)
    event, _ = create(pg, [a])
    v1 = head(pg, event)
    b = grounded_claim(pg, T2, "2 more tanker aircraft arrived at Base North", event_date="2026-10-05",
                       event_date_confidence="MODERATE", locations=["Base North"])
    run = event_run(pg, [a, b], context_events=[event])
    out = ingest_events(pg, run, [proposal("UPDATE_EXISTING_EVENT", target=event, target_version=v1["head_version_id"],
                                           claims=[b], event_candidate=candidate_event(
                                               [a, b], roles={b["claim_id"]: "UPDATES"},
                                               event_date_start="2026-10-03", event_date_end="2026-10-05",
                                               event_date_confidence="MODERATE", locations=["Base North"]))])
    assert out["versions_created"] == 1 and out["events_created"] == 0      # new reporting updates, no new event
    v2 = head(pg, event)
    assert v2["head_version_no"] == 2 and v2["head_content_hash"] != v1["head_content_hash"]
    assert version_claims(pg, v1["head_version_id"]) == {a["claim_id"]: "SUPPORTS"}           # old membership intact
    assert version_claims(pg, v2["head_version_id"]) == {a["claim_id"]: "SUPPORTS", b["claim_id"]: "UPDATES"}
    with pg.admin() as x:
        assert x.execute("SELECT lfhe.event_version_stored_hash(%s) h", (v1["head_version_id"],)).fetchone()["h"] == v1["head_content_hash"]


def test_ai_update_cannot_drop_claims_existing_ones_are_carried_forward(pg):
    """No silent claim loss: an AI update that omits an existing claim keeps it (migration 2100);
    existing claims need not be run inputs (they reach the model as context)."""
    a = c1(pg)
    event, _ = create(pg, [a])
    b = grounded_claim(pg, T2, "2 more tanker aircraft arrived at Base North")
    v1 = head(pg, event)["head_version_id"]
    run = event_run(pg, [b], context_events=[event])                 # only the new claim is an input
    out = ingest_events(pg, run, [proposal("UPDATE_EXISTING_EVENT", target=event, target_version=v1, claims=[b],
                                           event_candidate={**candidate_event([b]),
                                                            "claims": [{"claim_id": b["claim_id"], "role": "UPDATES"}]})])
    assert out["outcome"] == "PROPOSALS_RECORDED"
    assert version_claims(pg, head(pg, event)["head_version_id"]) == {a["claim_id"]: "SUPPORTS", b["claim_id"]: "UPDATES"}


@pytest.mark.parametrize("mutate, reason", [
    (lambda cand, a, b, v: {**cand, "claims": [{"claim_id": a["claim_id"], "role": "CONTEXTUALISES"},
                                                {"claim_id": b["claim_id"], "role": "SUPPORTS"}]},
     "AI_UPDATE_MAY_NOT_REMOVE_OR_RECAST_CLAIMS"),
    (lambda cand, a, b, v: {**cand, "event_date_start": "2026-10-11"}, "EVENT_DATE_NOT_FROM_CLAIMS"),   # e.g. publication date
    (lambda cand, a, b, v: {**cand, "locations": ["Capital City"]}, "EVENT_LOCATION_NOT_FROM_CLAIMS"),
    (lambda cand, a, b, v: {**cand, "event_type": "RUMOUR"}, "EVENT_TYPE_NOT_ALLOWED"),
])
def test_invalid_ai_updates_reject_the_whole_output(pg, mutate, reason):
    a = c1(pg)
    event, _ = create(pg, [a])
    b = grounded_claim(pg, T2, "2 more tanker aircraft arrived at Base North")
    v1 = head(pg, event)["head_version_id"]
    run = event_run(pg, [a, b], context_events=[event])
    cand = mutate(candidate_event([a, b]), a, b, v1)
    out = ingest_events(pg, run, [proposal("UPDATE_EXISTING_EVENT", target=event, target_version=v1, claims=[b],
                                           event_candidate=cand)])
    assert out["outcome"] == "OUTPUT_REJECTED" and reason in out["rejection_reasons"]
    assert head(pg, event)["head_version_no"] == 1


def test_stale_or_unsupplied_targets_are_rejected(pg):
    a = c1(pg)
    event, _ = create(pg, [a])
    b = grounded_claim(pg, T2, "2 more tanker aircraft arrived")
    v1 = head(pg, event)["head_version_id"]
    run = event_run(pg, [a, b])                        # event not supplied as context
    out = ingest_events(pg, run, [proposal("UPDATE_EXISTING_EVENT", target=event, target_version=v1, claims=[b],
                                           event_candidate=candidate_event([a, b]))])
    assert any(r.startswith("EVENT_NOT_IN_MODEL_RUN_CONTEXT_OR_STALE") for r in out["rejection_reasons"])
    run2 = event_run(pg, [a, b], context_events=[event])
    ingest_events(pg, run2, [proposal("UPDATE_EXISTING_EVENT", target=event, target_version=v1, claims=[b],
                                      event_candidate=candidate_event([a, b]))])
    assert head(pg, event)["head_version_no"] == 2
    out = ingest_events(pg, event_run(pg, [a, b], context_events=[event]), [
        proposal("UPDATE_EXISTING_EVENT", target=event, target_version=v1, claims=[b], event_candidate=candidate_event([a, b]))])
    assert "TARGET_VERSION_NOT_CURRENT_HEAD" in out["rejection_reasons"]


# --- test 15 ---------------------------------------------------------------------
def test_publication_date_is_not_event_date(pg):
    a = grounded_claim(pg, "Published today: the brigade received 4 radars last spring.", "the brigade received 4 radars",
                       event_date="2026-04", event_date_confidence="LOW")
    with pg.admin() as x:   # the snapshot is retrieved today; the claim's event date is April
        assert x.execute("SELECT system_retrieval_datetime::date = current_date AS today FROM lfhe.article_snapshots "
                         "WHERE id=%s", (a["snapshot_id"],)).fetchone()["today"]
    run = event_run(pg, [a])
    today = __import__("datetime").date.today().isoformat()
    bad = ingest_events(pg, run, [proposal("CREATE_NEW_EVENT", claims=[a], event_candidate=candidate_event(
        [a], event_date_start=today, event_date_confidence="HIGH"))])
    assert "EVENT_DATE_NOT_FROM_CLAIMS" in bad["rejection_reasons"]
    ok = ingest_events(pg, event_run(pg, [a]), [proposal("CREATE_NEW_EVENT", claims=[a], event_candidate=candidate_event(
        [a], event_date_start="2026-04", event_date_confidence="LOW"))])
    assert ok["events_created"] == 1


# --- tests 13, 16–19: suggestions never act; contradictions are kept ---------------
def test_suggestions_never_perform_structural_actions(pg):
    a, b = c1(pg), grounded_claim(pg, T3, "3 patrol drones were tested off the coast")
    e1, _ = create(pg, [a])
    e2, _ = create(pg, [b], event_type="TEST")       # same week, different development
    before = heads_of(pg, e1, e2)
    run = event_run(pg, [a, b], context_events=[e1, e2])
    out = ingest_events(pg, run, [
        proposal("SUGGEST_MERGE", target=e1, related=[e2], reason="same week and same air force"),
        proposal("SUGGEST_SPLIT", target=e1),
        proposal("SUGGEST_SUPERSEDE", target=e1, related=[e2]),
        proposal("KEEP_SEPARATE", related=[e1, e2])])
    assert out["outcome"] == "PROPOSALS_RECORDED" and out["events_created"] == out["versions_created"] == 0
    assert heads_of(pg, e1, e2) == before
    with pg.admin() as x:
        assert x.execute("SELECT count(*) n FROM lfhe.event_relationships WHERE from_event_id IN (%s, %s) "
                         "OR to_event_id IN (%s, %s)", (e1, e2, e1, e2)).fetchone()["n"] == 0
        assert x.execute("SELECT count(*) n FROM lfhe.event_actions a WHERE a.proposal_id IN "
                         "(SELECT id FROM lfhe.event_proposals WHERE model_run_id=%s)", (run,)).fetchone()["n"] == 0
    assert head(pg, e1)["successor_event_id"] is None and head(pg, e2)["successor_event_id"] is None


def test_contradiction_is_preserved_through_versions_and_merge(pg, analyst):
    a = c1(pg)
    d = grounded_claim(pg, T4, "denied that any tanker aircraft had arrived at Base North", locations=["Base North"])
    e1, _ = create(pg, [a, d], roles={d["claim_id"]: "CONTRADICTS"})
    v = head(pg, e1)
    assert version_claims(pg, v["head_version_id"])[d["claim_id"]] == "CONTRADICTS"
    e2 = human_event(pg, analyst, [d])                # the denial also stands alone as SUPPORTS
    with pg.as_user(analyst) as h:
        new = h.execute("SELECT lfhe.merge_events(%s, ARRAY[%s]::uuid[], %s::jsonb, 'same arrival, one denial') AS v",
                        (e1, e2, json.dumps(heads_of(pg, e1, e2)))).fetchone()["v"]
    assert version_claims(pg, new)[d["claim_id"]] == "CONTRADICTS"   # never weakened to SUPPORTS
    with pg.worker() as w, pytest.raises(psycopg.errors.InsufficientPrivilege):
        w.execute("SELECT lfhe.set_event_state(%s, 'CANDIDATE', 'CONTESTED', 'worker contests')", (e1,))
    with pg.as_user(analyst) as h:
        h.execute("SELECT lfhe.set_event_state(%s, 'CANDIDATE', 'CONTESTED', 'official denial vs report')", (e1,))
    assert head(pg, e1)["state"] == "CONTESTED"


# --- tests 20–23 ----------------------------------------------------------------
def non_humans(pg, make_user):
    viewer, admin = make_user("VIEWER"), make_user("ADMIN")
    return (pg.worker, pg.as_service_role, pg.as_anon, lambda: pg.as_user(viewer), lambda: pg.as_user(admin))


def test_merge_is_human_only_and_preserves_ids_versions_and_claims(pg, analyst, make_user):
    a, b = c1(pg), grounded_claim(pg, T2, "2 more tanker aircraft arrived at Base North")
    e1, _ = create(pg, [a])
    e2, _ = create(pg, [b])
    heads = heads_of(pg, e1, e2)
    for conn in non_humans(pg, make_user):
        with conn() as x, pytest.raises(psycopg.errors.InsufficientPrivilege):
            x.execute("SELECT lfhe.merge_events(%s, ARRAY[%s]::uuid[], %s::jsonb, 'not allowed')", (e1, e2, json.dumps(heads)))
    with pg.as_user(analyst) as h:
        with pytest.raises(psycopg.errors.SerializationFailure, match="EVENT_HEAD_STALE"):
            h.execute("SELECT lfhe.merge_events(%s, ARRAY[%s]::uuid[], %s::jsonb, 'stale view')",
                      (e1, e2, json.dumps({**heads, e2: heads[e1]})))
        new = h.execute("SELECT lfhe.merge_events(%s, ARRAY[%s]::uuid[], %s::jsonb, 'same arrival reported twice') AS v",
                        (e1, e2, json.dumps(heads))).fetchone()["v"]
    assert set(version_claims(pg, new)) == {a["claim_id"], b["claim_id"]}
    assert str(head(pg, e2)["head_version_id"]) == heads[e2] and head(pg, e2)["structural_status"] == "MERGED_INTO"
    with pg.admin() as x:
        assert str(x.execute("SELECT lfhe.resolve_event(%s) r", (e2,)).fetchone()["r"]) == e1
        rel = x.execute("SELECT * FROM lfhe.event_relationships WHERE from_event_id=%s", (e2,)).fetchone()
        assert (rel["relationship_type"], str(rel["to_version_id"]), rel["from_version_hash"]) == (
            "MERGED_INTO", str(new), head(pg, e2)["head_content_hash"])
        assert x.execute("SELECT count(*) n FROM lfhe.event_claim_redistributions WHERE action_id=%s",
                         (rel["action_id"],)).fetchone()["n"] == 1
        act = x.execute("SELECT * FROM lfhe.event_actions WHERE id=%s", (rel["action_id"],)).fetchone()
        assert act["action"] == "MERGE" and act["actor_user_id"] == analyst
        assert x.execute("SELECT count(*) n FROM lfhe.audit_log WHERE event_type='EVENT_MERGED' AND object_id=%s",
                         (str(act["id"]),)).fetchone()["n"] == 1
    with pg.as_user(analyst) as h, pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState, match="EVENT_NOT_OPEN"):
        h.execute("SELECT lfhe.update_event(%s, %s, %s::jsonb, 'edit a merged event')",
                  (e2, heads[e2], json.dumps(candidate_event([b]))))


def test_split_is_human_only_preserves_parent_and_redistributes_every_claim(pg, analyst, make_user):
    a, b, c = c1(pg), grounded_claim(pg, T2, "2 more tanker aircraft arrived"), grounded_claim(pg, T3, "3 patrol drones were tested")
    parent, _ = create(pg, [a, b, c])
    hv = head(pg, parent)["head_version_id"]
    spec = {"children": [candidate_event([c], title="Drone test", event_type="TEST")],
            "retained": candidate_event([a, b], title="Tanker arrivals")}
    for conn in non_humans(pg, make_user):
        with conn() as x, pytest.raises(psycopg.errors.InsufficientPrivilege):
            x.execute("SELECT lfhe.split_event(%s, %s, %s::jsonb, 'not allowed')", (parent, hv, json.dumps(spec)))
    with pg.as_user(analyst) as h:
        with pytest.raises(psycopg.errors.CheckViolation, match="SPLIT_WOULD_DROP_CLAIMS"):
            h.execute("SELECT lfhe.split_event(%s, %s, %s::jsonb, 'drops b')",
                      (parent, hv, json.dumps({**spec, "retained": candidate_event([a])})))
        stranger = grounded_claim(pg, T4, "denied that any tanker aircraft had arrived")
        with pytest.raises(psycopg.errors.CheckViolation, match="SPLIT_INTRODUCES_FOREIGN_CLAIMS"):
            h.execute("SELECT lfhe.split_event(%s, %s, %s::jsonb, 'adds a stranger')",
                      (parent, hv, json.dumps({**spec, "children": [candidate_event([c, stranger])]})))
        out = h.execute("SELECT lfhe.split_event(%s, %s, %s::jsonb, 'two distinct developments') AS r",
                        (parent, hv, json.dumps(spec))).fetchone()["r"]
    [child] = out["children"]
    assert version_claims(pg, child["version_id"]) == {c["claim_id"]: "SUPPORTS"}
    assert set(version_claims(pg, out["retained_version_id"])) == {a["claim_id"], b["claim_id"]}
    assert set(version_claims(pg, hv)) == {a["claim_id"], b["claim_id"], c["claim_id"]}         # history intact
    with pg.admin() as x:
        rel = x.execute("SELECT * FROM lfhe.event_relationships WHERE from_event_id=%s", (parent,)).fetchone()
        assert rel["relationship_type"] == "SPLIT_INTO" and str(rel["to_event_id"]) == child["event_id"]
        moved = {(str(r["claim_id"]), str(r["to_event_id"])) for r in x.execute(
            "SELECT * FROM lfhe.event_claim_redistributions WHERE action_id=%s", (out["action_id"],))}
        assert moved == {(c["claim_id"], child["event_id"]), (a["claim_id"], parent), (b["claim_id"], parent)}
        assert str(x.execute("SELECT lfhe.resolve_event(%s) r", (parent,)).fetchone()["r"]) == parent    # parent remains


def test_supersede_is_human_only_and_old_references_resolve(pg, analyst, make_user):
    a, b = c1(pg), grounded_claim(pg, T2, "2 more tanker aircraft arrived")
    old, _ = create(pg, [a])
    new = human_event(pg, analyst, [a, b], title="Tanker arrivals (consolidated)")
    heads = heads_of(pg, old, new)
    for conn in non_humans(pg, make_user):
        with conn() as x, pytest.raises(psycopg.errors.InsufficientPrivilege):
            x.execute("SELECT lfhe.supersede_event(%s, %s, %s::jsonb, 'not allowed')", (old, new, json.dumps(heads)))
    with pg.as_user(analyst) as h:
        h.execute("SELECT lfhe.supersede_event(%s, %s, %s::jsonb, 'consolidated representation')", (old, new, json.dumps(heads)))
    with pg.admin() as x:
        assert str(x.execute("SELECT lfhe.resolve_event(%s) r", (old,)).fetchone()["r"]) == new
        assert x.execute("SELECT count(*) n FROM lfhe.event_versions WHERE event_id=%s", (old,)).fetchone()["n"] == 1
    assert head(pg, old)["structural_status"] == "SUPERSEDED_BY" and str(head(pg, old)["head_version_id"]) == heads[old]


def test_reject_keeps_history(pg, analyst, make_user):
    a = c1(pg)
    event, _ = create(pg, [a])
    v = head(pg, event)
    for conn in non_humans(pg, make_user):
        with conn() as x, pytest.raises(psycopg.errors.InsufficientPrivilege):
            x.execute("SELECT lfhe.reject_event(%s, 'CANDIDATE', 'not allowed')", (event,))
    with pg.as_user(analyst) as h:
        h.execute("SELECT lfhe.reject_event(%s, 'CANDIDATE', 'not an air-domain event')", (event,))
    h2 = head(pg, event)
    assert h2["state"] == "REJECTED" and h2["head_version_id"] == v["head_version_id"]
    with pg.admin() as x:
        states = [r["new_state"] for r in x.execute("SELECT new_state FROM lfhe.event_state_history WHERE event_id=%s "
                                                     "ORDER BY seq", (event,))]
        assert states == ["CANDIDATE", "REJECTED"]
    b = grounded_claim(pg, T2, "2 more tanker aircraft arrived")
    out = ingest_events(pg, event_run(pg, [a, b], context_events=[event]), [proposal(
        "UPDATE_EXISTING_EVENT", target=event, target_version=v["head_version_id"], claims=[b],
        event_candidate=candidate_event([a, b]))])
    assert "TARGET_EVENT_NOT_OPEN" in out["rejection_reasons"]


# --- tests 24, 25 ---------------------------------------------------------------
def test_event_versions_are_immutable_and_hash_verified(pg):
    a = c1(pg)
    event, _ = create(pg, [a])
    v = head(pg, event)
    with pg.admin() as x:
        for sql in ("UPDATE lfhe.event_versions SET title='changed' WHERE id=%s",
                    "DELETE FROM lfhe.event_versions WHERE id=%s",
                    "DELETE FROM lfhe.event_claims WHERE event_version_id=%s"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                x.execute(sql, (v["head_version_id"],))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            x.execute("DELETE FROM lfhe.events WHERE id=%s", (event,))
    # a forged row with a wrong hash cannot be committed (deferred verification)
    with pg.admin(autocommit=False) as x:
        x.execute("INSERT INTO lfhe.event_versions (event_id, version_no, previous_version_id, title, description, "
                  "event_type, event_date_confidence, origin, created_by_model_run_id, content_hash) "
                  "SELECT event_id, 2, id, 'Forged', 'forged', 'OTHER', 'UNKNOWN', 'AI', created_by_model_run_id, "
                  "repeat('a', 64) FROM lfhe.event_versions WHERE id=%s", (v["head_version_id"],))
        x.execute("INSERT INTO lfhe.event_claims SELECT id, %s, 'SUPPORTS' FROM lfhe.event_versions "
                  "WHERE event_id=%s AND version_no=2", (a["claim_id"], event))
        with pytest.raises(psycopg.errors.CheckViolation, match="EVENT_VERSION_HASH_MISMATCH"):
            x.commit()


def test_material_change_changes_the_canonical_hash(pg):
    with pg.admin() as x:
        h = lambda fields, claims: x.execute(
            "SELECT lfhe.event_version_hash('11111111-1111-4111-8111-111111111111', 2, NULL, %s::jsonb, %s::jsonb) h",
            (json.dumps(fields), json.dumps(claims))).fetchone()["h"]
        base = {"title": "T", "description": "D", "event_type": "DELIVERY", "event_date_start": None,
                "event_date_end": None, "event_date_confidence": "UNKNOWN", "locations": ["A", "B"]}
        claims = [{"claim_id": "c1", "role": "SUPPORTS"}, {"claim_id": "c2", "role": "SUPPORTS"}]
        ref = h(base, claims)
        assert h({**base, "locations": ["B", "A"]}, list(reversed(claims))) == ref        # order-independent
        for changed in ({**base, "description": "D2"}, {**base, "event_type": "TEST"},
                        {**base, "event_date_start": "2026-10-03"}, {**base, "locations": ["A"]}):
            assert h(changed, claims) != ref
        assert h(base, claims[:1]) != ref and h(base, [claims[0], {**claims[1], "role": "CONTRADICTS"}]) != ref


# --- tests 27, 28 ---------------------------------------------------------------
def test_failed_or_rejected_m05_runs_leave_no_authoritative_state(pg):
    a = c1(pg)
    with pg.admin() as x:
        before = x.execute("SELECT (SELECT count(*) FROM lfhe.events) e, (SELECT count(*) FROM lfhe.event_versions) v").fetchone()
    for status in ("SCHEMA_VALIDATION_FAILED", "PROVIDER_ERROR"):
        run = event_run(pg, [a], status=status)
        out = ingest_events(pg, run, [proposal("CREATE_NEW_EVENT", claims=[a], event_candidate=candidate_event([a]))])
        assert out["outcome"] == status
    # one valid and one invalid proposal: nothing at all is materialised
    run = event_run(pg, [a])
    out = ingest_events(pg, run, [proposal("CREATE_NEW_EVENT", claims=[a], event_candidate=candidate_event([a])),
                                  proposal("CREATE_NEW_EVENT", claims=[a], event_candidate=candidate_event([a], event_type="X"))])
    assert out["outcome"] == "OUTPUT_REJECTED"
    with pg.admin() as x:
        after = x.execute("SELECT (SELECT count(*) FROM lfhe.events) e, (SELECT count(*) FROM lfhe.event_versions) v").fetchone()
    assert after == before


def test_claims_outside_input_or_cutoff_are_rejected(pg):
    from lineage_support import PAST
    a = c1(pg)
    outsider = grounded_claim(pg, T3, "3 patrol drones were tested")
    out = ingest_events(pg, event_run(pg, [a]), [proposal("CREATE_NEW_EVENT", claims=[outsider],
                                                          event_candidate=candidate_event([outsider]))])
    assert any(r.startswith("CLAIM_NOT_IN_MODEL_RUN_INPUT") for r in out["rejection_reasons"])
    out = ingest_events(pg, event_run(pg, [a], cutoff=PAST), [proposal("CREATE_NEW_EVENT", claims=[a],
                                                                       event_candidate=candidate_event([a]))])
    assert any(r.startswith("CLAIM_NOT_CUTOFF_ELIGIBLE") for r in out["rejection_reasons"])


def test_human_review_of_ai_version_is_hash_bound(pg, analyst):
    a = c1(pg)
    event, _ = create(pg, [a])
    v = head(pg, event)
    with pg.as_user(analyst) as h:
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            h.execute("SELECT lfhe.review_event_version(%s, %s, 'APPROVE', 'looks right')", (v["head_version_id"], "0" * 64))
        h.execute("SELECT lfhe.review_event_version(%s, %s, 'APPROVE', 'checked against both claims')",
                  (v["head_version_id"], v["head_content_hash"]))
    assert head(pg, event)["head_review_decision"] == "APPROVE" and not head(pg, event)["head_pending_review"]
