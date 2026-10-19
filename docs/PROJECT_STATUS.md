# LFHÉ — Project status

| Field | Value |
| --- | --- |
| Current phase | Phase 2 — Claim Pipeline (implementation complete) |
| Current gate | Control Gate 1 APPROVED (2026-10-11). Control Gate 2 evidence submitted (docs/control-gate-2-report.md); DEV 18/18 migrations + smoke 22/22 PASS and K-05 COMPLETED (6/8 PASS, 2 BLOCKED_BY_ROBOTS accepted by the PO) on 2026-10-19; awaiting SD-01…12 confirmation and the CG2 decision |
| Next authorised action | **None.** Phase 3 must not start without explicit Product Owner approval |

## Phase 2 progress (Addendum v1.0)

| Step | Status |
| --- | --- |
| P2-00 Baseline texts stored under docs/specs | done |
| P2-01 Allow-listed model settings (L-13), Anthropic adapter, low-variance guard | done |
| P2-02 Claim / entity / taxonomy schema, DB-authoritative QA-D18, human-only review | done |
| P2-03 M02/M03 prompt bundles 1.0.0 + schemas, deterministic M01 inputs | done |
| P2-04 QA-D18 Python mirror, QA-S18 fidelity foundation | done |
| P2-05 Orchestration, transparent repair, jobs, worker | done |
| P2-06 Human review UI (/claims), DEV smoke additions | done |
| P2-07 Acceptance corpus + §16 metrics, K-05 script | done |
| P2-08 Docs, CI, CG2 report | done |

## Phase 1 progress

| Step | Status |
| --- | --- |
| P1-01 Repository and project skeleton | done |
| P1-02 Environment separation | done |
| P1-03 Database foundation | done |
| P1-04 Authentication and RBAC | done |
| P1-05 Audit foundation | done |
| P1-06 Source Registry | done |
| P1-07 Jobs and scheduling | done |
| P1-08 Collection framework | done |
| P1-09 Article and original-language snapshot storage | done |
| P1-10 Model-run and prompt-version foundation | done |
| P1-11 Security / integration / acceptance tests | done |

## CG1 corrective pass

| Item | Status |
| --- | --- |
| CG1-01 Non-retryable item failures | resolved (docs/collection-semantics.md) |
| CG1-02 Snapshot identity / orphan objects | resolved (docs/snapshot-identity.md) |
| CG1-03 Recursive credential-key rejection | resolved (migration 1000) |
| CG1-04 Cross-domain redirects | resolved (docs/collection-semantics.md) |
| CG1-05 Model-run envelope / input / context hashes | resolved (docs/model-run-traceability.md) |
| CG1-07 robots.txt fail-closed + non-poisoned cache | resolved (docs/collection-semantics.md, robots section) |
| CG1-08 Credentials in URL values | resolved (migration 1300) + CG1-08A canonicalisation and source URL field validation (migration 1400) |
| CG1-06 Toolchain / CI / DEV Supabase | resolved — lock + Python 3.13 + gitleaks + GitHub CI PASS (run 38143832019) + DEV Supabase: 15/15 migrations, smoke 18/18 PASS incl. CG1-08, CG1-08A and pg_cron (2026-10-11 17:51) |

PO decisions on D-01…D-06 (2026-10-11): D-01 approved with condition (transactional
migration + append-only checksummed history + fix-forward + tested backup/restore;
transactional rollback is **not** a schema downgrade); D-02, D-03, D-05 approved;
D-04 approved as Phase 1 deferral (replay-grade availability required before REPLAY
testing); D-06 approved conditionally (CG1-06 verification since completed: CI + DEV smoke PASS).

## Decision register

| ID | Topic | Class | Status / decision |
| --- | --- | --- | --- |
| K-01 | Worker hosting | NON-BLOCKING | Phase 1 runs workers locally; hosting choice + ADR before first deployment |
| K-02 | Scheduler | NON-BLOCKING | pg_cron enqueue-only, calling `lfhe.enqueue_due_collections()` |
| K-03 | Queue | NON-BLOCKING | `processing_jobs` table + `SKIP LOCKED` |
| K-04 | Per-source retention rights | NON-BLOCKING | `retention_mode` per source; METADATA_ONLY sources cannot ground material claims (QA-D18) |
| K-05 | Real-source collection validation (approved set K05-01…08) | COMPLETED 2026-10-19 | 6/8 PASS (F3/F4/F5); K05-03 af.mil and K05-04 defense.gov BLOCKED_BY_ROBOTS — accepted by the PO as controlled fail-closed outcome; K05-02 collected via HTTP_FETCH (PO decision); docs/k05-report-20261019.json |
| K-06 | Separation of duties | NON-BLOCKING | Configurable; one person may hold several roles in the prototype, logged |
| K-07 | Region | NON-BLOCKING | EU region default |
| K-08 | Canonical JSON | NON-BLOCKING | RFC 8785 JCS + SHA-256 (ADR-0003) |
| K-09 | Template / renderer version + PDF hash in manifest | DEFER (P5–P6) | |
| K-10 | M05 automatic application scope | DEFER (P3) | CREATE → CANDIDATE, UPDATE → AI-originated version; MERGE / SPLIT / SUPERSEDE human |
| K-11 | GS-001 Patriot-trap test channel | DEFER (P4) | Decide at raw-input materialisation |
| K-12 | Canonical evidence-span field name | RESOLVED (P2) | `claims.evidence_span_original` (v1.2.2), verified by the database |
| K-13 | QA-04 naming | NON-BLOCKING | Event time is never an eligibility criterion |
| **DC-01** | **final_analytic_confidence — single source of truth** | **DEFERRED CONSTRAINT (PO guardrail 4)** | Phase 1 creates **no** confidence column anywhere. `human_reviews.modified_value` is a change record, never the canonical store of final confidence. Phase 4 defines canonical ownership on the approved assessment version; no generic approval table may hold an independently mutable copy. |

## Known limitations at Control Gate 1

| ID | Limitation | Impact / plan |
| --- | --- | --- |
| L-01 | Auth/RLS/RPC paths used by the web UI verified on DEV Supabase (smoke 16/16); the Next.js UI itself not yet clicked through in a browser against DEV | Manual UI walkthrough on DEV (non-blocking) |
| L-02 | S3 object-storage backend implemented but not exercised (LOCAL backend tested) | Test against the chosen bucket before PROD |
| L-03 | resolved: pg_cron job scheduled and ran successfully on DEV Supabase | — |
| L-04 | resolved: GitHub CI run 38143832019 green (secret-scan incl. gitleaks, python-tests, web) | — |
| L-05 | Per-host politeness interval is per worker process | Single collector worker in Phase 1; shared limiter if scaled |
| L-06 | Audit writes are serialised by one advisory lock (by design, guardrail 1) | Acceptable at Phase 1 volume; revisit with measurements |
| L-07 | Duplicates write nothing (CG1-02); an orphan object is still possible after a crash between object write and DB insert, or a race with differing raw bytes | Reported by `scripts/object_store_reconcile.py` (report-only) |
| L-08 | No down-migrations (D-01 approved with condition) | Transactional apply + checksummed append-only history + fix-forward + tested backup/restore; transactional rollback is not a schema downgrade |
| L-09 | Anthropic adapter implemented and tested with a mocked transport; **no real provider call has been made** (no key / no egress in the build environment); per-module model configuration via LFHE_M02/M03_MODEL_CONFIGURATION_ID | Real-provider smoke run by the PO (DEV) |
| L-10 | Language detection (py3langid) is a fallback only; html `lang` / feed language take precedence | Recorded per snapshot in `language_method` |

| L-11 | A later *scheduled* collection re-requests an item that was access-denied in an earlier job (once per schedule interval; never via job retry) | Optional per-URL suppression list later |
| L-13 | resolved (P2-01): provider-specific allow-listed model settings in DB (trigger + CHECK) and Python; key only from the secret-managed environment | — |
| L-14 | Credential detection inspects key names and URL userinfo/parameter names; a secret placed in a free-text value under a benign key, or in a URL path segment, is not detected | Operator guidance; no free-text secrets in config |
| L-12 | Snapshots created before migration 0900 have no `source_state` (test databases only) | Next collection creates a new version with state |

## Known limitations at Control Gate 2

| ID | Limitation | Impact / plan |
| --- | --- | --- |
| L-15 | QA-S18 deterministic layer uses closed marker lexicons (en, uk, ru, pl, hu, de, fr) and digit-number comparison; it is a safety net, not a semantic oracle; other languages get the quantity check only | Model self-check + human review remain; extend lexicons by controlled change |
| L-16 | Phase 2 has no authoritative rule that makes a claim high impact (v1.2 reasons refer to Phase 3+ objects); default `high_impact = false`, humans can mark | Rules arrive with events / assessments (Phase 3–4) |
| L-17 | `claim_status_auto_rules` is empty; no automatic corroboration exists (M04 is Phase 3) | Guard and revalidation are tested with a synthetic rule |
| L-18 | `/claims` UI built, type-checked and unit-tested; not yet clicked through on DEV with real claims | Walkthrough after the first real extraction |
| L-19 | Instruction-like source detection is pattern based (en + a few uk/pl/hu/ru phrases) | Flag only adds human review; never removes evidence |
