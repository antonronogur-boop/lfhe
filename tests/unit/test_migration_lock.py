"""P7-00 / Phase 7 test 20: migrations applied through CG6 are immutable and every new migration is
forward-only (sorts after the locked range). Hashes are computed exactly as scripts/apply_migrations.py does."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIG = ROOT / "database" / "migrations"
LOCK = json.loads((ROOT / "database" / "migrations.lock.json").read_text(encoding="utf-8"))


def digest(p: Path) -> str:
    return hashlib.sha256(p.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def test_locked_migrations_are_unchanged():
    locked = LOCK["migrations"]
    assert len(locked) == 41 and locked[-1]["filename"] == LOCK["locked_through"]
    for m in locked:
        p = MIG / m["filename"]
        assert p.is_file(), f"locked migration removed: {m['filename']}"
        assert digest(p) == m["sha256"], f"locked migration modified: {m['filename']}"


def test_new_migrations_are_forward_only():
    locked = {m["filename"] for m in LOCK["migrations"]}
    files = sorted(p.name for p in MIG.glob("*.sql"))
    new = [f for f in files if f not in locked]
    assert all(f > LOCK["locked_through"] for f in new), new
    assert files == sorted(locked) + sorted(new)
