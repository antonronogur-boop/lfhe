"""Deterministic M06 / M07 / M08 input building (Phase 4 Addendum §3, §19, §20).

* The primary subject is an exact event_version (id + content_hash) that is
  eligible for the run's (report_mode, information_cutoff) under the CLOSED
  Phase 3 as-of rules; a mismatching hash or an ineligible version fails closed.
* Claims come from that event version (eligible by construction); their status
  is the as-of status (lfhe.claim_status_asof), lineage / independence the as-of
  summary (lfhe.independence_summary_asof).
* Baselines and reference contexts enter only through their as-of selection
  (lfhe.baseline_asof / lfhe.reference_context_asof): approved, knowledge_as_of
  <= cutoff, every factual component eligible. Missing baseline → BASELINE_UNAVAILABLE.
* Eligibility is decided here, before the model is invoked — never by a model.
* The same database state yields the same envelope.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from lfhe_shared.envelopes import EnvelopeItem

from .claim_inputs import InputBuildError

M06_MODULE = "M06_RELEVANCE"
M07_MODULE = "M07_INTELLIGENCE_ASSESSOR"
M08_MODULE = "M08_CHALLENGER"
HU_NATO_DIMENSIONS = (
    "CAPABILITY", "READINESS", "FORCE_PROTECTION", "AIR_DEFENCE", "DETERRENCE", "INTEROPERABILITY",
    "PROCUREMENT_CAPABILITY_DEVELOPMENT", "DOCTRINE_ADAPTATION", "INDUSTRIAL_CAPACITY", "SENSOR_TO_DECISION",
    "UAS_C_UAS", "EASTERN_FLANK_POSTURE", "WARNING_MONITORING")


@dataclass(frozen=True)
class AnalysisInputs:
    task: dict
    inputs: list[EnvelopeItem]
    context: list[EnvelopeItem]


def _iso(v):
    return v.isoformat() if v is not None else None


def check_cutoff(report_mode: str, cutoff: datetime) -> None:
    if report_mode not in ("LIVE", "REPLAY"):
        raise InputBuildError("REPORT_MODE_INVALID", str(report_mode))
    if cutoff is None or cutoff.tzinfo is None:
        raise InputBuildError("CUTOFF_INVALID", "information_cutoff must be timezone-aware")


def event_version_item(conn, version_id: str, version_hash: str, mode: str, cutoff: datetime) -> tuple[EnvelopeItem, list[dict]]:
    v = conn.execute(
        """SELECT v.*, v.event_type::text AS etype, v.event_date_confidence::text AS edc,
                  lfhe.event_version_eligible(v.id, %s, %s) AS eligible
           FROM lfhe.event_versions v WHERE v.id = %s""", (mode, cutoff, str(version_id))).fetchone()
    if v is None:
        raise InputBuildError("EVENT_VERSION_NOT_FOUND", str(version_id))
    if v["content_hash"] != version_hash:
        raise InputBuildError("EVENT_VERSION_HASH_MISMATCH", str(version_id))
    if not v["eligible"]:
        raise InputBuildError("EVENT_VERSION_NOT_ELIGIBLE", f"{version_id} is not eligible for {mode} {cutoff.isoformat()}")
    asof = conn.execute("SELECT * FROM lfhe.event_asof(%s, %s, %s)", (v["event_id"], mode, cutoff)).fetchone()
    claims = conn.execute(
        """SELECT ec.claim_id, ec.role::text AS role, c.claim_text_original, c.span_exact_text, c.language_original,
                  c.claim_type::text AS claim_type, c.source_statement_status::text AS source_statement_status,
                  c.event_date, c.location_mentions, st.effective_claim_text_normalised, st.effective_attribution,
                  st.high_impact, s.claim_status::text AS asof_status, s.basis AS asof_status_basis,
                  (lfhe.claim_independence_group_asof(c.id, %s, %s)).independence_group AS independence_group
           FROM lfhe.event_claims ec JOIN lfhe.claims c ON c.id = ec.claim_id
           JOIN lfhe.claim_state st ON st.claim_id = c.id
           LEFT JOIN LATERAL lfhe.claim_status_asof(c.id, %s, %s) s ON true
           WHERE ec.event_version_id = %s ORDER BY ec.claim_id""",
        (mode, cutoff, mode, cutoff, str(version_id))).fetchall()
    claim_content = [{
        "claim_id": str(c["claim_id"]), "role": c["role"], "claim_text_original": c["claim_text_original"],
        "claim_text_normalised": c["effective_claim_text_normalised"], "attribution": c["effective_attribution"],
        "evidence_span_original": c["span_exact_text"], "language_original": c["language_original"],
        "claim_type": c["claim_type"], "source_statement_status": c["source_statement_status"],
        "claim_status": c["asof_status"] or "UNVERIFIED", "high_impact": bool(c["high_impact"]),
        "event_date": c["event_date"], "locations": c["location_mentions"],
        "independence_group": c["independence_group"]} for c in claims]
    item = EnvelopeItem("event_version", str(v["id"]), {
        "event_id": str(v["event_id"]), "event_version_id": str(v["id"]), "version_no": v["version_no"],
        "content_hash": v["content_hash"], "title": v["title"], "description": v["description"],
        "event_type": v["etype"], "event_date_start": v["event_date_start"], "event_date_end": v["event_date_end"],
        "event_date_confidence": v["edc"], "locations": list(v["locations"] or []),
        "state": asof["state"] if asof else None, "claims": claim_content})
    return item, claim_content


def baseline_item(conn, baseline_code: str | None, mode: str, cutoff: datetime) -> EnvelopeItem | None:
    if not baseline_code:
        return None
    row = conn.execute(
        """SELECT v.* FROM lfhe.baselines b JOIN lfhe.baseline_versions v ON v.id = lfhe.baseline_asof(b.id, %s, %s)
           WHERE b.code = %s""", (mode, cutoff, baseline_code)).fetchone()
    if row is None:
        return None
    return EnvelopeItem("baseline_version", str(row["id"]), {
        "baseline_version_id": str(row["id"]), "baseline_code": baseline_code, "version_no": row["version_no"],
        "content_hash": row["content_hash"], "knowledge_as_of": _iso(row["knowledge_as_of"]),
        "title": row["content"]["title"], "components": row["content"]["components"]})


def reference_context_items(conn, codes, mode: str, cutoff: datetime) -> list[EnvelopeItem]:
    items = []
    for code in sorted(set(codes or ())):
        row = conn.execute(
            """SELECT v.*, r.code, r.context_type FROM lfhe.reference_contexts r
               JOIN lfhe.reference_context_versions v ON v.id = lfhe.reference_context_asof(r.id, %s, %s)
               WHERE r.code = %s""", (mode, cutoff, code)).fetchone()
        if row is None:
            continue                  # not approved / not knowable at the cutoff: not supplied
        items.append(EnvelopeItem("reference_context_version", str(row["id"]), {
            "reference_context_version_id": str(row["id"]), "reference_context_code": row["code"],
            "context_type": row["context_type"], "version_no": row["version_no"], "content_hash": row["content_hash"],
            "knowledge_as_of": _iso(row["knowledge_as_of"]), "title": row["content"]["title"],
            "text": row["content"]["text"], "provenance_refs": row["content"]["provenance_refs"]}))
    return items


def pir_definitions(conn) -> list[dict]:
    return [{"id": r["id"], "label": r["label"], "definition": r["description"]} for r in conn.execute(
        "SELECT id, label, description FROM lfhe.taxonomy_items WHERE taxonomy_type = 'PIR' ORDER BY id")]


def build_m06_inputs(conn, event_version_id: str, event_version_hash: str, *, report_mode: str,
                     information_cutoff: datetime, baseline_code: str | None = None) -> AnalysisInputs:
    check_cutoff(report_mode, information_cutoff)
    ev, _ = event_version_item(conn, event_version_id, event_version_hash, report_mode, information_cutoff)
    bl = baseline_item(conn, baseline_code, report_mode, information_cutoff)
    task = {"report_mode": report_mode, "information_cutoff": information_cutoff.isoformat(),
            "event_version_id": str(event_version_id), "event_version_hash": event_version_hash,
            "baseline_version_id": bl.object_id if bl else None,
            "baseline_status": "BASELINE_AVAILABLE" if bl else "BASELINE_UNAVAILABLE",
            "previous_assessment_version_id": None,
            "pir_definitions": pir_definitions(conn), "hu_nato_dimensions": list(HU_NATO_DIMENSIONS)}
    return AnalysisInputs(task, [ev], [bl] if bl else [])
