"""Phase 4 test support: synthetic OSINT-style claims with stated availability, human
baselines / reference contexts, events. All content is invented ('Northland'); nothing
here is Gold Standard material."""
from __future__ import annotations

import json
from datetime import datetime

from lineage_support import grounded_claim, head

PRE = "2026-01-10T08:00:00+00:00"          # evidence available before the cutoff
KNOW = "2026-02-01T00:00:00+00:00"         # knowledge_as_of before the cutoff
CUT = "2026-03-01T00:00:00+00:00"          # REPLAY information cutoff
POST = "2026-05-10T08:00:00+00:00"         # evidence available after the cutoff
LATER = "2026-06-01T00:00:00+00:00"        # a later cutoff
FAR = "2100-01-01T00:00:00+00:00"          # LIVE "now"
CUT_DT = datetime.fromisoformat(CUT)


def pclaim(pg, text, exact, when=PRE, **kw):
    kw.setdefault("claim_type", "DEPLOYMENT")
    return grounded_claim(pg, text, exact, available_at=when, **kw)


def ref(obj_type, obj_id):
    return {"object_type": obj_type, "object_id": str(obj_id)}


def create_rc(pg, user, code, claims, *, as_of=KNOW, text="Northland operates a small tanker fleet.", reason="curated"):
    with pg.as_user(user) as h:
        return str(h.execute("SELECT lfhe.create_reference_context_version(%s::jsonb, %s) AS v", (json.dumps({
            "code": code, "context_type": "CAPABILITY_BASELINE", "title": f"{code} context", "text": text,
            "knowledge_as_of": as_of, "provenance_refs": [ref("claim", c["claim_id"]) for c in claims]}),
            f"analyst {reason}")).fetchone()["v"])


def create_baseline(pg, user, code, components, *, as_of=KNOW, reason="prior state"):
    """components: [(text, [(type, id), ...]), ...]"""
    with pg.as_user(user) as h:
        return str(h.execute("SELECT lfhe.create_baseline_version(%s::jsonb, %s) AS v", (json.dumps({
            "code": code, "title": f"{code} baseline", "scope": "Northland air-domain posture",
            "knowledge_as_of": as_of,
            "components": [{"text": t, "evidence": [ref(a, b) for a, b in ev]} for t, ev in components]}),
            f"analyst {reason}")).fetchone()["v"])


def version_hash(pg, table, version_id):
    with pg.admin() as x:
        return x.execute(f"SELECT content_hash FROM lfhe.{table} WHERE id=%s", (version_id,)).fetchone()["content_hash"]


def approve(pg, user, kind, version_id, decision="APPROVE"):
    table = {"baseline": "baseline_versions", "rc": "reference_context_versions"}[kind]
    fn = {"baseline": "decide_baseline_version", "rc": "decide_reference_context_version"}[kind]
    with pg.as_user(user) as h:
        h.execute(f"SELECT lfhe.{fn}(%s, %s, %s, 'analyst checked the evidence')",
                  (version_id, version_hash(pg, table, version_id), decision))


def worker_value(pg, sql, *args):
    with pg.worker() as c:
        return c.execute(sql, args).fetchone()["r"]


def human_event(pg, user, claims, *, title="Northland deployment", etype="DEPLOYMENT", locations=(), roles=None):
    with pg.as_user(user) as h:
        return str(h.execute("SELECT lfhe.create_event(%s::jsonb, 'analyst creates event') AS e", (json.dumps({
            "title": title, "description": "Synthetic Northland event.", "event_type": etype, "locations": list(locations),
            "claims": [{"claim_id": c["claim_id"], "role": (roles or {}).get(c["claim_id"], "SUPPORTS")} for c in claims]}),)
        ).fetchone()["e"])


__all__ = ["CUT", "CUT_DT", "FAR", "KNOW", "LATER", "POST", "PRE", "approve", "create_baseline", "create_rc", "head",
           "human_event", "pclaim", "ref", "version_hash", "worker_value"]
