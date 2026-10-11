# DEV Supabase deployment and smoke test (CG1-06)

Status at the CG1 corrective pass: **NOT RUN** — this environment cannot reach
the Supabase API and holds no DEV credentials. The steps below are for the
operator/Product Owner; record the JSON output of step 6 in PROJECT_STATUS.

1. Create a dedicated **DEV** Supabase project (EU region, K-07). Never reuse TEST/PROD.
2. Dashboard: Database → Extensions → enable `pg_cron` (optional, for step 6 cron checks).
   API settings → Exposed schemas: add `lfhe`.
3. Apply migrations with the DEV owner connection string (from the dashboard,
   kept in your shell only):
   ```bash
   python scripts/apply_migrations.py "$LFHE_DEV_DB_URL"
   psql "$LFHE_DEV_DB_URL" -c "SELECT lfhe.set_deployment_environment('DEV')"
   ```
   (`scripts/apply_migrations.py` = transactional per file + checksum history; no down-migrations, D-01.)
4. Auth → create two DEV users (e.g. smoke-admin@…, smoke-viewer@…) with
   passwords from your password manager, then:
   ```sql
   SELECT lfhe.bootstrap_grant_role('<smoke-admin uuid>', 'ADMIN');
   SELECT lfhe.bootstrap_grant_role('<smoke-viewer uuid>', 'VIEWER');
   ```
5. Web app against DEV: `apps/web/.env.local` with `NEXT_PUBLIC_SUPABASE_URL` and
   the **anon** key only; `npm run build && npm start`; sign in as admin, create /
   approve / activate / deactivate a source; sign in as viewer and confirm the
   create form is refused.
6. Automated smoke test:
   ```bash
   export LFHE_SMOKE_SUPABASE_URL=https://<dev-ref>.supabase.co
   export LFHE_SMOKE_ANON_KEY=...            LFHE_SMOKE_DB_URL=...
   export LFHE_SMOKE_ADMIN_EMAIL=...         LFHE_SMOKE_ADMIN_PASSWORD=...
   export LFHE_SMOKE_VIEWER_EMAIL=...        LFHE_SMOKE_VIEWER_PASSWORD=...
   export LFHE_SMOKE_SERVICE_ROLE_KEY=...    # optional; DEV only; never commit
   export LFHE_SMOKE_WAIT_CRON_SECONDS=420   # optional; waits for one pg_cron tick
   python scripts/supabase_dev_smoke.py
   ```
   Checks: migrations present; password sign-in; RLS (anon/viewer); viewer
   permissions; HUMAN_ONLY refusal for anon / viewer / service_role; nested
   credential key (CG1-03) and credential-bearing URL (CG1-08) rejected via RPC;
   admin source lifecycle; audit
   events + hash-chain verification; pg_cron job scheduled and (optionally) run.
   The script refuses to run unless `lfhe.deployment_environment = 'DEV'`.
7. Unset the exported variables afterwards.

## Phase 2 additions

* Migrations `20261011001600_claims_pipeline.sql` and `20261011001700_claim_jobs.sql` are applied with
  the same `scripts/apply_migrations.py` command (17 migrations in total).
* The smoke script adds Phase 2 checks: closed taxonomy seeded (62 items), viewer can read claims
  (`CLAIM_READ`), anon cannot, viewer / ADMIN / service_role cannot record a claim review, humans cannot
  call the worker ingestion function. The expected viewer permissions are now
  `SOURCE_READ, ARTICLE_READ, CLAIM_READ`. The smoke test creates no claims.
* K-05 real-source validation: `docs/runbooks/k05-real-source-validation.md`.
