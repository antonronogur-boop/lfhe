#!/usr/bin/env python3
"""DEV Supabase smoke test (CG1-06). Runs ONLY against a database whose
lfhe.deployment_environment is DEV.

Environment (never commit these; take them from the DEV project / secret manager):
  LFHE_SMOKE_SUPABASE_URL        https://<dev-ref>.supabase.co
  LFHE_SMOKE_ANON_KEY            DEV anon (publishable) key
  LFHE_SMOKE_DB_URL              DEV Postgres connection (owner, e.g. postgres) — assertions + setup checks
  LFHE_SMOKE_ADMIN_EMAIL / LFHE_SMOKE_ADMIN_PASSWORD     DEV user holding ADMIN
  LFHE_SMOKE_VIEWER_EMAIL / LFHE_SMOKE_VIEWER_PASSWORD   DEV user holding only VIEWER
  LFHE_SMOKE_SERVICE_ROLE_KEY    optional: proves service_role cannot call HUMAN_ONLY functions
  LFHE_SMOKE_WAIT_CRON_SECONDS   optional (default 0): wait for a pg_cron run of
                                 lfhe-enqueue-due-collections to succeed

Usage:
  python scripts/supabase_dev_smoke.py            # prints a JSON report, exit 1 on any FAIL

Side effects (DEV only): creates one inactive source named "smoke-<UTC timestamp>"
(sources are never deleted; it is deactivated at the end) and the
corresponding audit entries.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone

import httpx
import psycopg
from psycopg.rows import dict_row

RESULTS: list[dict] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append({"check": name, "result": "PASS" if ok else "FAIL", "detail": detail[:300]})
    return ok


def env(name: str, required: bool = True) -> str | None:
    value = os.environ.get(name)
    if required and not value:
        raise SystemExit(f"missing environment variable {name}")
    return value


class Rest:
    def __init__(self, base: str, anon: str):
        self.base, self.anon = base.rstrip("/"), anon
        self.http = httpx.Client(timeout=30)

    def sign_in(self, email: str, password: str) -> str:
        r = self.http.post(f"{self.base}/auth/v1/token?grant_type=password",
                           headers={"apikey": self.anon}, json={"email": email, "password": password})
        r.raise_for_status()
        return r.json()["access_token"]

    def _h(self, token: str | None, write=False):
        h = {"apikey": self.anon, "Authorization": f"Bearer {token or self.anon}", "Accept-Profile": "lfhe"}
        if write:
            h["Content-Profile"] = "lfhe"
        return h

    def select(self, table: str, token: str | None):
        return self.http.get(f"{self.base}/rest/v1/{table}?select=*&limit=5", headers=self._h(token))

    def rpc(self, fn: str, args: dict, token: str | None):
        return self.http.post(f"{self.base}/rest/v1/rpc/{fn}", headers=self._h(token, write=True), json=args)


def main() -> int:
    rest = Rest(env("LFHE_SMOKE_SUPABASE_URL"), env("LFHE_SMOKE_ANON_KEY"))
    db = psycopg.connect(env("LFHE_SMOKE_DB_URL"), autocommit=True, row_factory=dict_row)
    environment = db.execute("SELECT environment FROM lfhe.deployment_environment").fetchone()
    if not environment or environment["environment"] != "DEV":
        raise SystemExit("refusing to run: lfhe.deployment_environment is not DEV")

    # 1. migrations / schema exposure
    applied = db.execute("SELECT count(*) AS n FROM public.lfhe_schema_migrations").fetchone()["n"]
    check("migrations applied", applied > 0, f"{applied} migration(s)")

    # 2. authentication
    admin = rest.sign_in(env("LFHE_SMOKE_ADMIN_EMAIL"), env("LFHE_SMOKE_ADMIN_PASSWORD"))
    viewer = rest.sign_in(env("LFHE_SMOKE_VIEWER_EMAIL"), env("LFHE_SMOKE_VIEWER_PASSWORD"))
    check("auth: password sign-in (admin, viewer)", bool(admin and viewer))

    # 3. RLS / grants
    r = rest.select("sources", None)
    check("RLS: anon cannot read lfhe.sources", r.status_code in (401, 403, 404) or r.json() == [],
          f"HTTP {r.status_code}")
    r = rest.select("sources", viewer)
    check("RLS: viewer can read sources (SOURCE_READ)", r.status_code == 200, f"HTTP {r.status_code}")
    r = rest.select("audit_log", viewer)
    check("RLS: viewer sees no audit rows (no AUDIT_READ)", r.status_code == 200 and r.json() == [],
          f"HTTP {r.status_code}")
    r = rest.rpc("my_permissions", {}, viewer)
    check("RPC: viewer permissions", r.status_code == 200 and set(r.json()) == {"SOURCE_READ", "ARTICLE_READ", "CLAIM_READ"},
          r.text)

    # 4. HUMAN_ONLY SECURITY DEFINER behaviour
    name = "smoke-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {"p": {"name": name, "canonical_domain": "example.org", "source_type": "OTHER",
                     "primary_language": "en", "collection_method": "RSS_ATOM",
                     "collection_config": {"feed_url": "https://example.org/feed.xml"}}}
    r = rest.rpc("create_source", payload, None)
    check("HUMAN_ONLY: anon cannot create_source", r.status_code >= 400, f"HTTP {r.status_code}")
    r = rest.rpc("create_source", payload, viewer)
    check("HUMAN_ONLY: viewer lacks SOURCE_CREATE", r.status_code >= 400, f"HTTP {r.status_code}")
    service_key = env("LFHE_SMOKE_SERVICE_ROLE_KEY", required=False)
    if service_key:
        r = rest.rpc("create_source", payload, service_key)
        check("HUMAN_ONLY: service_role cannot create_source", r.status_code >= 400, f"HTTP {r.status_code}")
    nested = {"p": {**payload["p"], "name": name + "-cred",
                    "collection_config": {"feed_url": "https://example.org/f.xml", "options": {"token": "x"}}}}
    r = rest.rpc("create_source", nested, admin)
    check("CG1-03: nested credential key rejected via RPC", r.status_code >= 400 and "CREDENTIAL_KEY_REJECTED" in r.text,
          f"HTTP {r.status_code}")

    synthetic = "SYNTHETIC-SMOKE-SECRET-0000"
    cred_url = {"p": {**payload["p"], "name": name + "-credurl",
                      "collection_config": {"feed_url": f"https://reader:{synthetic}@example.org/f.xml"}}}
    r = rest.rpc("create_source", cred_url, admin)
    leaked = db.execute("SELECT count(*) AS n FROM lfhe.audit_log WHERE new_state::text LIKE %s",
                        (f"%{synthetic}%",)).fetchone()["n"]
    check("CG1-08: credential-bearing URL rejected via RPC, not echoed, not audited",
          r.status_code >= 400 and "CREDENTIAL_URL_REJECTED" in r.text and synthetic not in r.text and leaked == 0,
          f"HTTP {r.status_code}")

    cred_ws = {"p": {**payload["p"], "name": name + "-cg108a",
                     "collection_config": {"feed_url": f"  /feed?api_key={synthetic}"}}}
    r = rest.rpc("create_source", cred_ws, admin)
    leaked = db.execute("SELECT count(*) AS n FROM lfhe.audit_log WHERE new_state::text LIKE %s",
                        (f"%{synthetic}%",)).fetchone()["n"]
    check("CG1-08A: whitespace/relative credential URL rejected via RPC, not echoed, not audited",
          r.status_code >= 400 and synthetic not in r.text and leaked == 0, f"HTTP {r.status_code}")

    # 5. source administration end-to-end
    r = rest.rpc("create_source", payload, admin)
    ok = check("source admin: admin creates source", r.status_code == 200, f"HTTP {r.status_code} {r.text}")
    if ok:
        sid = r.json()
        r1 = rest.rpc("set_collection_method_approval", {"p_id": sid, "p_approved": True, "p_reason": "DEV smoke test"}, admin)
        r2 = rest.rpc("set_source_active", {"p_id": sid, "p_active": True, "p_reason": "DEV smoke test"}, admin)
        r3 = rest.rpc("set_source_active", {"p_id": sid, "p_active": False, "p_reason": "DEV smoke test end"}, admin)
        check("source admin: approve / activate / deactivate", all(x.status_code in (200, 204) for x in (r1, r2, r3)),
              f"{r1.status_code}/{r2.status_code}/{r3.status_code}")
        events = {row["event_type"] for row in db.execute(
            "SELECT event_type, actor_type FROM lfhe.audit_log WHERE object_id = %s", (str(sid),)).fetchall()}
        check("audit: source lifecycle audited", {"SOURCE_CREATED", "SOURCE_COLLECTION_METHOD_APPROVED",
                                                  "SOURCE_ACTIVATED", "SOURCE_DEACTIVATED"} <= events, str(events))
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "shared"))
    from lfhe_shared.audit import verify_chain  # noqa: E402
    chain = verify_chain(db)
    check("audit: hash chain verifies", chain.ok, str(chain))

    # 6. pg_cron
    has_cron = db.execute("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='pg_cron') AS x").fetchone()["x"]
    if not has_cron:
        check("pg_cron: extension enabled", False, "pg_cron not enabled in this project (status: NOT ENABLED)")
    else:
        job = db.execute("SELECT jobid, schedule, active FROM cron.job WHERE jobname='lfhe-enqueue-due-collections'").fetchone()
        check("pg_cron: lfhe-enqueue-due-collections scheduled", bool(job and job["active"]), str(job))
        wait = int(env("LFHE_SMOKE_WAIT_CRON_SECONDS", required=False) or 0)
        deadline, ran = time.monotonic() + wait, None
        while job and wait and time.monotonic() < deadline and not ran:
            ran = db.execute("SELECT status, start_time FROM cron.job_run_details WHERE jobid=%s "
                             "AND start_time > now() - interval '15 minutes' ORDER BY start_time DESC LIMIT 1",
                             (job["jobid"],)).fetchone()
            if not ran:
                time.sleep(15)
        if wait:
            check("pg_cron: enqueue job ran successfully", bool(ran and ran["status"] == "succeeded"), str(ran))

    print(json.dumps({"environment": "DEV", "results": RESULTS}, indent=2, default=str))
    return 0 if all(r["result"] == "PASS" for r in RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
