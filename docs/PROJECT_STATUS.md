# LFHÉ — Project status

| Field | Value |
| --- | --- |
| Current phase | Phase 1 — Foundation |
| Current gate | Control Gate 1 NOT YET APPROVED; CG1-01…06 accepted; CG1-07/08 + CG1-PKG-01 final corrective report submitted 2026-10-11 (docs/cg1-final-corrective-report.md); K-05 real-source validation pending |
| Next authorised action | **None.** Phase 2 must not start without explicit Product Owner approval |

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
| CG1-08 Credentials in URL values | resolved (migration 1300; DB authoritative, Python/TS mirrors) |
| CG1-06 Toolchain / CI / DEV Supabase | resolved — lock + Python 3.13 + gitleaks + GitHub CI PASS (run 38143832019) + DEV Supabase: 14/14 migrations, smoke 17/17 PASS incl. CG1-08 and pg_cron (2026-10-11 17:21) |

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
| **K-05** | **Initial 5–10 source list** | **OPEN** | Product Owner to supply. No operational sources invented. Synthetic fixtures only. |
| K-06 | Separation of duties | NON-BLOCKING | Configurable; one person may hold several roles in the prototype, logged |
| K-07 | Region | NON-BLOCKING | EU region default |
| K-08 | Canonical JSON | NON-BLOCKING | RFC 8785 JCS + SHA-256 (ADR-0003) |
| K-09 | Template / renderer version + PDF hash in manifest | DEFER (P5–P6) | |
| K-10 | M05 automatic application scope | DEFER (P3) | CREATE → CANDIDATE, UPDATE → AI-originated version; MERGE / SPLIT / SUPERSEDE human |
| K-11 | GS-001 Patriot-trap test channel | DEFER (P4) | Decide at raw-input materialisation |
| K-12 | Canonical evidence-span field name | DEFER (P2) | `evidence_span_original` (v1.2.2) |
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
| L-09 | Model-run foundation uses FakeProvider only; no real provider adapter, no per-module model selection | Phase 2 |
| L-10 | Language detection (py3langid) is a fallback only; html `lang` / feed language take precedence | Recorded per snapshot in `language_method` |

| L-11 | A later *scheduled* collection re-requests an item that was access-denied in an earlier job (once per schedule interval; never via job retry) | Optional per-URL suppression list later |
| L-13 | Before Phase 2 real providers: model settings need a provider-specific allow-listed, non-secret schema; provider credentials only from approved secret management (PO, CG1-08) | Phase 2 prerequisite |
| L-14 | Credential detection inspects key names and URL userinfo/parameter names; a secret placed in a free-text value under a benign key, or in a URL path segment, is not detected | Operator guidance; no free-text secrets in config |
| L-12 | Snapshots created before migration 0900 have no `source_state` (test databases only) | Next collection creates a new version with state |
