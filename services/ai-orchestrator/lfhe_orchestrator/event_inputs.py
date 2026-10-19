"""Deterministic M04 / M05 input building (Phase 3 Addendum §8, §12, §13).

* Only cutoff-eligible claims enter an envelope (lfhe.claim_cutoff_eligible
  with the run's report_mode / information_cutoff); ineligible ones are
  reported, never silently used. Event time is never an eligibility criterion.
* Claims a human REJECTED or sent for reprocessing are not used.
* Minimum necessary context: M04 gets the claims, their articles and the
  validated lineage among them; M05 gets the new claims, a bounded set of
  candidate existing events and validated lineage.
* As-of discipline (CG3-01): lineage, independence groups and events enter an
  envelope only through their knowledge bound for (report_mode, cutoff) —
  lfhe.lineage_usable, lfhe.claim_independence_group_asof, lfhe.event_asof.
  An event is represented by its latest cutoff-eligible version with the
  state / structural outcome provable at the cutoff, never by a later head.
* The same database state yields the same envelope.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from lfhe_shared.envelopes import EnvelopeItem

from .claim_inputs import InputBuildError

M04_MODULE = "M04_LINEAGE"
M05_MODULE = "M05_EVENT_BUILDER"
RELATIONSHIP_TYPES = ("COMMON_ORIGINAL_SOURCE", "DERIVED_REPORTING")
MAX_CONTEXT_EVENTS = 20


@dataclass(frozen=True)
class AnalysisInputs:
    task: dict
    inputs: list[EnvelopeItem]
    context: list[EnvelopeItem]
    excluded_claims: dict = field(default_factory=dict)     # claim_id -> reason


def _iso(v):
    return v.isoformat() if v is not None else None


def _check_cutoff(report_mode: str, cutoff: datetime) -> None:
    if report_mode not in ("LIVE", "REPLAY"):
        raise InputBuildError("REPORT_MODE_INVALID", str(report_mode))
    if cutoff is None or cutoff.tzinfo is None:
        raise InputBuildError("CUTOFF_INVALID", "information_cutoff must be timezone-aware")


def _claims(conn, claim_ids, report_mode, cutoff):
    rows = conn.execute(
        """
        SELECT c.id, c.article_id, c.source_id, c.language_original, c.claim_text_original, c.span_exact_text,
               c.claim_type::text AS claim_type, c.source_statement_status::text AS source_statement_status,
               c.evidence_directness::text AS evidence_directness, c.event_date, c.location_mentions,
               st.effective_claim_text_normalised, st.effective_attribution, st.review_state, st.high_impact,
               st.high_impact_reasons,
               lfhe.claim_cutoff_eligible(c.id, %(mode)s, %(cutoff)s) AS eligible,
               (lfhe.claim_independence_group_asof(c.id, %(mode)s, %(cutoff)s)).independence_group AS independence_group,
               coalesce((SELECT jsonb_agg(m.mention_text_original ORDER BY m.mention_index)
                         FROM lfhe.entity_mentions m WHERE m.claim_id = c.id), '[]'::jsonb) AS mentions
        FROM lfhe.claims c JOIN lfhe.claim_state st ON st.claim_id = c.id
        WHERE c.id = ANY(%(ids)s::uuid[]) ORDER BY c.id
        """, {"ids": [str(i) for i in claim_ids], "mode": report_mode, "cutoff": cutoff}).fetchall()
    found = {str(r["id"]) for r in rows}
    missing = [str(i) for i in claim_ids if str(i) not in found]
    if missing:
        raise InputBuildError("CLAIM_NOT_FOUND", ", ".join(missing))
    usable, excluded = [], {}
    for r in rows:
        if not r["eligible"]:
            excluded[str(r["id"])] = "NOT_CUTOFF_ELIGIBLE"
        elif r["review_state"] in ("REJECTED", "REPROCESSING_REQUESTED"):
            excluded[str(r["id"])] = f"REVIEW_STATE_{r['review_state']}"
        else:
            usable.append(r)
    return usable, excluded


def _lineage_context(conn, claim_ids, report_mode, cutoff) -> list[EnvelopeItem]:
    rows = conn.execute(
        """SELECT l.id, l.child_claim_id, l.relationship_type::text AS relationship_type, l.parent_claim_id,
                  l.parent_article_id, o.name AS external_origin_name
           FROM lfhe.claim_lineage l LEFT JOIN lfhe.external_origins o ON o.id = l.external_origin_id
           WHERE (l.child_claim_id = ANY(%(ids)s::uuid[]) OR l.parent_claim_id = ANY(%(ids)s::uuid[]))
             -- not the current-state view: a retraction counts only if it is knowledge-bound to the cutoff
             AND lfhe.lineage_usable(l.id, %(mode)s, %(cutoff)s)
           ORDER BY l.id""",
        {"ids": [str(i) for i in claim_ids], "mode": report_mode, "cutoff": cutoff}).fetchall()
    return [EnvelopeItem("claim_lineage", str(r["id"]), {
        "child_claim_id": str(r["child_claim_id"]), "relationship_type": r["relationship_type"],
        "parent_claim_id": str(r["parent_claim_id"]) if r["parent_claim_id"] else None,
        "parent_article_id": str(r["parent_article_id"]) if r["parent_article_id"] else None,
        "external_origin_name": r["external_origin_name"]}) for r in rows]


def _claim_item(r, *, for_events: bool) -> EnvelopeItem:
    content = {
        "claim_id": str(r["id"]), "article_id": str(r["article_id"]), "source_id": str(r["source_id"]),
        "language_original": r["language_original"], "claim_text_original": r["claim_text_original"],
        "claim_text_normalised": r["effective_claim_text_normalised"], "attribution": r["effective_attribution"],
        "claim_type": r["claim_type"], "event_date": r["event_date"],
    }
    if for_events:
        content |= {"locations": r["location_mentions"], "entity_mentions": r["mentions"],
                    "independence_group": r["independence_group"]}
    else:
        content |= {"evidence_span_original": r["span_exact_text"], "source_statement_status": r["source_statement_status"],
                    "evidence_directness": r["evidence_directness"]}
    return EnvelopeItem("claim", str(r["id"]), content)


def build_m04_inputs(conn, claim_ids, *, report_mode: str, information_cutoff: datetime) -> AnalysisInputs:
    _check_cutoff(report_mode, information_cutoff)
    rows, excluded = _claims(conn, claim_ids, report_mode, information_cutoff)
    if len(rows) < 1:
        raise InputBuildError("NO_ELIGIBLE_CLAIMS", f"excluded: {excluded}")
    article_ids = sorted({str(r["article_id"]) for r in rows})
    arts = conn.execute(
        """SELECT a.id, a.canonical_url, a.source_id, s.name, s.canonical_domain, s.source_type::text AS source_type,
                  (SELECT sn.title_original FROM lfhe.article_snapshots sn WHERE sn.article_id = a.id
                   ORDER BY sn.snapshot_version DESC LIMIT 1) AS title,
                  (SELECT sn.publication_datetime FROM lfhe.article_snapshots sn WHERE sn.article_id = a.id
                   ORDER BY sn.snapshot_version DESC LIMIT 1) AS publication_datetime,
                  (SELECT sn.language FROM lfhe.article_snapshots sn WHERE sn.article_id = a.id
                   ORDER BY sn.snapshot_version DESC LIMIT 1) AS language
           FROM lfhe.articles a JOIN lfhe.sources s ON s.id = a.source_id WHERE a.id = ANY(%s::uuid[]) ORDER BY a.id""",
        (article_ids,)).fetchall()
    inputs = [_claim_item(r, for_events=False) for r in rows] + [
        EnvelopeItem("article", str(a["id"]), {
            "article_id": str(a["id"]), "source_id": str(a["source_id"]), "source_name": a["name"],
            "canonical_domain": a["canonical_domain"], "source_type": a["source_type"], "canonical_url": a["canonical_url"],
            "title": a["title"], "publication_datetime": _iso(a["publication_datetime"]), "language": a["language"]})
        for a in arts]
    task = {"report_mode": report_mode, "information_cutoff": information_cutoff.isoformat(),
            "relationship_types": list(RELATIONSHIP_TYPES),
            "high_impact_context": {str(r["id"]): {"high_impact": bool(r["high_impact"]),
                                                   "high_impact_reasons": list(r["high_impact_reasons"] or [])}
                                    for r in rows}}
    return AnalysisInputs(task, inputs, _lineage_context(conn, [r["id"] for r in rows], report_mode, information_cutoff),
                          excluded)


def candidate_events(conn, rows, report_mode, cutoff, limit=MAX_CONTEXT_EVENTS) -> list[EnvelopeItem]:
    """Events open AS OF the cutoff whose as-of version shares an event type, a
    location or an entity mention with the new claims (deterministic, newest
    as-of version first, bounded). Fields, membership and state come from the
    as-of representation (lfhe.event_asof); later versions never leak."""
    types = sorted({r["claim_type"] for r in rows})
    locations = sorted({l for r in rows for l in (r["location_mentions"] or [])})
    mentions = sorted({m for r in rows for m in (r["mentions"] or [])})
    match = """(v.event_type::text = ANY(%(types)s) OR v.locations && %(locs)s::text[]
               OR EXISTS (SELECT 1 FROM lfhe.event_claims ec JOIN lfhe.entity_mentions m ON m.claim_id = ec.claim_id
                          WHERE ec.event_version_id = v.id AND m.mention_normalised = ANY(
                            SELECT lfhe.normalise_entity_name(x) FROM unnest(%(mentions)s::text[]) x)))"""
    asof = conn.execute(
        f"""
        WITH pre AS (            -- cheap superset: some version of the event matches
          SELECT DISTINCT v.event_id FROM lfhe.event_versions v WHERE {match}
        )
        SELECT a.event_id, a.version_id, a.state::text AS state, v.version_no, v.content_hash, v.title, v.description,
               v.event_type::text AS event_type, v.event_date_start, v.event_date_end,
               v.event_date_confidence::text AS event_date_confidence, v.locations, v.created_at
        FROM pre CROSS JOIN LATERAL lfhe.event_asof(pre.event_id, %(mode)s, %(cutoff)s) a
        JOIN lfhe.event_versions v ON v.id = a.version_id
        WHERE a.is_open AND {match}
        ORDER BY v.created_at DESC, a.event_id LIMIT %(limit)s
        """, {"types": types, "locs": locations, "mentions": mentions, "limit": limit,
              "mode": report_mode, "cutoff": cutoff}).fetchall()
    items = []
    for h in sorted(asof, key=lambda x: str(x["event_id"])):
        claims = conn.execute(
            """SELECT ec.claim_id, ec.role::text AS role, st.effective_claim_text_normalised, c.event_date,
                      lfhe.claim_cutoff_eligible(c.id, %s, %s) AS eligible
               FROM lfhe.event_claims ec JOIN lfhe.claims c ON c.id = ec.claim_id
               JOIN lfhe.claim_state st ON st.claim_id = c.id
               WHERE ec.event_version_id = %s ORDER BY ec.claim_id""",
            (report_mode, cutoff, h["version_id"])).fetchall()
        if not claims or not all(c["eligible"] for c in claims):
            continue        # defensive: an as-of version is eligible by construction
        items.append(EnvelopeItem("event_version", str(h["version_id"]), {
            "event_id": str(h["event_id"]), "version_id": str(h["version_id"]), "version_no": h["version_no"],
            "content_hash": h["content_hash"], "state": h["state"], "title": h["title"],
            "description": h["description"], "event_type": h["event_type"], "event_date_start": h["event_date_start"],
            "event_date_end": h["event_date_end"], "event_date_confidence": h["event_date_confidence"],
            "locations": list(h["locations"] or []),
            "claims": [{"claim_id": str(c["claim_id"]), "role": c["role"],
                        "claim_text_normalised": c["effective_claim_text_normalised"], "event_date": c["event_date"]}
                       for c in claims]}))
    return items


def build_m05_inputs(conn, claim_ids, *, report_mode: str, information_cutoff: datetime) -> AnalysisInputs:
    _check_cutoff(report_mode, information_cutoff)
    rows, excluded = _claims(conn, claim_ids, report_mode, information_cutoff)
    if not rows:
        raise InputBuildError("NO_ELIGIBLE_CLAIMS", f"excluded: {excluded}")
    context = candidate_events(conn, rows, report_mode, information_cutoff)
    context += _lineage_context(conn, [r["id"] for r in rows], report_mode, information_cutoff)
    task = {"report_mode": report_mode, "information_cutoff": information_cutoff.isoformat()}
    return AnalysisInputs(task, [_claim_item(r, for_events=True) for r in rows], context, excluded)
