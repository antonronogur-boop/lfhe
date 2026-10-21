"""Phase 5 test support: approved Phase 4 assessments (real M07 → M08 → human review), reports,
candidate selection, scripted M09 outputs. All material is synthetic ('Northland'); nothing
here is Gold Standard material."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from lfhe_orchestrator.providers import FakeProvider
from lfhe_orchestrator.report_pipeline import run_report_edit
from pipeline_support import activate_real_prompts, model_configuration
from test_p4_assessments import assess, out as m07_out, setup_event, version_of
from test_p4_challenge_review import CONF_RAT, chal, challenge, review

P5_MODULES = ("M02_CLAIM_EXTRACTOR", "M03_CLASSIFIER", "M07_INTELLIGENCE_ASSESSOR", "M08_CHALLENGER", "M09_EXECUTIVE_EDITOR")
SECTION_KEYS = {"KEY_JUDGMENT": "key_judgments", "SIGNIFICANT_DEVELOPMENT": "significant_developments",
                "INDICATOR_WARNING": "indicators_warning", "TREND_WATCH": "trend_watch", "WHAT_TO_WATCH": "what_to_watch",
                "CAVEAT": "caveats"}


def now():
    return datetime.now(timezone.utc) + timedelta(minutes=10)


def activate(pg):
    return activate_real_prompts(pg, P5_MODULES)


def approved_assessment(pg, analyst, *, statements=None, conf="LOW", contra=True, indicators=None, extra_claims=()):
    """statements: optional callable(claims) -> M07 statements. Returns (version_row, claims, event)."""
    e, vid, vh, claims = setup_event(pg, analyst, contra=contra, extra=extra_claims)
    stm = statements(claims) if statements else None
    ind = indicators(claims) if indicators else ()
    r = assess(pg, vid, vh, lambda m, env: m07_out(env, json.loads(json.dumps(stm)) if stm else None, claims=claims,
                                                   indicators=ind))
    assert r.outcome == "ASSESSMENT_RECORDED", r
    v = version_of(pg, r.final_run_id)
    assert challenge(pg, v, lambda m, env: chal(env)).outcome == "CHALLENGE_RECORDED"
    review(pg, analyst, v, "APPROVE", conf, CONF_RAT)
    return v, claims, (e, vid, vh)


def statements_of(pg, version_id):
    with pg.admin() as x:
        return {r["statement_local_id"]: r for r in x.execute(
            "SELECT *, statement_type::text AS t FROM lfhe.assessment_statements WHERE assessment_version_id=%s", (version_id,))}


def new_report(pg, user, code, *, mode="LIVE", cutoff=None, title="Northland air-domain weekly"):
    with pg.as_user(user) as h:
        rid = str(h.execute("SELECT lfhe.create_report(%s::jsonb, 'analyst opens the weekly cycle') r", (json.dumps({
            "code": code, "title": title, "cycle_label": "2026-W43", "report_mode": mode,
            "information_cutoff": (cutoff or now()).isoformat()}),)).fetchone()["r"])
        h.execute("SELECT lfhe.refresh_report_candidates(%s)", (rid,))
    return rid


def candidates(pg, rid):
    with pg.admin() as x:
        return {str(r["object_id"]): r for r in x.execute(
            "SELECT *, candidate_type::text AS ctype FROM lfhe.report_candidate_state WHERE report_id=%s", (rid,))}


def decide(pg, user, cand, decision="INCLUDE", section="KEY_JUDGMENT", priority=1, reason="analyst selects for the report"):
    with pg.admin() as x:
        prev = x.execute("SELECT latest_decision_id FROM lfhe.report_candidate_state WHERE candidate_id=%s",
                         (cand["candidate_id"],)).fetchone()["latest_decision_id"]
    with pg.as_user(user) as h:
        return str(h.execute("SELECT lfhe.decide_report_candidate(%s, %s, %s, %s, %s, %s, %s) r", (
            cand["candidate_id"], cand["object_hash"], decision, section if decision == "INCLUDE" else None,
            priority if decision == "INCLUDE" else None, prev, reason)).fetchone()["r"])


def freeze(pg, user, rid):
    with pg.as_user(user) as h:
        r = h.execute("SELECT lfhe.freeze_report_selection(%s, 'analyst requests the M09 draft') r", (rid,)).fetchone()["r"]
    return r["selection_set_id"], r["content_hash"]


def select(pg, user, rid, placements):
    """placements: [(object_id, section, priority)] → frozen (set_id, hash)."""
    cands = candidates(pg, rid)
    for oid, section, prio in placements:
        decide(pg, user, cands[str(oid)], "INCLUDE", section, prio)
    return freeze(pg, user, rid)


# --- scripted M09 --------------------------------------------------------------------------
def pool(env):
    return env["inputs"][0]["content"]["candidates"]


def auto_items(env, *, sections=None):
    """One item per candidate in its human-assigned section; one VERBATIM statement per approved
    statement; caveat-class statements as role CAVEAT. Always valid by construction."""
    out = {k: [] for k in SECTION_KEYS.values()}
    n = 0
    for i, c in enumerate(pool(env), 1):
        sec = (sections or {}).get(c["candidate_id"], c["section"])
        stmts = []
        for s in c["statements"]:
            n += 1
            stmts.append(rs(n, s["text"], "CAVEAT" if s["caveat_class"] else sec, [s["assessment_statement_id"]],
                            c["final_analytic_confidence"], s["likelihood_term"], "VERBATIM_APPROVED"))
        out[SECTION_KEYS[sec]].append({"item_local_id": f"IT{i}", "source_candidate_id": c["candidate_id"], "statements": stmts})
    return out


def rs(n, text, role, sources, conf=None, likelihood=None, transform="PARAPHRASE"):
    return {"report_statement_local_id": f"RS{n}", "text": text, "statement_role": role,
            "source_assessment_statement_ids": list(sources), "final_analytic_confidence": conf, "likelihood_term": likelihood,
            "editorial_transform": transform}


def m09(env, sections=None, *, length="WITHIN_LIMIT", removals=(), status="SUCCESS", **extra):
    res = {"selection_set_id": env["task"]["selection_set_id"], "selection_set_hash": env["task"]["selection_set_hash"],
           "header": {}, "length_status": length, "removal_recommendations": list(removals)}
    res.update(sections if sections is not None else auto_items(env))
    res.update(extra)
    return json.dumps({"module": "M09_EXECUTIVE_EDITOR", "status": status, "warnings": [], "human_review_required": True,
                       "result": res})


def run_m09(pg, set_id, set_hash, responder):
    with pg.worker() as c:
        return run_report_edit(c, set_id, set_hash, model_configuration_id=model_configuration(pg),
                               provider=FakeProvider(responder), worker_id="p5-test")


def rejected(r, code):
    return r.outcome == "OUTPUT_REJECTED" and any(x.startswith(code) for x in r.rejection_reasons)


def version_of_run(pg, run_id):
    with pg.admin() as x:
        return x.execute("SELECT * FROM lfhe.report_versions WHERE created_by_model_run_id=%s", (run_id,)).fetchone()


def latest_version(pg, rid):
    with pg.admin() as x:
        return x.execute("SELECT * FROM lfhe.report_versions WHERE report_id=%s ORDER BY version_no DESC LIMIT 1",
                         (rid,)).fetchone()


def content_of(pg, version_id):
    with pg.admin() as x:
        return x.execute("SELECT lfhe.report_version_content(%s) c", (version_id,)).fetchone()["c"]


def edit(pg, user, v, content, reason="analyst tightens the wording"):
    with pg.as_user(user) as h:
        return h.execute("SELECT lfhe.edit_report_version(%s, %s, %s::jsonb, %s) r",
                         (str(v["id"]), v["report_version_hash"], json.dumps(content), reason)).fetchone()["r"]


__all__ = ["CONF_RAT", "SECTION_KEYS", "activate", "approved_assessment", "auto_items", "candidates", "content_of", "decide",
           "edit", "freeze", "latest_version", "m09", "new_report", "now", "pool", "rejected", "rs", "run_m09", "select",
           "statements_of", "version_of_run"]
