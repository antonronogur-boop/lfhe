# LFHÉ — Authoritative specification index

Implementation must preserve these documents. Conflicts are resolved in the
precedence order below (Handoff Pack v1.1 §2). A Product Owner instruction never
silently weakens provenance, evidence discipline, human analytical / release
authority, the security boundary, auditability, INFORMATION_CUTOFF, the
FACT / ASSUMPTION / ASSESSMENT separation or the likelihood / confidence
separation — such a change is a REQUIREMENT CHANGE.

| # | Document | Version | Role |
| --- | --- | --- | --- |
| 1 | Explicit current Product Owner instruction | — | Highest precedence (subject to the caveat above) |
| 2 | LFHÉ System Concept | v1.0 | Intelligence / doctrinal baseline |
| 3 | LFHÉ Claude Master Specification | v1.0 | Analytical and AI-behaviour baseline |
| 4 | LFHÉ Specification Enforcement Addendum | v1.0 | Technical enforcement of 2–3 (A1–A3, G-01–G-18) |
| 5 | LFHÉ Development Specification | v1.0 | Implementation baseline |
| 6 | LFHÉ Module Prompt Baseline (cumulative) | v1.1 + v1.2 + v1.2.1 + v1.2.2 | AI module contracts; v1.2.1 §0 cumulative precedence |
| 7 | LFHÉ Gold Standard GS-001 + v1.1 Baseline Correction Addendum | GS-001 v1.1 | Regression HISTORICAL REPLAY benchmark (answer key evaluator-only) |
| 8 | LFHÉ Claude Handoff Pack | v1.1 | Development process |
| 9 | Control Gate 0 Architecture Review + PO decision (Phase 1 guardrails 1–4) | 2026-10-11 | Approved architecture (`docs/specs/LFHE_Control_Gate_0_Architecture_Review.md`) |
| 10 | Phase 2 Authoritative Baseline Addendum | v1.0 (2026-10-11) | PO replacement for the Phase 2 execution wording lost to context compression (`docs/specs/`); does not supersede 2–8 |
| 11 | Phase 3 Authoritative Baseline Addendum (Lineage & Events) | v1.0 (2026-10-19) | PO baseline for Phase 3 — M04 Lineage + M05 Event Builder (`docs/specs/LFHE_Phase3_Authoritative_Baseline_Addendum_v1.0.md`); stored before Phase 3 implementation per SD-12; does not supersede 2–9 or closed Phase 1/2 invariants |
| 12 | PO Decision — Control Gate 3 Targeted Corrective Pass (CG3-01…03) | 2026-10-19 | Approves SD3-01…SD3-11; requires as-of lineage/event context, terminal full split, no name-only external-origin collapse (`docs/specs/PO_Decision_2026-10-19_CG3_Targeted_Corrective_Pass.md`); forward-only migrations; DEV apply deferred |
| 13 | PO Decision — Final CG3 Correction (SD3-12 approved; SD3-13 replaced by knowledge-bound retractions) | 2026-10-19 | CG3-02, CG3-03 accepted; lineage retractions must be as-of aware (`docs/specs/PO_Decision_2026-10-19_CG3_Final_Correction.md`); one forward-only migration |
| 14 | PO Decision — Control Gate 3 | 2026-10-19 | **CG3 APPROVED; Phase 3 ACCEPTED AND CLOSED**; Phase 4 not authorised (SD-12) (`docs/specs/PO_Decision_2026-10-19_Control_Gate_3.md`) |
| 15 | Phase 4 Authoritative Baseline Addendum (Relevance, Assessment & Challenge) | v1.0 (2026-10-19) | PO baseline for Phase 4 — M06 Relevance, M07 Intelligence Assessor, M08 Challenger, analytical human review; baselines, reference contexts, trends, indicators (`docs/specs/LFHE_Phase4_Authoritative_Baseline_Addendum_v1.0.md`); stored before Phase 4 implementation per SD-12; does not supersede 2–9 or closed Phase 1–3 invariants |
| 16 | PO Decision — Authorise Phase 4 | 2026-10-19 | Phase 4 AUTHORISED; implementation order P4-00…P4-09; Phase 5 NOT authorised (`docs/specs/PO_Decision_2026-10-19_Authorise_Phase4.md`) |
| 17 | PO Decision — Final CG4 Pre-Closure Action | 2026-10-20 | DEV evidence for 2700–3300 accepted (34/34, 42/42); SD4-01…SD4-18 APPROVED; **CR4-01 resolved**: PO-defined canonical likelihood vocabulary (7 ordered terms, no numeric bands; explicit PO decision, not recovered from an earlier spec) via migration 3400; **CR4-02 APPROVED / CLOSED** (trend direction/velocity human free text; controlled vocabulary required before any machine use); Phase 5 NOT authorised (`docs/specs/PO_Decision_2026-10-20_CG4_PreClosure_CR4-01.md`) |
| 18 | PO Decision — Control Gate 4 | 2026-10-20 | **CG4 APPROVED; Phase 4 ACCEPTED AND CLOSED**; K-11, real-provider trial and Phase 4 review UI NON-BLOCKING follow-on items; Phase 5 NOT authorised (SD-12) (`docs/specs/PO_Decision_2026-10-20_Control_Gate_4.md`) |
| 19 | Phase 5 Authoritative Baseline Addendum (Executive Reporting) | v1.0 (2026-10-21) | PO baseline for Phase 5 — report candidate pool, human selection, M09 Executive Editor, reports / report_versions / items / statements / statement sources, canonical JCS JSON + SHA-256, deterministic rendering foundation, analyst report workspace (`docs/specs/LFHE_Phase5_Authoritative_Baseline_Addendum_v1.0.md`); stored before Phase 5 implementation per SD-12; does not supersede 2–9 or closed Phase 1–4 invariants |
| 20 | PO Decision — Authorise Phase 5 | 2026-10-21 | Phase 5 AUTHORISED; implementation order P5-00…P5-10; Phase 6 NOT authorised (`docs/specs/PO_Decision_2026-10-21_Authorise_Phase5.md`) |
| 21 | PO Decision — Control Gate 5 | 2026-10-23 | **CG5 APPROVED; Phase 5 ACCEPTED AND CLOSED**; SD5-01…SD5-20 approved, no change requests; `/reports` browser click-through, K-11, real-provider trial and Phase 4 review UI NON-BLOCKING follow-on items; Phase 6 NOT authorised (SD-12) (`docs/specs/PO_Decision_2026-10-23_Control_Gate_5.md`) |
| 22 | Phase 6 Authoritative Baseline Addendum (QA, Approval & Release) | v1.0 (2026-10-23) | PO baseline for Phase 6 — M10-D deterministic QA, M10-S semantic QA auditor, combined QA, warning acknowledgement, human content approval, security / handling review, PDF release artifact, deterministic release eligibility, human release decision, atomic release manifest + RELEASED (DC6-01…DC6-06) (`docs/specs/LFHE_Phase6_Authoritative_Baseline_Addendum_v1.0.md`); stored before Phase 6 implementation per SD-12; approved by the authorising decision itself; does not supersede 2–9 or closed Phase 1–5 invariants |
| 23 | PO Decision — Authorise Phase 6 | 2026-10-23 | Phase 6 AUTHORISED; baseline approved; implementation order P6-00…P6-10 without intermediate approvals; STOP at CG6; Phase 7 NOT authorised (`docs/specs/PO_Decision_2026-10-23_Authorise_Phase6.md`) |
| 24 | PO Decision — CG6 Targeted Correction (CR6-01) | 2026-10-23 | DEV Phase 6 deployment accepted (40/40, smoke 61/61); SD6-01…09 and SD6-11…19 APPROVED; SD6-10 NOT APPROVED as implemented → **CR6-01**: release manifest must carry `baseline_version_ids` (Prompt Pack delta-audit PG-07), via a new forward-only migration; CG6 on HOLD for this correction only; Phase 7 NOT authorised (`docs/specs/PO_Decision_2026-10-23_CG6_Targeted_Correction_CR6-01.md`) |
| 25 | PO Decision — Control Gate 6 | 2026-10-23 | **CONTROL GATE 6 APPROVED; PHASE 6 ACCEPTED AND CLOSED**; DEV 41/41 migrations, smoke 62/62 PASS; SD6-01…09, SD6-11…19 APPROVED; SD6-10 APPROVED AS CORRECTED BY CR6-01; CR6-01 RESOLVED AND CLOSED; no remaining change requests; non-blocking follow-ons recorded (Next.js security update tracked separately, before any exposed deployment); Phase 7 NOT authorised (SD-12) (`docs/specs/PO_Decision_2026-10-23_Control_Gate_6.md`) |
| 26 | Phase 7 Authoritative Baseline (Controlled Operational Pilot & Validation) | v1.0 (2026-10-23) | PO baseline for Phase 7 — pilot instrumentation, REPLAY / LIVE cycles, real-provider trial (M07–M10-S), browser E2E validation, controlled benchmark, capacity / economic analysis (capacity value ≠ cash saving), CG7 (40 criteria) and a separate capability outcome; core Phase 1–6 frozen; does not alter closed semantics (`docs/specs/LFHE_Phase7_Authoritative_Baseline_v1.0.md`); stored verbatim in P7-00 |
| 27 | PO Decision — Authorise Phase 7 | 2026-10-23 | Phase 7 AUTHORISED; P7-00…P7-09 in baseline order without intermediate approvals (except baseline-required decisions, spec conflicts, closed-semantics / security-boundary changes, new CRs, STOP conditions); public OSINT / synthetic / authorised replay only; real-provider evidence required; 6 cycles target, no fabricated completion; STOP after P7-09 (`docs/specs/PO_Decision_2026-10-23_Authorise_Phase7.md`) |
| 28 | PO Decision — CR7-02 Approved | 2026-10-25 | **CR7-02 APPROVED FOR MERGE AND VALIDATION**: the registered `output_schema.json` is transmitted to the model as trusted request context; untrusted-data boundary, prompt bundles / versions / hashes, ingestion, schema validation, human authority, provenance, QA and release semantics preserved; no other Phase 2 behaviour may change; CG2 / Phase 2 not reopened; criterion 19 only from the completed real-provider P7-BM-01 benchmark; CG7 remains open (`docs/specs/PO_Decision_2026-10-25_CR7-02.md`) |

## Recorded normalisations (Product Owner, 2026-10-08)

- **PIR-01:** the System Concept's full list governs (incl. long-range strike,
  air C2); the Master Spec's shorter list does not narrow scope.
- **PIR-07:** "new opportunity" is additive; it does not replace or narrow the
  Concept categories (incl. technological adaptation).
- **INFORMATION_CUTOFF:** PUBLICATION / PUBLIC AVAILABILITY TIME, EVENT TIME
  and SYSTEM RETRIEVAL TIME are distinct. LIVE: public availability and
  retrieval ≤ cutoff. REPLAY: public availability ≤ historical cutoff; late
  technical retrieval does not make pre-cutoff information post-cutoff. Event
  time is never an eligibility criterion.

## Gold-standard isolation

GS-001 answer-key material (`expected-*`, `evaluation`, the benchmark document
itself) is **not stored in this repository's pipeline-readable tree** and must
never enter prompts, fixtures, reference context or baselines. See ADR-0007.
