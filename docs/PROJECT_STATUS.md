# LFHÉ — Project status

| Field | Value |
| --- | --- |
| Current phase | Phase 1 — Foundation |
| Current gate | Control Gate 1 report submitted (2026-10-11); **awaiting Product Owner decision** |
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
| L-01 | Web UI (source administration) type-checked, unit-tested and built, but **not** exercised end-to-end against a live Supabase project | Server-side enforcement is tested at DB level; E2E against a DEV Supabase project before first deployment |
| L-02 | S3 object-storage backend implemented but not exercised (LOCAL backend tested) | Test against the chosen bucket before PROD |
| L-03 | pg_cron schedule migration is conditional and was not run (no pg_cron in the local cluster) | Verify on the Supabase DEV project |
| L-04 | CI workflow defined but not executed on GitHub from this environment; gitleaks not run locally (repository scanner + tests run) | First push runs CI |
| L-05 | Per-host politeness interval is per worker process | Single collector worker in Phase 1; shared limiter if scaled |
| L-06 | Audit writes are serialised by one advisory lock (by design, guardrail 1) | Acceptable at Phase 1 volume; revisit with measurements |
| L-07 | Raw object written before the DB row: a DB failure can leave an unreferenced, content-addressed object | Harmless (write-once, hash-named); garbage collection later |
| L-08 | No down-migrations | Reversibility = transactional apply per file + fix-forward + backup/restore (round-trip tested) |
| L-09 | Model-run foundation uses FakeProvider only; no real provider adapter, no per-module model selection | Phase 2 |
| L-10 | Language detection (py3langid) is a fallback only; html `lang` / feed language take precedence | Recorded per snapshot in `language_method` |

