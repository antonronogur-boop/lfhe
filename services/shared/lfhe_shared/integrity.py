"""Independent integrity checks over stored snapshots (CG1-02)."""
from __future__ import annotations

from .canonical_json import canonical_sha256


def verify_snapshot_states(conn, source_id=None) -> list[str]:
    """Recompute source_state_sha256 = canonical_sha256(source_state) for every
    snapshot that carries a state (rows created before CG1-02 have none)."""
    rows = conn.execute(
        "SELECT s.id, s.source_state, s.source_state_sha256 FROM lfhe.article_snapshots s "
        "JOIN lfhe.articles a ON a.id = s.article_id "
        "WHERE s.source_state IS NOT NULL AND (%s::uuid IS NULL OR a.source_id = %s::uuid)",
        (source_id, source_id)).fetchall()
    return [f"snapshot {r['id']}: source_state hash mismatch" for r in rows
            if canonical_sha256(r["source_state"]) != r["source_state_sha256"]]
