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

    # 4b. Phase 2 claim pipeline (P2): read/RBAC surface only; no claims are created by the smoke test
    taxonomy = db.execute("SELECT count(*) AS n FROM lfhe.taxonomy_items WHERE taxonomy_version='LFHE-TAX-1.2'").fetchone()["n"]
    check("P2: closed taxonomy LFHE-TAX-1.2 seeded (62 items)", taxonomy == 62, f"{taxonomy} item(s)")
    r = rest.select("claims", viewer)
    check("P2: viewer can read claims (CLAIM_READ)", r.status_code == 200, f"HTTP {r.status_code}")
    r = rest.select("claims", None)
    check("P2: anon cannot read claims", r.status_code in (401, 403, 404) or r.json() == [], f"HTTP {r.status_code}")
    review = {"p_claim_id": "00000000-0000-4000-8000-000000000000", "p_claim_hash": "0" * 64,
              "p_expected_previous_review_id": None, "p_decision": "APPROVE", "p_reason": "smoke test probe"}
    r = rest.rpc("review_claim", review, viewer)
    check("P2: viewer cannot record a claim review (HUMAN_ONLY + CLAIM_REVIEW)",
          r.status_code >= 400 and "CLAIM_REVIEW" in r.text, f"HTTP {r.status_code}")
    r = rest.rpc("review_claim", review, admin)
    check("P2: ADMIN cannot record a claim review (no CLAIM_REVIEW)",
          r.status_code >= 400 and "CLAIM_REVIEW" in r.text, f"HTTP {r.status_code}")
    if service_key:
        r = rest.rpc("review_claim", review, service_key)
        check("P2: service_role cannot record a claim review", r.status_code >= 400, f"HTTP {r.status_code}")
    r = rest.rpc("ingest_claim_extraction", {"p": {}}, admin)
    check("P2: humans cannot call the worker ingestion function", r.status_code >= 400, f"HTTP {r.status_code}")

    # 4c. Phase 3 lineage & events (P3): schema / RLS / RBAC surface only; no data is created
    p3_tables = ["external_origins", "lineage_ingestion_results", "lineage_proposals", "corroboration_recommendations",
                 "claim_lineage", "claim_lineage_retractions", "events", "event_actions", "event_versions",
                 "event_claims", "event_state_history", "event_relationships", "event_proposals",
                 "event_version_reviews", "event_ingestion_results", "event_claim_redistributions"]
    rls = {r["relname"]: r["relrowsecurity"] for r in db.execute(
        "SELECT c.relname, c.relrowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'lfhe' AND c.relname = ANY(%s)", (p3_tables,))}
    check("P3: lineage/event tables present with RLS", len(rls) == len(p3_tables) and all(rls.values()),
          f"{sum(rls.values())}/{len(p3_tables)}")
    rules = db.execute("SELECT count(*) AS n FROM lfhe.claim_status_auto_rules").fetchone()["n"]
    check("P3: claim_status_auto_rules empty (no automatic status rule)", rules == 0, f"{rules} rule(s)")
    loose = db.execute(
        "SELECT count(*) AS n FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'lfhe' "
        "AND p.prosecdef AND NOT coalesce(p.proconfig @> ARRAY['search_path=pg_catalog, pg_temp'], false)").fetchone()["n"]
    check("P3: every SECURITY DEFINER pins search_path", loose == 0, f"{loose} function(s)")
    r = rest.select("events", viewer)
    check("P3: viewer can read events (CLAIM_READ)", r.status_code == 200, f"HTTP {r.status_code}")
    r = rest.select("events", None)
    check("P3: anon cannot read events", r.status_code in (401, 403, 404) or r.json() == [], f"HTTP {r.status_code}")
    zero = "00000000-0000-4000-8000-000000000000"
    merge = {"p_target": zero, "p_sources": [zero], "p_expected_heads": {}, "p_reason": "smoke test probe"}
    for who, token in (("viewer", viewer), ("ADMIN", admin)):
        r = rest.rpc("merge_events", merge, token)
        check(f"P3: {who} cannot MERGE (HUMAN_ONLY + EVENT_ACTION)",
              r.status_code >= 400 and "EVENT_ACTION" in r.text, f"HTTP {r.status_code}")
        r = rest.rpc("decide_lineage_proposal", {"p_proposal_id": zero, "p_accept": True, "p_reason": "smoke probe"}, token)
        check(f"P3: {who} cannot validate lineage (CLAIM_REVIEW)",
              r.status_code >= 400 and "CLAIM_REVIEW" in r.text, f"HTTP {r.status_code}")
    if service_key:
        r = rest.rpc("merge_events", merge, service_key)
        check("P3: service_role cannot MERGE", r.status_code >= 400, f"HTTP {r.status_code}")
    bad = [fn for fn in ("ingest_lineage", "ingest_event_proposals")
           if rest.rpc(fn, {"p": {}}, admin).status_code < 400]
    check("P3: humans cannot call the M04/M05 ingestion functions", not bad, ", ".join(bad))

    # 4d. Phase 4 relevance / assessment / challenge / review (P4): schema / RLS / RBAC surface only
    p4_tables = ["reference_contexts", "reference_context_versions", "baselines", "baseline_versions", "relevance_results",
                 "relevance_decisions", "assessments", "assessment_versions", "assessment_statements",
                 "assessment_statement_evidence", "assessment_state_history", "challenge_runs", "challenge_flags",
                 "challenge_flag_dispositions", "analytical_approvals", "trends", "trend_versions", "trend_events",
                 "indicators", "indicator_versions", "indicator_claims"]
    rls = {r["relname"]: r["relrowsecurity"] for r in db.execute(
        "SELECT c.relname, c.relrowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'lfhe' AND c.relname = ANY(%s)", (p4_tables,))}
    check("P4: assessment/challenge/trend tables present with RLS", len(rls) == len(p4_tables) and all(rls.values()),
          f"{sum(rls.values())}/{len(p4_tables)}")
    owners = [f"{r['table_name']}.{r['column_name']}" for r in db.execute(
        "SELECT c.table_name, c.column_name FROM information_schema.columns c JOIN information_schema.tables t "
        "ON t.table_schema = c.table_schema AND t.table_name = c.table_name AND t.table_type = 'BASE TABLE' "
        "WHERE c.table_schema = 'lfhe' AND (c.column_name ILIKE '%%analytic%%' OR c.column_name = 'confidence')")]
    check("P4: final_analytic_confidence has exactly one owner (DC-01)",
          owners == ["analytical_approvals.final_analytic_confidence"], ", ".join(owners))
    canonical = ["REMOTE_CHANCE", "HIGHLY_UNLIKELY", "UNLIKELY", "ROUGHLY_EVEN_CHANCE", "LIKELY",
                 "HIGHLY_LIKELY", "ALMOST_CERTAIN"]                      # PO decision 2026-10-20 (CR4-01)
    terms = [(r["code"], r["rank"]) for r in db.execute("SELECT code, rank FROM lfhe.likelihood_terms ORDER BY rank, code")]
    check("P4: likelihood vocabulary is exactly the canonical CR4-01 set in rank order",
          terms == [(c, i) for i, c in enumerate(canonical, 1)], ", ".join(f"{r}:{c}" for c, r in terms))
    r = rest.select("assessment_versions", viewer)
    check("P4: viewer can read assessment versions (CLAIM_READ)", r.status_code == 200, f"HTTP {r.status_code}")
    r = rest.select("assessment_versions", None)
    check("P4: anon cannot read assessment versions", r.status_code in (401, 403, 404) or r.json() == [], f"HTTP {r.status_code}")
    approve_args = {"p_version": zero, "p_hash": "0" * 64, "p_decision": "APPROVE", "p_final_confidence": "LOW",
                    "p_confidence_rationale": "smoke test probe rationale text", "p_reason": "smoke test probe"}
    dispose_args = {"p_flag": zero, "p_disposition": "ACCEPTED", "p_reason": "smoke test probe"}
    for who, token in (("viewer", viewer), ("ADMIN", admin)):
        r = rest.rpc("review_assessment", approve_args, token)
        check(f"P4: {who} cannot APPROVE an assessment (HUMAN_ONLY + ASSESSMENT_REVIEW)",
              r.status_code >= 400 and "ASSESSMENT_REVIEW" in r.text, f"HTTP {r.status_code}")
        r = rest.rpc("dispose_challenge_flag", dispose_args, token)
        check(f"P4: {who} cannot dispose of an M08 flag (ASSESSMENT_REVIEW)",
              r.status_code >= 400 and "ASSESSMENT_REVIEW" in r.text, f"HTTP {r.status_code}")
    if service_key:
        r = rest.rpc("review_assessment", approve_args, service_key)
        check("P4: service_role cannot APPROVE an assessment", r.status_code >= 400, f"HTTP {r.status_code}")
    bad = [fn for fn in ("ingest_relevance", "ingest_assessment", "ingest_challenge")
           if rest.rpc(fn, {"p": {}}, admin).status_code < 400]
    check("P4: humans cannot call the M06/M07/M08 ingestion functions", not bad, ", ".join(bad))

    # 4e. Phase 5 executive reporting (P5): schema / RLS / RBAC surface only; no report is created
    p5_tables = ["reports", "report_candidate_pool", "report_selection_decisions", "report_selection_sets",
                 "report_selection_set_items", "report_versions", "report_items", "report_item_statements",
                 "report_statement_sources", "report_removal_proposals", "report_removal_decisions", "report_renders",
                 "report_edit_ingestion_results"]
    rls = {r["relname"]: r["relrowsecurity"] for r in db.execute(
        "SELECT c.relname, c.relrowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'lfhe' AND c.relname = ANY(%s)", (p5_tables,))}
    check("P5: report tables present with RLS", len(rls) == len(p5_tables) and all(rls.values()), f"{sum(rls.values())}/{len(p5_tables)}")
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "shared"))
    from lfhe_shared.canonical_json import canonical_sha256  # noqa: E402
    probe = {"b": [1, True, None], "a": "é\u0001\"x", "C": {}}
    got = db.execute("SELECT lfhe.jcs_sha256(%s::jsonb) AS h", (json.dumps(probe),)).fetchone()["h"]
    check("P5: SQL RFC 8785 JCS hash equals the Python canonical hash", got == canonical_sha256(probe), got[:16])
    states = db.execute("SELECT pg_get_constraintdef(c.oid) AS d FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
                        "JOIN pg_namespace n ON n.oid = t.relnamespace WHERE n.nspname = 'lfhe' AND t.relname IN "
                        "('report_versions', 'report_renders') AND pg_get_constraintdef(c.oid) ~ '^CHECK \\(\\((state|status) = '").fetchall()
    check("P5: report versions are DRAFT_VERSION and renders PREVIEW only (no QA / approval / release state)",
          len(states) == 2 and all("RELEASED" not in r["d"] for r in states), "; ".join(r["d"] for r in states))
    r = rest.select("report_candidate_state", viewer)
    check("P5: viewer can read the report candidate pool (CLAIM_READ)", r.status_code == 200, f"HTTP {r.status_code}")
    r = rest.select("report_versions", None)
    check("P5: anon cannot read report versions", r.status_code in (401, 403, 404) or r.json() == [], f"HTTP {r.status_code}")
    select_args = {"p_candidate": zero, "p_object_hash": "0" * 64, "p_decision": "INCLUDE", "p_section": "KEY_JUDGMENT",
                   "p_priority": 1, "p_expected_previous_decision": None, "p_reason": "smoke test probe"}
    r = rest.rpc("decide_report_candidate", select_args, viewer)
    check("P5: viewer cannot select report content (HUMAN_ONLY + REPORT_EDIT)",
          r.status_code >= 400 and "REPORT_EDIT" in r.text, f"HTTP {r.status_code}")
    r = rest.rpc("edit_report_version", {"p_version": zero, "p_hash": "0" * 64, "p": {}, "p_reason": "smoke test probe"}, admin)
    check("P5: ADMIN cannot edit a report version (no REPORT_EDIT)",
          r.status_code >= 400 and "REPORT_EDIT" in r.text, f"HTTP {r.status_code}")
    if service_key:
        r = rest.rpc("freeze_report_selection", {"p_report": zero, "p_reason": "smoke test probe"}, service_key)
        check("P5: service_role cannot freeze a report selection", r.status_code >= 400, f"HTTP {r.status_code}")
    bad = [fn for fn in ("ingest_report_edit", "record_report_render") if rest.rpc(fn, {"p": {}}, admin).status_code < 400]
    check("P5: humans cannot call the M09 ingestion / render recording functions", not bad, ", ".join(bad))

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
