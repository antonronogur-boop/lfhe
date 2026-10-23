#!/usr/bin/env python3
"""Phase 7 pilot metrics export (P7-07) from the DEV / pilot database.

    python scripts/pilot_export.py --cost COST-2026-A --cycles-per-week 1 [--cycle P7C-LIVE-01 ...] \
        [--benchmark P7-BM-01] > pilot-export.json

Connection: $LFHE_DEV_DB_URL (the PO's existing DEV database URL; never printed). The export is
recomputed from stored records, contains measurements and aggregate benchmark scores only, and is
refused if it would contain a credential pattern or label content (lfhe_pilot.export)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in ("services/shared", "services/pilot"):
    sys.path.insert(0, str(ROOT / p))

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from lfhe_pilot.export import build_export  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cycle", action="append", help="cycle code (repeatable); default: all cycles")
    ap.add_argument("--benchmark", action="append", help="benchmark code (repeatable)")
    ap.add_argument("--cost", help="cost assumption code (explicit; capacity value is omitted without it)")
    ap.add_argument("--cycles-per-week", type=Decimal, help="explicit cycles per week for the FTE / annual figures")
    a = ap.parse_args()
    url = os.environ.get("LFHE_DEV_DB_URL")
    if not url:
        print("LFHE_DEV_DB_URL is not set", file=sys.stderr)
        return 2
    with psycopg.connect(url, row_factory=dict_row, autocommit=True) as conn:
        conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")   # the export never writes
        doc = build_export(conn, cycle_codes=a.cycle, benchmark_codes=a.benchmark, cost_assumption_code=a.cost,
                           cycles_per_week=a.cycles_per_week,
                           generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    json.dump(doc, sys.stdout, indent=1, sort_keys=True, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
