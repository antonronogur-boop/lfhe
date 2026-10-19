"""Phase 4 acceptance corpus (Addendum §24) — measured through the real pipeline: real
M06/M07/M08 bundles, real input builders, real ingestion and the real HUMAN_ONLY
functions; only the model is scripted (FakeProvider replays the corpus' outputs, sound,
naive and adversarial). Corpus truth labels are read only here.

Writes the CG4 metrics to $LFHE_P4_METRICS_OUT when set."""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from conftest import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "tests" / "integration"))     # scripted-output helpers shared with the P4 integration tests
from lfhe_orchestrator.assessment_pipeline import run_assessment, run_challenge, run_relevance
from lfhe_orchestrator.providers import FakeProvider, render_messages
from p4_support import approve, create_baseline, create_rc, head, human_event, pclaim
from pipeline_support import activate_real_prompts, model_configuration
from test_p4_assessments import fill_attribution, st
from test_p4_challenge_review import CONF_RAT, chal
from test_p4_relevance import out as m06_out

pytestmark = pytest.mark.db
CORPUS = json.loads((REPO_ROOT / "tests" / "fixtures" / "phase4_acceptance" / "corpus.json").read_text())
GS_MARKERS = ("gs-001", "gold standard", "gold-standard", "gold_standard", "answer key", "answer-key", "answer_key")
MODULES = ("M02_CLAIM_EXTRACTOR", "M03_CLASSIFIER", "M06_RELEVANCE", "M07_INTELLIGENCE_ASSESSOR", "M08_CHALLENGER")


def now():
    return datetime.now(timezone.utc) + timedelta(minutes=5)


def outcome_code(r):
    if r.outcome == "OUTPUT_REJECTED":
        return {f"OUTPUT_REJECTED:{x.split(':')[0]}" for x in r.rejection_reasons}
    return {r.outcome}


def envelope_text(provider) -> str:
    parts = []
    for mod, env, _ in provider.calls:
        system, messages = render_messages(mod, env)
        parts.append(system + json.dumps(env, ensure_ascii=False) + "".join(m["content"] for m in messages))
    return "\n".join(parts)


def m07_output(env, sc, ids):
    statements = [st(s["local"], s["type"], s["text"], prov=s["prov"], claims=[ids[c] for c in s["claims"]],
                     contra=[ids[c] for c in s["contra"]], premises=s["premises"], evidence=s["evidence"],
                     attr=s["attr"], attr_text=s["attr_text"]) for s in sc["statements"]]
    r = {"event_id": env["task"]["event_id"], "event_version_id": env["task"]["event_version_id"],
         "baseline_version_id": env["task"]["baseline_version_id"],
         "previous_assessment_version_id": env["task"]["previous_assessment_version_id"],
         "assessment_statements": fill_attribution(env, statements),
         "derived_summary": {"text": "", "source_statement_ids": []}, "indicators_to_watch": [],
         "ai_recommended_confidence": sc.get("confidence", "MODERATE"),
         "ai_confidence_rationale": "Corpus rationale: evidence base as listed in the statements."}
    r.update(sc.get("extra", {}))
    return json.dumps({"module": "M07_INTELLIGENCE_ASSESSOR", "status": "SUCCESS", "warnings": [],
                       "human_review_required": True, "result": r})


def snapshot(x, vid):
    v = x.execute("SELECT content, content_hash, ai_recommended_confidence::text c FROM lfhe.assessment_versions WHERE id=%s",
                  (vid,)).fetchone()
    s = x.execute("SELECT statement_local_id, statement_text, statement_type::text t, epistemic_category::text c "
                  "FROM lfhe.assessment_statements WHERE assessment_version_id=%s ORDER BY 1", (vid,)).fetchall()
    return json.dumps([dict(v), [dict(r) for r in s]], default=str, sort_keys=True)


def test_phase4_acceptance_corpus(pg, make_user):
    activate_real_prompts(pg, MODULES)
    analyst, viewer = make_user("ANALYST"), make_user("VIEWER")
    mc = model_configuration(pg)
    m = {k: 0 for k in (
        "scenario_expectation_mismatches", "below_threshold_hidden", "manual_promotion_failures",
        "recommended_without_concrete_or_not_established_rationale", "hindsight_leakage",
        "unsupported_factual_statements_persisted", "statements_without_provenance", "category_violations",
        "unlabelled_contradiction_removal", "republication_inflation", "unsupported_causal_accepted_as_fact",
        "m07_final_confidence_set", "m08_modified_m07", "non_human_final_approvals", "hash_mismatch_accepted",
        "assessment_version_mutations", "gs_leakage", "traceability_gaps")}
    texts, run_ids, details = [], [], []

    # --- M06 ---------------------------------------------------------------------------
    for sc in CORPUS["relevance"]:
        c = pclaim(pg, sc["claim"]["text"], sc["claim"]["exact"])
        e = human_event(pg, analyst, [c], title=f"Corpus {sc['id']}")
        h = head(pg, e)
        vid, vh = str(h["head_version_id"]), h["head_content_hash"]
        o = dict(sc["output"])
        prov = FakeProvider(lambda mod, env, o=o: m06_out(env, **o))
        with pg.worker() as w:
            r = run_relevance(w, vid, vh, report_mode="LIVE", information_cutoff=now(), model_configuration_id=mc,
                              provider=prov, worker_id="p4-acceptance")
        texts.append(envelope_text(prov))
        run_ids += r.model_run_ids
        ok = sc["expect"] in outcome_code(r)
        m["scenario_expectation_mismatches"] += not ok
        details.append({"id": sc["id"], "expected": sc["expect"], "got": sorted(outcome_code(r))})
        with pg.as_user(viewer) as v:
            if v.execute("SELECT 1 FROM lfhe.event_relevance_queue WHERE event_id=%s", (e,)).fetchone() is None:
                m["below_threshold_hidden"] += 1
        if sc.get("promote"):
            try:
                with pg.as_user(analyst) as hu:
                    d = hu.execute("SELECT lfhe.promote_event_version(%s, %s, 'REQUEST_ASSESSMENT', 'analyst requests despite low score') r",
                                   (vid, vh)).fetchone()["r"]
                with pg.admin() as x:
                    audited = x.execute("SELECT count(*) n FROM lfhe.audit_log WHERE event_type='MANUAL_ASSESSMENT_REQUESTED' "
                                        "AND object_id IN (%s, %s, %s)", (str(d), vid, e)).fetchone()["n"]
                m["manual_promotion_failures"] += audited == 0
            except psycopg.Error:
                m["manual_promotion_failures"] += 1
    with pg.admin() as x:
        for r in x.execute("SELECT hu_nato_relevance_established, hu_nato_relevance_rationale t, automatic_assessment_recommended a, "
                           "applicable_pir_ids p FROM lfhe.relevance_results WHERE model_run_id = ANY(%s::uuid[])", (run_ids,)):
            if not (r["a"] or "PIR_07" in r["p"]):
                continue                                   # §24.3 applies to recommended / PIR-07 events
            generic = x.execute("SELECT lfhe.text_is_generic_relevance(%s) g", (r["t"],)).fetchone()["g"]
            concrete = r["hu_nato_relevance_established"] and not generic
            not_est = (not r["hu_nato_relevance_established"]) and len(r["t"].strip()) >= 20 and not generic
            m["recommended_without_concrete_or_not_established_rationale"] += not (concrete or not_est)

    # --- M07 / M08 / human review ------------------------------------------------------
    recorded = []
    for sc in CORPUS["assessments"]:
        ids, objs = {}, []
        for local, c in sc["claims"].items():
            kw = {k: c[k] for k in ("source_statement_status",) if k in c}
            objs.append((local, pclaim(pg, c["text"], c["exact"], **kw)))
            ids[local] = objs[-1][1]["claim_id"]
            if c.get("corroborate"):
                with pg.as_user(analyst) as hu:
                    hu.execute("SELECT lfhe.set_claim_status(%s, 'UNVERIFIED', 'CORROBORATED', 'analyst corroborates')", (ids[local],))
        for local, c in sc.get("outside_claim", {}).items():
            ids[local] = pclaim(pg, c["text"], c["exact"])["claim_id"]
        for child, parent in sc.get("lineage", []):
            with pg.as_user(analyst) as hu:
                hu.execute("SELECT lfhe.record_claim_lineage(%s::jsonb, 'corpus lineage')", (json.dumps({
                    "child_claim_id": ids[child], "relationship_type": "DERIVED_REPORTING", "parent_claim_id": ids[parent]}),))
        roles = {ids[k]: v for k, v in sc.get("roles", {}).items()}
        e = human_event(pg, analyst, [o for _, o in objs], title=f"Corpus {sc['id']}", roles=roles)
        h = head(pg, e)
        vid, vh = str(h["head_version_id"]), h["head_content_hash"]
        prov = FakeProvider(lambda mod, env, sc=sc, ids=ids: m07_output(env, sc, ids))
        with pg.worker() as w:
            r = run_assessment(w, vid, vh, report_mode="LIVE", information_cutoff=now(), model_configuration_id=mc,
                               provider=prov, worker_id="p4-acceptance")
        texts.append(envelope_text(prov))
        run_ids += r.model_run_ids
        ok = sc["expect"] in outcome_code(r)
        m["scenario_expectation_mismatches"] += not ok
        details.append({"id": sc["id"], "expected": sc["expect"], "got": sorted(outcome_code(r))})
        if r.outcome != "ASSESSMENT_RECORDED":
            continue
        with pg.admin() as x:
            v = x.execute("SELECT * FROM lfhe.assessment_versions WHERE created_by_model_run_id=%s", (r.final_run_id,)).fetchone()
            before = snapshot(x, v["id"])
        flags = sc.get("challenge", [{"flag_type": "MISSING_ALTERNATIVE", "severity": "WARNING", "affected_statement_local_id": None,
                                      "affected_field": "STATEMENT_SET", "explanation": "Consider a routine rotation.",
                                      "recommended_action": "ANALYST_REVIEW", "evidence_claim_ids": []}])
        cprov = FakeProvider(lambda mod, env, flags=flags: chal(env, flags=flags))
        with pg.worker() as w:
            cr = run_challenge(w, str(v["id"]), v["content_hash"], model_configuration_id=mc, provider=cprov,
                               worker_id="p4-acceptance")
        texts.append(envelope_text(cprov))
        run_ids += cr.model_run_ids
        assert cr.outcome == "CHALLENGE_RECORDED", (sc["id"], cr)
        with pg.admin() as x:
            m["m08_modified_m07"] += snapshot(x, v["id"]) != before
        recorded.append((sc, v, ids))

        # adversarial human-side attempts: wrong hash, machine approval, direct mutation
        with pg.as_user(analyst) as hu:
            try:
                hu.execute("SELECT lfhe.review_assessment(%s, %s, 'APPROVE', 'LOW', %s, 'wrong hash')", (v["id"], "0" * 64, CONF_RAT))
                m["hash_mismatch_accepted"] += 1
            except psycopg.Error:
                pass
        for conn in (pg.worker, pg.as_service_role):
            try:
                with conn() as c:
                    c.execute("SELECT lfhe.review_assessment(%s, %s, 'APPROVE', 'HIGH', %s, 'machine')", (v["id"], v["content_hash"], CONF_RAT))
                m["non_human_final_approvals"] += 1
            except psycopg.Error:
                pass
        with pg.admin() as x:
            for sql in ("UPDATE lfhe.assessment_versions SET ai_recommended_confidence='HIGH' WHERE id=%s",
                        "DELETE FROM lfhe.assessment_statements WHERE assessment_version_id=%s"):
                try:
                    x.execute(sql, (v["id"],))
                    m["assessment_version_mutations"] += 1
                except psycopg.Error:
                    pass

        decision = sc.get("review")
        with pg.as_user(analyst) as hu:
            if decision == "APPROVE":
                hu.execute("SELECT lfhe.review_assessment(%s, %s, 'APPROVE', 'LOW', %s, 'analyst approves')", (v["id"], v["content_hash"], CONF_RAT))
            elif decision == "REJECT":
                hu.execute("SELECT lfhe.review_assessment(%s, %s, 'REJECT', NULL, NULL, 'analyst rejects')", (v["id"], v["content_hash"]))
            elif decision == "MODIFY_AND_APPROVE":
                with pg.admin() as x:
                    cur = x.execute("SELECT content FROM lfhe.assessment_versions WHERE id=%s", (v["id"],)).fetchone()["content"]
                stm = cur["statements"]
                for s_ in stm:
                    if s_["statement_type"] == "ANALYTIC_JUDGMENT":
                        s_["statement_text"] = "Northland may be trialling tanker support at Fort Aster; evidence is thin."
                hu.execute("SELECT lfhe.modify_and_approve_assessment(%s, %s, %s::jsonb, 'LOW', %s, 'analyst revises judgment')",
                           (v["id"], v["content_hash"], json.dumps({"assessment_statements": [
                               {k: s_[k] for k in ("statement_local_id", "statement_type", "statement_text", "provenance_class",
                                                   "supporting_claim_ids", "contradicting_claim_ids", "supporting_reference_context_ids",
                                                   "uses_baseline", "premise_statement_local_ids", "attribution_required",
                                                   "attribution_text", "evidence_required", "likelihood")} for s_ in stm],
                               "derived_summary": {"text": "", "source_statement_ids": []}, "indicators_to_watch": []}), CONF_RAT))
        with pg.admin() as x:
            m["assessment_version_mutations"] += snapshot(x, v["id"]) != before

    # --- REPLAY hindsight --------------------------------------------------------------
    rp = CORPUS["replay"]
    cut = datetime.fromisoformat(rp["cutoff"])
    pre = pclaim(pg, rp["pre"]["text"], rp["pre"]["exact"], rp["pre"]["available_at"])
    post = pclaim(pg, rp["post"]["text"], rp["post"]["exact"], rp["post"]["available_at"])
    b1 = create_baseline(pg, analyst, "BL-ACC-1", [("2 tankers based at Fort Aster", [("claim", pre["claim_id"])])],
                         as_of="2026-02-01T00:00:00+00:00")
    approve(pg, analyst, "baseline", b1)
    b2 = create_baseline(pg, analyst, "BL-ACC-1", [("8 tankers based at Fort Aster", [("claim", post["claim_id"])])],
                         as_of="2026-06-01T00:00:00+00:00")
    approve(pg, analyst, "baseline", b2)
    r1 = create_rc(pg, analyst, "RC-ACC-1", [pre], as_of="2026-02-01T00:00:00+00:00", text="Fort Aster hosts a small tanker unit.")
    approve(pg, analyst, "rc", r1)
    r2 = create_rc(pg, analyst, "RC-ACC-1", [post], as_of="2026-06-01T00:00:00+00:00", text="Fort Aster hosts a large tanker unit.")
    approve(pg, analyst, "rc", r2)
    e = human_event(pg, analyst, [pre], title="Corpus REPLAY tanker unit")
    h = head(pg, e)
    late = {b2, r2, post["claim_id"]}
    for module in ("M06_RELEVANCE", "M07_INTELLIGENCE_ASSESSOR"):
        prov = FakeProvider(lambda mod, env: json.dumps({"module": mod.module_code, "status": "INSUFFICIENT_INFORMATION",
                                                         "warnings": [], "human_review_required": True, "result": None}))
        with pg.worker() as w:
            if module == "M06_RELEVANCE":
                rr = run_relevance(w, str(h["head_version_id"]), h["head_content_hash"], report_mode="REPLAY", information_cutoff=cut,
                                   model_configuration_id=mc, provider=prov, worker_id="p4-acceptance", baseline_code="BL-ACC-1")
            else:
                rr = run_assessment(w, str(h["head_version_id"]), h["head_content_hash"], report_mode="REPLAY", information_cutoff=cut,
                                    model_configuration_id=mc, provider=prov, worker_id="p4-acceptance", baseline_code="BL-ACC-1",
                                    reference_context_codes=["RC-ACC-1"])
        run_ids += rr.model_run_ids
        sent = envelope_text(prov)
        texts.append(sent)
        m["hindsight_leakage"] += sum(1 for i in late if i in sent)
        m["hindsight_leakage"] += ("8 tanker aircraft" in sent) + ("large tanker unit" in sent)
        assert b1 in sent and (module == "M06_RELEVANCE" or r1 in sent)
    with pg.worker() as w:                                      # a post-cutoff event version is never eligible
        pe = human_event(pg, analyst, [post], title="Corpus REPLAY late event")
        ph = head(pg, pe)
        if w.execute("SELECT lfhe.p4_object_eligible('event_version', %s, 'REPLAY', %s) r", (ph["head_version_id"], cut)).fetchone()["r"]:
            m["hindsight_leakage"] += 1

    # --- persisted-state metrics over everything the corpus produced -------------------
    with pg.admin() as x:
        vids = [r["id"] for r in x.execute("SELECT DISTINCT v.id FROM lfhe.assessment_versions v WHERE v.created_by_model_run_id = ANY(%s::uuid[]) "
                                          "OR v.previous_version_id IN (SELECT id FROM lfhe.assessment_versions WHERE created_by_model_run_id = ANY(%s::uuid[]))",
                                          (run_ids, run_ids))]
        for s in x.execute("""SELECT s.*, s.statement_type::text t, s.epistemic_category::text c, s.provenance_class::text p,
                                     lfhe.statement_category(s.statement_type)::text expected,
                                     (SELECT count(*) FROM lfhe.assessment_statement_evidence e WHERE e.statement_id=s.id AND e.role='SUPPORTS') sup,
                                     (SELECT count(*) FROM lfhe.assessment_statement_evidence e WHERE e.statement_id=s.id) ev
                              FROM lfhe.assessment_statements s WHERE s.assessment_version_id = ANY(%s::uuid[])""", (vids,)):
            m["category_violations"] += s["c"] != s["expected"]
            if s["c"] == "FACT":
                m["unsupported_factual_statements_persisted"] += s["sup"] == 0
                m["unsupported_causal_accepted_as_fact"] += x.execute("SELECT lfhe.p4_text_has('causal', %s) r",
                                                                      (s["statement_text"],)).fetchone()["r"]
            if s["p"] != "NONE_REQUIRED":
                m["statements_without_provenance"] += s["ev"] == 0 and not s["uses_baseline"]
        for vid in vids:
            v = x.execute("SELECT * FROM lfhe.assessment_versions WHERE id=%s", (vid,)).fetchone()
            missing = x.execute("""SELECT count(*) n FROM lfhe.event_claims ec WHERE ec.event_version_id=%s AND ec.role='CONTRADICTS'
                                   AND NOT EXISTS (SELECT 1 FROM lfhe.assessment_statement_evidence e JOIN lfhe.assessment_statements s
                                                   ON s.id=e.statement_id WHERE s.assessment_version_id=%s AND e.role='CONTRADICTS'
                                                   AND e.object_id=ec.claim_id)""", (v["event_version_id"], vid)).fetchone()["n"]
            m["unlabelled_contradiction_removal"] += missing
            if v["ai_recommended_confidence"] == "HIGH" and x.execute(
                    "SELECT lfhe.p4_single_lineage(%s::jsonb, %s, %s) r",
                    (json.dumps(v["content"]["statements"]), v["report_mode"], v["information_cutoff"])).fetchone()["r"]:
                m["republication_inflation"] += 1
            m["assessment_version_mutations"] += x.execute(
                "SELECT lfhe.p4_hash('lfhe-assessment-version/1', content) <> content_hash AND origin='AI' r FROM lfhe.assessment_versions "
                "WHERE id=%s", (vid,)).fetchone()["r"] or 0
        for a in x.execute("SELECT a.*, (SELECT count(*) FROM lfhe.user_roles ur WHERE ur.user_id=a.reviewer_user_id) roles "
                           "FROM lfhe.analytical_approvals a WHERE assessment_version_id = ANY(%s::uuid[])", (vids,)):
            m["non_human_final_approvals"] += a["roles"] == 0
        m["m07_final_confidence_set"] = x.execute(
            "SELECT count(*) n FROM lfhe.model_runs WHERE id = ANY(%s::uuid[]) AND parsed_output -> 'result' ? 'final_analytic_confidence' "
            "AND status='SUCCEEDED'", (run_ids,)).fetchone()["n"]
        for r in x.execute("SELECT * FROM lfhe.model_runs WHERE id = ANY(%s::uuid[])", (run_ids,)):
            for col in ("prompt_version_id", "prompt_content_hash", "module_version", "model_configuration_id", "model_config_hash",
                        "envelope_sha256", "input_snapshot_sha256", "context_snapshot_sha256", "completed_at"):
                m["traceability_gaps"] += r[col] is None
            m["traceability_gaps"] += not {"report_mode", "information_cutoff"} <= set(r["task_parameters"] or {})
        approvals = x.execute("SELECT count(*) n FROM lfhe.analytical_approvals WHERE assessment_version_id = ANY(%s::uuid[]) "
                              "AND decision IN ('APPROVE','MODIFY_AND_APPROVE')", (vids,)).fetchone()["n"]
    joined = "\n".join(texts).lower()
    m["gs_leakage"] = sum(joined.count(k) for k in GS_MARKERS)

    m.update({"relevance_scenarios": len(CORPUS["relevance"]), "assessment_scenarios": len(CORPUS["assessments"]),
              "assessments_recorded": len(recorded), "human_approvals": approvals, "model_runs": len(set(run_ids))})
    if os.environ.get("LFHE_P4_METRICS_OUT"):
        with open(os.environ["LFHE_P4_METRICS_OUT"], "w") as f:
            json.dump({"metrics": m, "scenarios": details}, f, indent=2)
    zero = [k for k in m if k not in ("relevance_scenarios", "assessment_scenarios", "assessments_recorded", "human_approvals",
                                      "model_runs") and m[k] != 0]
    assert zero == [], (m, details)
    assert m["assessments_recorded"] == 3 and approvals == 2
