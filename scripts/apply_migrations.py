#!/usr/bin/env python3
"""Apply versioned SQL migrations (for local/plain-PostgreSQL use and tests).

In Supabase environments the Supabase CLI applies the same files from
``database/migrations``. This tool exists so the identical files can be applied
to a plain PostgreSQL (tests, DEV without the CLI).

Rules:
* files are applied in lexical (timestamp) order;
* each file runs in its own transaction — a failure leaves no partial state;
* applied files are recorded with a SHA-256 checksum; a previously applied
  file whose content changed is refused (migrations are append-only — fix
  forward with a new migration).

Usage: python scripts/apply_migrations.py <postgres-url> [migrations-dir]
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import psycopg

DEFAULT_DIR = Path(__file__).resolve().parent.parent / "database" / "migrations"

TRACKING_DDL = """
CREATE TABLE IF NOT EXISTS public.lfhe_schema_migrations (
  filename   text PRIMARY KEY,
  sha256     text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now()
);
REVOKE ALL ON public.lfhe_schema_migrations FROM PUBLIC;
"""


class MigrationError(RuntimeError):
    pass


def migration_files(directory: Path = DEFAULT_DIR) -> list[Path]:
    return sorted(p for p in directory.glob("*.sql") if p.is_file())


def apply_all(conninfo: str, directory: Path = DEFAULT_DIR) -> list[str]:
    applied_now: list[str] = []
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute(TRACKING_DDL)
        done = {
            row[0]: row[1]
            for row in conn.execute("SELECT filename, sha256 FROM public.lfhe_schema_migrations")
        }
        for path in migration_files(directory):
            sql = path.read_text(encoding="utf-8")
            digest = hashlib.sha256(sql.encode("utf-8")).hexdigest()
            if path.name in done:
                if done[path.name] != digest:
                    raise MigrationError(
                        f"{path.name} was modified after being applied (append-only migrations)"
                    )
                continue
            try:
                with conn.transaction():
                    conn.execute(sql)
                    conn.execute(
                        "INSERT INTO public.lfhe_schema_migrations (filename, sha256) VALUES (%s, %s)",
                        (path.name, digest),
                    )
            except psycopg.Error as exc:
                raise MigrationError(f"{path.name} failed and was rolled back: {exc}") from exc
            applied_now.append(path.name)
    return applied_now


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    target_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_DIR
    for name in apply_all(sys.argv[1], target_dir):
        print(f"applied {name}")
