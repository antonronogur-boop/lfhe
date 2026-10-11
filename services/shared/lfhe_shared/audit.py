"""Independent audit-chain verification and chain-head export (G-14).

The verifier does NOT trust the database's own hash computation: it fetches
each entry's fields (as their canonical text forms) and recomputes the SHA-256
chain in Python using the documented canonical serialisation 'v1' (mirrors
``lfhe.audit_canonical_v1``).

Chain heads exported to external storage let an auditor later prove that the
log has not been rewritten up to that point, even by a database owner.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import psycopg

GENESIS = "0" * 64

_FETCH = """
SELECT seq,
       to_char(occurred_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS occurred_at,
       actor_type::text AS actor_type,
       coalesce(actor_user_id::text, '') AS actor_user_id,
       actor_db_role, event_type, object_type, object_id,
       coalesce(previous_state::text, 'null') AS previous_state,
       coalesce(new_state::text, 'null') AS new_state,
       metadata::text AS metadata,
       previous_entry_hash, entry_hash
FROM lfhe.audit_log
WHERE seq > %s
ORDER BY seq
"""


def canonical_v1(row: dict, previous_hash: str) -> str:
    return "\n".join([
        "v1", str(row["seq"]), row["occurred_at"], row["actor_type"], row["actor_user_id"],
        row["actor_db_role"], row["event_type"], row["object_type"], row["object_id"],
        row["previous_state"], row["new_state"], row["metadata"], previous_hash,
    ])


@dataclass(frozen=True)
class ChainVerification:
    ok: bool
    entries_checked: int
    head_seq: int
    head_hash: str
    first_bad_seq: int | None = None
    reason: str | None = None


def verify_chain(conn: psycopg.Connection, *, from_seq: int = 0,
                 from_hash: str = GENESIS) -> ChainVerification:
    """Recompute the hash chain from (from_seq, from_hash) to the head."""
    expected_seq = from_seq + 1
    prev_hash = from_hash
    checked = 0
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(_FETCH, (from_seq,))
        for row in cur:
            if row["seq"] != expected_seq:
                return ChainVerification(False, checked, expected_seq - 1, prev_hash,
                                         row["seq"], f"gap: expected seq {expected_seq}")
            if row["previous_entry_hash"] != prev_hash:
                return ChainVerification(False, checked, expected_seq - 1, prev_hash,
                                         row["seq"], "previous_entry_hash does not link")
            recomputed = hashlib.sha256(canonical_v1(row, prev_hash).encode("utf-8")).hexdigest()
            if recomputed != row["entry_hash"]:
                return ChainVerification(False, checked, expected_seq - 1, prev_hash,
                                         row["seq"], "entry content does not match entry_hash")
            prev_hash = row["entry_hash"]
            expected_seq += 1
            checked += 1
    return ChainVerification(True, checked, expected_seq - 1, prev_hash)


def export_chain_head(conn: psycopg.Connection, destination: Path) -> dict:
    """Verify the full chain and write the head to a JSON file (append-only log).

    In deployed environments the destination is a separate, write-once
    location (e.g. a versioned object-storage bucket outside the database's
    control). Refuses to export a broken chain.
    """
    result = verify_chain(conn)
    if not result.ok:
        raise RuntimeError(f"audit chain broken at seq {result.first_bad_seq}: {result.reason}")
    env = conn.execute("SELECT environment FROM lfhe.deployment_environment").fetchone()
    record = {
        "environment": env[0] if env and not isinstance(env, dict) else (env or {}).get("environment"),
        "head_seq": result.head_seq,
        "head_hash": result.head_hash,
        "entries_verified": result.entries_checked,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "canonicalisation": "v1",
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def verify_against_exported_head(conn: psycopg.Connection, head: dict) -> ChainVerification:
    """Check that the live chain still contains the exported head unchanged."""
    result = verify_chain(conn)
    if not result.ok:
        return result
    row = conn.execute("SELECT entry_hash FROM lfhe.audit_log WHERE seq = %s",
                       (head["head_seq"],)).fetchone()
    stored = None if row is None else (row[0] if not isinstance(row, dict) else row["entry_hash"])
    if stored != head["head_hash"]:
        return ChainVerification(False, result.entries_checked, result.head_seq, result.head_hash,
                                 head["head_seq"], "exported head no longer present in chain")
    return result


__all__ = ["ChainVerification", "GENESIS", "canonical_v1", "verify_chain",
           "export_chain_head", "verify_against_exported_head", "asdict"]
