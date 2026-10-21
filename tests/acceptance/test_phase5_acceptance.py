"""Phase 5 acceptance corpus (Addendum §27) — measured through the real pipeline: real M07 → M08 →
human approval for the source material, real candidate pool / HUMAN selection, real M09 bundle,
input builder and ingestion, real HUMAN_ONLY edit / removal functions and the real renderer; only
the model is scripted (FakeProvider replays labelled sound, naive and adversarial M09 behaviours).

Writes the CG5 metrics to $LFHE_P5_METRICS_OUT when set."""
import copy
import json
import os
import re
import sys

import psycopg
import pytest

from conftest import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "tests" / "integration"))     # shared scripted-output helpers
from lfhe_orchestrator.providers import FakeProvider, render_messages   # noqa: E402
from lfhe_orchestrator.report_pipeline import run_report_edit           # noqa: E402
from lfhe_orchestrator.report_render import render_report_html          # noqa: E402
from lfhe_shared.canonical_json import canonical_sha256                 # noqa: E402
from p5_helpers import (activate, park_report_jobs, approved_assessment, auto_items, candidates, content_of, m09, new_report, pool, rs,   # noqa: E402
                        select, statements_of)
from pipeline_support import model_configuration                        # noqa: E402

pytestmark = pytest.mark.db
CORPUS = json.loads((REPO_ROOT / "tests" / "fixtures" / "phase5_acceptance" / "corpus.json").read_text())
GS_MARKERS = ("gs-001", "gold standard", "gold-standard", "gold_standard", "answer key", "answer-key", "answer_key")


def outcome_codes(r):
    if r.outcome == "OUTPUT_REJECTED":
        return {f"OUTPUT_REJECTED:{x.split(':')[0]}" for x in r.rejection_reasons}
    return {r.outcome}


def find(sec, text_part, key="key_judgments", cand=None):
    for it in sec[key]:
        if cand and it["source_candidate_id"] != cand:
            continue
        for st in it["statements"]:
            if text_part in st["text"]:
                return it, st
    raise KeyError(text_part)


def mutate(name, env, ctx):
    sec = auto_items(env)
    kj = ctx["cand"]["KJ"]
    extra = {}
    removals, length = [], "WITHIN_LIMIT"
    if name == "compress_merge":
        it, judg = find(sec, "probably", cand=kj)
        _, fact = find(sec, "4 tanker aircraft arrived", cand=kj)
        it["statements"] = [s for s in it["statements"] if s is not fact]
        judg.update(text="The air force reported that 4 tanker aircraft arrived at Fort Aster; Northland is probably expanding "
                         "air-refuelling support at Fort Aster.", editorial_transform="COMPRESSION",
                    source_assessment_statement_ids=judg["source_assessment_statement_ids"] + fact["source_assessment_statement_ids"])
    elif name == "foreign_candidate":
        so = ctx["foreign_statements"]
        sec["significant_developments"].append({"item_local_id": "FX1", "source_candidate_id": ctx["cand"]["FOREIGN"], "statements": [
            rs(500, so["AS1"]["statement_text"], "SIGNIFICANT_DEVELOPMENT", [str(so["AS1"]["id"])])]})
    elif name == "drop_sources":
        sec["key_judgments"][0]["statements"][0]["source_assessment_statement_ids"] = []
    elif name == "inject_number":
        _, st = find(sec, "4 tanker aircraft arrived", cand=kj)
        st.update(text=st["text"].replace("4 tanker", "6 tanker"), editorial_transform="PARAPHRASE")
    elif name == "inject_name":
        _, st = find(sec, "probably", cand=kj)
        st.update(text=st["text"].rstrip(".") + " and Port Vell.", editorial_transform="PARAPHRASE")
    elif name == "inject_causal":
        _, st = find(sec, "probably", cand=kj)
        st.update(text=st["text"].rstrip(".") + " because of the exercise.", editorial_transform="PARAPHRASE")
    elif name == "drop_attribution":
        _, st = find(sec, "4 tanker aircraft arrived", cand=kj)
        st.update(text="4 tanker aircraft arrived at Fort Aster.", editorial_transform="COMPRESSION")
    elif name == "strengthen":
        _, st = find(sec, "probably", cand=kj)
        st.update(text=st["text"].replace("probably", "certainly"), editorial_transform="PARAPHRASE")
    elif name == "confidence_high":
        for st in find(sec, "probably", cand=kj)[0]["statements"]:
            st["final_analytic_confidence"] = "HIGH"
    elif name == "add_likelihood":
        _, st = find(sec, "probably", cand=kj)
        st["likelihood_term"] = "LIKELY"
    elif name == "change_likelihood":
        _, st = find(sec, "is likely expanding", cand=ctx["cand"]["LK"])
        st.update(likelihood_term="HIGHLY_LIKELY", text=st["text"].replace("is likely", "is highly likely"),
                  editorial_transform="PARAPHRASE")
    elif name == "omit_contradiction":
        it, st = find(sec, "spokesman denied", cand=kj)
        it["statements"].remove(st)
    elif name == "remove_caveat_proposal":
        _, st = find(sec, "spokesman denied", cand=kj)
        removals, length = [{"removal_local_id": "RM1", "target_item_local_id": None,
                             "target_report_statement_local_id": st["report_statement_local_id"], "reason": "Length: the denial."}], "EXCEEDS_LIMIT"
    elif name == "valid_removal_proposal":
        sd_item = sec["significant_developments"][0]
        removals, length = [{"removal_local_id": "RM1", "target_item_local_id": sd_item["item_local_id"],
                             "target_report_statement_local_id": None, "reason": "Two-page limit: lowest-priority development."}], "EXCEEDS_LIMIT"
    elif name == "four_kj":
        it, judg = find(sec, "probably", cand=kj)
        sec["key_judgments"] += [{"item_local_id": f"K4{i}", "source_candidate_id": kj,
                                  "statements": [dict(judg, report_statement_local_id=f"RS{600 + i}")]} for i in range(3)]
    elif name == "promote_sd":
        sec["key_judgments"] += sec["significant_developments"]
        sec["significant_developments"] = []
    elif name == "human_only_key":
        extra = {"include": [ctx["cand"]["FOREIGN"]]}
    elif name == "operational_wtw":
        _, judg = find(sec, "is likely expanding", cand=ctx["cand"]["LK"])
        sec["what_to_watch"].append({"item_local_id": "W1", "source_candidate_id": ctx["cand"]["LK"], "statements": [
            dict(judg, report_statement_local_id="RS700", statement_role="WHAT_TO_WATCH", editorial_transform="PARAPHRASE",
                 text="Northland is likely expanding air-refuelling support at Fort Aster; forces should strike the tanker base.")]})
    elif name == "filler":
        _, fact = find(sec, "4 tanker aircraft arrived", cand=ctx["cand"]["SD"], key="significant_developments")
        sec["significant_developments"][0]["statements"].append(dict(fact, report_statement_local_id="RS800",
            text="Further developments at Fort Aster are expected.", editorial_transform="PARAPHRASE"))
    elif name == "republication_confidence":
        _, st = find(sec, "probably", cand=kj)
        st.update(text="Several outlets independently corroborated that " + st["text"][0].lower() + st["text"][1:],
                  editorial_transform="PARAPHRASE")
    elif name == "unknown_statement":
        sec["key_judgments"][0]["statements"][0]["source_assessment_statement_ids"] = ["00000000-0000-4000-8000-0000000000ee"]
    return m09(env, sec, length=length, removals=removals, **extra)


def test_phase5_acceptance_corpus(pg, make_user):
    from test_p4_assessments import default_statements, st
    activate(pg)
    analyst = make_user("ANALYST")
    lk = {"term": "LIKELY", "rationale": "Rotation pattern in the cited reports."}

    def with_lk(claims):
        base = default_statements(claims)
        base[2] = st("AS3", "ANALYTIC_JUDGMENT", "Northland is likely expanding air-refuelling support at Fort Aster.",
                     claims=[claims[0]], premises=["AS1"], evidence=True, likelihood=lk)
        return base
    kj, _, _ = approved_assessment(pg, analyst, conf="LOW")
    sd, _, _ = approved_assessment(pg, analyst, conf="MODERATE")
    lkv, _, _ = approved_assessment(pg, analyst, statements=with_lk, conf="LOW")
    foreign, _, _ = approved_assessment(pg, analyst, conf="LOW")
    rid = new_report(pg, analyst, "RPT-ACC-5")
    cands = candidates(pg, rid)
    sid, sh = select(pg, analyst, rid, [(kj["id"], "KEY_JUDGMENT", 1), (lkv["id"], "KEY_JUDGMENT", 2),
                                        (sd["id"], "SIGNIFICANT_DEVELOPMENT", 1)])
    ctx = {"cand": {"KJ": str(cands[str(kj["id"])]["candidate_id"]), "SD": str(cands[str(sd["id"])]["candidate_id"]),
                    "LK": str(cands[str(lkv["id"])]["candidate_id"]), "FOREIGN": str(cands[str(foreign["id"])]["candidate_id"])},
           "foreign_statements": statements_of(pg, foreign["id"])}
    mc = model_configuration(pg)
    texts, runs, details, accepted = [], [], [], []
    m = {k: 0 for k in (
        "scenario_expectation_mismatches", "unselected_candidate_included", "report_statements_without_mapping",
        "unsupported_new_facts_accepted", "unsupported_new_judgments_accepted", "attribution_strength_violations",
        "confidence_changes_by_m09", "likelihood_changes_by_m09", "silent_caveat_contradiction_deletion",
        "automatic_substantive_removals", "fabricated_filler_accepted", "report_version_mutations",
        "human_statements_without_provenance", "non_human_authoritative_decisions", "canonical_hash_nondeterminism",
        "statement_provenance_gaps", "gs_leakage", "m09_traceability_gaps", "preview_render_nondeterminism",
        "human_adversarial_accepted")}
    adversarial_fact = {"inject_number", "inject_name", "foreign_candidate", "unknown_statement"}
    adversarial_judgment = {"inject_causal", "strengthen", "republication_confidence", "operational_wtw"}
    for sc in CORPUS["m09"]:
        prov = FakeProvider(lambda mod, env, sc=sc: mutate(sc["mutation"], env, ctx))
        with pg.worker() as w:
            r = run_report_edit(w, sid, sh, model_configuration_id=mc, provider=prov, worker_id="p5-acceptance")
        for mod, env, _ in prov.calls:
            system, msgs = render_messages(mod, env)
            texts.append(system + json.dumps(env, ensure_ascii=False) + "".join(x["content"] for x in msgs))
        runs += r.model_run_ids
        got = outcome_codes(r)
        m["scenario_expectation_mismatches"] += sc["expect"] not in got
        details.append({"id": sc["id"], "mutation": sc["mutation"], "expected": sc["expect"], "got": sorted(got)})
        if r.outcome == "REPORT_VERSION_RECORDED":
            accepted.append(r.final_run_id)
            m["unsupported_new_facts_accepted"] += sc["mutation"] in adversarial_fact
            m["unsupported_new_judgments_accepted"] += sc["mutation"] in adversarial_judgment
            m["fabricated_filler_accepted"] += sc["mutation"] == "filler"
            m["confidence_changes_by_m09"] += sc["mutation"] == "confidence_high"
            m["likelihood_changes_by_m09"] += sc["mutation"] in ("add_likelihood", "change_likelihood")
    # human-side adversarial and valid actions on the latest accepted version
    x = pg.admin()                                       # kept open for the human scenarios below

    def latest():
        return x.execute("SELECT * FROM lfhe.report_versions WHERE report_id=%s ORDER BY version_no DESC LIMIT 1", (rid,)).fetchone()
    base = latest()
    so = statements_of(pg, kj["id"])

    def h_edit(v, content, who=analyst, conn=None):
        with (conn() if conn else pg.as_user(who)) as h:
            return h.execute("SELECT lfhe.edit_report_version(%s, %s, %s::jsonb, 'corpus human edit') r",
                             (v["id"], v["report_version_hash"], json.dumps(content))).fetchone()["r"]

    for sc in CORPUS["human"]:
        ok = True
        try:
            v = latest()
            c = content_of(pg, v["id"])
            if sc["mutation"] == "unmapped_statement":
                c["key_judgments"][0]["statements"].append(rs(900, "Analyst view without a source.", "KEY_JUDGMENT", [], "LOW"))
                h_edit(v, c)
            elif sc["mutation"] == "caveat_removal":
                it = next(i for i in c["key_judgments"] if i["source_candidate_id"] == ctx["cand"]["KJ"])
                it["statements"] = [s_ for s_ in it["statements"] if str(so["AS2"]["id"]) not in s_["source_assessment_statement_ids"]]
                h_edit(v, dict(c, remove_source_statement_ids=[str(so["AS2"]["id"])]))
            elif sc["mutation"] == "wrong_hash":
                h_edit(dict(v, report_version_hash="0" * 64), c)
            elif sc["mutation"] == "worker_edit":
                h_edit(v, c, conn=pg.worker)
            elif sc["mutation"] == "service_role_selection":
                with pg.as_service_role() as h:
                    h.execute("SELECT lfhe.freeze_report_selection(%s, 'machine')", (rid,))
            elif sc["mutation"] == "valid_reword":
                it = next(i for i in c["key_judgments"] if i["source_candidate_id"] == ctx["cand"]["KJ"])
                judg = next(s_ for s_ in it["statements"] if "probably" in s_["text"])
                judg.update(text="Northland is probably expanding tanker support at Fort Aster.", editorial_transform="COMPRESSION")
                h_edit(v, c)
            elif sc["mutation"] == "stale_version":
                h_edit(base, c)
            elif sc["mutation"] == "removal_accept":
                pending = x.execute("""SELECT v.* FROM lfhe.report_versions v JOIN lfhe.report_version_states s ON s.report_version_id=v.id
                                       WHERE v.report_id=%s AND s.length_review_pending ORDER BY v.version_no DESC LIMIT 1""", (rid,)).fetchone()
                assert pending is not None, "corpus needs a pending removal review"
                # bring it back to the head: re-run the valid proposal so the pending version is the latest
                prov = FakeProvider(lambda mod, env: mutate("valid_removal_proposal", env, ctx))
                with pg.worker() as w:
                    rr = run_report_edit(w, sid, sh, model_configuration_id=mc, provider=prov, worker_id="p5-acceptance")
                runs += rr.model_run_ids
                accepted.append(rr.final_run_id)
                pv = x.execute("SELECT * FROM lfhe.report_versions WHERE created_by_model_run_id=%s", (rr.final_run_id,)).fetchone()
                props = x.execute("SELECT id FROM lfhe.report_removal_proposals WHERE report_version_id=%s", (pv["id"],)).fetchall()
                with pg.as_user(analyst) as h:
                    h.execute("SELECT lfhe.decide_report_removals(%s, %s, %s::jsonb, 'analyst accepts the cut')",
                              (pv["id"], pv["report_version_hash"], json.dumps([{"proposal_id": str(p_["id"]), "decision": "ACCEPT"} for p_ in props])))
        except psycopg.Error as exc:
            ok = False
            sc = dict(sc, error=str(exc).splitlines()[0][:300])
        expected_ok = sc["expect"] == "ACCEPTED"
        m["scenario_expectation_mismatches"] += ok != expected_ok
        m["human_adversarial_accepted"] += ok and not expected_ok
        details.append({"id": sc["id"], "mutation": sc["mutation"], "expected": sc["expect"], "got": "ACCEPTED" if ok else "REJECTED",
                        "error": sc.get("error")})

    x.close()
    # --- metrics over everything persisted for this report ----------------------------------------
    with pg.admin() as x:
        versions = x.execute("SELECT * FROM lfhe.report_versions WHERE report_id=%s ORDER BY version_no", (rid,)).fetchall()
        sel_stmts = {str(r["statement_id"]) for r in x.execute("SELECT statement_id FROM lfhe.report_selection_statements(%s)", (sid,))}
        sel_cands = {str(r["candidate_id"]) for r in x.execute("SELECT candidate_id FROM lfhe.report_selection_set_items WHERE selection_set_id=%s", (sid,))}
        caveat = {str(r["id"]) for r in x.execute("SELECT id FROM lfhe.assessment_statements WHERE id = ANY(%s::uuid[]) "
                                                  "AND lfhe.p5_caveat_class(id)", (list(sel_stmts),))}
        approved_conf = {str(r["id"]): r["c"] for r in x.execute(
            "SELECT s.id, lfhe.p5_final_confidence(s.assessment_version_id)::text c FROM lfhe.assessment_statements s "
            "WHERE s.id = ANY(%s::uuid[])", (list(sel_stmts),))}
        src = {str(r["id"]): r for r in x.execute("SELECT * FROM lfhe.assessment_statements WHERE id = ANY(%s::uuid[])", (list(sel_stmts),))}
        for v in versions:
            canon = v["canonical_json"]
            m["canonical_hash_nondeterminism"] += (canonical_sha256(canon) != v["report_version_hash"]) + \
                (x.execute("SELECT lfhe.jcs_sha256(canonical_json) h FROM lfhe.report_versions WHERE id=%s", (v["id"],)).fetchone()["h"]
                 != v["report_version_hash"])
            mapped = set()
            for sec in canon["sections"]:
                for it in sec["items"]:
                    m["unselected_candidate_included"] += it["source_candidate_id"] not in sel_cands
                    for s_ in it["statements"]:
                        mapped |= set(s_["sources"])
                        m["report_statements_without_mapping"] += not s_["sources"]
                        m["statement_provenance_gaps"] += len(set(s_["sources"]) - sel_stmts)
                        confs = {approved_conf.get(i) for i in s_["sources"]}
                        m["confidence_changes_by_m09"] += s_["final_analytic_confidence"] is not None and confs != {s_["final_analytic_confidence"]}
                        terms = {src[i]["likelihood_term"] for i in s_["sources"] if i in src and src[i]["likelihood_term"]}
                        m["likelihood_changes_by_m09"] += (set([s_["likelihood_term"]]) - {None}) != terms
                        for i in s_["sources"]:
                            a = src.get(i)
                            if a and a["attribution_required"] and (a["attribution_text"] or "").lower() not in s_["text"].lower():
                                m["attribution_strength_violations"] += 1
                        for num in re.findall(r"\d+(?:[.,]\d+)?", s_["text"]):
                            m["unsupported_new_facts_accepted"] += not any(num in src[i]["statement_text"] for i in s_["sources"] if i in src)
            unmapped = sel_stmts - mapped - set(canon["human_removals"])
            m["silent_caveat_contradiction_deletion"] += len(unmapped & caveat)
            if v["origin"] == "MODEL":
                m["automatic_substantive_removals"] += len(sel_stmts - mapped)
            for sql in ("UPDATE lfhe.report_versions SET length_status='NEAR_LIMIT' WHERE id=%s", "DELETE FROM lfhe.report_items WHERE report_version_id=%s"):
                try:
                    x.execute(sql, (v["id"],))
                    m["report_version_mutations"] += 1
                except psycopg.Error:
                    pass
            h1 = render_report_html(canon, str(v["id"]), v["report_version_hash"])
            m["preview_render_nondeterminism"] += h1 != render_report_html(copy.deepcopy(canon), str(v["id"]), v["report_version_hash"])
        m["human_statements_without_provenance"] = x.execute(
            """SELECT count(*) n FROM lfhe.report_item_statements s JOIN lfhe.report_items i ON i.id = s.report_item_id
               JOIN lfhe.report_versions v ON v.id = i.report_version_id WHERE v.report_id=%s AND s.author_type='HUMAN'
               AND NOT EXISTS (SELECT 1 FROM lfhe.report_statement_sources x WHERE x.report_item_statement_id = s.id)""", (rid,)).fetchone()["n"]
        m["non_human_authoritative_decisions"] = x.execute(
            """SELECT (SELECT count(*) FROM lfhe.report_selection_decisions d WHERE d.report_id=%s
                       AND NOT EXISTS (SELECT 1 FROM lfhe.user_roles ur WHERE ur.user_id = d.actor_user_id))
                    + (SELECT count(*) FROM lfhe.report_versions v WHERE v.report_id=%s AND v.origin='HUMAN'
                       AND NOT EXISTS (SELECT 1 FROM lfhe.user_roles ur WHERE ur.user_id = v.created_by_user))
                    + (SELECT count(*) FROM lfhe.report_removal_decisions d JOIN lfhe.report_versions v ON v.id=d.report_version_id
                       WHERE v.report_id=%s AND NOT EXISTS (SELECT 1 FROM lfhe.user_roles ur WHERE ur.user_id = d.actor_user_id)) n""",
            (rid, rid, rid)).fetchone()["n"]
        for r in x.execute("SELECT * FROM lfhe.model_runs WHERE id = ANY(%s::uuid[])", (runs,)):
            for col in ("prompt_version_id", "prompt_content_hash", "module_version", "model_configuration_id", "model_config_hash",
                        "envelope_sha256", "input_snapshot_sha256", "context_snapshot_sha256", "completed_at"):
                m["m09_traceability_gaps"] += r[col] is None
            m["m09_traceability_gaps"] += not {"report_mode", "information_cutoff"} <= set(r["task_parameters"] or {})
        human_versions = x.execute("SELECT count(*) n FROM lfhe.report_versions WHERE report_id=%s AND origin='HUMAN'", (rid,)).fetchone()["n"]
    joined = "\n".join(texts).lower()
    m["gs_leakage"] = sum(joined.count(k) for k in GS_MARKERS)
    m.update({"m09_scenarios": len(CORPUS["m09"]), "human_scenarios": len(CORPUS["human"]), "accepted_model_versions": len(accepted),
              "report_versions": len(versions), "human_versions": human_versions, "model_runs": len(set(runs))})
    park_report_jobs(pg)
    if os.environ.get("LFHE_P5_METRICS_OUT"):
        with open(os.environ["LFHE_P5_METRICS_OUT"], "w") as f:
            json.dump({"metrics": m, "scenarios": details}, f, indent=2)
    counts = ("m09_scenarios", "human_scenarios", "accepted_model_versions", "report_versions", "human_versions", "model_runs")
    assert [k for k in m if k not in counts and m[k] != 0] == [], (m, details)
    assert m["accepted_model_versions"] >= 3 and human_versions >= 2
