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

## Phase 3 additions (incl. CG3 corrective pass and final correction)

* Migrations `20261011001800` … `20261011002600` (9 files: lineage, events, phase3 jobs, 2100, 2200,
  2300 as-of context, 2400 full-split terminal, 2500 origin identity, 2600 knowledge-bound
  retractions) are applied with the same `scripts/apply_migrations.py` command (27 migrations in
  total). Already applied files are skipped by checksum; a changed applied file is refused.
* The smoke script adds 10 Phase 3 checks (11 with `LFHE_SMOKE_SERVICE_ROLE_KEY`): Phase 3 tables
  present with RLS, `claim_status_auto_rules` empty, every SECURITY DEFINER pins `search_path`,
  viewer can read events / anon cannot, viewer and ADMIN cannot MERGE or validate lineage,
  service_role cannot MERGE, humans cannot call the M04/M05 ingestion functions.

## Phase 4 additions

* Migrations `20261011002700` … `20261011003300` (7 files: baselines / reference contexts, relevance,
  assessments, challenges, analytical review, trends / indicators, phase 4 jobs) are applied with the
  same `scripts/apply_migrations.py` command (34 migrations in total). Already applied files are
  skipped by checksum.
* The smoke script adds 10 Phase 4 checks (11 with `LFHE_SMOKE_SERVICE_ROLE_KEY`): Phase 4 tables
  present with RLS, `final_analytic_confidence` has exactly one owner (DC-01), likelihood vocabulary
  is exactly the canonical CR4-01 set in rank order (migration 3400), viewer can read assessment versions / anon cannot, viewer and ADMIN cannot APPROVE
  an assessment or dispose of an M08 flag, service_role cannot APPROVE, humans cannot call the
  M06/M07/M08 ingestion functions. Expected result without the service-role key: 42/42 PASS. The
  smoke test creates no Phase 4 data.
* Worker configuration for Phase 4 jobs: `LFHE_M06_MODEL_CONFIGURATION_ID`,
  `LFHE_M07_MODEL_CONFIGURATION_ID`, `LFHE_M08_MODEL_CONFIGURATION_ID` (registered rows, low-variance).
* CR4-01 (PO decision 2026-10-20): migration `20261011003400_p4_likelihood_vocabulary.sql` → 35
  migrations in total; the smoke total stays 42/42 PASS (the former "vocabulary empty" check was
  replaced, not added).

## Phase 5 additions

* Migrations `20261011003500` … `20261011003700` (reports / candidate pool / selection + JCS, report
  versions / items / statements / sources / removal review, report renders) are applied with the same
  `scripts/apply_migrations.py` command (38 migrations in total).
* The smoke script adds 8 Phase 5 checks (9 with `LFHE_SMOKE_SERVICE_ROLE_KEY`): report tables present
  with RLS, SQL RFC 8785 JCS hash equals the Python canonical hash, report versions DRAFT_VERSION / renders
  PREVIEW only, viewer can read the candidate pool / anon cannot read report versions, viewer cannot
  select report content, ADMIN cannot edit a report version, (service_role cannot freeze a selection),
  humans cannot call the M09 ingestion / render recording functions. Expected result without the
  service-role key: 50/50 PASS. The smoke test creates no report.
* Worker configuration for Phase 5 jobs: `LFHE_M09_MODEL_CONFIGURATION_ID` (registered, low-variance).
  The web workspace is at `/reports`.

## Phase 6 additions

* Migrations `20261011003800_p6_qa.sql` and `20261011003900_p6_approval_release.sql` are applied with the
  same `scripts/apply_migrations.py` command (40 migrations in total).
* The smoke script adds 11 Phase 6 checks (12 with `LFHE_SMOKE_SERVICE_ROLE_KEY`): QA / approval / release
  tables present with RLS, no application role can write them, only authenticated humans may EXECUTE
  `release_report`, Phase 6 authority held only by REVIEWER / SECURITY_REVIEWER / RELEASE_AUTHORITY,
  RELEASED guard and immutability triggers present, viewer can read QA results / releases, anon cannot read
  releases, viewer cannot release, ADMIN cannot release or approve content, (service_role cannot release),
  humans cannot call the M10 / QA-result / release-PDF worker functions, release eligibility fails closed
  for an unknown version. Expected result without the service-role key: **61/61 PASS**. The smoke test
  creates no QA run, approval or release.
* Worker configuration for Phase 6 jobs: `LFHE_M10_MODEL_CONFIGURATION_ID` (registered, low-variance) for
  RUN_REPORT_QA; RENDER_RELEASE_PDF needs headless Chromium (`LFHE_CHROMIUM_PATH`, or chromium /
  google-chrome on PATH; `LFHE_CHROMIUM_NO_SANDBOX=1` only on hosts without user-namespace sandboxing)
  and the configured object storage (release PDFs are stored write-once under `release-pdf/sha256/…`).
  The prompt bundle `packages/prompts/M10_QA_AUDITOR/1.0.0` is registered with
  `scripts/prompt_registry.py register` and activated by a human (PROMPT_ACTIVATE) as for M02–M09.

### CR6-01 addition

* Migration `20261011004000_p6_cr6_01_manifest_baseline_ids.sql` (release manifest `baseline_version_ids`) →
  41 migrations in total; the smoke adds one check (release manifest carries and requires
  `baseline_version_ids`). Expected result without the service-role key: **62/62 PASS**.

## Phase 7 additions

* Migration `20261011004100_p7_pilot_instrumentation.sql` (pilot measurement tables, views and HUMAN_ONLY
  pilot functions; no Phase 1–6 object changed) → **42 migrations** in total.
* The smoke adds 6 Phase 7 checks: pilot tables present with RLS (13/13); no application role writes a pilot
  table and the worker cannot read pilot data; 16 HUMAN_ONLY pilot functions not executable by worker /
  service_role / anon; viewer and ADMIN cannot create pilot cycles (PILOT_MANAGE); PILOT_LEAD holds no
  analytical / QA / approval / security / release authority; applied migrations 1–41 match
  `database/migrations.lock.json`. Expected result without the service-role key: **68/68 PASS**. The smoke
  creates no pilot record. Pilot operation: `docs/runbooks/phase7-pilot.md`.

### CR7-01 addition

* Migration `20261011004200_cr7_01_provider_fixed_sampling.sql` → **43 migrations**; the smoke adds one check
  (`provider_fixed_sampling` allowed for anthropic and never combined with temperature). Expected: **69/69 PASS**.
