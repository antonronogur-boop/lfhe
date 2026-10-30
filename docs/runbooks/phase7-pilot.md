# Phase 7 controlled pilot — operator runbook (P7-03, P7-04, P7-06)

Baseline: `docs/specs/LFHE_Phase7_Authoritative_Baseline_v1.0.md`. Design: `docs/pilot-design.md`.
Everything here is **public OSINT, synthetic or authorised historical public replay material only**
(§5). The application stays on DEV / localhost and is **not externally exposed** (§29 — the
Next.js security dependency update must be resolved before any exposed or operational deployment).

Never paste a password, key or token into a chat, a ticket, a commit, a prompt or a pilot record.
Credentials live only in your password manager / secret manager and your shell session.

## 0. Apply the Phase 7 migration and run the smoke (PowerShell, from `C:\Users\bdatA\lfhe`)

```powershell
git pull
python scripts/apply_migrations.py $env:LFHE_DEV_DB_URL
python scripts/supabase_dev_smoke.py | Out-File -Encoding utf8 dev-smoke-phase7.json
```

*Historical, pre-CR7-03 (2026-10-23):* **42 migrations** (new: `20261011004100_p7_pilot_instrumentation.sql`), smoke **68 / 68 PASS**
(62 earlier + 6 Phase 7 checks: pilot tables with RLS; no direct writes / no worker reads; 16 HUMAN_ONLY
pilot functions not exposed to worker / service_role / anon; viewer and ADMIN cannot create a cycle;
PILOT_LEAD holds no analytical / QA / approval / security / release authority; the 41 applied migrations
match `database/migrations.lock.json`). The smoke creates no pilot record.

**Current:** after merging CR7-03 the repository holds **44 migrations** (4200 CR7-01, 4300 CR7-03); applying them and the
smoke (+3 CR7-03 checks) is described in §3a. Roles, the cost assumption and the provider price are already recorded
(PO) — §1 and §2 are done.

## 1. Pilot roles (once)

Pilot measurement needs the new role `PILOT_LEAD` (manage cycles, comparators, cost assumptions,
prices, UX dispositions, benchmark labels). It grants **no** analytical, QA, approval, security or
release authority. Separation of duties stays as in Phase 6: the analyst (ANALYST), the reviewer
(REVIEWER), the security reviewer (SECURITY_REVIEWER) and the release authority (RELEASE_AUTHORITY)
are distinct DEV users. Every participant automatically holds `PILOT_PARTICIPATE` through these roles.

```sql
-- as an ADMIN human (USER_ROLE_MANAGE) in the app's SQL path, or as the DEV owner for bootstrap:
SELECT lfhe.bootstrap_grant_role('<pilot lead user uuid>', 'PILOT_LEAD');
```

## 2. Explicit economic inputs (before analysis)

In `/pilot` (PILOT_LEAD): **Record a cost assumption** — currency, loaded hourly cost, weekly work
hours, working weeks per year and the basis (where the figure comes from). Nothing is seeded; without
an assumption no capacity value is computed. Provider prices (for model cost) are recorded in `/pilot` → **Record a provider price** (provider,
model, currency, input / output cost per million tokens, effective from, source); a run without a matching price has **unknown** cost, never zero.

## 3. Real provider on DEV (P7-03, also needed for LIVE / REPLAY cycles)

1. Register the M07–M10 prompt bundles (registrar login, `LFHE_REGISTRAR_DATABASE_URL` in your shell):
   `python scripts/prompt_registry.py register packages/prompts/M07_INTELLIGENCE_ASSESSOR/1.0.0 …`
   (M02–M10 as needed), then an ADMIN human activates each (`lfhe.activate_prompt_version`).
2. Register one model configuration per module (registrar). For the 5.5 models (they reject `temperature`, CR7-01):
   `SELECT lfhe.register_model_configuration('anthropic', '<model id>', '{"provider_fixed_sampling": true, "max_tokens": 16000, "timeout_seconds": 300}');`
3. Run the worker on your machine with the key from your secret manager (never typed into a file):
   ```powershell
   $env:LFHE_ENV="DEV"; $env:LFHE_DATABASE_URL=<worker login from your password manager>
   $env:LFHE_M07_MODEL_CONFIGURATION_ID="<id>"   # … M02–M10 likewise
   # LFHE_ANTHROPIC_API_KEY comes from your secret manager into this shell only
   python -m lfhe_orchestrator.worker
   ```
   Every call becomes an immutable `model_run` (provider, model, configuration hash, prompt semver /
   hash, tokens, provider response id, latency); failures stay `PROVIDER_ERROR` / `SCHEMA_VALIDATION_FAILED`
   and a repair is a separate run.

**Alternative / additional controlled trial (synthetic only):** GitHub → Actions → `pilot-real-provider`
→ *Run workflow* with the model identifier. It needs the repository secret `LFHE_ANTHROPIC_API_KEY`
(GitHub → Settings → Secrets and variables → Actions; you add it, nobody else sees it). It runs one
synthetic chain through real M07 → M08 → human approval → real M09 → M10-D + real M10-S, and the
P7-BM-01 benchmark (18 seeded cases) with the real M10-S, and uploads `p7-real-provider-results`
(trial + benchmark JSON, secret-scanned) and also publishes them as run annotations; Claude reads them back with
`scripts/fetch_pilot_result.py <run id>` — nothing needs to be sent back.

## 3a. Operational path in the web UI (CR7-03) — claims → events → assessment

Apply migration `20261011004300_cr7_03_workflow_job_requests.sql` first (§0: `apply_migrations.py` applies it; expected
**44 migrations**; the smoke adds 3 CR7-03 checks — request functions not exposed to worker / service_role / anon, VIEWER and ADMIN refused, append-only request log — all PASS). Run the worker with a model configuration for **every**
module M02–M10 (`LFHE_M02_MODEL_CONFIGURATION_ID` … `LFHE_M10_MODEL_CONFIGURATION_ID`; all `anthropic /
claude-sonnet-5-5`, `provider_fixed_sampling`) and the object store settings for the release PDF. Then, as ANALYST:

1. **Claims → Article intake (M02)** — *Extract all pending* (or *Extract* per article). The worker extracts (M02) and
   classifies (M03). Job status is visible on the page and under **Pipeline jobs**.
2. **Claims → Needs review** — open each claim: original-language evidence span, source, public availability; record
   APPROVE / MODIFY_AND_APPROVE / REJECT / ESCALATE / REQUEST_REPROCESSING.
3. **Claims → All claims** — tick the claims of one development, choose the **analysis context** (the report = its mode
   and exact cutoff; or LIVE now), *Build events (M05)* (optionally *Analyse lineage (M04)*). Or **Events → New event
   from claims** (manual, with roles; CONTRADICTS keeps a denial visible).
4. **Events → <event>** — review the event version, change state (CANDIDATE → ACTIVE …), *Request relevance (M06)*,
   validate / override the relevance result. *Request assessment (M07)* is available when M06 recommends assessment, or
   after an audited *manual assessment request*. M08 runs automatically after M07.
5. **Assessments → Awaiting human review** — dispose every M08 flag, then APPROVE with the final analytic confidence and
   rationale (or REJECT / ESCALATE / REQUEST_REPROCESSING, or modify-and-approve the wording).
6. **Reports → <report> → Candidate pool** — *Refresh eligible candidates*, INCLUDE in a section, *Request M09 draft*;
   QA tab → *Request QA*.
7. REVIEWER: **QA & content approval** queue; SECURITY_REVIEWER: **Security review** queue; RELEASE_AUTHORITY:
   **Release decisions** queue (request release PDF, then release with the typed confirmation).

Every request is a HUMAN_ONLY, audited, idempotent database call (`request_workflow_job`); a repeated click while a job is
queued or running creates nothing; a re-request is possible only after a permanent failure.

**K-05 DEV corpus inventory (read-only, SQL editor)** — what the first REPLAY cycle can use:

```sql
SELECT (SELECT count(*) FROM lfhe.articles) AS articles,
       (SELECT count(*) FROM lfhe.article_snapshots) AS snapshots,
       (SELECT count(*) FROM lfhe.article_snapshots WHERE public_availability_datetime <= '2026-10-19 11:25:00+00') AS replay_eligible_snapshots,
       (SELECT count(*) FROM lfhe.claims) AS claims,
       (SELECT count(*) FROM lfhe.event_heads WHERE is_current) AS events,
       (SELECT count(*) FROM lfhe.assessment_versions) AS assessments,
       (SELECT count(*) FROM lfhe.assessment_version_states WHERE state = 'APPROVED') AS approved_assessments;
```

## 4. A pilot cycle (P7-06) — target 6 complete cycles: ≥ 2 REPLAY, ≥ 2 LIVE

1. ANALYST creates the report (`/reports`, mode and cutoff as planned). First REPLAY cycle (PO, 2026-10-30): code
   `RPT-P7-REPLAY-01`, title `LFHÉ Phase 7 pilot — REPLAY cycle 1 (K-05 DEV corpus)`, cycle label `P7-REPLAY-01`, mode
   REPLAY, cutoff `2026-10-19 13:25` Budapest (= 11:25 UTC; the form uses the web server's local time), reason
   `First measured Phase 7 REPLAY pilot cycle`; cycle `P7C-REPLAY-01`, boundary `PUBLIC_OSINT`, comparator `NONE`
   (comparable scope no). Create both only when the timed work starts — never to test.
2. PILOT_LEAD creates the cycle (`/pilot` → New pilot cycle): same mode and **exactly the same cutoff**,
   data boundary, input scope, analyst user id, provider setup; then **Bind report** (refused if mode or
   cutoff differ) and **Record comparator** (method, timed / documented baseline in whole minutes,
   comparable scope yes / no, reference). Method `NONE` is allowed but makes every productivity figure
   non-claimable.
3. ANALYST works the normal workflow. In `/pilot/<cycle>` start the timer with the current stage
   (switching stage closes the previous segment; Stop when pausing). Only active work is timed; the
   database clock is used; nothing is typed in afterwards.
4. Reviewers / security reviewer / release authority time their own stages the same way.
5. Anyone records UX findings (area, severity BLOCKING / MAJOR / MINOR / ENHANCEMENT, class).
6. At the end the analyst records the workload rating (raw NASA-TLX, 0–100 per dimension).
7. PILOT_LEAD: **Bind the report chain's model runs**, check *Measurement completeness*, then close as
   **COMPLETED** (refused while anything is missing) or **STOPPED** with the reason (§27 stop conditions,
   or the path is unusable). Closed cycles are immutable.

Terminal pilot states: the latest report version is RELEASED, RELEASE_REJECTED, SECURITY_REJECTED or
CONTENT_REJECTED — a human gate decided. Releasing inside LFHÉ is **not** operational dissemination (§7.2).

## 5. Browser end-to-end validation (P7-04) — a human in a real browser

Walk the path at least once per mode and record every problem as a UX finding (**Pilot → UX findings**):
claims (`/claims`) → events (`/events`) → assessment (`/assessments`) → report workspace
(`/reports/<id>` pool / draft / versions) → QA view (`?view=qa`) → warning acknowledgement →
content approval → security review (`?view=release`) → release decision → released artifact and
provenance inspection (PDF download, manifest hash). Automated tests do not replace this step.
BLOCKING findings stop the affected path until resolved or the path is declared unusable.

The automated browser E2E (`tests/e2e/test_pilot_path_e2e.py`, local throw-away stack with a SYNTHETIC_TEST_ONLY model)
proves the path technically; it does not replace this human validation (§17). Run it locally with
`LFHE_E2E_POSTGREST=<postgrest binary> python -m pytest tests/e2e` (PostgreSQL 16, Node 22 + `npm ci` in `apps/web`,
Playwright + Chromium); or start the stack for manual inspection with `python tests/e2e/stack.py`.

## 6. Export (P7-07)

```powershell
python scripts/pilot_export.py --cost <COST-CODE> --cycles-per-week <n> | Out-File -Encoding utf8 pilot-export.json
```

The export recomputes everything from stored records, is read-only, carries aggregate benchmark scores
only and is refused if it would contain a credential pattern. Send back `pilot-export.json`.
