"""Test harness: a throw-away PostgreSQL 16 cluster with the real migrations.

* Starts a private cluster (initdb + pg_ctl) on a free port.
* Applies the LOCAL-ONLY Supabase shim, then every file in
  database/migrations via scripts/apply_migrations.py.
* Records the deployment environment as TEST.
* Creates test login roles that mirror production topology:
    - worker_test       : member of lfhe_worker (Python workers)
    - authenticator     : PostgREST-style login that SET ROLEs to
                          authenticated / service_role (from the shim)
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import dict_row

REPO_ROOT = Path(__file__).resolve().parents[1]
SHIM = REPO_ROOT / "tests" / "fixtures" / "supabase_shim.sql"


def _pg_bin(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    for version in ("17", "16", "15"):
        candidate = Path(f"/usr/lib/postgresql/{version}/bin/{name}")
        if candidate.exists():
            return str(candidate)
    pytest.skip(f"PostgreSQL binary {name!r} not available")


def _as_pg_user(cmd: list[str]) -> list[str]:
    # PostgreSQL refuses to run as root; drop to the postgres OS user if needed.
    if os.geteuid() == 0:
        return ["runuser", "-u", "postgres", "--", *cmd]
    return cmd


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class PgCluster:
    port: int
    dbname: str = "lfhe_test"

    def url(self, user: str = "postgres", dbname: str | None = None) -> str:
        return f"postgresql://{user}@127.0.0.1:{self.port}/{dbname or self.dbname}"

    @property
    def admin_url(self) -> str:
        return self.url("postgres")

    @property
    def worker_url(self) -> str:
        return self.url("worker_test")

    def admin(self, autocommit: bool = True) -> psycopg.Connection:
        return psycopg.connect(self.admin_url, autocommit=autocommit, row_factory=dict_row)

    def worker(self, autocommit: bool = True) -> psycopg.Connection:
        return psycopg.connect(self.worker_url, autocommit=autocommit, row_factory=dict_row)

    @contextlib.contextmanager
    def as_role(self, db_role: str, claims: dict | None, autocommit: bool = True):
        """PostgREST-style session: login as authenticator, SET ROLE, set JWT claims."""
        conn = psycopg.connect(self.url("authenticator"), autocommit=autocommit, row_factory=dict_row)
        try:
            conn.execute(f"SET ROLE {db_role}")
            if claims is not None:
                conn.execute("SELECT set_config('request.jwt.claims', %s, false)", (json.dumps(claims),))
            yield conn
        finally:
            conn.close()

    def as_user(self, user_id: uuid.UUID | str, autocommit: bool = True):
        return self.as_role("authenticated", {"sub": str(user_id), "role": "authenticated"}, autocommit)

    def as_service_role(self, autocommit: bool = True):
        return self.as_role("service_role", {"role": "service_role"}, autocommit)

    def as_anon(self, autocommit: bool = True):
        return self.as_role("anon", {"role": "anon"}, autocommit)


@pytest.fixture(scope="session")
def pg_cluster_raw():
    base = Path(tempfile.mkdtemp(prefix="lfhe-pg-", dir="/var/tmp"))
    datadir = base / "data"
    if os.geteuid() == 0:
        shutil.chown(base, "postgres", "postgres")
    port = _free_port()
    subprocess.run(
        _as_pg_user([_pg_bin("initdb"), "-D", str(datadir), "-U", "postgres", "-A", "trust",
                     "-E", "UTF8", "--locale=C.UTF-8"]),
        check=True, capture_output=True,
    )
    subprocess.run(
        _as_pg_user([_pg_bin("pg_ctl"), "-D", str(datadir), "-l", str(base / "log.txt"), "-w",
                     "-o", f"-p {port} -k {base} -c listen_addresses=127.0.0.1 "
                           f"-c max_connections=100 -c fsync=off", "start"]),
        check=True, capture_output=True,
    )
    try:
        yield PgCluster(port=port), base, datadir
    finally:
        subprocess.run(_as_pg_user([_pg_bin("pg_ctl"), "-D", str(datadir), "-m", "immediate", "stop"]),
                       capture_output=True)
        shutil.rmtree(base, ignore_errors=True)


def create_database(cluster: PgCluster, dbname: str, environment: str = "TEST") -> None:
    from apply_migrations import apply_all

    with psycopg.connect(cluster.url("postgres", "postgres"), autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
        c.execute(f'CREATE DATABASE "{dbname}"')
    url = cluster.url("postgres", dbname)
    with psycopg.connect(url, autocommit=True) as c:
        c.execute(SHIM.read_text())
    apply_all(url)
    with psycopg.connect(url, autocommit=True) as c:
        c.execute("SELECT lfhe.set_deployment_environment(%s)", (environment,))
        c.execute(
            "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='worker_test') THEN "
            "CREATE ROLE worker_test LOGIN; END IF; END $$"
        )
        c.execute("GRANT lfhe_worker TO worker_test")
        c.execute(f'GRANT CONNECT ON DATABASE "{dbname}" TO worker_test, authenticator')


@pytest.fixture(scope="session")
def pg(pg_cluster_raw) -> PgCluster:
    cluster, _, _ = pg_cluster_raw
    create_database(cluster, cluster.dbname)
    return cluster


def new_user(pg: PgCluster, email: str | None = None) -> uuid.UUID:
    uid = uuid.uuid4()
    with pg.admin() as c:
        c.execute("INSERT INTO auth.users (id, email) VALUES (%s, %s)",
                  (uid, email or f"{uid.hex[:8]}@test.invalid"))
    return uid


def grant_role(pg: PgCluster, user_id: uuid.UUID, role: str) -> None:
    """Owner-level role assignment for test setup (production: lfhe.grant_user_role)."""
    with pg.admin() as c:
        c.execute("SELECT lfhe.bootstrap_grant_role(%s, %s)", (user_id, role))


@pytest.fixture
def make_user(pg):
    def _make(*roles: str) -> uuid.UUID:
        uid = new_user(pg)
        for r in roles:
            grant_role(pg, uid, r)
        return uid
    return _make


def wait_for(predicate, timeout: float = 10.0, interval: float = 0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False
