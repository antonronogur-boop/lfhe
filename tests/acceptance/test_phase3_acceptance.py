"""Phase 3 acceptance corpus (Addendum §16) — measured through the real
pipeline: real M04/M05 bundles, real input builders, real ingestion and the
real human (RBAC) functions; only the model is scripted (FakeProvider replays
the corpus' model_output blocks, including deliberately naive / over-eager
outputs). Corpus truth labels are read only here.

Writes the CG3 metrics to $LFHE_P3_METRICS_OUT when set."""
import json
import os
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from conftest import REPO_ROOT
from lfhe_orchestrator.event_pipeline import run_event_builder, run_lineage
from lfhe_orchestrator.providers import FakeProvider, render_messages
from lineage_support import grounded_claim, head, version_claims
from pipeline_support import activate_real_prompts, model_configuration

pytestmark = pytest.mark.db
CORPUS = json.loads((REPO_ROOT / "tests" / "fixtures" / "phase3_acceptance" / "corpus.json").read_text())
GS_MARKERS = ("gs-001", "gold standard", "gold-standard", "gold_standard", "answer key", "answer-key", "answer_key")


def cutoff():
    return datetime.now(timezone.utc) + timedelta(minutes=5)


def make_claims(pg, spec: dict) -> dict:
    out = {}
    for local, c in spec.items():
        extra = {k: c[k] for k in ("claim_type", "locations", "available_at") if k in c}
        out[local] = grounded_claim(pg, c["text"], c["exact"], language=c["language"], **extra)["claim_id"]
    return out


def envelope_text(provider) -> str:
    return "\n".join(json.dumps(env, ensure_ascii=False) + "\n".join(
        m["content"] for m in render_messages(mod, env)[1]) + render_messages(mod, env)[0]
        for mod, env, _ in provider.calls)


def m04_output(sc, ids):
    mo = sc["model_output"]
    return json.dumps({"module": "M04_LINEAGE", "status": "SUCCESS", "warnings": [], "human_review_required": False,
                       "result": {
                           "claim_relationships": [{
                               "child_claim_id": ids[r["child"]], "relationship_type": r["type"],
                               "parent_claim_id": ids[r["parent_claim"]] if r.get("parent_claim") else None,
                               "parent_article_id": None, "external_origin_name": r.get("external_origin_name"),
                               "external_origin_url": r.get("external_origin_url"), "confidence": "MODERATE",
                               "explanation": "corpus"}
                               for r in mo["claim_relationships"]],
                           "corroboration_recommendations": [{
                               "claim_id": ids[r["claim"]], "recommendation": r["recommendation"],
                               "recommended_status": r["recommended_status"],
                               "supporting_claim_ids": [ids[s] for s in r["supporting"]], "explanation": "corpus"}
                               for r in mo["corroboration_recommendations"]]}})


def m05_output(sc, ids, events, env):
    ctx = {i["content"]["event_id"]: i["content"]["version_id"] for i in env["context"] if i["object_type"] == "event_version"}
    out = []
    for o in sc["model_output"]:
        target = events[sc[o["target"]]["scenario"], sc[o["target"]]["claim"]] if o.get("target") else None
        related = [events[sc[o["related"]]["scenario"], sc[o["related"]]["claim"]]] if o.get("related") else []
        for e in [target, *related]:
            assert e is None or e in ctx, f"{sc['id']}: event {e} not supplied as context"
        cand = None
        if o["proposal"] in ("CREATE_NEW_EVENT", "UPDATE_EXISTING_EVENT"):
            cand = {"title": o["title"], "description": "Synthetic corpus event.", "event_type": o["event_type"],
                    "event_date_start": None, "event_date_end": None, "event_date_confidence": "UNKNOWN",
                    "locations": o.get("locations", []),
                    "claims": [{"claim_id": ids[k], "role": r} for k, r in o["claims"].items()]}
        out.append({"proposal": o["proposal"], "target_event_id": target,
                    "target_event_version_id": ctx.get(target) if target else None, "related_event_ids": related,
                    "claim_ids": [ids[k] for k in o.get("claims", {})], "event_candidate": cand, "reason": "corpus",
                    "confidence": "MODERATE"})
    return json.dumps({"module": "M05_EVENT_BUILDER", "status": "SUCCESS", "warnings": [], "human_review_required": False,
                       "result": {"proposals": out}})


def statuses(pg, ids):
    with pg.admin() as x:
        return {str(r["claim_id"]): r["claim_status"] for r in x.execute(
            "SELECT claim_id, claim_status FROM lfhe.claim_state WHERE claim_id = ANY(%s::uuid[])", (list(ids),))}


def live_claims(pg, event_ids) -> set:
    """Claims reachable from the current heads of the events the given IDs resolve to."""
    with pg.admin() as x:
        heads = {str(x.execute("SELECT lfhe.resolve_event(%s) r", (e,)).fetchone()["r"]) for e in event_ids}
        found = set()
        for e in heads:
            found |= set(version_claims(pg, head(pg, e)["head_version_id"]))
            for r in x.execute("SELECT to_event_id FROM lfhe.event_relationships WHERE from_event_id=%s "
                               "AND relationship_type='SPLIT_INTO'", (e,)):
                found |= set(version_claims(pg, head(pg, r["to_event_id"])["head_version_id"]))
        return found


def test_phase3_acceptance_corpus(pg, make_user):
    activate_real_prompts(pg, ("M02_CLAIM_EXTRACTOR", "M03_CLASSIFIER", "M04_LINEAGE", "M05_EVENT_BUILDER"))
    analyst = make_user("ANALYST")
    mc = model_configuration(pg)
    m = {"lineage_scenarios": {}, "event_scenarios": {}, "republication_inflation": 0,
         "surface_difference_independence": 0, "independence_established_true": 0, "silent_status_finalisation": 0,
         "high_impact_changes_without_human": 0, "ai_structural_actions": 0, "unvalidated_ai_grouping_promoted": 0,
         "over_merge_in_validated_events": 0, "claims_lost_in_structural_ops": 0, "ancestry_breaks": 0,
         "gs_leakage": 0, "model_runs": 0, "model_runs_incomplete_provenance": 0,
         "false_dependence_collapse": 0, "replay_context_leakage": 0, "retraction_hindsight_leakage": 0}
    all_claims, all_runs, envelopes = set(), [], []

    # ---------------- M04 lineage scenarios ----------------
    for sc in CORPUS["lineage_scenarios"]:
        ids = make_claims(pg, sc["claims"])
        all_claims |= set(ids.values())
        for h in sc.get("high_impact", []):
            with pg.as_user(analyst) as u:
                u.execute("SELECT lfhe.mark_claim_high_impact(%s, true, NULL, 'corpus: key capability claim')", (ids[h],))
        before = statuses(pg, ids.values())
        provider = FakeProvider(lambda mod, env, sc=sc, ids=ids: m04_output(sc, ids))
        with pg.worker() as c:
            out = run_lineage(c, list(ids.values()), report_mode="LIVE", information_cutoff=cutoff(),
                              model_configuration_id=mc, provider=provider, worker_id="p3-acceptance")
        assert out.outcome in ("PROPOSALS_RECORDED", "NO_PROPOSALS"), (sc["id"], out)
        all_runs += out.model_run_ids
        envelopes.append(envelope_text(provider))
        after_ai = statuses(pg, ids.values())
        m["silent_status_finalisation"] += sum(after_ai[k] != before[k] for k in before)
        with pg.worker() as w:                                    # a worker can never decide
            for rec in w.execute("SELECT id FROM lfhe.corroboration_recommendations WHERE model_run_id=%s",
                                 (out.final_run_id,)).fetchall():
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    w.execute("SELECT lfhe.decide_corroboration_recommendation(%s, true, 'UNVERIFIED', "
                              "'CORROBORATED', 'worker tries')", (rec["id"],))
        unvalidated = summary_of(pg, ids.values())
        if sc["human"].get("accept_lineage"):
            with pg.as_user(analyst) as u:
                chosen = {}          # explicit human identity decisions (CG3-03): origin name → origin id
                for p in u.execute("SELECT id, external_origin_name FROM lfhe.lineage_proposals WHERE model_run_id=%s "
                                   "ORDER BY proposal_index", (out.final_run_id,)).fetchall():
                    select = chosen.get(p["external_origin_name"]) if sc["human"].get("explicit_origin_reuse") else None
                    lid = u.execute("SELECT lfhe.decide_lineage_proposal(%s, true, 'corpus: lineage evidenced in text', %s) "
                                    "AS id", (p["id"], select)).fetchone()["id"]
                    if p["external_origin_name"]:
                        chosen.setdefault(p["external_origin_name"], u.execute(
                            "SELECT external_origin_id FROM lfhe.claim_lineage WHERE id=%s", (lid,)).fetchone()["external_origin_id"])
        dec = sc["human"].get("decide_recommendation")
        if dec:
            with pg.as_user(analyst) as u:
                rec = u.execute("SELECT id FROM lfhe.corroboration_recommendations WHERE model_run_id=%s AND claim_id=%s",
                                (out.final_run_id, ids[dec["claim"]])).fetchone()["id"]
                u.execute("SELECT lfhe.decide_corroboration_recommendation(%s, true, 'UNVERIFIED', %s, "
                          "'corpus: analyst confirms on review')", (rec, dec["new_status"]))
        validated = summary_of(pg, ids.values())
        for s in (unvalidated, validated):
            m["independence_established_true"] += bool(s["independence_established"])
        truth = sc["truth"]["origin_groups"]
        if truth == "UNKNOWN":
            m["surface_difference_independence"] += int(validated["claims_with_unknown_lineage"] != len(ids)
                                                         or validated["independence_established"])
        elif sc["human"].get("accept_lineage"):
            m["republication_inflation"] += max(0, validated["distinct_groups_upper_bound"] - len(truth))
            m["false_dependence_collapse"] += max(0, len(truth) - validated["distinct_groups_upper_bound"])
        else:   # lineage not validated: nothing may be treated as independent confirmation
            m["republication_inflation"] += sum(statuses(pg, ids.values())[k] != before[k] for k in before
                                                if not dec)
        with pg.admin() as x:
            m["high_impact_changes_without_human"] += x.execute(
                "SELECT count(*) n FROM lfhe.claim_status_history WHERE claim_id = ANY(%s::uuid[]) "
                "AND high_impact_at_change AND (actor_type <> 'HUMAN' OR basis <> 'HUMAN_DECISION')",
                (list(ids.values()),)).fetchone()["n"]
        m["lineage_scenarios"][sc["id"]] = {"claims": len(ids), "outcome": out.outcome,
                                            "before_validation": unvalidated, "after_human_decision": validated,
                                            "truth_origin_groups": truth if truth == "UNKNOWN" else len(truth),
                                            "status_after_ai": after_ai == before}

    # ---------------- M05 event scenarios ----------------
    events, scenario_events, claim_of = {}, {}, {}
    for sc in CORPUS["event_scenarios"]:
        ids = make_claims(pg, sc["claims"])
        all_claims |= set(ids.values())
        provider = FakeProvider(lambda mod, env, sc=sc, ids=ids: m05_output(sc, ids, events, env))
        with pg.worker() as c:
            out = run_event_builder(c, list(ids.values()), report_mode="LIVE", information_cutoff=cutoff(),
                                    model_configuration_id=mc, provider=provider, worker_id="p3-acceptance")
            mats = c.execute("SELECT proposal_type::text t, materialised_event_id e, materialised_version_id v "
                             "FROM lfhe.event_proposals WHERE model_run_id=%s ORDER BY proposal_index",
                             (out.final_run_id,)).fetchall()
            m["ai_structural_actions"] += c.execute(
                "SELECT count(*) n FROM lfhe.event_actions WHERE proposal_id IN "
                "(SELECT id FROM lfhe.event_proposals WHERE model_run_id=%s)", (out.final_run_id,)).fetchone()["n"]
        assert out.outcome == "PROPOSALS_RECORDED", (sc["id"], out)
        all_runs += out.model_run_ids
        envelopes.append(envelope_text(provider))
        for row, o in zip(mats, sc["model_output"]):
            if row["t"] == "CREATE_NEW_EVENT":
                assert head(pg, row["e"])["state"] == "CANDIDATE"
                for k in o["claims"]:
                    events[sc["id"], k] = str(row["e"])
            if row["t"] in ("CREATE_NEW_EVENT", "UPDATE_EXISTING_EVENT"):
                scenario_events.setdefault(sc["id"], set()).add(str(row["e"]))
        claim_of.update({k: v for k, v in ids.items()})
        h = sc.get("human", {})
        if h.get("review"):
            [row] = [r for r in mats if r["t"] == "UPDATE_EXISTING_EVENT"]
            ev = str(row["e"])
            v = head(pg, ev)
            assert v["head_pending_review"] and v["state"] == "CANDIDATE"     # AI grouping is not validated
            m["ai_over_eager_versions_held_for_review"] = m.get("ai_over_eager_versions_held_for_review", 0) + 1
            with pg.as_user(analyst) as u:
                u.execute("SELECT lfhe.review_event_version(%s, %s, %s, 'corpus: weakly related, not the same event')",
                          (v["head_version_id"], v["head_content_hash"], h["review"]))
                keep = {c: r for c, r in version_claims(pg, v["head_version_id"]).items()
                        if c not in {ids[k] for k in h["correct_by_update_removing"]}}
                prev = dict(u.execute("SELECT title, description, event_type::text event_type, locations FROM lfhe.event_versions "
                                      "WHERE id=%s", (v["head_version_id"],)).fetchone())
                u.execute("SELECT lfhe.update_event(%s, %s, %s::jsonb, 'corpus: remove weakly related claim')",
                          (ev, v["head_version_id"], json.dumps({**prev, "locations": list(prev["locations"] or []), "claims": [
                              {"claim_id": c, "role": r} for c, r in keep.items()]})))
            with pg.admin() as x:
                act = x.execute("SELECT details FROM lfhe.event_actions WHERE action='UPDATE' AND details->>'event_id'=%s "
                                "ORDER BY created_at DESC LIMIT 1", (ev,)).fetchone()["details"]
            assert act["removed_claim_ids"] == [ids[k] for k in h["correct_by_update_removing"]]   # recorded, not silent
        m["event_scenarios"][sc["id"]] = {"claims": len(ids), "outcome": out.outcome,
                                          "proposals": [r["t"] for r in mats],
                                          "events_touched": len(scenario_events.get(sc["id"], ()))}

    # truth-based clustering check on every event the corpus touched
    label = {}
    for sc in CORPUS["event_scenarios"]:
        if isinstance(sc["truth"]["event_clusters"], list):
            for cl in sc["truth"]["event_clusters"]:
                found = next((label[claim_of[k]] for k in cl if claim_of[k] in label), f"{sc['id']}:{cl[0]}")
                for k in cl:
                    label[claim_of[k]] = found
    touched = set().union(*scenario_events.values())
    with pg.admin() as x:
        for e in sorted(touched):
            hv = head(pg, e)
            labels = {label[c] for c in version_claims(pg, hv["head_version_id"]) if c in label}
            if len(labels) <= 1:
                continue
            origin = x.execute("SELECT origin FROM lfhe.event_versions WHERE id=%s", (hv["head_version_id"],)).fetchone()["origin"]
            if origin == "HUMAN" or hv["head_review_decision"] == "APPROVE":
                m["over_merge_in_validated_events"] += 1
            elif hv["state"] != "CANDIDATE":
                m["unvalidated_ai_grouping_promoted"] += 1
            else:
                m["over_merge_pending_ai_heads"] = m.get("over_merge_pending_ai_heads", 0) + 1
        # E3: later reporting updated the existing event instead of creating a new one
        radar = events["E1_WEAKLY_RELATED_SAME_COUNTRY_WEEK", "radar"]
        m["old_event_new_reporting_updated"] = claim_of["radar2"] in version_claims(pg, head(pg, radar)["head_version_id"])
        assert m["old_event_new_reporting_updated"]

    # ---------------- human structural chain ----------------
    st = CORPUS["structural_scenario"]
    ids = make_claims(pg, st["claims"])
    all_claims |= set(ids.values())

    def human_event(keys, title, etype="DEPLOYMENT", roles=None):
        with pg.as_user(analyst) as u:
            return str(u.execute("SELECT lfhe.create_event(%s::jsonb, 'corpus: analyst creates') AS e", (json.dumps({
                "title": title, "description": "Synthetic corpus event.", "event_type": etype, "locations": [],
                "claims": [{"claim_id": ids[k], "role": (roles or {}).get(k, "SUPPORTS")} for k in keys]}),)).fetchone()["e"])
    def heads_of(*evs):
        return {e: str(head(pg, e)["head_version_id"]) for e in evs}
    e_m1 = human_event(["m1", "d1"], "Fighter deployment to Base South", roles={"d1": "CONTRADICTS"})
    e_m2 = human_event(["m2"], "Fighter deployment (hu report)")
    e_mix = human_event(["s1", "s2"], "Base East activity")
    before_ops = {e: set(version_claims(pg, head(pg, e)["head_version_id"])) for e in (e_m1, e_m2, e_mix)}
    old_versions = {e: (head(pg, e)["head_version_id"], head(pg, e)["head_content_hash"]) for e in (e_m1, e_m2, e_mix)}
    with pg.as_user(analyst) as u:
        u.execute("SELECT lfhe.merge_events(%s, ARRAY[%s]::uuid[], %s::jsonb, 'corpus: same deployment')",
                  (e_m1, e_m2, json.dumps(heads_of(e_m1, e_m2))))
        u.execute("SELECT lfhe.split_event(%s, %s, %s::jsonb, 'corpus: two developments')", (
            e_mix, heads_of(e_mix)[e_mix], json.dumps({
                "children": [{"title": "Drone test at Base East", "description": "Synthetic corpus event.", "event_type": "TEST",
                              "locations": [], "claims": [{"claim_id": ids["s2"], "role": "SUPPORTS"}]}],
                "retained": {"title": "Transport aircraft to Base East", "description": "Synthetic corpus event.",
                             "event_type": "DEPLOYMENT", "locations": [], "claims": [{"claim_id": ids["s1"], "role": "SUPPORTS"}]}})))
    consolidated = human_event(["m1", "m2", "d1"], "Fighter deployment to Base South (consolidated)", roles={"d1": "CONTRADICTS"})
    with pg.as_user(analyst) as u:
        u.execute("SELECT lfhe.supersede_event(%s, %s, %s::jsonb, 'corpus: consolidated representation')",
                  (e_m1, consolidated, json.dumps(heads_of(e_m1, consolidated))))
    for e, claims in before_ops.items():
        m["claims_lost_in_structural_ops"] += len(claims - live_claims(pg, [e]))
    with pg.admin() as x:
        for e, (vid, h) in old_versions.items():
            ok = x.execute("SELECT lfhe.event_version_stored_hash(%s) h", (vid,)).fetchone()["h"] == h
            m["ancestry_breaks"] += int(not ok)
        m["ancestry_breaks"] += int(str(x.execute("SELECT lfhe.resolve_event(%s) r", (e_m2,)).fetchone()["r"]) != consolidated)
        m["ancestry_breaks"] += int(str(x.execute("SELECT lfhe.resolve_event(%s) r", (e_m1,)).fetchone()["r"]) != consolidated)
        m["ancestry_breaks"] += int(str(x.execute("SELECT lfhe.resolve_event(%s) r", (e_mix,)).fetchone()["r"]) != e_mix)
        cons = version_claims(pg, head(pg, consolidated)["head_version_id"])
        assert cons[ids["d1"]] == "CONTRADICTS"                                  # contradiction preserved
        # every structural action is a human action
        m["ai_structural_actions"] += x.execute(
            "SELECT count(*) n FROM lfhe.event_relationships r JOIN lfhe.event_actions a ON a.id = r.action_id "
            "WHERE a.actor_user_id IS NULL").fetchone()["n"]

        # ---------------- REPLAY as-of discipline (CG3-01) ----------------
        m["replay"] = replay_scenario(pg, analyst, mc, all_runs, envelopes)
        m["replay_context_leakage"] = m["replay"]["leaks"]
        m["retraction_hindsight_leakage"] = m["replay"]["retraction_hindsight_leakage"]

        # ---------------- provenance + GS isolation ----------------
        runs = x.execute("SELECT * FROM lfhe.model_runs WHERE id = ANY(%s::uuid[])", (all_runs,)).fetchall()
        m["model_runs"] = len(runs)
        for r in runs:
            need = ("prompt_version_id", "prompt_semver", "prompt_content_hash", "module_version",
                    "model_configuration_id", "model_config_hash", "provider", "model", "input_manifest",
                    "input_snapshot_sha256", "context_manifest", "context_snapshot_sha256", "envelope_sha256",
                    "task_parameters")
            missing = [k for k in need if r.get(k) in (None, "")]
            if r["status"] == "SUCCEEDED" and r.get("raw_output") in (None, ""):
                missing.append("raw_output")
            if r["status"] != "SUCCEEDED" and not (r.get("error_code") or r.get("validation_errors")):
                missing.append("failure_state")
            m["model_runs_incomplete_provenance"] += int(bool(missing))
    blob = "\n".join(envelopes).lower()
    m["gs_leakage"] = sum(blob.count(k) for k in GS_MARKERS)

    out_path = os.environ.get("LFHE_P3_METRICS_OUT")
    if out_path:
        with open(out_path, "w") as f:
            json.dump(m, f, indent=1, sort_keys=True, default=str)

    for key in ("republication_inflation", "surface_difference_independence", "independence_established_true",
                "silent_status_finalisation", "high_impact_changes_without_human", "ai_structural_actions",
                "unvalidated_ai_grouping_promoted", "over_merge_in_validated_events", "claims_lost_in_structural_ops",
                "ancestry_breaks", "gs_leakage", "model_runs_incomplete_provenance", "false_dependence_collapse",
                "replay_context_leakage", "retraction_hindsight_leakage"):
        assert m[key] == 0, (key, m)
    assert m["model_runs"] >= len(CORPUS["lineage_scenarios"]) + len(CORPUS["event_scenarios"])


def summary_of(pg, ids):
    with pg.worker() as c:
        return c.execute("SELECT lfhe.independence_summary(%s::uuid[]) AS s", (list(ids),)).fetchone()["s"]



def replay_scenario(pg, analyst, mc, all_runs, envelopes) -> dict:
    """R1: v1 from pre-cutoff evidence, v2 (+ CONFIRMED) and a lineage decision from post-cutoff
    evidence; a REPLAY between them must see none of the later knowledge."""
    from lfhe_orchestrator.event_inputs import build_m04_inputs, build_m05_inputs
    from lineage_support import ingest_lineage, rel
    sc = CORPUS["replay_scenario"]
    cut = datetime.fromisoformat(sc["information_cutoff"])
    ids = make_claims(pg, sc["claims"])

    def payload(v):
        return json.dumps({"title": v["title"], "description": v["description"], "event_type": "DEPLOYMENT",
                           "locations": v["locations"], "claims": [{"claim_id": ids[k], "role": "SUPPORTS"} for k in v["claims"]]})
    with pg.as_user(analyst) as u:
        ev = str(u.execute("SELECT lfhe.create_event(%s::jsonb, 'corpus: replay v1') AS e", (payload(sc["v1"]),)).fetchone()["e"])
        v1 = str(head(pg, ev)["head_version_id"])
        u.execute("SELECT lfhe.update_event(%s, %s, %s::jsonb, 'corpus: later reporting')", (ev, v1, payload(sc["v2"])))
        u.execute("SELECT lfhe.set_event_state(%s, 'ACTIVE', %s, 'corpus: confirmed on the later report')",
                  (ev, sc["v2"]["then_state"]))
    ll = sc["later_lineage"]
    from claims_support import make_model_run       # the M04 run that saw post-cutoff evidence
    run = make_model_run(pg, "M04_LINEAGE", [("claim", ids[k]) for k in ll["run_inputs"]],
                         task_parameters={"report_mode": "LIVE", "information_cutoff": "2100-01-01T00:00:00+00:00"})
    ingest_lineage(pg, run, [rel({"claim_id": ids[ll["child"]]}, "DERIVED_REPORTING", parent_claim={"claim_id": ids[ll["parent"]]})])
    all_runs.append(run)
    with pg.as_user(analyst) as u:
        p = u.execute("SELECT id FROM lfhe.lineage_proposals WHERE model_run_id=%s", (run,)).fetchone()["id"]
        later_lid = str(u.execute("SELECT lfhe.decide_lineage_proposal(%s, true, 'corpus: traced by the later audit') AS id",
                                  (p,)).fetchone()["id"])
    rl = sc["retracted_lineage"]                       # validated on pre-cutoff evidence, retracted on later evidence
    with pg.as_user(analyst) as u:
        lid = u.execute("SELECT lfhe.record_claim_lineage(%s::jsonb, 'corpus: analyst read both texts') AS id", (json.dumps({
            "child_claim_id": ids[rl["child"]], "relationship_type": "DERIVED_REPORTING", "parent_claim_id": ids[rl["parent"]],
            "evidence_basis": [{"object_type": "claim", "object_id": ids[k]} for k in rl["lineage_evidence"]]}),)).fetchone()["id"]
        u.execute("SELECT lfhe.retract_claim_lineage(%s, 'corpus: later correction', %s::jsonb)",
                  (lid, json.dumps([{"object_type": "claim", "object_id": ids[k]} for k in rl["retraction_evidence"]])))
    with pg.worker() as c:
        retracted = c.execute("SELECT lfhe.independence_summary_asof(%s::uuid[], 'REPLAY', %s) s",
                              ([ids[rl["child"]], ids[rl["parent"]]], cut)).fetchone()["s"]
        m05 = build_m05_inputs(c, [ids["probe"], ids["copy"]], report_mode="REPLAY", information_cutoff=cut)
        m04 = build_m04_inputs(c, [ids["pre"], ids["copy"]], report_mode="REPLAY", information_cutoff=cut)
        groups = c.execute("SELECT lfhe.independence_summary_asof(%s::uuid[], 'REPLAY', %s) s",
                           ([ids["pre"], ids["copy"]], cut)).fetchone()["s"]
    events = {i.content["event_id"]: i for i in m05.context if i.object_type == "event_version"}
    blob = json.dumps([i.content for i in m05.context + m04.context], ensure_ascii=False)
    leaks = sum(blob.count(x) for x in sc["later_only_markers"]) + blob.count(ids["post"])
    leaks += int(ev not in events or events[ev].object_id != v1)                       # must see exactly v1
    leaks += int(ev in events and events[ev].content["state"] != "ACTIVE")             # later CONFIRMED must not leak
    leaks += sum(1 for i in m04.context + m05.context if i.object_type == "claim_lineage" and i.object_id == later_lid)
    retraction_kept = any(i.object_type == "claim_lineage" and i.object_id == str(lid) for i in m04.context)
    leaks += int(groups["distinct_groups_upper_bound"] != 2)                           # later lineage must not collapse
    retraction_leaks = int(retracted["distinct_groups_upper_bound"] != 1) + int(not retraction_kept)  # later retraction must not split
    envelopes.append(blob)
    return {"leaks": leaks, "retraction_hindsight_leakage": retraction_leaks, "replay_retracted_pair": retracted,
            "event_version_seen": "v1" if ev in events and events[ev].object_id == v1 else "other",
            "replay_independence": groups}
