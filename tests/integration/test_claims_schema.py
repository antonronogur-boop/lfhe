"""P2-02 — claim pipeline schema: database-authoritative QA-D18 grounding,
immutable claims, status history, high-impact guard, human review,
conservative entities, closed taxonomy (Addendum v1.0 §6–§13, §15)."""
import json
import uuid

import psycopg
import pytest
from psycopg.types.json import Jsonb

from claims_support import candidate, extraction_run, ingest, make_model_run, make_text_snapshot, span_for
from lfhe_shared.audit import verify_chain

pytestmark = pytest.mark.db

EN = ("The Ministry of Defence said on 3 October that 12 interceptor drones were delivered to the "
      "air defence brigade. Officials reported that the radar may enter service next year.")
UK = ("Міністерство оборони повідомило, що 🛩️ бригада ППО отримала 12 дронів-перехоплювачів. "
      "За словами посадовців, радар може бути прийнятий на озброєння наступного року.")


@pytest.fixture
def snap(pg):
    return make_text_snapshot(pg, EN)


def claims_of(pg, run_id):
    with pg.admin() as c:
        return c.execute("SELECT * FROM lfhe.claims WHERE created_by_model_run_id=%s ORDER BY claim_local_id",
                         (run_id,)).fetchall()


def rejections_of(pg, run_id):
    with pg.admin() as c:
        return c.execute("SELECT * FROM lfhe.claim_extraction_rejections WHERE model_run_id=%s", (run_id,)).fetchall()


# ---------------------------------------------------------------------------
# Grounding (tests 1–5, 25)
# ---------------------------------------------------------------------------
def test_exact_original_language_span_is_persisted_and_resolvable(pg, snap):
    run = extraction_run(pg, snap)
    exact = "12 interceptor drones were delivered to the air defence brigade"
    out = ingest(pg, snap, run, [candidate(EN, exact)])
    assert out["outcome"] == "CLAIMS_PERSISTED" and out["claims_persisted"] == 1
    [c] = claims_of(pg, run)
    span = c["evidence_span_original"]
    assert span == {"article_snapshot_id": snap["snapshot_id"], "text_representation_id": snap["rep_id"],
                    "language": "en", "exact_text": exact, "start": EN.index(exact), "end": EN.index(exact) + len(exact),
                    "locator_type": "TEXT_REPRESENTATION_CODE_POINTS", "offset_unit": "UNICODE_CODE_POINT"}
    assert EN[span["start"]:span["end"]] == exact
    assert c["fact_assumption_marker"] == "FACT" and c["independent_confirmation"] == "NOT_ASSESSED"
    assert c["source_reliability_assessment"] is None and c["claim_credibility"] is None
    assert len(c["claim_hash"]) == 64
    with pg.admin() as a:
        [h] = a.execute("SELECT * FROM lfhe.claim_status_history WHERE claim_id=%s", (c["id"],)).fetchall()
        assert (h["old_status"], h["new_status"], h["basis"], h["actor_type"]) == (
            None, "UNVERIFIED", "INITIAL_EXTRACTION", "WORKER")
        events = {r["event_type"] for r in a.execute(
            "SELECT event_type FROM lfhe.audit_log WHERE object_id IN (%s, %s)", (str(c["id"]), run)).fetchall()}
        assert {"CLAIM_CREATED", "CLAIM_EXTRACTION_RECORDED"} <= events


@pytest.mark.parametrize("mutate, reason", [
    (lambda s: {**s, "start": s["start"] + 1}, "EXACT_TEXT_MISMATCH"),                 # wrong offset
    (lambda s: {**s, "end": 10_000}, "OFFSETS_INVALID"),
    (lambda s: {**s, "start": -1}, "OFFSETS_INVALID"),
    (lambda s: {**s, "exact_text": s["exact_text"].replace("12", "21")}, "EXACT_TEXT_MISMATCH"),  # wrong exact_text
    (lambda s: {**s, "language": "hu"}, "LANGUAGE_MISMATCH"),
    (lambda s: {**s, "locator_type": "CSS_SELECTOR"}, "LOCATOR_TYPE_UNSUPPORTED"),
])
def test_invalid_spans_are_rejected_not_persisted(pg, snap, mutate, reason):
    run = extraction_run(pg, snap)
    exact = "12 interceptor drones were delivered"
    bad = candidate(EN, exact)
    bad["evidence_span_original"] = mutate(bad["evidence_span_original"])
    out = ingest(pg, snap, run, [bad])
    assert out["outcome"] == "ALL_REJECTED" and out["claims_persisted"] == 0
    assert claims_of(pg, run) == []
    [r] = rejections_of(pg, run)
    assert r["grounding_failure"] and r["reason_codes"][0] == "CLAIM_NOT_GROUNDED_IN_ORIGINAL_SOURCE"
    assert reason in r["reason_codes"]


def test_translation_only_grounding_fails(pg):
    snap = make_text_snapshot(pg, UK, language="uk")
    run = extraction_run(pg, snap)
    translation = "the air defence brigade received 12 interceptor drones"   # working translation, not in source
    c = candidate(UK, "бригада ППО отримала 12 дронів-перехоплювачів", language="uk")
    c["evidence_span_original"] = {"exact_text": translation, "start": 0, "end": len(translation),
                                   "language": "en", "locator_type": "TEXT_REPRESENTATION_CODE_POINTS"}
    c["claim_text_original"] = translation
    out = ingest(pg, snap, run, [c])
    assert out["claims_persisted"] == 0
    [r] = rejections_of(pg, run)
    assert {"CLAIM_NOT_GROUNDED_IN_ORIGINAL_SOURCE", "LANGUAGE_MISMATCH", "EXACT_TEXT_MISMATCH"} <= set(r["reason_codes"])


def test_wrong_snapshot_text_representation_relationship_fails(pg, snap):
    other = make_text_snapshot(pg, EN)
    run = make_model_run(pg, "M02_CLAIM_EXTRACTOR", [("text_representation", other["rep_id"]),
                                                     ("text_representation", snap["rep_id"])])
    payload_snap = {**snap, "rep_id": other["rep_id"]}            # rep of another snapshot
    with pytest.raises(psycopg.errors.CheckViolation, match="CLAIM_PROVENANCE_INVALID"):
        ingest(pg, payload_snap, run, [candidate(EN, "12 interceptor drones")])
    with pg.worker() as c:
        probs = c.execute("SELECT lfhe.claim_grounding_problems(%s,%s,%s,%s,'en','TEXT_REPRESENTATION_CODE_POINTS',0,3,'The','The') AS p",
                          (other["rep_id"], snap["snapshot_id"], snap["article_id"], snap["source_id"])).fetchone()["p"]
    assert probs == ["TEXT_REPRESENTATION_NOT_OF_SNAPSHOT"]


def test_claim_text_original_must_lie_inside_the_span(pg, snap):
    run = extraction_run(pg, snap)
    c = candidate(EN, "12 interceptor drones were delivered", original="12 interceptor drones were shot down")
    assert ingest(pg, snap, run, [c])["claims_persisted"] == 0
    assert "CLAIM_TEXT_ORIGINAL_NOT_IN_SPAN" in rejections_of(pg, run)[0]["reason_codes"]


def test_non_nfc_exact_text_fails(pg):
    text = "Le ministère a annoncé l'arrivée des radars."
    snap = make_text_snapshot(pg, text, language="fr")
    run = extraction_run(pg, snap)
    c = candidate(text, "Le ministère a annoncé", language="fr")
    decomposed = c["evidence_span_original"]["exact_text"].replace("è", "è")
    c["evidence_span_original"]["exact_text"] = decomposed
    c["claim_text_original"] = decomposed
    assert ingest(pg, snap, run, [c])["claims_persisted"] == 0
    assert "EXACT_TEXT_NOT_NFC" in rejections_of(pg, run)[0]["reason_codes"]


def test_metadata_only_snapshot_cannot_ground(pg):
    snap = make_text_snapshot(pg, EN, retention="METADATA_ONLY")
    assert snap["rep_id"] is None        # no text is retained at all
    other = make_text_snapshot(pg, EN)
    with pg.worker() as c:
        probs = c.execute("SELECT lfhe.claim_grounding_problems(%s,%s,%s,%s,'en','TEXT_REPRESENTATION_CODE_POINTS',0,3,'The','The') AS p",
                          (other["rep_id"], snap["snapshot_id"], snap["article_id"], snap["source_id"])).fetchone()["p"]
    assert "TEXT_REPRESENTATION_NOT_OF_SNAPSHOT" in probs


def test_unicode_code_point_offsets_are_stable(pg):
    snap = make_text_snapshot(pg, UK, language="uk")
    run = extraction_run(pg, snap)
    exact = "бригада ППО отримала 12 дронів-перехоплювачів"
    out = ingest(pg, snap, run, [candidate(UK, exact, language="uk")])
    assert out["claims_persisted"] == 1
    [c] = claims_of(pg, run)
    # the emoji before the span is outside the BMP-free assumption: offsets are code points, not UTF-16 / bytes
    assert UK[c["span_start"]:c["span_end"]] == exact
    assert c["span_start"] == UK.index(exact) != UK.encode("utf-8").index(exact.encode("utf-8"))
    with pg.admin() as a:
        stored = a.execute("SELECT substr(text_content, %s + 1, %s) AS s FROM lfhe.text_representations WHERE id=%s",
                           (c["span_start"], c["span_end"] - c["span_start"], snap["rep_id"])).fetchone()["s"]
    assert stored == exact


# ---------------------------------------------------------------------------
# Backstops and provenance
# ---------------------------------------------------------------------------
def test_direct_insert_of_ungrounded_claim_is_blocked_even_for_owner(pg, snap):
    run = extraction_run(pg, snap)
    ingest(pg, snap, run, [])           # creates the result row
    with pg.admin() as a, pytest.raises(psycopg.errors.CheckViolation, match="CLAIM_NOT_GROUNDED_IN_ORIGINAL_SOURCE"):
        a.execute("""INSERT INTO lfhe.claims (source_id, article_id, article_snapshot_id, text_representation_id,
          created_by_model_run_id, claim_local_id, language_original, claim_text_original, claim_text_normalised,
          claim_type, source_statement_status, event_date_confidence, evidence_type, evidence_directness,
          source_uncertainty_preserved, potential_contradiction, span_locator_type, span_start, span_end,
          span_exact_text, evidence_span_original, human_review_required, claim_hash)
          VALUES (%s,%s,%s,%s,%s,'X1','en','invented','invented','OTHER','UNKNOWN','UNKNOWN','UNKNOWN','UNKNOWN',
                  true,false,'TEXT_REPRESENTATION_CODE_POINTS',0,8,'invented','{}',false,repeat('0',64))""",
                  (snap["source_id"], snap["article_id"], snap["snapshot_id"], snap["rep_id"], run))


def test_claims_require_a_succeeded_m02_run_that_had_the_text_as_input(pg, snap):
    wrong_module = make_model_run(pg, "M03_CLASSIFIER", [("text_representation", snap["rep_id"])],
                                  context=[("taxonomy", "LFHE-TAX-1.2")], task_parameters={"taxonomy_version": "LFHE-TAX-1.2"})
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
        ingest(pg, snap, wrong_module, [candidate(EN, "12 interceptor drones")])
    not_input = make_model_run(pg, "M02_CLAIM_EXTRACTOR", [("article_snapshot", snap["snapshot_id"])])
    with pytest.raises(psycopg.errors.CheckViolation, match="CLAIM_PROVENANCE_INVALID"):
        ingest(pg, snap, not_input, [candidate(EN, "12 interceptor drones")])


def test_failed_runs_are_recorded_without_claims(pg, snap):
    for status in ("SCHEMA_VALIDATION_FAILED", "PROVIDER_ERROR"):
        run = extraction_run(pg, snap, status=status)
        out = ingest(pg, snap, run, [candidate(EN, "12 interceptor drones")])
        assert out["outcome"] == status and claims_of(pg, run) == []


def test_ingestion_is_once_per_model_run(pg, snap):
    run = extraction_run(pg, snap)
    ingest(pg, snap, run, [candidate(EN, "12 interceptor drones")])
    with pytest.raises(psycopg.errors.UniqueViolation):
        ingest(pg, snap, run, [candidate(EN, "12 interceptor drones")])
    assert len(claims_of(pg, run)) == 1


def test_claim_rows_are_immutable(pg, snap):
    run = extraction_run(pg, snap)
    ingest(pg, snap, run, [candidate(EN, "12 interceptor drones")])
    [c] = claims_of(pg, run)
    with pg.admin() as a:
        for sql in ("UPDATE lfhe.claims SET claim_text_normalised='x' WHERE id=%s", "DELETE FROM lfhe.claims WHERE id=%s",
                    "DELETE FROM lfhe.claim_status_history WHERE claim_id=%s"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                a.execute(sql, (c["id"],))


@pytest.mark.parametrize("field, value", [("claim_type", "RUMOUR"), ("claim_type", "EVENT"),
                                          ("source_statement_status", "CONFIRMED")])
def test_closed_enums_reject_unknown_values(pg, snap, field, value):
    run = extraction_run(pg, snap)
    with pytest.raises(psycopg.errors.InvalidTextRepresentation):
        ingest(pg, snap, run, [candidate(EN, "12 interceptor drones", **{field: value})])
    assert claims_of(pg, run) == []
    with pg.admin() as a:
        labels = [r["e"] for r in a.execute("SELECT unnest(enum_range(NULL::lfhe.claim_status))::text AS e").fetchall()]
    assert labels == ["UNVERIFIED", "PARTIALLY_CORROBORATED", "CORROBORATED", "CONFIRMED_PRIMARY",
                      "CONTESTED", "DISPROVEN", "SUPERSEDED"]


def test_review_flags_are_closed_and_force_human_review(pg, snap):
    run = extraction_run(pg, snap)
    ingest(pg, snap, run, [candidate(EN, "12 interceptor drones", review_flags=["NORMALISATION_NEGATION_LOSS"],
                                     human_review_required=False)])
    [c] = claims_of(pg, run)
    assert c["review_flags"] == ["NORMALISATION_NEGATION_LOSS"] and c["human_review_required"] is True
    run2 = extraction_run(pg, snap)
    with pytest.raises(psycopg.errors.CheckViolation):
        ingest(pg, snap, run2, [candidate(EN, "12 interceptor drones", review_flags=["LOOKS_FINE"])])


def test_mentions_not_in_source_are_dropped_and_flagged(pg, snap):
    run = extraction_run(pg, snap)
    ingest(pg, snap, run, [candidate(EN, "12 interceptor drones were delivered", entities=[
        {"mention_text_original": "Ministry of Defence", "entity_type": "ORGANISATION"},
        {"mention_text_original": "Wagner Group", "entity_type": "ORGANISATION"}],
        locations=["Kyiv"])])
    [c] = claims_of(pg, run)
    assert "ENTITY_MENTION_NOT_IN_SOURCE" in c["review_flags"] and c["human_review_required"]
    assert c["location_mentions"] == []
    with pg.admin() as a:
        mentions = [r["mention_text_original"] for r in a.execute(
            "SELECT mention_text_original FROM lfhe.entity_mentions WHERE claim_id=%s", (c["id"],)).fetchall()]
    assert mentions == ["Ministry of Defence"]


# ---------------------------------------------------------------------------
# Status, high impact, revalidation (test 13)
# ---------------------------------------------------------------------------
@pytest.fixture
def auto_rule(pg):
    with pg.admin() as a:
        a.execute("INSERT INTO lfhe.claim_status_auto_rules (rule_code, from_status, to_status, description) "
                  "VALUES ('TEST_PARTIAL', 'UNVERIFIED', 'PARTIALLY_CORROBORATED', 'synthetic test rule') "
                  "ON CONFLICT DO NOTHING")
    return "TEST_PARTIAL"


def one_claim(pg, snap=None):
    snap = snap or make_text_snapshot(pg, EN)
    run = extraction_run(pg, snap)
    ingest(pg, snap, run, [candidate(EN, "12 interceptor drones were delivered")])
    return claims_of(pg, run)[0], run


def state(pg, claim_id):
    with pg.admin() as a:
        return a.execute("SELECT * FROM lfhe.claim_status_usability u JOIN lfhe.claim_state s USING (claim_id) "
                         "WHERE claim_id=%s", (claim_id,)).fetchone()


def test_automatic_status_requires_configured_rule(pg):
    c, run = one_claim(pg)
    with pg.worker() as w, pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState, match="AUTO_RULE_NOT_CONFIGURED"):
        w.execute("SELECT lfhe.apply_automatic_claim_status(%s, 'NO_SUCH_RULE', %s, NULL)", (c["id"], run))


def test_high_impact_claim_cannot_be_changed_automatically(pg, auto_rule):
    c, run = one_claim(pg)
    with pg.worker() as w:
        w.execute("SELECT lfhe.set_claim_high_impact(%s, true, ARRAY['KEY_NUMERICAL_ASSERTION']::lfhe.high_impact_reason[], "
                  "'orchestrator rule: numerical assertion')", (c["id"],))
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="HIGH_IMPACT_REQUIRES_HUMAN"):
            w.execute("SELECT lfhe.apply_automatic_claim_status(%s, %s, %s, NULL)", (c["id"], auto_rule, run))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            w.execute("SELECT lfhe.set_claim_high_impact(%s, true, ARRAY['HUMAN_MARKED_HIGH_IMPACT']::lfhe.high_impact_reason[], "
                      "'worker pretending to be human')", (c["id"],))


def test_low_to_high_impact_after_automatic_status_requires_revalidation(pg, make_user, auto_rule):
    analyst = make_user("ANALYST")
    c, run = one_claim(pg)
    with pg.worker() as w:
        w.execute("SELECT lfhe.apply_automatic_claim_status(%s, %s, %s, NULL)", (c["id"], auto_rule, run))
    assert state(pg, c["id"])["status_usable"] is True
    with pg.worker() as w:
        w.execute("SELECT lfhe.set_claim_high_impact(%s, true, ARRAY['SUPPORTS_REPORT_CANDIDATE']::lfhe.high_impact_reason[], "
                  "'became a report candidate')", (c["id"],))
    s = state(pg, c["id"])
    assert s["high_impact"] and s["revalidation_pending"] and s["status_usable"] is False
    assert s["claim_status"] == "PARTIALLY_CORROBORATED"
    with pg.admin() as a:
        rv = a.execute("SELECT id FROM lfhe.claim_revalidations WHERE claim_id=%s", (c["id"],)).fetchone()["id"]
        assert a.execute("SELECT count(*) AS n FROM lfhe.audit_log WHERE event_type='HIGH_IMPACT_REVALIDATION_REQUIRED' "
                         "AND object_id=%s", (str(rv),)).fetchone()["n"] == 1
    with pg.worker() as w, pytest.raises(psycopg.errors.InsufficientPrivilege):
        w.execute("SELECT lfhe.decide_high_impact_revalidation(%s, true, 'worker cannot decide')", (rv,))
    with pg.as_user(analyst) as h:
        h.execute("SELECT lfhe.decide_high_impact_revalidation(%s, false, 'automatic corroboration not accepted')", (rv,))
    s = state(pg, c["id"])
    assert s["claim_status"] == "UNVERIFIED" and s["status_basis"] == "HIGH_IMPACT_REVALIDATION_REJECTED"
    assert not s["revalidation_pending"] and s["status_usable"]


def test_revalidation_approval_makes_strengthened_status_usable(pg, make_user, auto_rule):
    analyst = make_user("ANALYST")
    c, run = one_claim(pg)
    with pg.worker() as w:
        w.execute("SELECT lfhe.apply_automatic_claim_status(%s, %s, %s, NULL)", (c["id"], auto_rule, run))
        w.execute("SELECT lfhe.set_claim_high_impact(%s, true, ARRAY['MAY_CHANGE_TREND']::lfhe.high_impact_reason[], "
                  "'may change trend')", (c["id"],))
    with pg.admin() as a:
        rv = a.execute("SELECT id FROM lfhe.claim_revalidations WHERE claim_id=%s", (c["id"],)).fetchone()["id"]
    with pg.as_user(analyst) as h:
        h.execute("SELECT lfhe.decide_high_impact_revalidation(%s, true, 'checked the two sources by hand')", (rv,))
        with pytest.raises(psycopg.errors.UniqueViolation):
            h.execute("SELECT lfhe.decide_high_impact_revalidation(%s, true, 'second decision')", (rv,))
    s = state(pg, c["id"])
    assert s["claim_status"] == "PARTIALLY_CORROBORATED" and s["status_human_confirmed"] and s["status_usable"]


def test_human_marked_high_impact_cannot_be_removed_by_worker(pg, make_user):
    analyst = make_user("ANALYST")
    c, _ = one_claim(pg)
    with pg.as_user(analyst) as h:
        h.execute("SELECT lfhe.mark_claim_high_impact(%s, true, NULL, 'key claim for the weekly report')", (c["id"],))
    with pg.worker() as w, pytest.raises(psycopg.errors.InsufficientPrivilege):
        w.execute("SELECT lfhe.set_claim_high_impact(%s, false, '{}', 'rule says low impact')", (c["id"],))
    s = state(pg, c["id"])
    assert s["high_impact"] and s["high_impact_reasons"] == ["HUMAN_MARKED_HIGH_IMPACT"]
    with pg.admin() as a:
        assert a.execute("SELECT count(*) AS n FROM lfhe.audit_log WHERE event_type='CLAIM_MARKED_HIGH_IMPACT_BY_HUMAN' "
                         "AND object_id=%s", (str(c["id"]),)).fetchone()["n"] == 1


def test_high_impact_status_change_by_human_is_usable(pg, make_user):
    analyst = make_user("ANALYST")
    c, _ = one_claim(pg)
    with pg.worker() as w:
        w.execute("SELECT lfhe.set_claim_high_impact(%s, true, ARRAY['KEY_CAPABILITY_ASSERTION']::lfhe.high_impact_reason[], "
                  "'capability assertion')", (c["id"],))
    with pg.as_user(analyst) as h:
        h.execute("SELECT lfhe.set_claim_status(%s, 'UNVERIFIED', 'CORROBORATED', 'two independent official sources')",
                  (c["id"],))
        with pytest.raises(psycopg.errors.SerializationFailure, match="STATUS_STALE"):
            h.execute("SELECT lfhe.set_claim_status(%s, 'UNVERIFIED', 'CONTESTED', 'stale view of the claim')", (c["id"],))
    s = state(pg, c["id"])
    assert s["claim_status"] == "CORROBORATED" and s["status_basis"] == "HUMAN_DECISION" and s["status_usable"]


# ---------------------------------------------------------------------------
# Human review (tests 14, 15)
# ---------------------------------------------------------------------------
def test_non_human_roles_cannot_review_or_set_status(pg, make_user):
    c, _ = one_claim(pg)
    viewer, admin = make_user("VIEWER"), make_user("ADMIN")
    calls = [("SELECT lfhe.review_claim(%s, %s, NULL, 'APPROVE', 'looks right to me')", (c["id"], c["claim_hash"])),
             ("SELECT lfhe.set_claim_status(%s, 'UNVERIFIED', 'CORROBORATED', 'not allowed here')", (c["id"],)),
             ("SELECT lfhe.mark_claim_high_impact(%s, true, NULL, 'not allowed here')", (c["id"],))]
    for sql, args in calls:
        for conn in (pg.worker, pg.as_service_role, pg.as_anon, lambda: pg.as_user(viewer), lambda: pg.as_user(admin)):
            with conn() as x, pytest.raises(psycopg.errors.InsufficientPrivilege):
                x.execute(sql, args)
    with pg.admin() as a:
        assert a.execute("SELECT count(*) AS n FROM lfhe.claim_reviews WHERE claim_id=%s", (c["id"],)).fetchone()["n"] == 0


def test_human_review_is_audited_and_bound_to_object_and_version(pg, make_user):
    analyst = make_user("ANALYST")
    c, _ = one_claim(pg)
    with pg.as_user(analyst) as h:
        with pytest.raises(psycopg.errors.CheckViolation, match="REVIEW_OBJECT_MISMATCH"):
            h.execute("SELECT lfhe.review_claim(%s, %s, NULL, 'APPROVE', 'wrong content hash')", (c["id"], "0" * 64))
        r1 = h.execute("SELECT lfhe.review_claim(%s, %s, NULL, 'MODIFY_AND_APPROVE', 'restore attribution', %s::jsonb) AS id",
                       (c["id"], c["claim_hash"], Jsonb({"claim_text_normalised":
                        "The Ministry of Defence said 12 interceptor drones were delivered"}))).fetchone()["id"]
        with pytest.raises(psycopg.errors.SerializationFailure, match="REVIEW_STALE"):
            h.execute("SELECT lfhe.review_claim(%s, %s, NULL, 'REJECT', 'based on stale view')", (c["id"], c["claim_hash"]))
        with pytest.raises(psycopg.errors.InvalidParameterValue):
            h.execute("SELECT lfhe.review_claim(%s, %s, %s, 'MODIFY_AND_APPROVE', 'change the span', %s::jsonb)",
                      (c["id"], c["claim_hash"], r1, Jsonb({"span_exact_text": "x"})))
        r2 = h.execute("SELECT lfhe.review_claim(%s, %s, %s, 'ESCALATE', 'needs senior analyst') AS id",
                       (c["id"], c["claim_hash"], r1)).fetchone()["id"]
    s = state(pg, c["id"])
    assert s["review_state"] == "ESCALATED" and s["latest_review_id"] == r2
    with pg.admin() as a:
        rows = a.execute("SELECT event_type, actor_type, actor_user_id, metadata FROM lfhe.audit_log "
                         "WHERE object_type='claim' AND object_id=%s AND event_type IN ('CLAIM_MODIFIED','REVIEW_ESCALATED') "
                         "ORDER BY seq", (str(c["id"]),)).fetchall()
        assert [r["event_type"] for r in rows] == ["CLAIM_MODIFIED", "REVIEW_ESCALATED"]
        assert all(r["actor_type"] == "HUMAN" and r["actor_user_id"] == analyst for r in rows)
        assert rows[0]["metadata"]["claim_hash"] == c["claim_hash"]
        assert verify_chain(a).ok


# ---------------------------------------------------------------------------
# Entities (test 16)
# ---------------------------------------------------------------------------
def test_entity_resolution_is_conservative(pg, make_user):
    analyst = make_user("ANALYST")
    tag = uuid.uuid4().hex[:6]
    text = (f"Unit Alpha-{tag} and Brigade Delta-{tag} trained with Alpha-{tag} Systems. "
            f"Radar Kappa-{tag} was shown.")
    with pg.as_user(analyst) as h:
        unit = h.execute("SELECT lfhe.create_entity(%s, 'MILITARY_UNIT', NULL, 'synthetic unit') AS id",
                         (f"Unit Alpha-{tag}",)).fetchone()["id"]
        h.execute("SELECT lfhe.add_entity_alias(%s, %s, 'en', 'short form used by the unit''s own press office')",
                  (unit, f"Alpha-{tag}"))
        company = h.execute("SELECT lfhe.create_entity(%s, 'ORGANISATION', NULL, 'synthetic company') AS id",
                            (f"Alpha-{tag} Systems",)).fetchone()["id"]
        h.execute("SELECT lfhe.add_entity_alias(%s, %s, 'en', 'trading name in the company register extract')",
                  (company, f"Alpha-{tag}"))
        h.execute("SELECT lfhe.create_entity(%s, 'SYSTEM', NULL, 'synthetic radar') AS id", (f"Radar Kappa-{tag}",))
    snap = make_text_snapshot(pg, text)
    run = extraction_run(pg, snap)
    ingest(pg, snap, run, [candidate(text, text[:text.index(".")], entities=[
        {"mention_text_original": f"Unit Alpha-{tag}", "entity_type": "MILITARY_UNIT"},   # exact canonical → RESOLVED
        {"mention_text_original": f"Alpha-{tag}", "entity_type": None},                   # 2 entities → AMBIGUOUS
        {"mention_text_original": f"Brigade Delta-{tag}", "entity_type": "MILITARY_UNIT"},  # unknown → UNRESOLVED
        {"mention_text_original": f"Alpha-{tag}", "entity_type": "SYSTEM"},              # type mismatch → UNRESOLVED
        {"mention_text_original": f"Kappa-{tag}", "entity_type": "SYSTEM"},              # similar, not alias → UNRESOLVED
    ])])
    [c] = claims_of(pg, run)
    with pg.admin() as a:
        res = a.execute("SELECT * FROM lfhe.entity_mention_resolution WHERE claim_id=%s ORDER BY mention_index",
                        (c["id"],)).fetchall()
    assert [r["resolution_status"] for r in res] == ["RESOLVED", "AMBIGUOUS", "UNRESOLVED", "UNRESOLVED", "UNRESOLVED"]
    assert res[0]["entity_id"] == unit and set(res[1]["candidate_entity_ids"]) == {unit, company}
    assert all(r["entity_id"] is None for r in res[1:])
    # a human may resolve the ambiguous mention; the worker may not override it afterwards
    with pg.as_user(analyst) as h:
        h.execute("SELECT lfhe.link_entity_mention(%s, 'RESOLVED', %s, 'context: same sentence names the company')",
                  (res[1]["mention_id"], company))
    with pg.worker() as w:
        assert w.execute("SELECT lfhe.auto_resolve_mention(%s) AS s", (res[1]["mention_id"],)).fetchone()["s"] == "RESOLVED"
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            w.execute("SELECT lfhe.create_entity('x', 'OTHER', NULL, 'worker cannot create')")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            w.execute("SELECT lfhe.link_entity_mention(%s, 'RESOLVED', %s, 'worker cannot link')", (res[2]["mention_id"], unit))
    with pg.admin() as a:
        cur = a.execute("SELECT * FROM lfhe.entity_mention_resolution WHERE mention_id=%s", (res[1]["mention_id"],)).fetchone()
        assert cur["method"] == "HUMAN" and cur["entity_id"] == company


def test_alias_requires_a_basis_and_relationships_are_human_and_audited(pg, make_user):
    analyst = make_user("ANALYST")
    with pg.as_user(analyst) as h:
        e1 = h.execute("SELECT lfhe.create_entity('Synthetic Air Wing', 'MILITARY_UNIT', NULL, 'synthetic') AS id").fetchone()["id"]
        e2 = h.execute("SELECT lfhe.create_entity('Synthetic Air Force', 'ORGANISATION', NULL, 'synthetic') AS id").fetchone()["id"]
        with pytest.raises(psycopg.errors.CheckViolation):
            h.execute("SELECT lfhe.add_entity_alias(%s, 'SAW', 'en', 'similar')", (e1,))
        rel = h.execute("SELECT lfhe.create_entity_relationship(%s, 'SUBORDINATE_TO', %s, "
                        "'organisation chart published by the air force') AS id", (e1, e2)).fetchone()["id"]
        with pytest.raises(psycopg.errors.CheckViolation):
            h.execute("SELECT lfhe.create_entity_relationship(%s, 'SAME_AS', %s, 'names look alike, so merge')", (e1, e2))
    with pg.admin() as a:
        assert a.execute("SELECT count(*) AS n FROM lfhe.audit_log WHERE event_type='ENTITY_RELATIONSHIP_CREATED' "
                         "AND object_id=%s", (str(rel),)).fetchone()["n"] == 1


# ---------------------------------------------------------------------------
# Taxonomy (tests 17–20)
# ---------------------------------------------------------------------------
def classification_run(pg, claim_ids, version="LFHE-TAX-1.2"):
    return make_model_run(pg, "M03_CLASSIFIER", [("claim", str(i)) for i in claim_ids],
                          context=[("taxonomy", version)], task_parameters={"taxonomy_version": version})


def classify(pg, run, assignments, **extra):
    with pg.worker() as w:
        return w.execute("SELECT lfhe.ingest_classification(%s::jsonb) AS r", (Jsonb({
            "model_run_id": run, "output_status": "SUCCESS", "classification_confidence": "MODERATE",
            "human_review_required": False, "warnings": [], "assignments": assignments, **extra}),)).fetchone()["r"]


def a(tt, tid, cid, conf="HIGH"):
    return {"taxonomy_type": tt, "taxonomy_id": tid, "target_object_type": "CLAIM", "target_object_id": str(cid),
            "confidence": conf}


def test_taxonomy_is_closed_and_seeded_from_v12(pg):
    with pg.admin() as x:
        counts = {r["taxonomy_type"]: r["n"] for r in x.execute(
            "SELECT taxonomy_type, count(*) AS n FROM lfhe.taxonomy_items GROUP BY 1").fetchall()}
        assert counts == {"TOPIC": 37, "TAG": 13, "PIR": 8, "GEO": 4}
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            x.execute("UPDATE lfhe.taxonomy_items SET label='x' WHERE id='TOPIC_UAS'")


def test_multi_label_assignments_with_target_ids(pg):
    c1, _ = one_claim(pg)
    c2, _ = one_claim(pg)
    run = classification_run(pg, [c1["id"], c2["id"]])
    out = classify(pg, run, [a("TOPIC", "TOPIC_UAS", c1["id"]), a("TOPIC", "TOPIC_C_UAS", c1["id"], "MODERATE"),
                             a("PIR", "PIR_05", c1["id"]), a("GEO", "GEO_PRIORITY_1", c1["id"], "LOW"),
                             a("TAG", "TAG_MASS", c2["id"])])
    assert out["outcome"] == "ASSIGNMENTS_PERSISTED" and out["assignments"] == 5
    with pg.admin() as x:
        rows = x.execute("SELECT target_object_id, taxonomy_id FROM lfhe.taxonomy_assignments WHERE model_run_id=%s",
                         (run,)).fetchall()
    assert {(r["target_object_id"], r["taxonomy_id"]) for r in rows} == {
        (c1["id"], "TOPIC_UAS"), (c1["id"], "TOPIC_C_UAS"), (c1["id"], "PIR_05"), (c1["id"], "GEO_PRIORITY_1"),
        (c2["id"], "TAG_MASS")}


@pytest.mark.parametrize("bad, reason", [
    (lambda cid: a("TOPIC", "TOPIC_HYPERSONICS", cid), "TAXONOMY_ID_NOT_IN_SUPPLIED_TAXONOMY"),   # invented
    (lambda cid: a("PIR", "PIR_09", cid), "TAXONOMY_ID_NOT_IN_SUPPLIED_TAXONOMY"),
    (lambda cid: a("GEO", "GEO_ARCTIC", cid), "TAXONOMY_ID_NOT_IN_SUPPLIED_TAXONOMY"),
    (lambda cid: a("TAG", "TOPIC_UAS", cid), "TAXONOMY_ID_NOT_IN_SUPPLIED_TAXONOMY"),            # wrong type
    (lambda cid: a("TOPIC", "TOPIC_UAS", uuid.uuid4()), "TARGET_NOT_IN_MODEL_RUN_INPUT"),
    (lambda cid: {**a("TOPIC", "TOPIC_UAS", cid), "target_object_type": "ARTICLE"}, "TARGET_OBJECT_TYPE_NOT_ALLOWED"),
])
def test_invalid_assignment_rejects_the_whole_output(pg, bad, reason):
    c, _ = one_claim(pg)
    run = classification_run(pg, [c["id"]])
    out = classify(pg, run, [a("TOPIC", "TOPIC_UAS", c["id"]), bad(c["id"])])
    assert out["outcome"] == "OUTPUT_REJECTED" and out["assignments"] == 0
    assert any(r.startswith(reason) for r in out["rejection_reasons"])
    with pg.admin() as x:
        assert x.execute("SELECT count(*) AS n FROM lfhe.taxonomy_assignments WHERE model_run_id=%s",
                         (run,)).fetchone()["n"] == 0
        res = x.execute("SELECT * FROM lfhe.claim_classification_results WHERE model_run_id=%s", (run,)).fetchone()
        assert res["human_review_required"] is True


def test_classification_requires_supplied_taxonomy_and_m03_run(pg):
    c, _ = one_claim(pg)
    no_ctx = make_model_run(pg, "M03_CLASSIFIER", [("claim", str(c["id"]))], task_parameters={"taxonomy_version": "LFHE-TAX-1.2"})
    with pytest.raises(psycopg.errors.CheckViolation, match="TAXONOMY_NOT_SUPPLIED"):
        classify(pg, no_ctx, [a("TOPIC", "TOPIC_UAS", c["id"])])
    other_version = classification_run(pg, [c["id"]], version="LFHE-TAX-9.9")
    assert classify(pg, other_version, [a("TOPIC", "TOPIC_UAS", c["id"])])["outcome"] == "OUTPUT_REJECTED"
    with pg.admin() as x, pytest.raises(psycopg.errors.CheckViolation, match="TAXONOMY_PROVENANCE_INVALID"):
        m02 = extraction_run(pg, make_text_snapshot(pg, EN))
        x.execute("INSERT INTO lfhe.claim_classification_results (model_run_id, model_run_status, outcome, "
                  "taxonomy_version, assignments_persisted, human_review_required) "
                  "VALUES (%s, 'SUCCEEDED', 'ASSIGNMENTS_PERSISTED', 'LFHE-TAX-1.2', 1, false)", (m02,))
        x.execute("INSERT INTO lfhe.taxonomy_assignments (model_run_id, taxonomy_type, taxonomy_id, target_object_type, "
                  "target_object_id, assignment_confidence) VALUES (%s, 'TOPIC', 'TOPIC_UAS', 'CLAIM', %s, 'HIGH')", (m02, c["id"]))


# ---------------------------------------------------------------------------
# Read access
# ---------------------------------------------------------------------------
def test_claim_read_requires_claim_read_permission(pg, make_user):
    c, _ = one_claim(pg)
    viewer, nobody = make_user("VIEWER"), make_user()
    with pg.as_user(viewer) as v:
        assert v.execute("SELECT count(*) AS n FROM lfhe.claims WHERE id=%s", (c["id"],)).fetchone()["n"] == 1
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            v.execute("INSERT INTO lfhe.claim_reviews (claim_id) VALUES (%s)", (c["id"],))
    with pg.as_user(nobody) as n:
        assert n.execute("SELECT count(*) AS n FROM lfhe.claims WHERE id=%s", (c["id"],)).fetchone()["n"] == 0
    with pg.as_anon() as an, pytest.raises(psycopg.errors.InsufficientPrivilege):
        an.execute("SELECT * FROM lfhe.claims LIMIT 1")
