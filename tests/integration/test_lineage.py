"""P3-01 — M04 lineage persistence, human validation, derived independence,
claim-status workflow (Phase 3 Addendum §3, §4, §12, §14; required tests 1–9)."""
import psycopg
import pytest

from lineage_support import (PAST, grounded_claim, ingest_lineage, lineage_run, proposals, rel, summary)

pytestmark = pytest.mark.db

WIRE = "According to Reuters, the air force received 4 new tanker aircraft on Monday."
EN_A = "The defence ministry said 6 radars were delivered to the northern brigade."
HU_B = "A minisztérium közölte, hogy hat radart szállítottak az északi dandárnak."


@pytest.fixture
def analyst(make_user):
    return make_user("ANALYST")


def accept(pg, user, proposal_id, reason="checked both texts: same wire report"):
    with pg.as_user(user) as h:
        return h.execute("SELECT lfhe.decide_lineage_proposal(%s, true, %s) AS id", (proposal_id, reason)).fetchone()["id"]


# --- tests 1, 3: same underlying source in two outlets = one group -----------
def test_same_underlying_source_in_two_outlets_is_one_independence_group(pg, analyst):
    a = grounded_claim(pg, WIRE, "According to Reuters, the air force received 4 new tanker aircraft")
    b = grounded_claim(pg, "Reuters reported: " + WIRE, "According to Reuters, the air force received 4 new tanker aircraft")
    assert summary(pg, [a, b])["distinct_groups_upper_bound"] == 2           # before any lineage: unknown, not "2 confirmations"
    assert summary(pg, [a, b])["independence_established"] is False
    run = lineage_run(pg, [a, b])
    out = ingest_lineage(pg, run, [rel(a, origin="Reuters"), rel(b, origin="Reuters")])
    assert out["outcome"] == "PROPOSALS_RECORDED"
    assert summary(pg, [a, b])["distinct_groups_upper_bound"] == 2           # proposals alone change nothing
    p1, p2 = proposals(pg, run)
    accept(pg, analyst, p1["id"])
    with pg.as_user(analyst) as h:   # the second outlet names the same origin → link to the same origin object
        origin = h.execute("SELECT id FROM lfhe.external_origins WHERE evidence_claim_id=%s", (a["claim_id"],)).fetchone()["id"]
        h.execute("SELECT lfhe.record_claim_lineage(%s::jsonb, 'same Reuters report, verified wording')",
                  (f'{{"child_claim_id": "{b["claim_id"]}", "relationship_type": "COMMON_ORIGINAL_SOURCE", '
                   f'"external_origin_id": "{origin}"}}',))
    s = summary(pg, [a, b])
    assert s["distinct_groups_upper_bound"] == 1 and s["claims_with_unknown_lineage"] == 0
    assert s["independence_established"] is False


# --- tests 2, 5: different language/publisher/wording ≠ independence -----------
def test_surface_differences_never_establish_independence(pg):
    a = grounded_claim(pg, EN_A, "6 radars were delivered to the northern brigade")
    b = grounded_claim(pg, HU_B, "hat radart szállítottak az északi dandárnak", language="hu")
    s = summary(pg, [a, b])
    assert s["claims_with_unknown_lineage"] == 2 and s["independence_established"] is False
    run = lineage_run(pg, [a, b])
    out = ingest_lineage(pg, run, [rel(b, "INDEPENDENT_REPORTING", parent_claim=a)])
    assert out["outcome"] == "OUTPUT_REJECTED"
    assert any(r.startswith("RELATIONSHIP_TYPE_NOT_ALLOWED") for r in out["rejection_reasons"])
    assert proposals(pg, run) == []
    with pg.admin() as c:
        labels = [r["e"] for r in c.execute("SELECT unnest(enum_range(NULL::lfhe.lineage_relationship_type))::text e")]
    assert labels == ["COMMON_ORIGINAL_SOURCE", "DERIVED_REPORTING"]


# --- test 4: derived reporting does not add confirmations ----------------------
def test_derived_reporting_does_not_increase_independent_groups(pg, analyst):
    a = grounded_claim(pg, EN_A, "6 radars were delivered to the northern brigade")
    b = grounded_claim(pg, "Citing the ministry, " + EN_A, "6 radars were delivered to the northern brigade")
    c = grounded_claim(pg, "A blog repeated: " + EN_A, "6 radars were delivered to the northern brigade")
    run = lineage_run(pg, [a, b, c])
    ingest_lineage(pg, run, [rel(b, "DERIVED_REPORTING", parent_claim=a), rel(c, "DERIVED_REPORTING", parent_claim=b)])
    for p in proposals(pg, run):
        accept(pg, analyst, p["id"], "republication of the same ministry statement")
    assert summary(pg, [a, b, c])["distinct_groups_upper_bound"] == 1


def test_retraction_preserves_history_and_restores_unknown(pg, analyst):
    a = grounded_claim(pg, EN_A, "6 radars were delivered")
    b = grounded_claim(pg, "Copy: " + EN_A, "6 radars were delivered")
    run = lineage_run(pg, [a, b])
    ingest_lineage(pg, run, [rel(b, "DERIVED_REPORTING", parent_claim=a)])
    lin = accept(pg, analyst, proposals(pg, run)[0]["id"])
    assert summary(pg, [a, b])["distinct_groups_upper_bound"] == 1
    with pg.as_user(analyst) as h:
        h.execute("SELECT lfhe.retract_claim_lineage(%s, 'second outlet had its own reporter on site')", (lin,))
    s = summary(pg, [a, b])
    assert s["distinct_groups_upper_bound"] == 2 and s["claims_with_unknown_lineage"] == 2
    with pg.admin() as x:
        assert x.execute("SELECT count(*) n FROM lfhe.claim_lineage WHERE id=%s", (lin,)).fetchone()["n"] == 1
        events = [r["event_type"] for r in x.execute(
            "SELECT event_type FROM lfhe.audit_log WHERE object_id IN (%s, %s, %s) ORDER BY seq",
            (str(lin), b["claim_id"], str(proposals(pg, run)[0]["id"])))]
        assert {"LINEAGE_VALIDATED", "CLAIM_LINEAGE_RETRACTED", "INDEPENDENCE_GROUP_CHANGED"} <= set(events)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            x.execute("DELETE FROM lfhe.claim_lineage WHERE id=%s", (lin,))


# --- invented / unevidenced origins, inputs, cutoff ---------------------------
@pytest.mark.parametrize("bad, reason", [
    (lambda a, b: rel(b, origin="Associated Press"), "EXTERNAL_ORIGIN_NOT_EVIDENCED"),
    (lambda a, b: rel(a, origin="Reuters", url="https://www.reuters.com/x"), "EXTERNAL_ORIGIN_URL_NOT_IN_SOURCE"),
    (lambda a, b: rel(a, parent_claim=b, rtype="DERIVED_REPORTING") | {"parent_article_id": a["article_id"]},
     "EXACTLY_ONE_PARENT_REQUIRED"),
    (lambda a, b: rel(a, parent_claim=a), "SELF_LINEAGE"),
    (lambda a, b: rel(a, parent_article="00000000-0000-4000-8000-000000000000"), "ARTICLE_NOT_IN_MODEL_RUN_INPUT"),
])
def test_invalid_lineage_rejects_the_whole_output(pg, bad, reason):
    a = grounded_claim(pg, WIRE, "According to Reuters, the air force received 4 new tanker aircraft")
    b = grounded_claim(pg, EN_A, "6 radars were delivered")
    run = lineage_run(pg, [a, b])
    out = ingest_lineage(pg, run, [rel(b, "DERIVED_REPORTING", parent_claim=a), bad(a, b)])
    assert out["outcome"] == "OUTPUT_REJECTED" and any(r.startswith(reason) for r in out["rejection_reasons"])
    assert proposals(pg, run) == []


def test_claims_outside_the_input_or_after_the_cutoff_are_rejected(pg):
    a = grounded_claim(pg, EN_A, "6 radars were delivered")
    b = grounded_claim(pg, "Copy: " + EN_A, "6 radars were delivered")
    outsider = grounded_claim(pg, WIRE, "the air force received 4 new tanker aircraft")
    run = lineage_run(pg, [a, b])
    out = ingest_lineage(pg, run, [rel(outsider, "DERIVED_REPORTING", parent_claim=a)])
    assert any(r.startswith("CLAIM_NOT_IN_MODEL_RUN_INPUT") for r in out["rejection_reasons"])
    old = lineage_run(pg, [a, b], cutoff=PAST)            # retrieved after this cutoff → not eligible
    out = ingest_lineage(pg, old, [rel(b, "DERIVED_REPORTING", parent_claim=a)])
    assert any(r.startswith("CLAIM_NOT_CUTOFF_ELIGIBLE") for r in out["rejection_reasons"])
    with pytest.raises(psycopg.errors.CheckViolation, match="CUTOFF_NOT_DECLARED"):
        from claims_support import make_model_run
        undeclared = make_model_run(pg, "M04_LINEAGE", [("claim", a["claim_id"])])
        ingest_lineage(pg, undeclared, [])


def test_failed_m04_runs_record_no_proposals(pg):
    a = grounded_claim(pg, EN_A, "6 radars were delivered")
    for status in ("SCHEMA_VALIDATION_FAILED", "PROVIDER_ERROR"):
        run = lineage_run(pg, [a], status=status)
        assert ingest_lineage(pg, run, [rel(a, origin="ministry")])["outcome"] == status
        assert proposals(pg, run) == []


# --- tests 6, 7: recommendation alone never changes status; human decision is bound + audited
def test_m04_recommendation_does_not_change_status_until_a_human_decides(pg, analyst):
    a = grounded_claim(pg, EN_A, "6 radars were delivered")
    b = grounded_claim(pg, HU_B, "hat radart szállítottak", language="hu")
    run = lineage_run(pg, [a, b])
    ingest_lineage(pg, run, recommendations=[{"claim_id": a["claim_id"], "recommendation": "POTENTIAL_CORROBORATION",
                                              "recommended_status": "CORROBORATED", "supporting_claim_ids": [b["claim_id"]],
                                              "explanation": "second outlet reports the same delivery"}])
    with pg.admin() as x:
        assert x.execute("SELECT claim_status FROM lfhe.claim_state WHERE claim_id=%s", (a["claim_id"],)).fetchone()["claim_status"] == "UNVERIFIED"
        rec = x.execute("SELECT * FROM lfhe.corroboration_recommendations WHERE model_run_id=%s", (run,)).fetchone()
    assert rec["human_review_required"]
    with pg.as_user(analyst) as h:
        with pytest.raises(psycopg.errors.SerializationFailure, match="STATUS_STALE"):
            h.execute("SELECT lfhe.decide_corroboration_recommendation(%s, true, 'CORROBORATED', 'CORROBORATED', 'x x x x x')",
                      (rec["id"],))
        hist = h.execute("SELECT lfhe.decide_corroboration_recommendation(%s, true, 'UNVERIFIED', 'PARTIALLY_CORROBORATED', "
                         "'lineage of the second outlet still unknown') AS id", (rec["id"],)).fetchone()["id"]
    with pg.admin() as x:
        h = x.execute("SELECT * FROM lfhe.claim_status_history WHERE id=%s", (hist,)).fetchone()
        assert (h["basis"], h["actor_type"], h["new_status"], str(h["recommending_model_run_id"])) == (
            "HUMAN_DECISION", "HUMAN", "PARTIALLY_CORROBORATED", run)
        ev = {r["event_type"]: r["actor_type"] for r in x.execute(
            "SELECT event_type, actor_type FROM lfhe.audit_log WHERE object_id IN (%s, %s)", (str(hist), str(rec["id"])))}
        assert ev.get("CLAIM_STATUS_CHANGED") == "HUMAN"


# --- test 8: high impact --------------------------------------------------------
def test_high_impact_recommendation_requires_human_confirmation(pg, analyst):
    a = grounded_claim(pg, EN_A, "6 radars were delivered")
    with pg.as_user(analyst) as h:
        h.execute("SELECT lfhe.mark_claim_high_impact(%s, true, NULL, 'key capability claim for the report')", (a["claim_id"],))
    run = lineage_run(pg, [a])
    ingest_lineage(pg, run, recommendations=[{"claim_id": a["claim_id"], "recommendation": "POTENTIAL_CONTESTED",
                                              "recommended_status": "CONTESTED", "supporting_claim_ids": [],
                                              "explanation": "conflicting figure elsewhere"}])
    with pg.admin() as x:
        rec = x.execute("SELECT * FROM lfhe.corroboration_recommendations WHERE model_run_id=%s", (run,)).fetchone()
        x.execute("INSERT INTO lfhe.claim_status_auto_rules (rule_code, from_status, to_status, description) VALUES "
                  "('P3_TEST_RULE', 'UNVERIFIED', 'CONTESTED', 'synthetic') ON CONFLICT DO NOTHING")
    assert rec["high_impact_at_recommendation"] and rec["human_review_required"]
    with pg.worker() as w, pytest.raises(psycopg.errors.InsufficientPrivilege, match="HIGH_IMPACT_REQUIRES_HUMAN"):
        w.execute("SELECT lfhe.apply_automatic_claim_status(%s, 'P3_TEST_RULE', %s, NULL)", (a["claim_id"], run))
    with pg.as_user(analyst) as h:
        h.execute("SELECT lfhe.decide_corroboration_recommendation(%s, true, 'UNVERIFIED', 'CONTESTED', "
                  "'competing figure confirmed by a second official source')", (rec["id"],))
    with pg.admin() as x:
        s = x.execute("SELECT * FROM lfhe.claim_status_usability WHERE claim_id=%s", (a["claim_id"],)).fetchone()
    assert s["claim_status"] == "CONTESTED" and s["status_human_confirmed"] and s["status_usable"]


# --- test 9: non-humans cannot finalise lineage/status ---------------------------
def test_non_humans_cannot_finalise_lineage_or_status(pg, make_user):
    a = grounded_claim(pg, EN_A, "6 radars were delivered")
    b = grounded_claim(pg, "Copy: " + EN_A, "6 radars were delivered")
    run = lineage_run(pg, [a, b])
    ingest_lineage(pg, run, [rel(b, "DERIVED_REPORTING", parent_claim=a)],
                   [{"claim_id": a["claim_id"], "recommendation": "POTENTIAL_SOURCE_DEPENDENCE", "recommended_status": None,
                     "supporting_claim_ids": [], "explanation": "copy"}])
    [p] = proposals(pg, run)
    with pg.admin() as x:
        rec = x.execute("SELECT id FROM lfhe.corroboration_recommendations WHERE model_run_id=%s", (run,)).fetchone()["id"]
    viewer, admin = make_user("VIEWER"), make_user("ADMIN")
    calls = [("SELECT lfhe.decide_lineage_proposal(%s, true, 'not allowed')", (p["id"],)),
             ("SELECT lfhe.record_claim_lineage(%s::jsonb, 'not allowed')",
              (f'{{"child_claim_id": "{b["claim_id"]}", "relationship_type": "DERIVED_REPORTING", "parent_claim_id": "{a["claim_id"]}"}}',)),
             ("SELECT lfhe.decide_corroboration_recommendation(%s, true, 'UNVERIFIED', 'CORROBORATED', 'not allowed')", (rec,))]
    for sql, args in calls:
        for conn in (pg.worker, pg.as_service_role, pg.as_anon, lambda: pg.as_user(viewer), lambda: pg.as_user(admin)):
            with conn() as x, pytest.raises(psycopg.errors.InsufficientPrivilege):
                x.execute(sql, args)
    with pg.admin() as x:
        assert x.execute("SELECT count(*) n FROM lfhe.claim_lineage WHERE child_claim_id=%s", (b["claim_id"],)).fetchone()["n"] == 0
        assert x.execute("SELECT claim_status FROM lfhe.claim_state WHERE claim_id=%s", (a["claim_id"],)).fetchone()["claim_status"] == "UNVERIFIED"



# --- CG3-03: external-origin identity is never inferred from the name alone (migration 2500)
MOD = "Southland Ministry of Defence"


def origin_claim(pg, url=None, n=5):
    text = f"According to the {MOD}, {n} jets landed." + (f" Statement: {url}" if url else "")
    return grounded_claim(pg, text, f"the {MOD}, {n} jets landed")


def accept_origin(pg, user, claims_urls, *, select=None):
    """One M04 run proposing COMMON_ORIGINAL_SOURCE for each (claim, url); accept each proposal.
    select: index → existing external_origin_id chosen explicitly by the human."""
    claims = [c for c, _ in claims_urls]
    run = lineage_run(pg, claims)
    ingest_lineage(pg, run, [rel(c, origin=MOD, url=u) for c, u in claims_urls])
    origins = []
    for n, p in enumerate(proposals(pg, run)):
        with pg.as_user(user) as h:
            lid = h.execute("SELECT lfhe.decide_lineage_proposal(%s, true, 'origin named in the text', %s) AS id",
                            (p["id"], (select or {}).get(n))).fetchone()["id"]
            origins.append(str(h.execute("SELECT external_origin_id FROM lfhe.claim_lineage WHERE id=%s",
                                         (lid,)).fetchone()["external_origin_id"]))
    return origins, claims


def test_same_name_without_explicit_reuse_does_not_collapse(pg, analyst):
    (o1, o2), claims = accept_origin(pg, analyst, [(origin_claim(pg), None), (origin_claim(pg, n=6), None)])
    assert o1 != o2                                                      # case 3: name alone ≠ same origin
    assert summary(pg, claims)["distinct_groups_upper_bound"] == 2


def test_same_name_with_explicit_human_selection_is_one_group(pg, analyst):
    a, b = origin_claim(pg), origin_claim(pg, n=6)
    (o1,), _ = accept_origin(pg, analyst, [(a, None)])
    (o2,), _ = accept_origin(pg, analyst, [(b, None)], select={0: o1})
    assert o1 == o2                                                      # case 1 / case 5 (L3 via explicit validation)
    assert summary(pg, [a, b])["distinct_groups_upper_bound"] == 1


def test_same_name_different_urls_remain_distinct_same_url_is_reused(pg, analyst):
    u1, u2 = "https://example.org/mod/statement-1", "https://example.org/mod/statement-2"
    (o1, o2), _ = accept_origin(pg, analyst, [(origin_claim(pg, u1), u1), (origin_claim(pg, u2, 6), u2)])
    assert o1 != o2                                                      # case 2
    (o3,), _ = accept_origin(pg, analyst, [(origin_claim(pg, u1, 7), u1)])
    assert o3 == o1                                                      # unambiguous: same canonical URL + name


def test_ambiguous_identity_never_creates_false_dependence(pg, analyst):
    u1 = "https://example.org/mod/statement-9"
    (o1, o2), claims = accept_origin(pg, analyst, [(origin_claim(pg, u1), u1), (origin_claim(pg, n=6), None)])
    assert o1 != o2 and summary(pg, claims)["distinct_groups_upper_bound"] == 2      # URL vs no URL: kept apart
    other = grounded_claim(pg, "According to the Westland Air Staff, 2 jets landed.", "the Westland Air Staff, 2 jets landed")
    run = lineage_run(pg, [other])
    ingest_lineage(pg, run, [rel(other, origin="Westland Air Staff")])
    [p] = proposals(pg, run)
    with pg.as_user(analyst) as h, pytest.raises(psycopg.errors.CheckViolation, match="EXTERNAL_ORIGIN_INVALID"):
        h.execute("SELECT lfhe.decide_lineage_proposal(%s, true, 'wrong origin chosen', %s)", (p["id"], o1))
    u2 = "https://example.org/mod/statement-10"
    c = origin_claim(pg, u2, 8)
    run = lineage_run(pg, [c])
    ingest_lineage(pg, run, [rel(c, origin=MOD, url=u2)])
    [p] = proposals(pg, run)
    with pg.as_user(analyst) as h, pytest.raises(psycopg.errors.CheckViolation, match="EXTERNAL_ORIGIN_IDENTITY_CONFLICT"):
        h.execute("SELECT lfhe.decide_lineage_proposal(%s, true, 'conflicting URL', %s)", (p["id"], o1))
