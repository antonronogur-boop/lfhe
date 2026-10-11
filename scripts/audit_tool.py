#!/usr/bin/env python3
"""Audit chain operations: verify the chain or export a verified chain head.

Usage:
    python scripts/audit_tool.py verify <postgres-url>
    python scripts/audit_tool.py export <postgres-url> <heads.jsonl>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "services" / "shared"))

import psycopg  # noqa: E402

from lfhe_shared.audit import export_chain_head, verify_chain  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[1] not in {"verify", "export"}:
        print(__doc__)
        return 2
    with psycopg.connect(argv[2]) as conn:
        if argv[1] == "verify":
            result = verify_chain(conn)
            print(result)
            return 0 if result.ok else 1
        if len(argv) < 4:
            print(__doc__)
            return 2
        print(export_chain_head(conn, Path(argv[3])))
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
