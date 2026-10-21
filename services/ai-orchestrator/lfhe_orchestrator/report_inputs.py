"""Deterministic M09 input building (Phase 5 Addendum §3, §7, §23).

* M09 sees exactly one frozen, HUMAN-made selection set (id + JCS/SHA-256 hash). It never
  selects the candidate pool itself.
* Every selected candidate is re-checked here for as-of eligibility (approved / current for the
  report's mode and cutoff) and for its pinned hash; anything else fails closed before a model
  is invoked.
* The statement pool is built from approved assessment statements only (with their deterministic
  attribution, likelihood, contested and caveat flags) and the approved final_analytic_confidence
  from the canonical approval row. ai_recommended_confidence is never supplied.
* The same database state yields the same envelope. The builder reads only the database.
"""
from __future__ import annotations

from lfhe_shared.envelopes import EnvelopeItem

from .assessment_inputs import AnalysisInputs, check_cutoff
from .claim_inputs import InputBuildError

M09_MODULE = "M09_EXECUTIVE_EDITOR"
EDITORIAL_TRANSFORMS = ["VERBATIM_APPROVED", "PARAPHRASE", "COMPRESSION", "NON_ANALYTIC_FORMATTING"]


def _statements(conn, candidate_type: str, object_id: str) -> list[dict]:
    rows = conn.execute(
        """SELECT s.id, s.assessment_version_id, s.statement_local_id, s.statement_type::text AS stype,
                  s.epistemic_category::text AS cat, s.statement_text, s.attribution_required, s.attribution_text,
                  s.likelihood_term, lfhe.p5_statement_contested(s.id) AS contested, lfhe.p5_caveat_class(s.id) AS caveat
           FROM lfhe.report_candidate_statements(%s::lfhe.report_candidate_type, %s) cs
           JOIN lfhe.assessment_statements s ON s.id = cs.statement_id
           ORDER BY s.assessment_version_id, s.statement_local_id""", (candidate_type, object_id)).fetchall()
    return [{"assessment_statement_id": str(r["id"]), "assessment_version_id": str(r["assessment_version_id"]),
             "statement_local_id": r["statement_local_id"], "statement_type": r["stype"], "epistemic_category": r["cat"],
             "text": r["statement_text"], "attribution_required": r["attribution_required"],
             "attribution_text": r["attribution_text"], "likelihood_term": r["likelihood_term"],
             "contested": r["contested"], "caveat_class": r["caveat"]} for r in rows]


def build_m09_inputs(conn, selection_set_id: str, selection_set_hash: str) -> AnalysisInputs:
    sel = conn.execute("SELECT * FROM lfhe.report_selection_sets WHERE id = %s", (str(selection_set_id),)).fetchone()
    if sel is None:
        raise InputBuildError("SELECTION_SET_NOT_FOUND", str(selection_set_id))
    if sel["content_hash"] != selection_set_hash:
        raise InputBuildError("SELECTION_HASH_MISMATCH", str(selection_set_id))
    rep = conn.execute("SELECT *, report_mode::text AS mode FROM lfhe.reports WHERE id = %s", (sel["report_id"],)).fetchone()
    mode, cutoff = rep["mode"], rep["information_cutoff"]
    check_cutoff(mode, cutoff)
    candidates = []
    for it in conn.execute(
            """SELECT i.*, i.candidate_type::text AS ctype, i.section::text AS sec,
                      lfhe.report_candidate_eligible(i.candidate_type, i.object_id, %s, %s) AS eligible,
                      lfhe.p5_candidate_pins(i.candidate_type, i.object_id) AS pins
               FROM lfhe.report_selection_set_items i WHERE i.selection_set_id = %s
               ORDER BY i.section, i.priority, i.candidate_id""", (mode, cutoff, sel["id"])).fetchall():
        if not it["eligible"] or conn.execute("SELECT lfhe.report_object_hash(%s::lfhe.report_candidate_type, %s) AS h",
                                              (it["ctype"], it["object_id"])).fetchone()["h"] != it["object_hash"]:
            raise InputBuildError("CANDIDATE_NOT_ELIGIBLE", f'{it["ctype"]}:{it["object_id"]}')
        pins = it["pins"]
        av = (pins.get("assessment_version") or {}).get("id")
        conf = conn.execute("SELECT lfhe.p5_final_confidence(%s)::text AS c", (av,)).fetchone()["c"] if av else None
        c = {"candidate_id": str(it["candidate_id"]), "candidate_type": it["ctype"], "section": it["sec"],
             "priority": it["priority"], "pins": pins, "final_analytic_confidence": conf,
             "statements": _statements(conn, it["ctype"], str(it["object_id"]))}
        if it["ctype"] == "INDICATOR_VERSION":
            iv = conn.execute("SELECT content FROM lfhe.indicator_versions WHERE id = %s", (it["object_id"],)).fetchone()
            c["indicator"] = {"indicator_text": iv["content"]["indicator_text"],
                              "observable_condition": iv["content"]["observable_condition"]}
        elif it["ctype"] == "TREND_VERSION":
            tv = conn.execute("SELECT content FROM lfhe.trend_versions WHERE id = %s", (it["object_id"],)).fetchone()["content"]
            c["trend"] = {k: tv[k] for k in ("title", "direction", "velocity", "uncertainty")}
            c["final_analytic_confidences"] = sorted({conn.execute("SELECT lfhe.p5_final_confidence(%s)::text AS c",
                                                                    (s["assessment_version_id"],)).fetchone()["c"]
                                                      for s in c["statements"]})
        if not c["statements"]:
            raise InputBuildError("CANDIDATE_HAS_NO_APPROVED_STATEMENTS", c["candidate_id"])
        candidates.append(c)
    targets = [{"section": r["section"], "target_min": r["target_min"], "target_max": r["target_max"], "hard_max": r["hard_max"]}
               for r in conn.execute("SELECT section::text AS section, target_min, target_max, hard_max "
                                     "FROM lfhe.report_section_targets ORDER BY section")]
    terms = [r["code"] for r in conn.execute("SELECT code FROM lfhe.likelihood_terms ORDER BY rank")]
    item = EnvelopeItem("report_selection_set", str(sel["id"]), {
        "selection_set_id": str(sel["id"]), "content_hash": sel["content_hash"], "candidates": candidates})
    task = {"report_mode": mode, "information_cutoff": cutoff.isoformat(), "report_code": rep["code"],
            "cycle_label": rep["cycle_label"], "selection_set_id": str(sel["id"]), "selection_set_hash": sel["content_hash"],
            "section_targets": targets, "likelihood_terms": terms, "editorial_transforms": EDITORIAL_TRANSFORMS}
    return AnalysisInputs(task, [item], [])
