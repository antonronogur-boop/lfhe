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
