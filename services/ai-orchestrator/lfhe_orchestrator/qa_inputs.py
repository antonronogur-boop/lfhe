"""Deterministic M10-S input building (Phase 6 Addendum §9, §27, §28).

* M10-S sees exactly one report version, bound by (report_version_id, report_version_hash);
  a mismatching hash or an unknown version fails closed before any model is invoked.
* Inputs: the canonical report content of that version (every report statement with its
  report_item_statement_id and cited source ids), each cited APPROVED assessment statement
  (type, epistemic category, text, attribution, likelihood, final_analytic_confidence, supporting /
  contradicting evidence), and each evidence claim (normalised text, ORIGINAL-LANGUAGE text and exact
  original-language span, attribution, source statement status, as-of status, independence group).
* Context: event relationships among the reported events, approved reference context versions that
  the cited assessments legitimately used, the deterministic (M10-D) findings in the task.
* Only database state is read; no file, no network, no benchmark evaluation material. The same
  state yields the same envelope.
"""
from __future__ import annotations

from lfhe_shared.envelopes import EnvelopeItem

from .assessment_inputs import AnalysisInputs, check_cutoff
from .claim_inputs import InputBuildError

M10_MODULE = "M10_QA_AUDITOR"
S_CHECKS = ["QA-01", "QA-05", "QA-06", "QA-07", "QA-09", "QA-13", "QA-17", "S18", "S19", "S20"]


def _s(v):
    return None if v is None else str(v)


def _report_item(conn, v) -> EnvelopeItem:
    canon = v["canonical_json"]
    rows = {(r["item_local_id"], r["report_statement_local_id"]): str(r["id"]) for r in conn.execute(
        """SELECT st.id, st.report_statement_local_id, i.item_local_id FROM lfhe.report_item_statements st
           JOIN lfhe.report_items i ON i.id = st.report_item_id WHERE i.report_version_id = %s""", (v["id"],))}
    items = []
    for sec in canon["sections"]:
        for it in sec["items"]:
            stmts = []
            for st in it["statements"]:
                key = (it["item_local_id"], st["report_statement_local_id"])
                if key not in rows:
                    raise InputBuildError("REPORT_STATEMENT_ROW_MISSING", "/".join(key))
                stmts.append({"report_item_statement_id": rows[key], **{k: st[k] for k in (
                    "report_statement_local_id", "statement_role", "text", "sources", "final_analytic_confidence",
                    "likelihood_term", "editorial_transform", "contested")}})
            items.append({"section": sec["section"], "item_local_id": it["item_local_id"],
                          "source_candidate_id": it["source_candidate_id"], "pins": it["pins"],
                          "final_analytic_confidence": it.get("final_analytic_confidence"), "statements": stmts})
    return EnvelopeItem("report_version", str(v["id"]), {
        "report_version_id": str(v["id"]), "report_version_hash": v["report_version_hash"], "report": canon["report"],
        "version_no": canon["version_no"], "items": items, "coverage": canon.get("coverage"),
        "human_removals": canon.get("human_removals") or [], "length_status": canon.get("length_status")})


def build_m10s_inputs(conn, report_version_id: str, report_version_hash: str, deterministic_qa_run_id: str) -> AnalysisInputs:
    v = conn.execute("SELECT *, report_mode::text AS mode FROM lfhe.report_versions WHERE id = %s",
                     (str(report_version_id),)).fetchone()
    if v is None:
        raise InputBuildError("REPORT_VERSION_NOT_FOUND", str(report_version_id))
    if v["report_version_hash"] != report_version_hash:
        raise InputBuildError("VERSION_HASH_MISMATCH", str(report_version_id))
    d = conn.execute("SELECT * FROM lfhe.qa_runs WHERE id = %s AND kind = 'D'", (str(deterministic_qa_run_id),)).fetchone()
    if d is None or str(d["report_version_id"]) != str(v["id"]) or d["report_version_hash"] != report_version_hash:
        raise InputBuildError("DETERMINISTIC_RUN_NOT_FOR_VERSION", str(deterministic_qa_run_id))
    mode, cutoff = v["mode"], v["information_cutoff"]
    check_cutoff(mode, cutoff)
    inputs = [_report_item(conn, v)]
    stmts = conn.execute(
        """SELECT DISTINCT a.id, a.assessment_version_id, a.statement_local_id, a.statement_type::text AS stype,
                  a.epistemic_category::text AS cat, a.statement_text, a.attribution_required, a.attribution_text,
                  a.likelihood_term, lfhe.p5_final_confidence(a.assessment_version_id)::text AS conf
           FROM lfhe.report_statement_sources x JOIN lfhe.assessment_statements a ON a.id = x.assessment_statement_id
           JOIN lfhe.report_item_statements st ON st.id = x.report_item_statement_id
           JOIN lfhe.report_items i ON i.id = st.report_item_id
           WHERE i.report_version_id = %s ORDER BY a.id""", (v["id"],)).fetchall()
    claim_ids: set[str] = set()
    rc_ids: set[str] = set()
    for a in stmts:
        ev = conn.execute("""SELECT object_type, object_id::text AS oid, role::text AS role FROM lfhe.assessment_statement_evidence
                             WHERE statement_id = %s ORDER BY object_type, object_id, role""", (a["id"],)).fetchall()
        for e in ev:
            if e["object_type"] == "claim":
                claim_ids.add(e["oid"])
            elif e["object_type"] == "reference_context_version":
                rc_ids.add(e["oid"])
        inputs.append(EnvelopeItem("assessment_statement", str(a["id"]), {
            "assessment_statement_id": str(a["id"]), "assessment_version_id": str(a["assessment_version_id"]),
            "statement_local_id": a["statement_local_id"], "statement_type": a["stype"], "epistemic_category": a["cat"],
            "text": a["statement_text"], "attribution_required": a["attribution_required"],
            "attribution_text": a["attribution_text"], "likelihood_term": a["likelihood_term"],
            "final_analytic_confidence": a["conf"],
            "supporting_evidence": [{"object_type": e["object_type"], "object_id": e["oid"]} for e in ev if e["role"] == "SUPPORTS"],
            "contradicting_evidence": [{"object_type": e["object_type"], "object_id": e["oid"]} for e in ev
                                       if e["role"] == "CONTRADICTS"]}))
    for c in conn.execute(
            """SELECT c.*, st.effective_claim_text_normalised, st.effective_attribution,
                      c.source_statement_status::text AS sss, s.claim_status::text AS status_asof,
                      g.lineage_known, g.independence_group,
                      lfhe.claim_cutoff_eligible(c.id, %(mode)s, %(cutoff)s) AS eligible
               FROM lfhe.claims c JOIN lfhe.claim_state st ON st.claim_id = c.id
               LEFT JOIN LATERAL lfhe.claim_status_asof(c.id, %(mode)s, %(cutoff)s) s ON true
               LEFT JOIN LATERAL lfhe.claim_independence_group_asof(c.id, %(mode)s, %(cutoff)s) g ON true
               WHERE c.id = ANY(%(ids)s::uuid[]) ORDER BY c.id""",
            {"ids": sorted(claim_ids), "mode": mode, "cutoff": cutoff}).fetchall():
        inputs.append(EnvelopeItem("claim", str(c["id"]), {
            "claim_id": str(c["id"]), "source_id": str(c["source_id"]), "article_snapshot_id": str(c["article_snapshot_id"]),
            "claim_text_normalised": c["effective_claim_text_normalised"], "claim_text_original": c["claim_text_original"],
            "evidence_span_original": {"language": c["language_original"], "exact_text": c["span_exact_text"],
                                       "start": c["span_start"], "end": c["span_end"]},
            "attribution": c["effective_attribution"], "source_statement_status": c["sss"],
            "claim_status_asof": c["status_asof"] or "UNVERIFIED", "cutoff_eligible": c["eligible"],
            "independence": {"lineage_known": c["lineage_known"], "independence_group": _s(c["independence_group"])}}))
    events = [r["event_id"] for r in conn.execute(
        """SELECT DISTINCT ev.event_id::text AS event_id FROM lfhe.report_items i JOIN lfhe.event_versions ev ON ev.id = i.pinned_event_version_id
           WHERE i.report_version_id = %s ORDER BY 1""", (v["id"],))]
    rels = [{"relationship_type": r["t"], "from_event_id": str(r["from_event_id"]), "to_event_id": str(r["to_event_id"])}
            for r in conn.execute(
                """SELECT relationship_type::text AS t, from_event_id, to_event_id FROM lfhe.event_relationships
                   WHERE from_event_id = ANY(%(e)s::uuid[]) OR to_event_id = ANY(%(e)s::uuid[])
                   ORDER BY from_event_id, to_event_id, relationship_type""", {"e": events})]
    context = [EnvelopeItem("event_relationships", str(v["id"]), {"reported_event_ids": events, "relationships": rels})]
    for rc in conn.execute(
            """SELECT DISTINCT rcv.id, rcv.content FROM lfhe.reference_context_versions rcv
               WHERE rcv.id = ANY(%(ids)s::uuid[]) OR rcv.id IN (
                 SELECT arc.reference_context_version_id FROM lfhe.assessment_reference_contexts arc
                 WHERE arc.assessment_version_id = ANY(%(avs)s::uuid[])) ORDER BY rcv.id""",
            {"ids": sorted(rc_ids), "avs": sorted({str(a["assessment_version_id"]) for a in stmts})}).fetchall():
        context.append(EnvelopeItem("reference_context_version", str(rc["id"]), rc["content"]))
    findings = [{"check_id": f["check_id"], "status": f["status"], "severity": f["severity"], "finding_code": f["finding_code"],
                 "affected_statement_id": _s(f["affected_statement_id"]), "details": f["details"]}
                for f in conn.execute(
                    """SELECT check_id, status, severity::text AS severity, finding_code, affected_statement_id, details
                       FROM lfhe.qa_check_results WHERE qa_run_id = %s AND status <> 'PASS' ORDER BY finding_no""", (d["id"],))]
    codes = conn.execute("SELECT lfhe.p6_recommended_actions() AS a").fetchone()["a"]
    task = {"report_id": str(v["report_id"]), "report_version_id": str(v["id"]), "report_version_hash": report_version_hash,
            "report_mode": mode, "information_cutoff": cutoff.isoformat(), "deterministic_qa_run_id": str(d["id"]),
            "deterministic_findings": findings, "diagnostic_only": any(f["severity"] == "CRITICAL" for f in findings),
            "semantic_checks": S_CHECKS, "recommended_actions": list(codes)}
    return AnalysisInputs(task, inputs, context)
