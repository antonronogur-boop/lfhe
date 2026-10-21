"""P5-01 … P5-06 — report candidate pool, HUMAN selection, M09 Executive Editor, immutable
JCS-hashed report versions, length / removal review, provenance-preserving human edits
(Phase 5 Addendum §3–§19, §24, §25; required tests 1–44); scripted M09."""
import json

import psycopg
import pytest

from p5_helpers import (park_report_jobs, activate, approved_assessment, auto_items, candidates, content_of, decide, edit, freeze,
                        latest_version, m09, new_report, pool, rejected, rs, run_m09, select, statements_of, version_of_run)

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def p5(pg):
    yield activate(pg)
    park_report_jobs(pg)


@pytest.fixture
def analyst(make_user):
    return make_user("ANALYST")


def test_smoke_end_to_end(pg, p5, analyst):
    v, claims, _ = approved_assessment(pg, analyst)
    rid = new_report(pg, analyst, "RPT-SMOKE-1")
    sid, sh = select(pg, analyst, rid, [(v["id"], "KEY_JUDGMENT", 1)])
    r = run_m09(pg, sid, sh, lambda m, env: m09(env))
    assert r.outcome == "REPORT_VERSION_RECORDED", r


def kj_env_item(env, cid=None):
    c = next(x for x in pool(env) if cid is None or x["candidate_id"] == cid)
    return c, {s["statement_local_id"]: s for s in c["statements"]}


def one_item(env, stmts, cid=None, section="key_judgments", item="KJ1"):
    c, _ = kj_env_item(env, cid)
    base = {k: [] for k in ("key_judgments", "significant_developments", "indicators_warning", "trend_watch",
                            "what_to_watch", "caveats")}
    base[section] = [{"item_local_id": item, "source_candidate_id": c["candidate_id"], "statements": stmts}]
    return base


def default_kj_statements(env, cid=None, **over):
    """A valid paraphrased KJ item: AS3 judgment + AS1 fact merged, AS2 / AS4 caveats kept."""
    c, s = kj_env_item(env, cid)
    conf = c["final_analytic_confidence"]
    out = [rs(1, over.get("kj", "Northland is probably expanding air-refuelling support at Fort Aster."), "KEY_JUDGMENT",
              [s["AS3"]["assessment_statement_id"]], over.get("conf", conf), over.get("lk")),
           rs(2, over.get("fact", "The air force reported that 4 tanker aircraft arrived at Fort Aster."), "KEY_JUDGMENT",
              [s["AS1"]["assessment_statement_id"]], conf)]
    if "AS2" in s:
        out.append(rs(3, "The arrival may not have happened; a spokesman denied it.", "CAVEAT", [s["AS2"]["assessment_statement_id"]], conf))
    out.append(rs(4, "It is unknown how long the aircraft will remain.", "CAVEAT", [s["AS4"]["assessment_statement_id"]], conf))
    return out


def report_with(pg, analyst, code, placements):
    rid = new_report(pg, analyst, code)
    return rid, select(pg, analyst, rid, placements)


# --- 1, 2, 3, 6: candidate pool --------------------------------------------------------------
def test_only_eligible_approved_current_versions_enter_the_pool(pg, p5, analyst):
    from test_p4_assessments import assess, out as m07_out, setup_event, version_of
    from test_p4_challenge_review import chal, challenge, review, CONF_RAT
    v1, claims, (e, vid, vh) = approved_assessment(pg, analyst)
    # unapproved draft, IN_REVIEW and REJECTED versions
    e2, vid2, vh2, c2 = setup_event(pg, analyst)
    draft = version_of(pg, assess(pg, vid2, vh2, lambda m, env: m07_out(env, claims=c2)).final_run_id)
    e3, vid3, vh3, c3 = setup_event(pg, analyst)
    rej = version_of(pg, assess(pg, vid3, vh3, lambda m, env: m07_out(env, claims=c3)).final_run_id)
    challenge(pg, rej, lambda m, env: chal(env))
    review(pg, analyst, rej, "REJECT")
    rid = new_report(pg, analyst, "RPT-POOL-1")
    pool_ids = set(candidates(pg, rid))
    assert str(v1["id"]) in pool_ids and str(draft["id"]) not in pool_ids and str(rej["id"]) not in pool_ids
    c = candidates(pg, rid)[str(v1["id"])]
    assert (c["ctype"], c["object_hash"], c["recommended_section"]) == ("ASSESSMENT_VERSION", v1["content_hash"], "KEY_JUDGMENT")
    # 3: a later approved version supersedes v1 as current source
    r2 = assess(pg, vid, vh, lambda m, env: m07_out(env, claims=claims), previous_assessment_version_id=str(v1["id"]))
    v2 = version_of(pg, r2.final_run_id)
    challenge(pg, v2, lambda m, env: chal(env))
    review(pg, analyst, v2, "APPROVE", "MODERATE", CONF_RAT)
    with pytest.raises(psycopg.Error, match="CANDIDATE_NOT_ELIGIBLE"):
        decide(pg, analyst, c, "INCLUDE", "KEY_JUDGMENT", 1)
    with pg.as_user(analyst) as h:
        h.execute("SELECT lfhe.refresh_report_candidates(%s)", (rid,))
    now_pool = candidates(pg, rid)
    assert str(v2["id"]) in now_pool and str(v1["id"]) in now_pool                 # history stays visible
    # 6: the decision pins the exact candidate hash
    with pytest.raises(psycopg.Error, match="VERSION_HASH_MISMATCH"):
        with pg.as_user(analyst) as h:
            h.execute("SELECT lfhe.decide_report_candidate(%s, %s, 'INCLUDE', 'KEY_JUDGMENT', 1, NULL, 'stale hash given')",
                      (now_pool[str(v2["id"])]["candidate_id"], "0" * 64))
    d = decide(pg, analyst, now_pool[str(v2["id"])], "INCLUDE", "KEY_JUDGMENT", 1)
    with pg.admin() as x:
        row = x.execute("SELECT * FROM lfhe.report_selection_decisions WHERE id=%s", (d,)).fetchone()
        assert row["candidate_object_hash"] == v2["content_hash"]
        with pytest.raises(psycopg.Error):                                           # pool rows are immutable
            x.execute("DELETE FROM lfhe.report_candidate_pool WHERE report_id=%s", (rid,))
    with pg.as_user(analyst) as h, pytest.raises(psycopg.Error):                     # no direct pool writes
        h.execute("INSERT INTO lfhe.report_candidate_pool (report_id, candidate_type, object_id, object_hash, recommended_section) "
                  "VALUES (%s, 'ASSESSMENT_VERSION', %s, %s, 'KEY_JUDGMENT')", (rid, str(draft["id"]), draft["content_hash"]))


# --- 4, 5, 7: human selection -----------------------------------------------------------------
def test_selection_is_human_only_audited_and_m09_cannot_use_unselected_material(pg, p5, analyst, make_user):
    v, claims, _ = approved_assessment(pg, analyst)
    other, _, _ = approved_assessment(pg, analyst)
    rid = new_report(pg, analyst, "RPT-SEL-1")
    cands = candidates(pg, rid)
    c, o = cands[str(v["id"])], cands[str(other["id"])]
    args = (c["candidate_id"], c["object_hash"], "INCLUDE", "KEY_JUDGMENT", 1, None, "machine selection")
    for conn in (pg.worker, pg.as_service_role):
        with conn() as x, pytest.raises(psycopg.Error):
            x.execute("SELECT lfhe.decide_report_candidate(%s, %s, %s, %s, %s, %s, %s)", args)
    for role in ("VIEWER", "ADMIN", "REVIEWER"):
        with pg.as_user(make_user(role)) as x, pytest.raises(psycopg.Error, match="REPORT_EDIT"):
            x.execute("SELECT lfhe.decide_report_candidate(%s, %s, %s, %s, %s, %s, %s)", args)
    with pytest.raises(psycopg.Error, match="SECTION_NOT_ALLOWED_FOR_CANDIDATE"):
        decide(pg, analyst, c, "INCLUDE", "TREND_WATCH", 1)
    d1 = decide(pg, analyst, c, "INCLUDE", "KEY_JUDGMENT", 1)
    with pytest.raises(psycopg.Error, match="SELECTION_STALE"):
        with pg.as_user(analyst) as h:
            h.execute("SELECT lfhe.decide_report_candidate(%s, %s, 'EXCLUDE', NULL, NULL, NULL, 'ignores the newer decision')",
                      (c["candidate_id"], c["object_hash"]))
    d2 = decide(pg, analyst, o, "EXCLUDE")
    decide(pg, analyst, o, "RETURN_FOR_ANALYTICAL_REVISION")
    with pg.admin() as x:
        ev = [r["event_type"] for r in x.execute(
            "SELECT event_type FROM lfhe.audit_log WHERE object_type='report_candidate' AND object_id IN (%s,%s) "
            "AND event_type <> 'REPORT_CANDIDATE_ADDED' ORDER BY seq",
            (str(c["candidate_id"]), str(o["candidate_id"])))]
    assert ev == ["REPORT_CANDIDATE_SELECTED", "REPORT_CANDIDATE_REMOVED", "REPORT_CANDIDATE_RETURNED_FOR_REVISION"]
    for conn in (pg.worker, pg.as_service_role):
        with conn() as x, pytest.raises(psycopg.Error):
            x.execute("SELECT lfhe.freeze_report_selection(%s, 'machine freeze')", (rid,))
    sid, sh = freeze(pg, analyst, rid)
    with pg.admin() as x:
        items = x.execute("SELECT * FROM lfhe.report_selection_set_items WHERE selection_set_id=%s", (sid,)).fetchall()
        assert [(str(i["object_id"]), i["object_hash"]) for i in items] == [(str(v["id"]), v["content_hash"])]
        assert x.execute("SELECT count(*) n FROM lfhe.processing_jobs WHERE job_type='EDIT_REPORT' AND object_id=%s",
                         (sid,)).fetchone()["n"] == 1
    # 7: M09 output that uses the excluded candidate or its statements fails closed
    so = statements_of(pg, other["id"])
    r = run_m09(pg, sid, sh, lambda m, env: m09(env, dict(auto_items(env), significant_developments=[{
        "item_local_id": "SD1", "source_candidate_id": str(o["candidate_id"]),
        "statements": [rs(90, so["AS1"]["statement_text"], "SIGNIFICANT_DEVELOPMENT", [str(so["AS1"]["id"])])]}])))
    assert rejected(r, "SOURCE_CANDIDATE_NOT_SELECTED")

    def foreign(m, env):
        sec = auto_items(env)
        sec["key_judgments"][0]["statements"].append(rs(91, so["AS3"]["statement_text"], "KEY_JUDGMENT", [str(so["AS3"]["id"])], "LOW"))
        return m09(env, sec)
    assert rejected(run_m09(pg, sid, sh, foreign), "SOURCE_STATEMENT_NOT_IN_SELECTED_CANDIDATE")
    with pg.admin() as x:
        assert x.execute("SELECT count(*) n FROM lfhe.report_versions WHERE report_id=%s", (rid,)).fetchone()["n"] == 0


# --- 8, 9, 10, 20, 40: provenance --------------------------------------------------------------
def test_every_report_statement_maps_to_approved_statements_and_items_pin_versions(pg, p5, analyst):
    v, claims, (e, vid, vh) = approved_assessment(pg, analyst)
    rid, (sid, sh) = report_with(pg, analyst, "RPT-PROV-1", [(v["id"], "KEY_JUDGMENT", 1)])
    s = statements_of(pg, v["id"])
    merged = [rs(1, "The air force reported that 4 tanker aircraft arrived at Fort Aster; Northland is probably expanding "
                    "air-refuelling support at Fort Aster.", "KEY_JUDGMENT", [str(s["AS1"]["id"]), str(s["AS3"]["id"])], "LOW",
                 transform="COMPRESSION"),
              rs(2, "The arrival may not have happened; a spokesman denied it.", "CAVEAT", [str(s["AS2"]["id"])], "LOW"),
              rs(3, "It is unknown how long the aircraft will remain.", "CAVEAT", [str(s["AS4"]["id"])], "LOW")]
    r = run_m09(pg, sid, sh, lambda m, env: m09(env, one_item(env, merged)))
    assert r.outcome == "REPORT_VERSION_RECORDED", r
    rv = version_of_run(pg, r.final_run_id)
    with pg.admin() as x:
        it = x.execute("SELECT * FROM lfhe.report_items WHERE report_version_id=%s", (rv["id"],)).fetchone()
        assert (str(it["pinned_assessment_version_id"]), it["pinned_assessment_version_hash"]) == (str(v["id"]), v["content_hash"])
        assert (str(it["pinned_event_version_id"]), it["pinned_event_version_hash"]) == (vid, vh)
        assert rv["canonical_json"]["sections"][0]["items"][0]["final_analytic_confidence"] == "LOW"
        srcs = {r_["report_statement_local_id"]: sorted(str(y["assessment_statement_id"]) for y in x.execute(
            "SELECT assessment_statement_id FROM lfhe.report_statement_sources WHERE report_item_statement_id=%s", (r_["id"],)))
            for r_ in x.execute("SELECT * FROM lfhe.report_item_statements WHERE report_item_id=%s", (it["id"],))}
        assert srcs["RS1"] == sorted([str(s["AS1"]["id"]), str(s["AS3"]["id"])])              # 20: merge keeps both
        assert x.execute("""SELECT count(*) n FROM lfhe.report_item_statements st JOIN lfhe.report_items i ON i.id=st.report_item_id
                            WHERE i.report_version_id=%s AND NOT EXISTS (SELECT 1 FROM lfhe.report_statement_sources x
                            WHERE x.report_item_statement_id=st.id)""", (rv["id"],)).fetchone()["n"] == 0       # 8
    bad = [dict(merged[0], source_assessment_statement_ids=["00000000-0000-4000-8000-0000000000ff"])] + merged[1:]
    assert rejected(run_m09(pg, sid, sh, lambda m, env: m09(env, one_item(env, bad))), "UNKNOWN_SOURCE_STATEMENT")      # 9
    assert run_m09(pg, sid, sh, lambda m, env: m09(env, one_item(env, [dict(merged[0], source_assessment_statement_ids=[])]))).outcome \
        == "SCHEMA_VALIDATION_FAILED"
    with pg.admin() as x:
        assert x.execute("SELECT count(*) n FROM lfhe.report_versions WHERE report_id=%s", (rid,)).fetchone()["n"] == 1


# --- 11, 12, 13, 14, 15: no new content, attribution and caveats survive ---------------------------
@pytest.mark.parametrize("over, code", [
    ({"kj": "Northland is probably expanding air-refuelling support at Fort Aster and Port Vell."}, "UNSUPPORTED_NEW_FACT"),
    ({"fact": "The air force reported that 6 tanker aircraft arrived at Fort Aster."}, "UNSUPPORTED_NEW_FACT"),
    ({"kj": "Northland is expanding air-refuelling support at Fort Aster because of the exercise."}, "UNSUPPORTED_NEW_JUDGMENT"),
    ({"kj": "Northland is clearly expanding air-refuelling support at Fort Aster."}, "EPISTEMIC_STRENGTHENING"),
    ({"kj": "NATO should strike the tanker base at Fort Aster."}, "OPERATIONAL_RECOMMENDATION_PROHIBITED"),
    ({"fact": "4 tanker aircraft arrived at Fort Aster."}, "ATTRIBUTION_REMOVED"),
])
def test_new_facts_judgments_strengthening_and_attribution_loss_fail_closed(pg, p5, analyst, over, code):
    v, _, _ = approved_assessment(pg, analyst)
    rid, (sid, sh) = report_with(pg, analyst, f"RPT-NEW-{code[:10]}-{abs(hash(json.dumps(over))) % 10000}", [(v["id"], "KEY_JUDGMENT", 1)])
    r = run_m09(pg, sid, sh, lambda m, env: m09(env, one_item(env, default_kj_statements(env, **over))))
    assert rejected(r, code), r


def test_contradiction_and_caveats_cannot_disappear(pg, p5, analyst):
    v, _, _ = approved_assessment(pg, analyst)
    rid, (sid, sh) = report_with(pg, analyst, "RPT-CAV-1", [(v["id"], "KEY_JUDGMENT", 1)])
    full = lambda env: default_kj_statements(env)                                       # noqa: E731
    no_contra = lambda env: [x for x in full(env) if x["report_statement_local_id"] != "RS3"]   # noqa: E731
    no_gap = lambda env: [x for x in full(env) if x["report_statement_local_id"] != "RS4"]      # noqa: E731
    assert rejected(run_m09(pg, sid, sh, lambda m, env: m09(env, one_item(env, no_contra(env)))), "SELECTED_STATEMENT_OMITTED")
    assert rejected(run_m09(pg, sid, sh, lambda m, env: m09(env, one_item(env, no_gap(env)))), "SELECTED_STATEMENT_OMITTED")
    # a caveat role needs a caveat source
    wrong = lambda env: full(env)[:2] + [dict(full(env)[2], statement_role="CAVEAT",               # noqa: E731
                                              source_assessment_statement_ids=full(env)[0]["source_assessment_statement_ids"])]
    assert rejected(run_m09(pg, sid, sh, lambda m, env: m09(env, one_item(env, wrong(env) + full(env)[2:]))), "CAVEAT_WITHOUT_CAVEAT_SOURCE")
    ok = run_m09(pg, sid, sh, lambda m, env: m09(env, one_item(env, full(env))))
    assert ok.outcome == "REPORT_VERSION_RECORDED", ok


# --- 16, 17, 18, 19: confidence and likelihood preservation ----------------------------------------
def test_m09_cannot_change_confidence_or_likelihood(pg, p5, analyst):
    from test_p4_assessments import default_statements, st
    LK = {"term": "LIKELY", "rationale": "Rotation pattern in the cited reports."}

    def with_lk(claims):
        base = default_statements(claims)
        base[2] = st("AS3", "ANALYTIC_JUDGMENT", "Northland is likely expanding air-refuelling support at Fort Aster.",
                     claims=[claims[0]], premises=["AS1"], evidence=True, likelihood=LK)
        return base
    v, _, _ = approved_assessment(pg, analyst, statements=with_lk, conf="LOW")
    plain, _, _ = approved_assessment(pg, analyst, conf="LOW")
    rid, (sid, sh) = report_with(pg, analyst, "RPT-CONF-1", [(v["id"], "KEY_JUDGMENT", 1)])
    lk_kj = "Northland is likely expanding air-refuelling support at Fort Aster."

    def go(**over):
        return run_m09(pg, sid, sh, lambda m, env: m09(env, one_item(env, default_kj_statements(env, **dict({"kj": lk_kj, "lk": "LIKELY"}, **over)))))
    assert go().outcome == "REPORT_VERSION_RECORDED"
    assert rejected(go(conf="HIGH"), "CONFIDENCE_CHANGED")                                   # 16
    assert rejected(go(conf=None), "CONFIDENCE_MISSING_ON_KEY_JUDGMENT")
    assert rejected(go(kj=lk_kj[:-1] + " (high confidence)."), "CONFIDENCE_CHANGED")
    assert rejected(go(lk=None), "LIKELIHOOD_REMOVED")                                       # 17
    assert rejected(go(lk="HIGHLY_LIKELY"), "LIKELIHOOD_CHANGED")
    assert rejected(go(kj="Northland is highly likely expanding air-refuelling support at Fort Aster."), "LIKELIHOOD_CHANGED")
    assert rejected(go(kj="Northland is expanding air-refuelling support at Fort Aster."), "LIKELIHOOD_REMOVED")
    rid2, (sid2, sh2) = report_with(pg, analyst, "RPT-CONF-2", [(plain["id"], "KEY_JUDGMENT", 1)])

    def go2(**over):
        return run_m09(pg, sid2, sh2, lambda m, env: m09(env, one_item(env, default_kj_statements(env, **over))))
    assert rejected(go2(lk="LIKELY"), "LIKELIHOOD_ADDED")                                    # 18
    assert rejected(go2(kj="It is almost certain that Northland is expanding air-refuelling support at Fort Aster."),
                    "LIKELIHOOD_ADDED")
    # 19: republication / repetition cannot strengthen at report stage
    assert rejected(go2(conf="MODERATE"), "CONFIDENCE_CHANGED")
    assert rejected(go2(kj="Independently corroborated reports show Northland is probably expanding air-refuelling support "
                           "at Fort Aster."), "EPISTEMIC_STRENGTHENING")
    with pg.admin() as x:
        cols = {c["column_name"] for c in x.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='lfhe' "
                                                    "AND table_name IN ('report_items','report_item_statements','report_versions')")}
    assert "ai_recommended_confidence" not in cols


# --- 21, 22, 23, 24, 25: length / removal review ---------------------------------------------------
def test_removal_is_proposed_by_m09_and_decided_only_by_a_human(pg, p5, analyst, make_user):
    kj, _, _ = approved_assessment(pg, analyst)
    sd, _, _ = approved_assessment(pg, analyst)
    rid, (sid, sh) = report_with(pg, analyst, "RPT-LEN-1", [(kj["id"], "KEY_JUDGMENT", 1), (sd["id"], "SIGNIFICANT_DEVELOPMENT", 1)])
    sd_item = lambda env: next(i for i in auto_items(env)["significant_developments"])           # noqa: E731
    r = run_m09(pg, sid, sh, lambda m, env: m09(env, length="EXCEEDS_LIMIT", removals=[{
        "removal_local_id": "RM1", "target_item_local_id": sd_item(env)["item_local_id"], "target_report_statement_local_id": None,
        "reason": "Two-page limit: lowest-priority development."}]))
    assert r.outcome == "REPORT_VERSION_RECORDED", r
    v = version_of_run(pg, r.final_run_id)
    with pg.admin() as x:
        st_ = x.execute("SELECT * FROM lfhe.report_version_states WHERE report_version_id=%s", (v["id"],)).fetchone()
        assert (st_["length_status"], st_["length_review_required"], st_["length_review_pending"], st_["removal_proposals"]) == \
            ("EXCEEDS_LIMIT", True, True, 1)
        assert x.execute("SELECT count(*) n FROM lfhe.report_items WHERE report_version_id=%s AND section='SIGNIFICANT_DEVELOPMENT'",
                         (v["id"],)).fetchone()["n"] == 1                                       # 22: not applied
        prop = x.execute("SELECT * FROM lfhe.report_removal_proposals WHERE report_version_id=%s", (v["id"],)).fetchone()
        assert len(prop["source_assessment_statement_ids"]) == 4
    dec = json.dumps([{"proposal_id": str(prop["id"]), "decision": "ACCEPT"}])
    for conn in (pg.worker, pg.as_service_role):
        with conn() as c, pytest.raises(psycopg.Error):
            c.execute("SELECT lfhe.decide_report_removals(%s, %s, %s::jsonb, 'machine removal')", (v["id"], v["report_version_hash"], dec))
    with pg.as_user(make_user("VIEWER")) as c, pytest.raises(psycopg.Error, match="REPORT_EDIT"):
        c.execute("SELECT lfhe.decide_report_removals(%s, %s, %s::jsonb, 'viewer removal')", (v["id"], v["report_version_hash"], dec))
    with pg.as_user(analyst) as c:
        with pytest.raises(psycopg.Error, match="REMOVAL_DECISIONS_INCOMPLETE"):
            c.execute("SELECT lfhe.decide_report_removals(%s, %s, '[]'::jsonb, 'nothing decided')", (v["id"], v["report_version_hash"]))
        res = c.execute("SELECT lfhe.decide_report_removals(%s, %s, %s::jsonb, 'analyst accepts the cut') r",
                        (v["id"], v["report_version_hash"], dec)).fetchone()["r"]
    with pg.admin() as x:
        nv = x.execute("SELECT * FROM lfhe.report_versions WHERE id=%s", (res["report_version_id"],)).fetchone()
        assert (nv["origin"], nv["version_no"], str(nv["previous_report_version_id"])) == ("HUMAN", 2, str(v["id"]))
        assert sorted(nv["canonical_json"]["human_removals"]) == sorted(str(u) for u in prop["source_assessment_statement_ids"])
        assert x.execute("SELECT count(*) n FROM lfhe.report_items WHERE report_version_id=%s AND section='SIGNIFICANT_DEVELOPMENT'",
                         (nv["id"],)).fetchone()["n"] == 0
        assert x.execute("SELECT length_review_pending p FROM lfhe.report_version_states WHERE report_version_id=%s",
                         (v["id"],)).fetchone()["p"] is False
        assert x.execute("SELECT count(*) n FROM lfhe.audit_log WHERE event_type='REPORT_REMOVAL_DECIDED' AND object_id=%s",
                         (str(v["id"]),)).fetchone()["n"] == 1


def test_caveats_cannot_be_removed_for_length_and_length_status_is_deterministic(pg, p5, analyst):
    v, _, _ = approved_assessment(pg, analyst)
    rid, (sid, sh) = report_with(pg, analyst, "RPT-LEN-2", [(v["id"], "KEY_JUDGMENT", 1)])
    # 25: proposing to drop the contradiction while the judgment stays is refused
    r = run_m09(pg, sid, sh, lambda m, env: m09(env, one_item(env, default_kj_statements(env)), length="EXCEEDS_LIMIT", removals=[{
        "removal_local_id": "RM1", "target_item_local_id": None, "target_report_statement_local_id": "RS3",
        "reason": "Shorten: the denial takes space."}]))
    assert rejected(r, "CAVEAT_REMOVAL_FOR_LENGTH_PROHIBITED")
    assert rejected(run_m09(pg, sid, sh, lambda m, env: m09(env, one_item(env, default_kj_statements(env)), removals=[{
        "removal_local_id": "RM1", "target_item_local_id": "NOPE", "target_report_statement_local_id": None,
        "reason": "Unknown target given."}])), "REMOVAL_TARGET_UNKNOWN")
    ok = run_m09(pg, sid, sh, lambda m, env: m09(env, one_item(env, default_kj_statements(env))))
    v1 = version_of_run(pg, ok.final_run_id)
    s = statements_of(pg, v["id"])
    with pytest.raises(psycopg.Error, match="CAVEAT_REMOVAL_PROHIBITED"):            # a human cannot drop it either
        c = content_of(pg, v1["id"])
        c["key_judgments"][0]["statements"] = [x for x in c["key_judgments"][0]["statements"] if x["report_statement_local_id"] != "RS3"]
        edit(pg, analyst, v1, dict(c, remove_source_statement_ids=[str(s["AS2"]["id"])]))
    # 24: deterministic length status (counts against §10 targets) + model status
    with pg.admin() as x:
        f = lambda content, st=None: x.execute("SELECT lfhe.p5_length_status(%s::jsonb, %s) r", (json.dumps(content), st)).fetchone()["r"]  # noqa: E731
        assert f({"what_to_watch": [{}] * 4}) == "EXCEEDS_LIMIT" and f({"significant_developments": [{}] * 6}) == "EXCEEDS_LIMIT"
        assert f({"what_to_watch": [{}] * 3, "indicators_warning": [{}] * 6}) == "WITHIN_LIMIT"
        assert f({}, "EXCEEDS_LIMIT") == "EXCEEDS_LIMIT" and f({}, "NEAR_LIMIT") == "NEAR_LIMIT"
    # a version needing review with no proposals is resolved by an explicit KEEP_LENGTH decision
    r2 = run_m09(pg, sid, sh, lambda m, env: m09(env, one_item(env, default_kj_statements(env)), length="EXCEEDS_LIMIT"))
    v2 = version_of_run(pg, r2.final_run_id)
    with pg.as_user(analyst) as c:
        assert c.execute("SELECT lfhe.decide_report_removals(%s, %s, '[]'::jsonb, 'analyst keeps the length') r",
                         (v2["id"], v2["report_version_hash"])).fetchone()["r"]["report_version_id"] is None
    with pg.admin() as x:
        assert x.execute("SELECT decision FROM lfhe.report_removal_decisions WHERE report_version_id=%s", (v2["id"],)).fetchone()["decision"] \
            == "KEEP_LENGTH"


# --- 26, 27, 28, 29, 30, 31, 32: structure ------------------------------------------------------------
def test_structure_limits_sections_and_no_filler(pg, p5, analyst):
    v, _, _ = approved_assessment(pg, analyst)
    sd, _, _ = approved_assessment(pg, analyst)
    rid, (sid, sh) = report_with(pg, analyst, "RPT-STR-1", [(v["id"], "KEY_JUDGMENT", 1), (sd["id"], "SIGNIFICANT_DEVELOPMENT", 2)])

    def four_kj(m, env):
        sec = auto_items(env)
        base = sec["key_judgments"][0]
        judg = next(x for x in base["statements"] if x["statement_role"] == "KEY_JUDGMENT" and "probably" in x["text"])
        sec["key_judgments"] += [{"item_local_id": f"KX{i}", "source_candidate_id": base["source_candidate_id"],
                                  "statements": [dict(judg, report_statement_local_id=f"RS{200 + i}")]} for i in range(3)]
        return m09(env, sec)
    assert rejected(run_m09(pg, sid, sh, four_kj), "MAX_KEY_JUDGMENTS_EXCEEDED")                       # 27

    def promote(m, env):                                                                               # SD material → KJ
        sec = auto_items(env)
        sec["key_judgments"] += sec.pop("significant_developments")
        sec["significant_developments"] = []
        return m09(env, sec)
    assert rejected(run_m09(pg, sid, sh, promote), "SECTION_NOT_AUTHORISED")
    assert run_m09(pg, sid, sh, lambda m, env: m09(env, dict(auto_items(env), supporting_developments=[]))).outcome \
        == "SCHEMA_VALIDATION_FAILED"                                                                  # 31
    r1 = run_m09(pg, sid, sh, lambda m, env: m09(env))
    assert r1.outcome == "REPORT_VERSION_RECORDED", r1
    v1 = version_of_run(pg, r1.final_run_id)
    cov = {c["section"]: c for c in v1["canonical_json"]["coverage"]}
    assert cov["SIGNIFICANT_DEVELOPMENT"]["count"] == 1 and cov["SIGNIFICANT_DEVELOPMENT"]["below_target"] is True     # 28 no filler
    assert cov["INDICATOR_WARNING"]["count"] == 0 and cov["INDICATOR_WARNING"]["below_target"] is True                  # 29
    assert cov["WHAT_TO_WATCH"]["count"] == 0 and cov["WHAT_TO_WATCH"]["below_target"] is True                          # 30
    with pytest.raises(psycopg.Error, match="REPORT_STATEMENT_WITHOUT_SOURCE"):                                        # 26
        c = content_of(pg, v1["id"])
        c["significant_developments"][0]["statements"].append(rs(99, "Further developments are expected.", "SIGNIFICANT_DEVELOPMENT", []))
        edit(pg, analyst, v1, c)
    with pytest.raises(psycopg.Error, match="STATEMENT_ROLE_INVALID"):
        c = content_of(pg, v1["id"])
        c["key_judgments"][0]["statements"][0]["statement_role"] = "SUPPORTING_DEVELOPMENT"
        edit(pg, analyst, v1, c)
    # 32: item order is fixed by the human priorities, not by the model's output order
    def reversed_order(m, env):
        sec = auto_items(env)
        both = sec["key_judgments"] + sec["significant_developments"]
        return m09(env, dict(sec, key_judgments=[i for i in reversed(both) if i["item_local_id"] == sec["key_judgments"][0]["item_local_id"]]))
    r2 = run_m09(pg, sid, sh, reversed_order)
    assert version_of_run(pg, r2.final_run_id)["canonical_json"]["sections"] == v1["canonical_json"]["sections"]


# --- 33, 34, 35, 36, 37, 38, 39: canonical JSON, hash, versioning -------------------------------------
def test_canonical_json_is_jcs_and_versions_are_immutable(pg, p5, analyst):
    from lfhe_shared.canonical_json import canonical_dumps, canonical_sha256
    v, _, _ = approved_assessment(pg, analyst)
    rid, (sid, sh) = report_with(pg, analyst, "RPT-HASH-1", [(v["id"], "KEY_JUDGMENT", 1)])
    r = run_m09(pg, sid, sh, lambda m, env: m09(env))
    rv = version_of_run(pg, r.final_run_id)
    with pg.admin() as x:
        jcs = x.execute("SELECT lfhe.jcs(canonical_json) j FROM lfhe.report_versions WHERE id=%s", (rv["id"],)).fetchone()["j"]
        assert jcs == canonical_dumps(rv["canonical_json"])                                        # 33
        assert rv["report_version_hash"] == canonical_sha256(rv["canonical_json"])                  # 34
        for obj in ({"b": "é\u0001\"\\\n\t/", "a": [1, -2, 0, True, None, "😀  "], "A": {}}, {"z": "ÖŐ\u007f", "y": 9007199254740991}):
            assert x.execute("SELECT lfhe.jcs(%s::jsonb) j", (json.dumps(obj),)).fetchone()["j"] == canonical_dumps(obj)
            assert x.execute("SELECT lfhe.jcs_sha256(%s::jsonb) j", (json.dumps(obj),)).fetchone()["j"] == canonical_sha256(obj)
        for bad in ({"x": 1.5}, {"ké": 1}, {"x": 9007199254740993}):
            with pytest.raises(psycopg.Error):
                x.execute("SELECT lfhe.jcs(%s::jsonb)", (json.dumps(bad),))
        before = x.execute("SELECT lfhe.jcs(canonical_json) j, report_version_hash h FROM lfhe.report_versions WHERE id=%s",
                           (rv["id"],)).fetchone()
        for sql in ("UPDATE lfhe.report_versions SET length_status='NEAR_LIMIT' WHERE id=%s",
                    "DELETE FROM lfhe.report_versions WHERE id=%s",
                    "UPDATE lfhe.report_item_statements SET statement_text='x' WHERE report_item_id IN (SELECT id FROM lfhe.report_items WHERE report_version_id=%s)",
                    "DELETE FROM lfhe.report_statement_sources WHERE report_item_statement_id IN (SELECT s.id FROM lfhe.report_item_statements s JOIN lfhe.report_items i ON i.id=s.report_item_id WHERE i.report_version_id=%s)"):
            with pytest.raises(psycopg.Error):                                                     # 36
                x.execute(sql, (rv["id"],))
    c = content_of(pg, rv["id"])
    c["key_judgments"][0]["statements"][0]["text"] = c["key_judgments"][0]["statements"][0]["text"].replace("Northland is probably", "Northland probably is")
    c["key_judgments"][0]["statements"][0]["editorial_transform"] = "PARAPHRASE"
    res = edit(pg, analyst, rv, c)                                                                 # 35, 37
    with pg.admin() as x:
        nv = x.execute("SELECT * FROM lfhe.report_versions WHERE id=%s", (res["report_version_id"],)).fetchone()
        assert (nv["version_no"], nv["origin"], str(nv["previous_report_version_id"])) == (2, "HUMAN", str(rv["id"]))
        assert nv["report_version_hash"] != rv["report_version_hash"]
        after = x.execute("SELECT lfhe.jcs(canonical_json) j, report_version_hash h FROM lfhe.report_versions WHERE id=%s",
                          (rv["id"],)).fetchone()
        assert after == before                                                                      # 38
    with pytest.raises(psycopg.Error, match="REPORT_VERSION_STALE"):                                 # 39
        edit(pg, analyst, rv, c)
    with pytest.raises(psycopg.Error, match="VERSION_HASH_MISMATCH"):
        edit(pg, analyst, dict(nv, report_version_hash="f" * 64), c)
    with pytest.raises(psycopg.Error, match="REPORT_EDIT_NO_CHANGE"):
        edit(pg, analyst, nv, content_of(pg, nv["id"]))


# --- 41, 42, 43, 44: human edits ------------------------------------------------------------------------
def test_human_edits_keep_provenance_are_audited_and_cannot_be_impersonated(pg, p5, analyst):
    v, _, _ = approved_assessment(pg, analyst)
    other, _, _ = approved_assessment(pg, analyst)
    rid, (sid, sh) = report_with(pg, analyst, "RPT-HUM-1", [(v["id"], "KEY_JUDGMENT", 1)])
    rv = version_of_run(pg, run_m09(pg, sid, sh, lambda m, env: m09(env)).final_run_id)
    c = content_of(pg, rv["id"])
    kj = c["key_judgments"][0]["statements"]
    judg = next(x for x in kj if "probably" in x["text"])
    judg["text"] = "Northland is probably expanding tanker support at Fort Aster."
    judg["editorial_transform"] = "COMPRESSION"
    res = edit(pg, analyst, rv, c)
    with pg.admin() as x:
        rows = x.execute("""SELECT s.*, (SELECT array_agg(assessment_statement_id::text) FROM lfhe.report_statement_sources y
                                         WHERE y.report_item_statement_id = s.id) AS srcs
                            FROM lfhe.report_item_statements s JOIN lfhe.report_items i ON i.id = s.report_item_id
                            WHERE i.report_version_id=%s""", (res["report_version_id"],)).fetchall()
        by = {r["report_statement_local_id"]: r for r in rows}
        assert by[judg["report_statement_local_id"]]["author_type"] == "HUMAN" and str(by[judg["report_statement_local_id"]]["user_id"]) == str(analyst)
        assert by[judg["report_statement_local_id"]]["srcs"] == judg["source_assessment_statement_ids"]       # 41
        unchanged = [r for r in rows if r["report_statement_local_id"] != judg["report_statement_local_id"]]
        assert unchanged and all(r["author_type"] == "MODEL" and r["model_run_id"] for r in unchanged)
        assert x.execute("SELECT count(*) n FROM lfhe.audit_log WHERE event_type='REPORT_TEXT_EDITED' AND object_id=%s",
                         (res["report_version_id"],)).fetchone()["n"] == 1                                     # 43
    nv = latest_version(pg, rid)
    so = statements_of(pg, other["id"])
    for mutate, code in ((lambda cc: cc["key_judgments"][0]["statements"].append(rs(80, "A new human sentence.", "KEY_JUDGMENT", [], "LOW")),
                          "REPORT_STATEMENT_WITHOUT_SOURCE"),
                         (lambda cc: cc["key_judgments"][0]["statements"].append(rs(81, so["AS3"]["statement_text"], "KEY_JUDGMENT",
                                                                                     [str(so["AS3"]["id"])], "LOW")),
                          "SOURCE_STATEMENT_NOT_IN_SELECTED_CANDIDATE")):
        cc = content_of(pg, nv["id"])
        mutate(cc)
        with pytest.raises(psycopg.Error, match=code):                                                       # 42
            edit(pg, analyst, nv, cc)
    # reorder only → REPORT_CONTENT_REORDERED
    cc = content_of(pg, nv["id"])
    cc["key_judgments"][0]["statements"].reverse()
    res2 = edit(pg, analyst, nv, cc, reason="analyst reorders the item")
    with pg.admin() as x:
        assert x.execute("SELECT count(*) n FROM lfhe.audit_log WHERE event_type='REPORT_CONTENT_REORDERED' AND object_id=%s",
                         (res2["report_version_id"],)).fetchone()["n"] == 1
    nv2 = latest_version(pg, rid)
    for conn in (pg.worker, pg.as_service_role, pg.as_anon):                                                  # 44
        with conn() as x, pytest.raises(psycopg.Error):
            x.execute("SELECT lfhe.edit_report_version(%s, %s, %s::jsonb, 'impersonated edit')",
                      (nv2["id"], nv2["report_version_hash"], json.dumps(content_of(pg, nv2["id"]))))
    with pg.worker() as w, pytest.raises(psycopg.Error):
        w.execute("INSERT INTO lfhe.report_versions (report_id, version_no, selection_set_id, selection_set_hash, report_mode, "
                  "information_cutoff, origin, created_by_user, length_status, length_review_required, canonical_json, report_version_hash) "
                  "SELECT report_id, 99, selection_set_id, selection_set_hash, report_mode, information_cutoff, 'HUMAN', %s, "
                  "'WITHIN_LIMIT', false, canonical_json, report_version_hash FROM lfhe.report_versions WHERE id=%s", (str(analyst), nv2["id"]))
