# LFHÉ — Project status

| Field | Value |
| --- | --- |
| Current phase | Phase 1 — Foundation |
| Current gate | Control Gate 0 APPROVED (2026-10-11); working towards Control Gate 1 |
| Next authorised action | Complete P1-01 … P1-11, then return the Control Gate 1 report and STOP |

## Phase 1 progress

| Step | Status |
| --- | --- |
| P1-01 Repository and project skeleton | in progress |
| P1-02 Environment separation | pending |
| P1-03 Database foundation | pending |
| P1-04 Authentication and RBAC | pending |
| P1-05 Audit foundation | pending |
| P1-06 Source Registry | pending |
| P1-07 Jobs and scheduling | pending |
| P1-08 Collection framework | pending |
| P1-09 Article and original-language snapshot storage | pending |
| P1-10 Model-run and prompt-version foundation | pending |
| P1-11 Security / integration / acceptance tests | pending |

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

## Known issues

_None yet._
