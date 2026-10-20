# LFHÉ — Project status

| Field | Value |
| --- | --- |
| Current phase | **Phase 4 — Relevance, Assessment & Challenge: IMPLEMENTED (P4-00…P4-09), awaiting Control Gate 4.** Phase 3 ACCEPTED AND CLOSED (2026-10-19) |
| Earlier gate | **Control Gate 2 APPROVED** by the PO on 2026-10-19 (docs/control-gate-2-report.md): DEV 18/18 migrations + smoke 22/22 PASS, K-05 CLOSED and ACCEPTED (6/8 PASS; K05-03, K05-04 BLOCKED_BY_ROBOTS accepted), SD-01…SD-12 approved. Commits: implementation/CI baseline `1b31ed5`; K-05 run on `613f61a`; final documentation commit `40c00ff` |
| Current gate | **CONTROL GATE 3 — APPROVED** by the PO on 2026-10-19 (docs/specs/PO_Decision_2026-10-19_Control_Gate_3.md): CG3-01 RESOLVED; CG3-02, CG3-03 RESOLVED / ACCEPTED; knowledge-bound retraction correction RESOLVED; SD3-01…SD3-12 APPROVED; SD3-13 replaced by the approved knowledge-bound retraction semantics (migration 2600); acceptance criteria 14/14, Phase 3 tests 63/63, Phase 1+2 regression 369/369, web 21/21; DEV 27/27 migrations, smoke 32/32 PASS, audit chain verified (108 entries). Optional service_role smoke check not run — NON-BLOCKING. Final code commit `128f1a7`; DEV evidence commit `106ecd9` |
| Next authorised action | **Only remaining action: the PO Control Gate 4 closure decision.** DEV final (2026-10-20): 35 migrations, smoke 42/42 PASS, canonical likelihood vocabulary verified, audit chain verified (124 entries) — docs/dev-smoke-20261020-phase4-final.json. SD4-01…SD4-18 APPROVED; CR4-01 RESOLVED (migration 3400); CR4-02 APPROVED / CLOSED. **Phase 5 NOT authorised** |

## Phase 4 progress (Addendum v1.0)

| Step | Status |
| --- | --- |
| P4-00 Baseline + PO authorisation stored under docs/specs, SPEC_INDEX rows 15–16 | done |
| P4-01 Baselines + reference contexts + eligibility (migration 2700) | done |
| P4-02 M06 relevance: schema, bundle, inputs, human validate/override/promote/request (2800) | done |
| P4-03 Statement-centric assessments, provenance, categories, attribution, likelihood (2900) | done |
| P4-04 M07 bundle, input builder (previous assessment as-of), orchestration | done |
| P4-05 M08 structured challenge + human flag disposition (3000) | done |
| P4-06 Human analytical review, final analytic confidence (DC-01), MODIFY_AND_APPROVE (3100) | done |
| P4-07 Trends (human/manual path) and indicators (3200) | done |
| P4-08 Jobs/worker (3300), security/reproducibility tests, RBAC sweep, acceptance corpus | done |
| P4-09 DEV smoke P4 checks, docs, CG4 report (docs/control-gate-4-report.md); CI run 39308694707 success on `9d29ae8` | done |
| DEV apply 2700–3300 + smoke (PO, 2026-10-20) | done — 34 migrations, smoke 42/42 PASS, audit chain ok, 120 entries (docs/dev-smoke-20261020-phase4.json); accepted by the PO as valid evidence |
| CG4 pre-closure (PO decision 2026-10-20, SPEC_INDEX 17): CR4-01 canonical likelihood vocabulary (migration 3400), CR4-02 closed | done — DEV final: 35 migrations, smoke 42/42 PASS (docs/dev-smoke-20261020-phase4-final.json) |

## Phase 3 progress (Addendum v1.0)

| Step | Status |
| --- | --- |
| P3-00 Baseline + PO decision stored under docs/specs, SPEC_INDEX row 11 | done |
| P3-01 M04 lineage schema: proposals, human-only validation, derived independence groups, cutoff eligibility | done |
| P3-02 M05 event schema: immutable hash-bound versions, AI CREATE → CANDIDATE / UPDATE → pending version, human-only structural actions | done |
| P3-03 M04/M05 prompt bundles 1.0.0 + schemas, deterministic input builders | done |
| P3-04 Orchestration, repair, ANALYSE_LINEAGE / BUILD_EVENTS jobs, worker; migration 2100 (AI update carries claims forward) | done |
| P3-05 Acceptance corpus + §16 metrics, GS isolation test; migration 2200 (external-origin reuse) | done |
| P3-06 Docs, DEV smoke additions, CI, CG3 report | done |
| CG3-C CG3 corrective pass: 2300 as-of context (CG3-01), 2400 terminal full split (CG3-02), 2500 no name-only origin collapse (CG3-03) | done |
| CG3-F Final CG3 correction: 2600 knowledge-bound lineage retractions (replaces SD3-13) | done |
| DEV apply 1800–2600 + smoke (PO, 2026-10-19 19:05) | done — 27 migrations, smoke 32/32 PASS, audit chain ok (docs/dev-smoke-20261019-phase3.json) |

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
| K-05 | Real-source collection validation (approved set K05-01…08) | CLOSED and ACCEPTED 2026-10-19 | 6/8 PASS (F3/F4/F5); K05-03 af.mil and K05-04 defense.gov BLOCKED_BY_ROBOTS at the RSS discovery/list page (no feed endpoint resolved) — accepted controlled outcome; K05-02 via HTTP_FETCH instead of RSS_ATOM (PO decision); result: docs/k05-report-20261019.json (syntactically repaired copy; received copy and repair in docs/k05-report-20261019.PROVENANCE.md) |
| K-06 | Separation of duties | NON-BLOCKING | Configurable; one person may hold several roles in the prototype, logged |
| K-07 | Region | NON-BLOCKING | EU region default |
| K-08 | Canonical JSON | NON-BLOCKING | RFC 8785 JCS + SHA-256 (ADR-0003) |
| K-09 | Template / renderer version + PDF hash in manifest | DEFER (P5–P6) | |
| K-10 | M05 automatic application scope | RESOLVED (P3) | CREATE → CANDIDATE, UPDATE → AI-originated version pending review (claims only added); MERGE / SPLIT / SUPERSEDE / REJECT human-only (docs/lineage-events.md) |
| K-11 | GS-001 Patriot-trap test channel | DEFER (P4) | Decide at raw-input materialisation |
| K-12 | Canonical evidence-span field name | RESOLVED (P2) | `claims.evidence_span_original` (v1.2.2), verified by the database |
| K-13 | QA-04 naming | NON-BLOCKING | Event time is never an eligibility criterion |
| **DC-01** | **final_analytic_confidence — single source of truth** | **RESOLVED (P4-06)** | Phases 1–3 had no confidence column. Phase 4: the only owner is the immutable human approval row `lfhe.analytical_approvals.final_analytic_confidence` (one approval per assessment version, bound to version + hash; projected read-only by the view `assessment_version_states`). No model-written row holds it; `ai_recommended_confidence` is a separate field. Guarded by `test_final_analytic_confidence_has_exactly_one_canonical_owner` and the DEV smoke. |

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
| L-17 | `claim_status_auto_rules` is empty; no automatic corroboration exists. Phase 3: M04 only recommends; the table stays empty by baseline (DEV smoke checks it) | Guard and revalidation are tested with a synthetic rule in the test database only |
| L-18 | `/claims` UI built, type-checked and unit-tested; not yet clicked through on DEV with real claims | Non-blocking follow-on (CG2 approved) |
| L-19 | Instruction-like source detection is pattern based (en + a few uk/pl/hu/ru phrases) | Flag only adds human review; never removes evidence |

## Known limitations at Control Gate 3

| ID | Limitation | Impact / plan |
| --- | --- | --- |
| L-20 | Event clustering quality is a model property; Phase 3 measures it with scripted model outputs (conservative and deliberately over-eager). The deterministic guarantees are: AI cannot MERGE/SPLIT/SUPERSEDE/REJECT, AI updates only add claims and stay pending review, context is bounded and cutoff-filtered | Real-provider clustering evaluation together with L-09 (non-blocking for CG3) |
| L-21 | No Phase 3 review UI (not in the Phase 3 baseline); human decisions are made through the HUMAN_ONLY RPCs | UI in a later phase if the PO requests it |
| L-22 | `distinct_groups_upper_bound` is an upper bound: claims without validated lineage each count as their own group and `claims_with_unknown_lineage` must be read with it; `independence_established` is always false | By design (baseline §5: unknown stays unknown) |
| L-23 | resolved (CG3-03, migration 2500): no name-only reuse; identity only by explicit human selection or same canonical URL + name | — |
| L-24 | ANALYSE_LINEAGE / BUILD_EVENTS are enqueued explicitly; no automatic chaining after extraction | Same pattern as SD-11; later phase may automate |
| L-25 | (SD3-12, APPROVED) The knowledge bound of a human-authored event version (and of a human state change) is its evidence set — member claims and consumed versions; free-text fields are the analyst's summary of that evidence and cannot be machine-proven free of later knowledge (SD3-12) | Analyst guidance; PO decision on SD3-12 |
| L-26 | As-of evaluation is computed on read (recursive eligibility over immutable data); cost grows with version chains and run manifests | Adequate at prototype volume; materialise bounds if measurements require |
| L-27 | Human-recorded lineage without a declared `evidence_basis` is never used in REPLAY (fail closed) | Analysts should declare the evidence they relied on |
| L-28 | A lineage retraction without a declared `evidence_basis` never alters REPLAY (it applies in LIVE when recorded ≤ cutoff) | Analysts should declare the evidence a retraction relies on |

## Known limitations at Control Gate 4

| ID | Limitation | Impact / plan |
| --- | --- | --- |
| L-29 | Causal / absence / operational / vague-indicator / generic-relevance guards are deterministic lexical heuristics (English); they are a safety net, not a semantic oracle | M08 challenge + mandatory human review remain; extend lexicons by controlled change |
| L-30 | resolved (CR4-01, migration 3400): PO-defined canonical likelihood vocabulary, 7 ordered terms, no numeric bands | — |
| L-31 | Trend direction / velocity are human free text (CR4-02 APPROVED / CLOSED); no AI trend creation | A controlled, versioned vocabulary must be approved before any AI/automatic authoritative trend state or machine logic on direction/velocity |
| L-32 | No Phase 4 review UI (not in the Phase 4 baseline); human decisions go through HUMAN_ONLY RPCs | Later phase if requested |
| L-33 | Relevance/assessment/challenge quality is a model property; measured with scripted outputs (sound, naive, adversarial). No real-provider call (see L-09) | Real-provider trial non-blocking (§20) |
| L-34 | The DS-38 automatic-assessment threshold is not defined by a higher-authority document: `automatic_assessment_recommended` is advisory and gates nothing | PO decision if a threshold is wanted |
| L-35 | As-of checks are recursive on read (see L-26); full suite now ≈ 2 min 10 s | Materialise bounds if measurements require |
