"""Database access for workers.

``connect`` refuses to return a connection when the database's recorded
deployment environment differs from ``LFHE_ENV`` (DEV / TEST / PROD guard),
or when the database has no recorded environment at all.
"""
from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from .config import Settings


class EnvironmentMismatch(RuntimeError):
    pass


def check_environment(conn: psycopg.Connection, expected: str) -> None:
    row = conn.execute("SELECT environment FROM lfhe.deployment_environment").fetchone()
    if row is None:
        raise EnvironmentMismatch("database has no recorded deployment environment")
    actual = row[0] if not isinstance(row, dict) else row["environment"]
    if actual != expected:
        raise EnvironmentMismatch(
            f"configured for {expected} but the database is recorded as {actual}"
        )


def connect(settings: Settings, *, autocommit: bool = False) -> psycopg.Connection:
    conn = psycopg.connect(
        settings.database_url.get_secret_value(),
        autocommit=autocommit,
        row_factory=dict_row,
        application_name="lfhe-worker",
    )
    try:
        check_environment(conn, settings.env.value)
        if not autocommit:
            conn.commit()
    except Exception:
        conn.close()
        raise
    return conn
