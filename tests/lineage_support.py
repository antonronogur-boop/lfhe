"""Phase 3 test support: grounded claims from several synthetic outlets, M04/M05 runs."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from psycopg.types.json import Jsonb

from claims_support import candidate, extraction_run, ingest, make_model_run, make_text_snapshot

FUTURE = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
PAST = "2020-01-01T00:00:00+00:00"


def grounded_claim(pg, text: str, exact: str, *, language: str = "en", **overrides) -> dict:
    """One outlet (source/article/snapshot) with one persisted claim."""
    snap = make_text_snapshot(pg, text, language=language)
    run = extraction_run(pg, snap)
    out = ingest(pg, snap, run, [candidate(text, exact, language=language, **overrides)])
    [cid] = out["claim_ids"]
    with pg.admin() as c:
        row = c.execute("SELECT * FROM lfhe.claims WHERE id=%s", (cid,)).fetchone()
    return {**snap, "claim_id": str(cid), "claim_hash": row["claim_hash"]}


def lineage_run(pg, claims: list[dict], *, mode="LIVE", cutoff=FUTURE, extra_inputs=(), status="SUCCEEDED") -> str:
    inputs = [("claim", c["claim_id"]) for c in claims] + [("article", c["article_id"]) for c in claims]
    inputs += list(extra_inputs)
    return make_model_run(pg, "M04_LINEAGE", list(dict.fromkeys(inputs)),
                          task_parameters={"report_mode": mode, "information_cutoff": cutoff}, status=status)


def ingest_lineage(pg, run: str, relationships=(), recommendations=(), **extra) -> dict:
    payload = {"model_run_id": run, "output_status": "SUCCESS", "human_review_required": False, "warnings": [],
               "claim_relationships": list(relationships), "corroboration_recommendations": list(recommendations),
               **extra}
    with pg.worker() as c:
        return c.execute("SELECT lfhe.ingest_lineage(%s::jsonb) AS r", (Jsonb(payload),)).fetchone()["r"]


def rel(child, rtype="COMMON_ORIGINAL_SOURCE", *, parent_claim=None, parent_article=None, origin=None, url=None,
        confidence="MODERATE", explanation="synthetic"):
    return {"child_claim_id": child["claim_id"], "relationship_type": rtype,
            "parent_claim_id": parent_claim["claim_id"] if parent_claim else None,
            "parent_article_id": parent_article, "external_origin_name": origin, "external_origin_url": url,
            "confidence": confidence, "explanation": explanation}


def summary(pg, claims: list[dict]) -> dict:
    with pg.worker() as c:
        return c.execute("SELECT lfhe.independence_summary(%s::uuid[]) AS s",
                         ([x["claim_id"] for x in claims],)).fetchone()["s"]


def proposals(pg, run):
    with pg.admin() as c:
        return c.execute("SELECT * FROM lfhe.lineage_proposals WHERE model_run_id=%s ORDER BY proposal_index",
                         (run,)).fetchall()


# ---------------------------------------------------------------------------
# Events (M05)
# ---------------------------------------------------------------------------
def head(pg, event_id) -> dict:
    with pg.admin() as c:
        return c.execute("SELECT * FROM lfhe.event_heads WHERE event_id=%s", (str(event_id),)).fetchone()


def event_run(pg, claims: list[dict], context_events=(), *, mode="LIVE", cutoff=FUTURE, status="SUCCEEDED") -> str:
    ctx = [("event_version", str(head(pg, e)["head_version_id"])) for e in context_events]
    return make_model_run(pg, "M05_EVENT_BUILDER", [("claim", c["claim_id"]) for c in claims], context=ctx,
                          task_parameters={"report_mode": mode, "information_cutoff": cutoff}, status=status)


def candidate_event(claims, *, title="Synthetic event", description="Synthetic description of the development.",
                    event_type="DELIVERY", roles=None, **fields) -> dict:
    roles = roles or {}
    return {"title": title, "description": description, "event_type": event_type, "event_date_start": None,
            "event_date_end": None, "event_date_confidence": "UNKNOWN", "locations": [],
            "claims": [{"claim_id": c["claim_id"], "role": roles.get(c["claim_id"], "SUPPORTS")} for c in claims],
            **fields}


def proposal(kind, *, target=None, target_version=None, related=(), claims=(), event_candidate=None,
             reason="synthetic", confidence="MODERATE") -> dict:
    return {"proposal": kind, "target_event_id": str(target) if target else None,
            "target_event_version_id": str(target_version) if target_version else None,
            "related_event_ids": [str(r) for r in related], "claim_ids": [c["claim_id"] for c in claims],
            "event_candidate": event_candidate, "reason": reason, "confidence": confidence}


def ingest_events(pg, run: str, proposals_: list[dict], **extra) -> dict:
    payload = {"model_run_id": run, "output_status": "SUCCESS", "human_review_required": False, "warnings": [],
               "proposals": proposals_, **extra}
    with pg.worker() as c:
        return c.execute("SELECT lfhe.ingest_event_proposals(%s::jsonb) AS r", (Jsonb(payload),)).fetchone()["r"]


def version_claims(pg, version_id) -> dict:
    with pg.admin() as c:
        return {str(r["claim_id"]): r["role"] for r in c.execute(
            "SELECT claim_id, role FROM lfhe.event_claims WHERE event_version_id=%s", (str(version_id),))}
