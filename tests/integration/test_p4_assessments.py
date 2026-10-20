"""P4-03 / P4-04 — statement-centric M07 assessments (Phase 4 Addendum §7–§12; required
tests 18–36) through the real M07 bundle, input builder and ingestion; scripted model."""
import json
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from psycopg.types.json import Jsonb

from claims_support import make_model_run
from lfhe_orchestrator.assessment_pipeline import run_assessment
from lfhe_orchestrator.providers import FakeProvider
from lineage_support import lineage_run
from p4_support import CUT_DT, KNOW, POST, approve, create_baseline, create_rc, head, human_event, pclaim
from pipeline_support import activate_real_prompts, model_configuration

pytestmark = pytest.mark.db
NOW = lambda: datetime.now(timezone.utc) + timedelta(minutes=5)   # noqa: E731
FACTUAL = {"KNOWN_FACT", "CHANGE_FROM_BASELINE", "INDICATOR_SUPPORT", "INDICATOR_WEAKEN"}


@pytest.fixture(scope="module")
def m07(pg):
    return activate_real_prompts(pg, ("M02_CLAIM_EXTRACTOR", "M03_CLASSIFIER", "M07_INTELLIGENCE_ASSESSOR"))


@pytest.fixture
def analyst(make_user):
    return make_user("ANALYST")


def setup_event(pg, analyst, *, contra=True, extra=()):
    a = pclaim(pg, "The air force said 4 tanker aircraft arrived at Fort Aster.", "4 tanker aircraft arrived at Fort Aster")
    claims, roles = [a], {}
    if contra:
        d = pclaim(pg, "A spokesman denied that any tanker aircraft arrived at Fort Aster.",
                   "denied that any tanker aircraft arrived at Fort Aster")
        claims.append(d)
        roles[d["claim_id"]] = "CONTRADICTS"
    claims += list(extra)
    e = human_event(pg, analyst, claims, title="Tanker arrival at Fort Aster", roles=roles)
    h = head(pg, e)
    return e, str(h["head_version_id"]), h["head_content_hash"], claims


def st(local, stype, text, prov="CASE_EVIDENCE", claims=(), contra=(), rcs=(), uses_baseline=False, premises=(),
       attr=None, attr_text=None, evidence=None, likelihood=None):
    return {"statement_local_id": local, "statement_type": stype, "statement_text": text, "provenance_class": prov,
            "supporting_claim_ids": [c["claim_id"] if isinstance(c, dict) else c for c in claims],
            "contradicting_claim_ids": [c["claim_id"] if isinstance(c, dict) else c for c in contra],
            "supporting_reference_context_ids": list(rcs), "uses_baseline": uses_baseline,
            "premise_statement_local_ids": list(premises), "attribution_required": attr,
            "attribution_text": attr_text, "evidence_required": stype in FACTUAL if evidence is None else evidence,
            "likelihood": likelihood}


def fill_attribution(env, statements):
    req = {c["claim_id"]: c["attribution_required_if_cited"] for c in env["inputs"][0]["content"]["claims"]}
    for s in statements:
        if s["attribution_required"] is None:
            needed = s["statement_type"] in FACTUAL and (any(req.get(c, True) for c in s["supporting_claim_ids"])
                                                         or (not s["supporting_claim_ids"] and s["supporting_reference_context_ids"]))
            s["attribution_required"] = bool(needed)
    return statements


def default_statements(claims):
    a = claims[0]
    out = [st("AS1", "KNOWN_FACT", "The air force reported that 4 tanker aircraft arrived at Fort Aster.", claims=[a],
              attr_text="The air force reported")]
    if len(claims) > 1:
        out.append(st("AS2", "ALTERNATIVE_EXPLANATION", "The arrival may not have happened; a spokesman denied it.",
                      prov="CASE_EVIDENCE", claims=[a], contra=[claims[1]], evidence=False))
    out.append(st("AS3", "ANALYTIC_JUDGMENT", "Northland is probably expanding air-refuelling support at Fort Aster.",
                  claims=[a], premises=["AS1"], evidence=True))
    out.append(st("AS4", "INFORMATION_GAP", "It is unknown how long the aircraft will remain.", prov="NONE_REQUIRED",
                  evidence=False))
    return out


def out(env, statements=None, *, claims=None, summary=None, indicators=(), conf="MODERATE",
        rationale="Single official source; contradicted by a denial; no independent confirmation.", **extra):
    statements = fill_attribution(env, statements if statements is not None else default_statements(claims))
    r = {"event_id": env["task"]["event_id"], "event_version_id": env["task"]["event_version_id"],
         "baseline_version_id": env["task"]["baseline_version_id"],
         "previous_assessment_version_id": env["task"]["previous_assessment_version_id"],
         "assessment_statements": statements,
         "derived_summary": summary or {"text": "", "source_statement_ids": []},
         "indicators_to_watch": list(indicators), "ai_recommended_confidence": conf, "ai_confidence_rationale": rationale}
    r.update(extra)
    return json.dumps({"module": "M07_INTELLIGENCE_ASSESSOR", "status": "SUCCESS", "warnings": [],
                       "human_review_required": True, "result": r})


def assess(pg, vid, vh, responder, mode="LIVE", cutoff=None, **kw):
    with pg.worker() as c:
        return run_assessment(c, vid, vh, report_mode=mode, information_cutoff=cutoff or NOW(),
                              model_configuration_id=model_configuration(pg), provider=FakeProvider(responder),
                              worker_id="p4-test", **kw)


def version_of(pg, run_id):
    with pg.admin() as x:
        return x.execute("SELECT * FROM lfhe.assessment_versions WHERE created_by_model_run_id=%s", (run_id,)).fetchone()


def statements_of(pg, version_id):
    with pg.admin() as x:
        return {r["statement_local_id"]: r for r in x.execute(
            "SELECT *, statement_type::text AS t, epistemic_category::text AS cat FROM lfhe.assessment_statements "
            "WHERE assessment_version_id=%s", (version_id,))}


def rejected(r, code):
    return r.outcome == "OUTPUT_REJECTED" and any(x.startswith(code) for x in r.rejection_reasons)


# --- 18: exact event version + hash ------------------------------------------------------
def test_assessment_is_bound_to_exact_event_version_and_is_immutable(pg, m07, analyst):
    e, vid, vh, claims = setup_event(pg, analyst)
    r = assess(pg, vid, vh, lambda m, env: out(env, claims=claims))
    assert r.outcome == "ASSESSMENT_RECORDED", r
    v = version_of(pg, r.final_run_id)
    assert (str(v["event_version_id"]), v["event_version_hash"]) == (vid, vh)
    with pg.admin() as x:
        assert x.execute("SELECT lfhe.p4_hash('lfhe-assessment-version/1', content) h FROM lfhe.assessment_versions "
                         "WHERE id=%s", (v["id"],)).fetchone()["h"] == v["content_hash"]
        assert x.execute("SELECT state::text s FROM lfhe.assessment_version_states WHERE assessment_version_id=%s",
                         (v["id"],)).fetchone()["s"] == "DRAFT"
        for sql in ("UPDATE lfhe.assessment_versions SET ai_confidence_rationale='tampered rationale text here' WHERE id=%s",
                    "UPDATE lfhe.assessment_statements SET statement_text='tampered' WHERE assessment_version_id=%s",
                    "DELETE FROM lfhe.assessment_statements WHERE assessment_version_id=%s"):
            with pytest.raises(psycopg.Error):
                x.execute(sql, (v["id"],))
    other = assess(pg, vid, vh, lambda m, env: out(env, claims=claims, event_version_id="00000000-0000-4000-8000-000000000001"))
    assert rejected(other, "EVENT_VERSION_NOT_SUPPLIED")


# --- 19, 20, 21, 22: provenance and categories --------------------------------------------
def test_statement_provenance_rules(pg, m07, analyst):
    e, vid, vh, claims = setup_event(pg, analyst)
    a, d = claims
    stranger = pclaim(pg, "Another outlet said 9 jets were based elsewhere.", "9 jets were based elsewhere")
    base = default_statements(claims)
    cases = [
        ([st("AS1", "KNOWN_FACT", "Northland has 4 tankers.", prov="NONE_REQUIRED")] + base[1:], "FACTUAL_STATEMENT_WITHOUT_EVIDENCE"),
        ([st("AS1", "KNOWN_FACT", "9 jets were based elsewhere, an outlet said.", claims=[stranger], attr_text="an outlet said")] + base[1:],
         "EVIDENCE_NOT_SUPPLIED"),
        (base + [st("AS9", "ANALYTIC_JUDGMENT", "Northland will likely keep the tankers there.", prov="CASE_EVIDENCE")],
         "PROVENANCE_CLASS_MISMATCH"),
        (base + [st("AS9", "ANALYTIC_JUDGMENT", "Northland will likely keep the tankers there.", prov="NONE_REQUIRED")],
         "JUDGMENT_WITHOUT_PREMISES"),
        (base + [st("AS9", "IMPLICATION", "Refuelling range grows.", claims=[a], premises=["AS77"])], "PREMISE_UNKNOWN"),
    ]
    for statements, code in cases:
        assert rejected(assess(pg, vid, vh, lambda m, env, s=statements: out(env, json.loads(json.dumps(s)))), code), code
    ok = assess(pg, vid, vh, lambda m, env: out(env, default_statements(claims) + [
        st("AS5", "ASSUMPTION", "We assume the arrivals are routine rotations.", prov="NONE_REQUIRED", evidence=False)]))
    s = statements_of(pg, version_of(pg, ok.final_run_id)["id"])
    assert s["AS5"]["cat"] == "ASSUMPTION" and s["AS1"]["cat"] == "FACT" and s["AS3"]["cat"] == "ASSESSMENT"    # 21
    with pg.admin() as x:                                                                                     # 22
        prem = x.execute("SELECT p.premise_statement_id FROM lfhe.assessment_statement_premises p WHERE p.statement_id=%s",
                         (s["AS3"]["id"],)).fetchall()
        ev = x.execute("SELECT object_type, object_id, role::text r FROM lfhe.assessment_statement_evidence WHERE statement_id=%s",
                       (s["AS3"]["id"],)).fetchall()
    assert [p["premise_statement_id"] for p in prem] == [s["AS1"]["id"]]
    assert {(r["object_type"], str(r["object_id"]), r["r"]) for r in ev} == {("claim", a["claim_id"], "SUPPORTS")}
    assert d


# --- 23: contradiction preserved -----------------------------------------------------------
def test_contradiction_must_stay_visible(pg, m07, analyst):
    e, vid, vh, claims = setup_event(pg, analyst)
    without = [s for s in default_statements(claims) if s["statement_local_id"] != "AS2"]
    assert rejected(assess(pg, vid, vh, lambda m, env: out(env, without)), "CONTRADICTION_OMITTED")
    ok = assess(pg, vid, vh, lambda m, env: out(env, claims=claims))
    with pg.admin() as x:
        assert x.execute("SELECT count(*) n FROM lfhe.assessment_statement_evidence e JOIN lfhe.assessment_statements s "
                         "ON s.id = e.statement_id WHERE s.assessment_version_id=%s AND e.role='CONTRADICTS' AND e.object_id=%s",
                         (version_of(pg, ok.final_run_id)["id"], claims[1]["claim_id"])).fetchone()["n"] == 1


# --- 24, 25: no confidence inflation; source opinion is not confirmation -----------------
def test_single_lineage_cannot_carry_high_confidence(pg, m07, analyst):
    a = pclaim(pg, "The ministry said 6 radars were installed at Fort Aster.", "6 radars were installed at Fort Aster")
    b = pclaim(pg, "Citing the ministry, a site says 6 radars were installed at Fort Aster.", "6 radars were installed at Fort Aster")
    with pg.as_user(analyst) as h:
        h.execute("SELECT lfhe.record_claim_lineage(%s::jsonb, 'site cites the ministry')", (json.dumps({
            "child_claim_id": b["claim_id"], "relationship_type": "DERIVED_REPORTING", "parent_claim_id": a["claim_id"]}),))
    e = human_event(pg, analyst, [a, b], title="Radars at Fort Aster")
    h = head(pg, e)
    vid, vh = str(h["head_version_id"]), h["head_content_hash"]
    stmts = [st("AS1", "KNOWN_FACT", "The ministry said 6 radars were installed at Fort Aster.", claims=[a, b],
                attr_text="The ministry said"),
             st("AS2", "ANALYTIC_JUDGMENT", "Air surveillance near Fort Aster is likely improving.", claims=[a, b], premises=["AS1"])]
    hi = assess(pg, vid, vh, lambda m, env: out(env, json.loads(json.dumps(stmts)), conf="HIGH",
                                                rationale="Two outlets report the same installation of radars."))
    assert rejected(hi, "CONFIDENCE_INFLATION_SINGLE_LINEAGE")
    assert assess(pg, vid, vh, lambda m, env: out(env, json.loads(json.dumps(stmts)), conf="MODERATE",
                                                  rationale="Single evidentiary line (site derives from ministry).")).outcome \
        == "ASSESSMENT_RECORDED"


def test_source_opinion_keeps_attribution_even_when_corroborated(pg, m07, analyst):
    op = pclaim(pg, "An analyst wrote that Northland will soon double its tanker fleet.",
                "Northland will soon double its tanker fleet", source_statement_status="SOURCE_EXPECTATION")
    with pg.as_user(analyst) as h:
        h.execute("SELECT lfhe.set_claim_status(%s, 'UNVERIFIED', 'CORROBORATED', 'analyst corroborates')", (op["claim_id"],))
    e = human_event(pg, analyst, [op], title="Expected tanker growth")
    h = head(pg, e)
    stmt = [st("AS1", "KNOWN_FACT", "Northland will soon double its tanker fleet.", claims=[op], attr=False)]
    r = assess(pg, str(h["head_version_id"]), h["head_content_hash"], lambda m, env: out(env, stmt))
    assert rejected(r, "ATTRIBUTION_CONTRADICTS_WORKFLOW_STATE")


# --- 26, 27: causality and negative evidence ---------------------------------------------
def test_unsupported_causality_and_negative_evidence_are_rejected_as_fact(pg, m07, analyst):
    e, vid, vh, claims = setup_event(pg, analyst)
    a = claims[0]
    base = default_statements(claims)
    causal = [st("AS1", "KNOWN_FACT", "The air force reported that 4 tankers arrived because of the eastern exercise.",
                 claims=[a], attr_text="The air force reported")] + base[1:]
    assert rejected(assess(pg, vid, vh, lambda m, env: out(env, causal)), "UNSUPPORTED_CAUSALITY_AS_FACT")
    silent = base + [st("AS8", "KNOWN_FACT", "The air force reported that no fighter jets have been reported at Fort Aster.",
                        claims=[a], attr_text="The air force reported")]
    assert rejected(assess(pg, vid, vh, lambda m, env: out(env, silent)), "NEGATIVE_EVIDENCE_FROM_SILENCE")
    judged = base + [st("AS8", "ANALYTIC_JUDGMENT", "The arrivals were probably caused by exercise planning.", claims=[a])]
    assert assess(pg, vid, vh, lambda m, env: out(env, judged)).outcome == "ASSESSMENT_RECORDED"   # judgment, not fact


# --- 28, 29: likelihood vs confidence (CR4-01: canonical PO vocabulary, migration 3400) ----
CANONICAL_LIKELIHOOD = ["REMOTE_CHANCE", "HIGHLY_UNLIKELY", "UNLIKELY", "ROUGHLY_EVEN_CHANCE", "LIKELY",
                        "HIGHLY_LIKELY", "ALMOST_CERTAIN"]
LK_RATIONALE = "Pattern of rotations in the cited reports."


def test_canonical_likelihood_vocabulary_is_exactly_the_po_set_in_rank_order(pg):
    with pg.admin() as x:
        rows = x.execute("SELECT code, rank, description, spec_source FROM lfhe.likelihood_terms ORDER BY rank").fetchall()
        assert [r["code"] for r in rows] == CANONICAL_LIKELIHOOD                       # exactly seven, no UNKNOWN
        assert [r["rank"] for r in rows] == list(range(1, 8))
        assert all(r["description"].strip() and "CR4-01" in r["spec_source"] for r in rows)
        assert not any(ch.isdigit() or ch == "%" for r in rows for ch in r["description"])   # no numeric bands
        with pytest.raises(psycopg.Error):                                            # immutable
            x.execute("UPDATE lfhe.likelihood_terms SET rank = 99 WHERE code = 'LIKELY'")
    with pg.worker() as w, pytest.raises(psycopg.Error):
        w.execute("INSERT INTO lfhe.likelihood_terms (code, rank, description, spec_source) VALUES ('UNKNOWN', 8, 'x', 'x')")


def test_likelihood_only_on_prospective_statements_and_distinct_from_confidence(pg, m07, analyst):
    e, vid, vh, claims = setup_event(pg, analyst)
    base = default_statements(claims)                    # AS3 = ANALYTIC_JUDGMENT
    seen = {}

    def with_lk(lk, idx=2, **kw):
        stmts = json.loads(json.dumps(base))
        stmts[idx]["likelihood"] = lk

        def responder(m, env):
            seen["terms"] = env["task"]["likelihood_terms"]
            return out(env, stmts, **kw)
        return assess(pg, vid, vh, responder)
    # 3: canonical term accepted on an eligible prospective ANALYTIC_JUDGMENT (and on IMPLICATION)
    r = with_lk({"term": "LIKELY", "rationale": LK_RATIONALE}, conf="LOW")
    assert r.outcome == "ASSESSMENT_RECORDED", r
    assert seen["terms"] == CANONICAL_LIKELIHOOD                                      # 7: M07 input, rank order
    v = version_of(pg, r.final_run_id)
    s = statements_of(pg, v["id"])
    assert s["AS3"]["likelihood_term"] == "LIKELY" and s["AS1"]["likelihood_term"] is None
    assert v["ai_recommended_confidence"] == "LOW"                                    # 8: separate dimension / column
    with pg.admin() as x:
        cols = {c["column_name"] for c in x.execute("SELECT column_name FROM information_schema.columns WHERE "
                                                    "table_schema='lfhe' AND table_name='assessment_statements'")}
    assert "likelihood_term" in cols and not any("confidence" in c for c in cols)
    impl = base + [st("AS9", "IMPLICATION", "Further tanker deployments to Fort Aster may follow.", claims=[claims[0]],
                      premises=["AS1"], likelihood={"term": "ROUGHLY_EVEN_CHANCE", "rationale": LK_RATIONALE})]
    assert assess(pg, vid, vh, lambda m, env: out(env, json.loads(json.dumps(impl)))).outcome == "ASSESSMENT_RECORDED"
    # likelihood stays optional: none at all is valid
    assert assess(pg, vid, vh, lambda m, env: out(env, json.loads(json.dumps(base)))).outcome == "ASSESSMENT_RECORDED"
    # 4: unknown term (incl. a lower-case / UNKNOWN / numeric-band style term)
    for term in ("PROBABLE", "UNKNOWN", "LIKELY_70_PERCENT"):
        assert rejected(with_lk({"term": term, "rationale": LK_RATIONALE}), "LIKELIHOOD_TERM_UNKNOWN"), term
    # 5: non-permitted statement types
    assert rejected(with_lk({"term": "LIKELY", "rationale": LK_RATIONALE}, idx=0), "LIKELIHOOD_NOT_APPLICABLE")   # KNOWN_FACT
    assert rejected(with_lk({"term": "LIKELY", "rationale": LK_RATIONALE}, idx=3), "LIKELIHOOD_NOT_APPLICABLE")   # INFORMATION_GAP
    # 6: rationale mandatory (schema for empty, database for a token rationale)
    assert with_lk({"term": "LIKELY", "rationale": ""}).outcome == "SCHEMA_VALIDATION_FAILED"
    assert with_lk({"term": "LIKELY"}).outcome == "SCHEMA_VALIDATION_FAILED"
    assert rejected(with_lk({"term": "LIKELY", "rationale": "short"}), "LIKELIHOOD_RATIONALE_REQUIRED")
    # 9: a likelihood never opens a path to final_analytic_confidence
    assert with_lk({"term": "LIKELY", "rationale": LK_RATIONALE}, final_analytic_confidence="HIGH").outcome \
        == "SCHEMA_VALIDATION_FAILED"


# --- 30, 31: confidence ---------------------------------------------------------------------
def test_m07_cannot_set_final_confidence_and_rationale_is_mandatory(pg, m07, analyst):
    e, vid, vh, claims = setup_event(pg, analyst)
    assert assess(pg, vid, vh, lambda m, env: out(env, claims=claims, final_analytic_confidence="HIGH")).outcome \
        == "SCHEMA_VALIDATION_FAILED"
    assert rejected(assess(pg, vid, vh, lambda m, env: out(env, claims=claims, rationale="short")),
                    "CONFIDENCE_RATIONALE_REQUIRED")
    run = make_model_run(pg, "M07_INTELLIGENCE_ASSESSOR", [("event_version", vid)],
                         task_parameters={"report_mode": "LIVE", "information_cutoff": NOW().isoformat()})
    env = {"task": {"event_id": e, "event_version_id": vid, "baseline_version_id": None, "previous_assessment_version_id": None},
           "inputs": [{"content": {"claims": [{"claim_id": c["claim_id"], "attribution_required_if_cited": True} for c in claims]}}]}
    payload = json.loads(out(env, claims=claims, final_analytic_confidence="HIGH"))["result"]
    with pg.worker() as c:
        r = c.execute("SELECT lfhe.ingest_assessment(%s::jsonb) r", (Jsonb({"model_run_id": run, "output_status": "SUCCESS",
                                                                               "result": payload}),)).fetchone()["r"]
    assert "FINAL_CONFIDENCE_IS_HUMAN_ONLY" in r["rejection_reasons"]
    with pg.admin() as x:
        cols = {r["column_name"] for r in x.execute("SELECT column_name FROM information_schema.columns WHERE "
                                                    "table_schema='lfhe' AND table_name='assessment_versions'")}
    assert "final_analytic_confidence" not in cols and "ai_recommended_confidence" in cols


# --- 32, 33, 34, 35: deterministic attribution -------------------------------------------
def test_attribution_is_deterministic_from_asof_workflow_state(pg, m07, analyst):
    corr = pclaim(pg, "Satellite imagery shows 3 tanker aircraft parked at Fort Aster.", "3 tanker aircraft parked at Fort Aster",
                  source_statement_status="DIRECT_OBSERVATION_REPORTED")
    plain = pclaim(pg, "A blog said 3 tanker aircraft are at Fort Aster.", "3 tanker aircraft are at Fort Aster")
    with pg.as_user(analyst) as h:
        h.execute("SELECT lfhe.set_claim_status(%s, 'UNVERIFIED', 'CORROBORATED', 'checked imagery')", (corr["claim_id"],))
    e = human_event(pg, analyst, [corr, plain], title="Tankers parked at Fort Aster")
    h = head(pg, e)
    vid, vh = str(h["head_version_id"]), h["head_content_hash"]
    lie = [st("AS1", "KNOWN_FACT", "3 tanker aircraft are at Fort Aster.", claims=[plain], attr=False)]
    assert rejected(assess(pg, vid, vh, lambda m, env: out(env, lie)), "ATTRIBUTION_CONTRADICTS_WORKFLOW_STATE")   # 32
    hidden = [st("AS1", "KNOWN_FACT", "3 tanker aircraft are at Fort Aster.", claims=[plain], attr=True, attr_text="A blog said")]
    assert rejected(assess(pg, vid, vh, lambda m, env: out(env, hidden)), "ATTRIBUTION_MISSING")
    good = [st("AS1", "KNOWN_FACT", "A blog said 3 tanker aircraft are at Fort Aster.", claims=[plain], attr_text="A blog said"),
            st("AS2", "KNOWN_FACT", "3 tanker aircraft are parked at Fort Aster.", claims=[corr])]
    r = assess(pg, vid, vh, lambda m, env: out(env, good))
    s = statements_of(pg, version_of(pg, r.final_run_id)["id"])
    assert s["AS1"]["attribution_required"] is True and s["AS2"]["attribution_required"] is False      # 33, 34
    ses = s["AS2"]["source_epistemic_status"][0]
    assert ses["claim_status"] == "CORROBORATED" and ses["corroborated_for_attribution"] is True
    # the same corroboration is not knowable in a REPLAY (human decision without evidence bound) → attribution required
    with pg.worker() as w:
        assert w.execute("SELECT lfhe.p4_attribution_required('KNOWN_FACT', ARRAY[%s]::uuid[], '{}', 'REPLAY', %s) r",
                         (corr["claim_id"], CUT_DT)).fetchone()["r"] is True


def test_high_impact_restrictions_still_apply_to_attribution(pg, m07, analyst):
    hi = pclaim(pg, "The ministry said a new air-defence system is operational at Fort Aster.",
                "a new air-defence system is operational at Fort Aster", source_statement_status="FACT_REPORTED_BY_SOURCE")
    run = lineage_run(pg, [hi])
    with pg.admin() as x:
        x.execute("INSERT INTO lfhe.claim_status_auto_rules (rule_code, from_status, to_status, description) VALUES "
                  "('P4_TEST_RULE', 'UNVERIFIED', 'CORROBORATED', 'synthetic test rule') ON CONFLICT DO NOTHING")
    with pg.worker() as w:
        w.execute("SELECT lfhe.apply_automatic_claim_status(%s, 'P4_TEST_RULE', %s, NULL)", (hi["claim_id"], run))
        assert w.execute("SELECT lfhe.p4_attribution_required('KNOWN_FACT', ARRAY[%s]::uuid[], '{}', 'LIVE', %s) r",
                         (hi["claim_id"], NOW())).fetchone()["r"] is False
    with pg.as_user(analyst) as h:
        h.execute("SELECT lfhe.mark_claim_high_impact(%s, true, NULL, 'key capability assertion')", (hi["claim_id"],))
    with pg.worker() as w:          # automatic status on a now high-impact claim needs revalidation → attribution again
        assert w.execute("SELECT lfhe.p4_attribution_required('KNOWN_FACT', ARRAY[%s]::uuid[], '{}', 'LIVE', %s) r",
                         (hi["claim_id"], NOW())).fetchone()["r"] is True


# --- 36: summary resolves only to statement IDs -------------------------------------------
def test_summary_is_derived_from_statement_ids_only(pg, m07, analyst):
    e, vid, vh, claims = setup_event(pg, analyst)
    assert rejected(assess(pg, vid, vh, lambda m, env: out(env, claims=claims, summary={"text": "Tankers arrived.",
                                                                                     "source_statement_ids": []})),
                    "SUMMARY_UNMAPPED")
    assert rejected(assess(pg, vid, vh, lambda m, env: out(env, claims=claims, summary={"text": "Tankers arrived.",
                                                                                     "source_statement_ids": ["AS99"]})),
                    "SUMMARY_REFERENCES_UNKNOWN_STATEMENT")
    r = assess(pg, vid, vh, lambda m, env: out(env, claims=claims, summary={"text": "Tankers reportedly arrived; denied.",
                                                                          "source_statement_ids": ["AS1", "AS2"]}))
    v = version_of(pg, r.final_run_id)
    s = statements_of(pg, v["id"])
    with pg.admin() as x:
        row = x.execute("SELECT * FROM lfhe.assessment_derived_summaries WHERE assessment_version_id=%s", (v["id"],)).fetchone()
    assert row["authoritative"] is False and set(row["source_statement_ids"]) == {s["AS1"]["id"], s["AS2"]["id"]}


# --- context: baseline, reference context, operational guard, indicators -----------------
def test_baseline_and_reference_context_rules(pg, m07, analyst):
    e, vid, vh, claims = setup_event(pg, analyst)
    a = claims[0]
    base = default_statements(claims)
    change = base + [st("AS7", "CHANGE_FROM_BASELINE", "The air force reported more tankers than in the baseline.",
                        claims=[a], uses_baseline=True, attr_text="The air force reported")]
    assert rejected(assess(pg, vid, vh, lambda m, env: out(env, json.loads(json.dumps(change)))), "BASELINE_UNAVAILABLE")
    prior = pclaim(pg, "The air force said 2 tanker aircraft were based at Fort Aster.", "2 tanker aircraft were based at Fort Aster")
    bl = create_baseline(pg, analyst, "BL-M07-1", [("2 tankers at Fort Aster", [("claim", prior["claim_id"])])])
    approve(pg, analyst, "baseline", bl)
    rc = create_rc(pg, analyst, "RC-M07-1", [prior], text="Fort Aster is Northland's main tanker base.")
    approve(pg, analyst, "rc", rc)
    late = create_rc(pg, analyst, "RC-M07-LATE", [pclaim(pg, "Later report on Fort Aster.", "Later report on Fort Aster", POST)],
                     as_of=datetime.now(timezone.utc).isoformat(), text="Later knowledge about the base.")
    approve(pg, analyst, "rc", late)
    with_ctx = change + [st("AS6", "KNOWN_FACT", "Per reference context, Fort Aster is Northland's main tanker base.",
                            prov="APPROVED_REFERENCE_CONTEXT", rcs=[rc], attr_text="Per reference context")]
    r = assess(pg, vid, vh, lambda m, env: out(env, json.loads(json.dumps(with_ctx))), baseline_code="BL-M07-1",
               reference_context_codes=["RC-M07-1"])
    assert r.outcome == "ASSESSMENT_RECORDED", r
    v = version_of(pg, r.final_run_id)
    assert str(v["baseline_version_id"]) == bl
    with pg.admin() as x:
        assert [str(y["reference_context_version_id"]) for y in x.execute(
            "SELECT reference_context_version_id FROM lfhe.assessment_reference_contexts WHERE assessment_version_id=%s",
            (v["id"],))] == [rc]
    unsupplied = base + [st("AS6", "KNOWN_FACT", "Per reference context, Fort Aster is the main base.",
                            prov="APPROVED_REFERENCE_CONTEXT", rcs=[rc], attr_text="Per reference context")]
    assert rejected(assess(pg, vid, vh, lambda m, env: out(env, json.loads(json.dumps(unsupplied)))),
                    "REFERENCE_CONTEXT_NOT_SUPPLIED")
    replay = assess(pg, vid, vh, lambda m, env: out(env, claims=claims), mode="REPLAY", cutoff=CUT_DT,
                    reference_context_codes=["RC-M07-1", "RC-M07-LATE"])
    with pg.admin() as x:
        ctx = x.execute("SELECT context_manifest FROM lfhe.model_runs WHERE id=%s", (replay.final_run_id,)).fetchone()
    ids = {i["object_id"] for i in ctx["context_manifest"] if i["object_type"] == "reference_context_version"}
    assert ids == {rc}                                                                     # later RC never in REPLAY
    assert KNOW


def test_operational_recommendations_and_unobservable_indicators_are_rejected(pg, m07, analyst):
    e, vid, vh, claims = setup_event(pg, analyst)
    a = claims[0]
    base = default_statements(claims)
    op = base + [st("AS8", "IMPLICATION", "NATO should strike the tanker base at Fort Aster.", claims=[a])]
    assert rejected(assess(pg, vid, vh, lambda m, env: out(env, op)), "OPERATIONAL_RECOMMENDATION_PROHIBITED")
    vague = [{"indicator_local_id": "IND1", "indicator_text": "Watch Northland", "observable_condition": "things",
              "related_statement_local_ids": ["AS3"], "supporting_claim_ids": []}]
    assert rejected(assess(pg, vid, vh, lambda m, env: out(env, claims=claims, indicators=vague)), "INDICATOR_NOT_OBSERVABLE")
    good = [{"indicator_local_id": "IND1", "indicator_text": "Further tanker deployments at Fort Aster",
             "observable_condition": "Additional tanker aircraft reported or imaged at Fort Aster within 30 days",
             "related_statement_local_ids": ["AS3"], "supporting_claim_ids": [a["claim_id"]]}]
    r = assess(pg, vid, vh, lambda m, env: out(env, claims=claims, indicators=good))
    with pg.admin() as x:
        assert x.execute("SELECT count(*) n FROM lfhe.assessment_indicator_proposals WHERE assessment_version_id=%s",
                         (version_of(pg, r.final_run_id)["id"],)).fetchone()["n"] == 1
