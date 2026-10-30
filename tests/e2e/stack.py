"""LOCAL TEST-ONLY browser E2E stack (CR7-03). Never points at DEV or any real Supabase project.

    PostgreSQL 16 (throw-away cluster, Supabase shim + every real migration)
      ← PostgREST (real binary, JWT secret per run)
      ← auth_gateway (GoTrue subset + /rest/v1 proxy, per-run users and passwords)
      ← Next.js production server (apps/web, `next start`, bound to 127.0.0.1)
    + the real worker loop (lfhe_orchestrator.worker.make_handlers) with the SYNTHETIC_TEST_ONLY scripted model

Usage (interactive, for manual inspection):  python tests/e2e/stack.py   (prints URLs + per-run credentials, Ctrl+C stops)
Requirements: PostgreSQL 16 binaries, a PostgREST binary (LFHE_E2E_POSTGREST or `postgrest` on PATH), Node 22 with
apps/web dependencies installed, Playwright + Chromium for the test itself. Nothing here holds or needs a real secret.
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "tests", ROOT / "tests" / "integration", ROOT / "scripts", ROOT / "tests" / "e2e"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import conftest as cf  # noqa: E402
from auth_gateway import Gateway  # noqa: E402

WEB = ROOT / "apps" / "web"
MODULES = ("M02_CLAIM_EXTRACTOR", "M03_CLASSIFIER", "M04_LINEAGE", "M05_EVENT_BUILDER", "M06_RELEVANCE",
           "M07_INTELLIGENCE_ASSESSOR", "M08_CHALLENGER", "M09_EXECUTIVE_EDITOR", "M10_QA_AUDITOR")
ROLES = {"analyst": ("ANALYST", "PILOT_LEAD"), "reviewer": ("REVIEWER",), "security": ("SECURITY_REVIEWER",),
         "release": ("RELEASE_AUTHORITY",), "viewer": ("VIEWER",), "admin": ("ADMIN",)}
# synthetic corpus (SYNTHETIC_TEST_ONLY): two public statements available before the REPLAY cutoff
AVAILABLE = "2026-01-10T08:00:00+00:00"
CUTOFF = "2026-03-01T00:00:00+00:00"
ARTICLES = ("The air force said 4 tanker aircraft arrived at Fort Aster.",
            "A spokesman denied that any tanker aircraft arrived at Fort Aster.")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def postgrest_binary() -> str | None:
    cand = os.environ.get("LFHE_E2E_POSTGREST") or shutil.which("postgrest")
    if not cand and Path("/tmp/claude-0/e2etools/postgrest").exists():
        cand = "/tmp/claude-0/e2etools/postgrest"
    return cand if cand and Path(cand).exists() else None


def wait_http(url: str, timeout: float = 90) -> None:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                if r.status < 500:
                    return
        except urllib.error.HTTPError as e:
            if e.code < 500:
                return
            last = e
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(0.3)
    raise RuntimeError(f"{url} did not come up: {last}")


@dataclass
class Stack:
    base: Path = field(default_factory=lambda: Path(tempfile.mkdtemp(prefix="lfhe-e2e-", dir="/var/tmp")))
    pg: cf.PgCluster | None = None
    gateway: Gateway | None = None
    web_port: int = 0
    users: dict = field(default_factory=dict)          # name -> {id, email, password}
    procs: list = field(default_factory=list)
    model_config: str = ""
    snapshots: list = field(default_factory=list)

    @property
    def web_url(self) -> str:
        return f"http://127.0.0.1:{self.web_port}"

    # --- PostgreSQL ---------------------------------------------------------------------------------
    def start_db(self) -> None:
        data = self.base / "pg"
        if os.geteuid() == 0:
            shutil.chown(self.base, "postgres", "postgres")
        port = free_port()
        subprocess.run(cf._as_pg_user([cf._pg_bin("initdb"), "-D", str(data), "-U", "postgres", "-A", "trust", "-E", "UTF8",
                                       "--locale=C.UTF-8"]), check=True, capture_output=True)
        subprocess.run(cf._as_pg_user([cf._pg_bin("pg_ctl"), "-D", str(data), "-l", str(self.base / "pg.log"), "-w", "-o",
                                       f"-p {port} -k {self.base} -c listen_addresses=127.0.0.1 -c fsync=off"
                                       f" -c max_connections=200", "start"]), check=True, capture_output=True)
        self._pgdata = data
        self.pg = cf.PgCluster(port=port, dbname="lfhe_e2e")
        cf.create_database(self.pg, self.pg.dbname, environment="TEST")

    def seed(self) -> None:
        from psycopg.types.json import Jsonb

        from claims_support import make_text_snapshot
        from pipeline_support import activate_real_prompts
        activate_real_prompts(self.pg, MODULES)
        # registered here, not via the session-cached test helper (this is a separate database)
        with self.pg.registrar() as c:
            self.model_config = str(c.execute("SELECT lfhe.register_model_configuration('fake', 'fake-model-1', %s::jsonb) AS id",
                                              (Jsonb({"temperature": 0}),)).fetchone()["id"])
        for name, roles in ROLES.items():
            uid = cf.new_user(self.pg, f"lfhe-{name}@e2e.invalid")
            for r in roles:
                cf.grant_role(self.pg, uid, r)
            self.users[name] = {"id": str(uid), "email": f"lfhe-{name}@e2e.invalid", "password": secrets.token_urlsafe(18)}
        for text in ARTICLES:
            self.snapshots.append(make_text_snapshot(self.pg, text, title="Synthetic Northland statement", available_at=AVAILABLE))

    # --- PostgREST + gateway ------------------------------------------------------------------------
    def start_api(self) -> None:
        binary = postgrest_binary()
        if binary is None:
            raise RuntimeError("PostgREST binary not found (set LFHE_E2E_POSTGREST)")
        secret = secrets.token_hex(32)
        rest_port = free_port()
        env = dict(os.environ, PGRST_DB_URI=self.pg.url("authenticator"), PGRST_DB_SCHEMAS="lfhe",
                   PGRST_DB_ANON_ROLE="anon", PGRST_JWT_SECRET=secret, PGRST_SERVER_PORT=str(rest_port),
                   PGRST_SERVER_HOST="127.0.0.1", PGRST_DB_POOL="20", PGRST_LOG_LEVEL="error")
        log = open(self.base / "postgrest.log", "wb")
        self.procs.append(subprocess.Popen([binary], env=env, stdout=log, stderr=subprocess.STDOUT))
        wait_http(f"http://127.0.0.1:{rest_port}/")
        self.gateway = Gateway(postgrest_port=rest_port, jwt_secret=secret)
        for u in self.users.values():
            self.gateway.add_user(u["id"], u["email"], u["password"])
        self.gateway.start()

    # --- worker -------------------------------------------------------------------------------------
    def start_worker(self) -> None:
        env = dict(os.environ, LFHE_CHROMIUM_NO_SANDBOX="1", PYTHONPATH=os.pathsep.join(
            [str(ROOT / "tests"), str(ROOT / "tests" / "integration"), str(ROOT / "tests" / "e2e")]))
        log = open(self.base / "worker.log", "wb")
        self.procs.append(subprocess.Popen(
            [sys.executable, str(ROOT / "tests" / "e2e" / "e2e_worker.py"), "--db", self.pg.worker_url,
             "--config", self.model_config, "--store", str(self.base / "objects")],
            env=env, stdout=log, stderr=subprocess.STDOUT))

    # --- web ----------------------------------------------------------------------------------------
    def web_env(self) -> dict:
        env = {k: v for k, v in os.environ.items() if k not in ("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY",
                                                                  "LFHE_DATABASE_URL")}
        env.update(NEXT_PUBLIC_SUPABASE_URL=f"http://127.0.0.1:{self.gateway.port}",
                   NEXT_PUBLIC_SUPABASE_ANON_KEY=self.gateway.anon_key(), NEXT_TELEMETRY_DISABLED="1", CI="1", TZ="UTC")
        return env

    def build_web(self) -> None:
        if os.environ.get("LFHE_E2E_SKIP_BUILD") == "1" and (WEB / ".next" / "BUILD_ID").exists():
            return
        for _ in range(2):
            r = subprocess.run(["npm", "run", "build"], cwd=WEB, env=self.web_env(), capture_output=True, text=True)
            # Next.js 16.4 stops the first build once to show its upgrade recommendation (known, docs: CG7 KNOWN
            # FAILURES); a retry continues. No dependency is upgraded here (PO: no automatic upgrades).
            if r.returncode == 0 or "SecurityFatalError" not in r.stderr:
                break
        if r.returncode != 0:
            raise RuntimeError(f"next build failed:\n{r.stdout[-4000:]}\n{r.stderr[-4000:]}")

    def start_web(self) -> None:
        self.web_port = free_port()
        log = open(self.base / "web.log", "wb")
        self.procs.append(subprocess.Popen(
            [str(WEB / "node_modules" / ".bin" / "next"), "start", "-H", "127.0.0.1", "-p", str(self.web_port)],
            cwd=WEB, env=self.web_env(), stdout=log, stderr=subprocess.STDOUT))
        wait_http(f"{self.web_url}/login", timeout=120)

    def up(self, *, build: bool = True) -> "Stack":
        self.start_db()
        self.seed()
        self.start_api()
        self.start_worker()
        if build:
            self.build_web()
        self.start_web()
        return self

    def down(self) -> None:
        for p in reversed(self.procs):
            p.send_signal(signal.SIGTERM)
        for p in self.procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
        if self.gateway:
            self.gateway.stop()
        if self.pg is not None:
            subprocess.run(cf._as_pg_user([cf._pg_bin("pg_ctl"), "-D", str(self._pgdata), "-m", "immediate", "stop"]),
                           capture_output=True)
        if os.environ.get("LFHE_E2E_KEEP") != "1":
            shutil.rmtree(self.base, ignore_errors=True)

    def sql(self, query: str, *args):
        with self.pg.admin() as c:
            return c.execute(query, args).fetchall()

    def info(self) -> dict:
        return {"web": self.web_url, "gateway": f"http://127.0.0.1:{self.gateway.port}", "db": self.pg.admin_url,
                "logs": str(self.base), "users": {k: {"email": v["email"], "password": v["password"]}
                                                    for k, v in self.users.items()}}


if __name__ == "__main__":       # pragma: no cover - manual use
    st = Stack().up(build=os.environ.get("LFHE_E2E_SKIP_BUILD") != "1")
    print(json.dumps(st.info(), indent=2), flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        st.down()
