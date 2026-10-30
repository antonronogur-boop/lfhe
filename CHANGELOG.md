# Changelog

All material project changes are recorded here.

## [Unreleased] — Phase 7 CR7-05 (PO decision: automatic analysis, human control only where it matters)

Migration `20261011004500_cr7_05_report_autopilot.sql` (46 migrations), `autopilot.py` worker chain, `/inbox`; see
`docs/cr7-05.md`. CG7 OPEN.

## [Unreleased] — Phase 7 CR7-04 (proven defect from the P7-04 walkthrough)

Migration `20261011004400_cr7_04_assessment_rejection_visibility.sql` (45 migrations), one bounded M07 attribution
repair run in `assessment_pipeline.py`, rejection reasons in the web UI; see `docs/cr7-04.md`. CG7 OPEN.

## [Unreleased] — Phase 7 CR7-03 (PO 2026-10-30, SPEC_INDEX 31)

Status: PO approved · implemented on branch `cr7-03-pilot-operational-path` · automated tests and technical browser E2E
PASS · not yet applied to DEV · human P7-04 outstanding · 0 / 6 real pilot cycles (first measured cycle: REPLAY).
Repository total: 44 migrations.

### Added
- Migration `20261011004300_cr7_03_workflow_job_requests.sql`: HUMAN_ONLY `request_workflow_job` /
  `request_pending_claim_extractions` (M02 / M04 / M05 / M06 / M07 / M08 requests; idempotent, audited
  `WORKFLOW_JOB_REQUESTED`, role-bound, cutoff-checked, manual-promotion rule for M07), append-only
  `workflow_job_requests`, status view `workflow_job_request_status`.
- Web: application shell with role-aware navigation, dashboard, design system (`app/globals.css`, `components/`),
  claims (queues, intake, detail), `/events`, `/assessments`, `/jobs`, decision queues (`/queue/review|security|release`),
  pilot workspace summary and UX-finding workflow, loading / error / empty / locked states.
- Browser E2E (`tests/e2e/`): local test-only stack (PostgreSQL + PostgREST + auth gateway + Next.js + worker with a
  SYNTHETIC_TEST_ONLY model) and a multi-role Playwright test of the full path to release and pilot completion.
- Docs: `docs/cr7-03.md`, runbook section for the operational path; DEV smoke checks for CR7-03.

### Changed
- Web pages restyled (reports, sources, pilot); claim actions return to the originating page; sign-in lands on the dashboard.
- No Phase 1–6 semantics changed; no dependency upgraded.

## [Unreleased] — Phase 1 Foundation

### Added
- P1-01 Repository skeleton, CI workflow (gitleaks + repository secret scan +
  tests), SPEC_INDEX, PROJECT_STATUS, ADRs 0001–0007.
- P1-02 Environment separation: static settings rules + database-recorded
  deployment environment checked at connect time.
- P1-03 Database foundation: `lfhe` schema, canonical enums, migration runner
  with checksums.
- P1-04 Authentication and RBAC: roles/permissions, HUMAN_ONLY SECURITY DEFINER
  functions with negative tests (guardrail 2).
- P1-05 Audit foundation: serialised SHA-256 hash chain, concurrency proof,
  independent verifier, chain-head export (guardrail 1).
- P1-06 Source registry (DB + web UI): approval and activation workflow.
- P1-07 Jobs: idempotent table queue, leases, backoff, scheduler entry point.
- P1-08 Collection framework: polite HTTP client, RSS/Atom, sitemap, official
  API and HTTP-fetch adapters, collection runs and error logging.
- P1-09 Articles, versioned immutable original-language snapshots, canonical
  clean text (`lfhe-clean-text` 1.0.0), write-once object store, span primitives.
- P1-10 Prompt-version source of truth and model-run traceability (guardrail 3),
  canonical JSON, prompt registry tooling, FakeProvider runner.
- CG1-01 Retryable / non-retryable item failure classification; no job retry for permanent failures.
- CG1-02 Snapshot identity = canonical source state; duplicates write no raw object; reconciliation report.
- CG1-03 Recursive credential-key validator (DB authoritative; Python + TS mirrors).
- CG1-04 Redirect hops checked against the source domain; explicit final-origin provenance.
- CG1-05 Model runs record envelope, input-set and context-set hashes (DB-verified set hashes).
- CG1-06 Python 3.13 hash-checked lock, pinned gitleaks in CI, DEV Supabase smoke script/runbook.
- P1-11 F1–F10 acceptance suite, backup/restore round-trip test, documentation.

## CR7-06 — LocalObjectStore Windows fix (release PDF)
- `put_if_absent` removed its temporary file after setting it read-only; Windows refuses to delete read-only files (WinError 5), so `RENDER_RELEASE_PDF` failed on DEV. The temporary name is now removed while writable and the final object is made read-only afterwards. Regression test added. No migration, no schema or behaviour change on Linux.
- `scripts/verify_release.py <report-code> <storage-root>`: read-only post-release check (DB PDF hash, PDF file on disk, manifest hash, `pilot_cycles = 0`, audit chain). Integration test added.
