#!/usr/bin/env python3
"""Report raw objects that no article_snapshot references (CG1-02).

    LFHE_DATABASE_URL=... LFHE_ENV=DEV python scripts/object_store_reconcile.py

Normal operation creates none (duplicates are detected before any object is
written); an unreferenced object can only result from a crash between the
object write and the database insert, or a concurrent race on the same new
document. Objects are content-addressed and write-once, so an orphan is
harmless. This tool only REPORTS; deleting is an explicit operator action.
Also re-verifies every stored source_state hash.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "services" / "shared"))

from lfhe_shared.config import load_settings  # noqa: E402
from lfhe_shared.db import connect  # noqa: E402
from lfhe_shared.integrity import verify_snapshot_states  # noqa: E402
from lfhe_shared.storage import build_object_store, find_unreferenced_objects  # noqa: E402


def main() -> int:
    settings = load_settings()
    with connect(settings, autocommit=True) as conn:
        orphans = find_unreferenced_objects(build_object_store(settings), conn)
        state_problems = verify_snapshot_states(conn)
    for key in orphans:
        print("UNREFERENCED:", key)
    for p in state_problems:
        print("STATE:", p)
    print(f"RECONCILE: {len(orphans)} unreferenced object(s), {len(state_problems)} state problem(s)")
    return 1 if state_problems else 0


if __name__ == "__main__":
    sys.exit(main())
