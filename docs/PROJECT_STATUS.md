# LFHÉ — Project status

| Field | Value |
| --- | --- |
| Current phase | **Phase 6 — QA, Approval & Release: ACCEPTED AND CLOSED** (CG6 APPROVED 2026-10-23, docs/specs/PO_Decision_2026-10-23_Control_Gate_6.md). Phases 1–6 ACCEPTED AND CLOSED. Phase 7 NOT authorised and NOT started |
| Earlier gate | **Control Gate 2 APPROVED** by the PO on 2026-10-19 (docs/control-gate-2-report.md): DEV 18/18 migrations + smoke 22/22 PASS, K-05 CLOSED and ACCEPTED (6/8 PASS; K05-03, K05-04 BLOCKED_BY_ROBOTS accepted), SD-01…SD-12 approved. Commits: implementation/CI baseline `1b31ed5`; K-05 run on `613f61a`; final documentation commit `40c00ff` |
| Earlier gate (CG3) | **CONTROL GATE 3 — APPROVED** by the PO on 2026-10-19 (docs/specs/PO_Decision_2026-10-19_Control_Gate_3.md): CG3-01 RESOLVED; CG3-02, CG3-03 RESOLVED / ACCEPTED; knowledge-bound retraction correction RESOLVED; SD3-01…SD3-12 APPROVED; SD3-13 replaced by the approved knowledge-bound retraction semantics (migration 2600); acceptance criteria 14/14, Phase 3 tests 63/63, Phase 1+2 regression 369/369, web 21/21; DEV 27/27 migrations, smoke 32/32 PASS, audit chain verified (108 entries). Optional service_role smoke check not run — NON-BLOCKING. Final code commit `128f1a7`; DEV evidence commit `106ecd9` |
| Earlier gate (CG4) | **CONTROL GATE 4 — APPROVED** by the PO on 2026-10-20 (docs/specs/PO_Decision_2026-10-20_Control_Gate_4.md): P4-00…P4-09 ACCEPTED; SD4-01…SD4-18 APPROVED; CR4-01 RESOLVED (migration 3400); CR4-02 APPROVED / CLOSED; acceptance criteria 20/20; full suite 500/500 (Phase 4 68/68, Phase 1–3 432/432); web 21/21; prompt lock PASS; secret scan / gitleaks clean; DEV 35/35 migrations, smoke 42/42 PASS (Phase 4 checks 10/10), audit chain verified (124 entries). Optional service_role smoke check NON-BLOCKING. CI run 39477359815 success. Evidence commit `413ef3e` |
| Earlier gate (CG5) | **CONTROL GATE 5 — APPROVED** by the PO on 2026-10-23 (docs/specs/PO_Decision_2026-10-23_Control_Gate_5.md): P5-00…P5-10 ACCEPTED; SD5-01…SD5-20 APPROVED; no change requests; CG5 criteria 22/22; acceptance corpus 30/30; full suite 532/532 (Phase 5 32/32, Phase 1–4 500/500); web 29/29, TypeScript and production build PASS; prompt lock PASS; secret scan / gitleaks clean; JCS / SHA-256 parity verified; DEV 38/38 migrations, smoke 50/50 PASS (Phase 5 checks 8/8), audit chain verified (132 entries), pg_cron active. Optional service_role smoke check NON-BLOCKING. Evidence commit `7007cbf` |
| Earlier gate (CG6) | **CONTROL GATE 6 — APPROVED** by the PO on 2026-10-23 (docs/specs/PO_Decision_2026-10-23_Control_Gate_6.md): P6-00…P6-10 ACCEPTED; SD6-01…09, SD6-11…19 APPROVED; SD6-10 APPROVED AS CORRECTED BY CR6-01; **CR6-01 RESOLVED AND CLOSED** (migration `20261011004000`, 3800/3900 unchanged); no remaining change requests; full suite 563/563 (Phase 6 31/31, Phase 1–5 532/532); web 35/35, TypeScript and production build PASS; prompt lock PASS; secret scan / gitleaks clean; mandatory CG6 metrics 0 violations; DEV 41/41 migrations, smoke 62/62 PASS, audit chain 140 entries OK (docs/dev-smoke-20261023-cr6-01.json); CI green (run 39986425665 on `9ceca46`) |
| Current gate | None open — CG1–CG6 APPROVED and CLOSED |
| Next authorised action | **None — STOPPED after CG6 closure.** Phase 7 only after a versioned Phase 7 baseline and explicit PO authorisation (SD-12). Non-blocking follow-on items: `/reports` (incl. QA / release views) browser click-through on DEV, K-11 / GS-001 Patriot-trap test channel, real-provider trial (incl. M10-S detection quality), Phase 4 review UI, optional service-role smoke, Next.js security dependency update (tracked separately, to be resolved before any externally exposed or operational deployment — PO, CG6). |

## Phase 6 progress (Addendum v1.0) — ACCEPTED AND CLOSED (CG6 APPROVED 2026-10-23)

| Step | Status |
| --- | --- |
| P6-00 Baseline + PO authorisation stored under docs/specs, SPEC_INDEX rows 22–23 | done |
| P6-01 Persistence / RBAC foundation (migrations 3800, 3900: QA, acknowledgement, approval, security, PDF, decision, manifest, RELEASED tables; RLS; HUMAN_ONLY functions) | done |
| P6-02 M10-D deterministic QA (`lfhe.run_m10d`, 25 checks, fail closed, no model_run) | done |
| P6-03 M10-S semantic QA auditor (M10_QA_AUDITOR 1.0.0, qa_inputs, ingestion of the stored model output) | done |
| P6-04 Combined QA + warnings (`record_qa_result`, reruns, `acknowledge_qa_warning`) | done |
| P6-05 Content approval + security review (`decide_report_content`, `decide_security_review`) | done |
| P6-06 PDF release artifact (headless Chromium, write-once storage, SHA-256 binding) | done |
| P6-07 Release eligibility + decision + manifest (`p6_release_checklist`, `decide_release`, atomic `release_report`, JCS manifest, correction path) | done |
| P6-08 Workspace UI (`/reports/[id]` qa + release views, PDF download) | done |
| P6-09 Acceptance corpus 41/41 (CG6 metrics 0), RBAC sweep, injection, atomicity, regression; CI | done |
| P6-10 DEV smoke P6 checks (11), docs, CG6 report (docs/control-gate-6-report.md) | done |
| CR6-01 manifest `baseline_version_ids` (migration 4000, tests/integration/test_p6_cr6_01.py) | done — RESOLVED AND CLOSED (CG6 2026-10-23) |
| DEV apply 4000 + smoke (PO, 2026-10-23) | done — 41 migrations, smoke 62/62 PASS |
| DEV apply 3800–3900 + smoke (PO, 2026-10-23) | done — 40 migrations, smoke 61/61 PASS, audit chain ok, 136 entries (docs/dev-smoke-20261023-phase6.json) |

## Phase 5 progress (Addendum v1.0) — ACCEPTED AND CLOSED (CG5 APPROVED 2026-10-23)

| Step | Status |
| --- | --- |
| P5-00 Baseline + PO authorisation stored under docs/specs, SPEC_INDEX rows 19–20 | done |
| P5-01 Reports, candidate pool, HUMAN selection, frozen selection sets + RBAC (migration 3500) | done |
| P5-02 Report versions / items / statements / statement sources (3600) | done |
| P5-03 Canonical JSON: RFC 8785 JCS in SQL (parity with Python) + SHA-256 version hash (3500 / 3600) | done |
| P5-04 M09_EXECUTIVE_EDITOR 1.0.0 bundle + deterministic input builder | done |
| P5-05 M09 ingestion (one validator, fail closed) + length / removal review (3600) | done |
| P5-06 Provenance-preserving human edits, immutable versioning (3600) | done |
| P5-07 Deterministic HTML / print-ready preview rendering, EDIT_REPORT / RENDER_REPORT jobs (3700) | done |
| P5-08 Analyst report workspace UI (`/reports`) | done |
| P5-09 Acceptance corpus (§27 metrics), security / adversarial tests, regressions | done |
| P5-10 DEV smoke P5 checks, docs, CG5 report (docs/control-gate-5-report.md); CI run 39652571441 success on `71ede49` | done |
| DEV apply 3500–3700 + smoke (PO, 2026-10-23) | done — 38 migrations, smoke 50/50 PASS, audit chain ok, 132 entries (docs/dev-smoke-20261023-phase5.json) |

## Phase 4 progress (Addendum v1.0) — ACCEPTED AND CLOSED (CG4 APPROVED 2026-10-20)

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
| K-09 | Template / renderer version + PDF hash in manifest | RESOLVED (P6-07) | Release manifest carries template version / hash, renderer version / hash and PDF SHA-256 (docs/qa-release-design.md §5) |
| K-10 | M05 automatic application scope | RESOLVED (P3) | CREATE → CANDIDATE, UPDATE → AI-originated version pending review (claims only added); MERGE / SPLIT / SUPERSEDE / REJECT human-only (docs/lineage-events.md) |
| K-11 | GS-001 Patriot-trap test channel | NON-BLOCKING follow-on (CG4 decision 2026-10-20) | Decide at raw-input materialisation; does not reopen CG4 |
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

## Known limitations at Control Gate 5

| ID | Limitation | Impact / plan |
| --- | --- | --- |
| L-36 | New-fact / new-judgment / strengthening / operational guards on report text are deterministic lexical heuristics (numbers, capitalised names, causal and certainty lexicons); they can miss a purely semantic change and can refuse a legitimate capitalised word absent from the sources | Fail-closed direction; semantic QA is Phase 6 (M10-S); human edits re-validated by the same rules |
| L-37 | `/reports` workspace built, type-checked, unit-tested and its server-side reads / RPCs tested as real `authenticated` sessions; not yet clicked through in a browser against DEV | Manual walkthrough on DEV (non-blocking, as L-01 / L-18) |
| L-38 | No PDF in Phase 5: the HTML carries the print layout; PDF rendering and the PDF hash belong to the Phase 6 release manifest (K-09) | Phase 6 |
| L-39 | M09 quality is a model property; measured with scripted outputs (sound, naive, adversarial); no real-provider call (L-09) | Real-provider trial non-blocking |
| L-40 | One report item derives from one candidate; a single report statement cannot merge statements of two different assessments (conservative: no false independent-evidence impression) | Separate sentences / items; revisit only by PO decision |
| L-41 | Full suite ≈ 2 min 50 s (as-of recursion, L-26 / L-35) | Materialise bounds if measurements require |

## Known limitations at Control Gate 6

| ID | Limitation | Impact / plan |
| --- | --- | --- |
| L-42 | M10-S detection quality is a model property; verified with a rule-based stand-in that reads only the envelope and with labelled scripted behaviours (obedient, repairing, fabricating, failing); no real-provider call | Real-provider trial non-blocking (SD6-11) |
| L-43 | Chromium PDF bytes are not claimed reproducible (DC6-04): every distinct byte artifact has its own identity; only the one chosen by the release transaction is released | By design |
| L-44 | Prompt Pack v1.2.1 §11 (referenced by CG0) is not stored in the repository; the only recovered higher-authority manifest requirement, `baseline_version_ids` (PG-07), is implemented (CR6-01) | No speculative fields (PO decision 2026-10-23) |
| L-45 | `/reports` QA / release views built, type-checked, unit-tested and their reads / RPCs tested as real `authenticated` sessions; not yet clicked through in a browser against DEV | Manual walkthrough on DEV (non-blocking, as L-37) |
| L-46 | The RENDER_RELEASE_PDF worker needs headless Chromium and object storage on its host; `--no-sandbox` only in root containers / CI runners without user namespaces | Worker hosting decision (K-01) |
| L-47 | `next build` printed a Next.js security-vulnerability upgrade reminder (first run stopped, retry passed; CI web job green) | Dependency upgrade = separate PO decision |
| L-48 | Full suite ≈ 4 min (as-of recursion, Chromium PDFs) | Acceptable for CI |
