<!-- PO decision received 2026-10-23 20:38 (Europe/Budapest). Stored verbatim (SD-12). -->

# PRODUCT OWNER DECISION — AUTHORISE PHASE 7

**Date:** 2026-10-23  
**Project:** LFHÉ  
**Phase:** Phase 7 — Controlled Operational Pilot & Validation

---

CONTROL GATE 6 is CLOSED.

The authoritative current project state is:

- CONTROL GATE 1 — APPROVED
- PHASE 1 — ACCEPTED AND CLOSED
- CONTROL GATE 2 — APPROVED
- PHASE 2 — ACCEPTED AND CLOSED
- CONTROL GATE 3 — APPROVED
- PHASE 3 — ACCEPTED AND CLOSED
- CONTROL GATE 4 — APPROVED
- PHASE 4 — ACCEPTED AND CLOSED
- CONTROL GATE 5 — APPROVED
- PHASE 5 — ACCEPTED AND CLOSED
- CONTROL GATE 6 — APPROVED
- PHASE 6 — ACCEPTED AND CLOSED
- CR6-01 — RESOLVED AND CLOSED
- Phase 7 — NOT YET STARTED

The Product Owner now authorises:

**PHASE 7 — CONTROLLED OPERATIONAL PILOT & VALIDATION**

using:

`LFHE_Phase7_Authoritative_Baseline_v1.0.md`

as the authoritative phase-specific baseline.

---

# AUTHORISATION

You are authorised to implement:

- P7-00
- P7-01
- P7-02
- P7-03
- P7-04
- P7-05
- P7-06
- P7-07
- P7-08
- P7-09

in the order defined by the Phase 7 baseline.

You do not need to request intermediate Product Owner approval between normal work packages unless:

- the baseline explicitly requires PO decision;
- a specification conflict is discovered;
- a closed Phase 1–6 semantic would need to change;
- a security boundary would need to change;
- a new Change Request is required;
- a STOP condition is triggered.

---

# P7-00 FIRST

Before functional Phase 7 implementation:

1. store the Phase 7 baseline verbatim under:

`docs/specs/LFHE_Phase7_Authoritative_Baseline_v1.0.md`

2. store this Product Owner authorisation verbatim under:

`docs/specs/PO_Decision_2026-10-23_Authorise_Phase7.md`

3. add both documents to:

`docs/SPEC_INDEX.md`

4. update:

`docs/PROJECT_STATUS.md`

to show:

`Phase 7 — AUTHORISED / IN PROGRESS`

5. confirm that CONTROL GATE 1–6 remain CLOSED.

6. confirm that all previously applied migrations remain unchanged.

Only after P7-00 may Phase 7 implementation begin.

---

# CORE PRODUCT OWNER INTENT

Phase 7 is not a general feature-development phase.

Its primary purpose is to determine whether the existing LFHÉ system provides measurable value under realistic analyst use.

The system core should therefore remain stable.

Default behaviour:

**USE → MEASURE → ANALYSE → LEARN**

not:

**USE → FIND SOMETHING IMPERFECT → REBUILD IT IMMEDIATELY**

Pilot findings are evidence first.

Only BLOCKING defects necessary to complete the authorised pilot path may be corrected without a separate scope decision.

Non-blocking improvements shall be recorded for later consideration.

---

# CLOSED PHASE PROTECTION

Do not reopen CG1–CG6.

Do not introduce new acceptance criteria for closed phases.

Do not reinterpret previous PO decisions.

Do not modify existing analytical semantics merely to improve Phase 7 metrics.

Do not optimise performance measurements by bypassing:

- human analytical validation;
- QA;
- warning acknowledgement;
- content approval;
- security review;
- release authority;
- provenance.

If Phase 7 identifies a genuine defect in closed behaviour:

1. record it;
2. classify it;
3. create a proposed Change Request;
4. STOP the affected implementation path if required;
5. request PO decision.

---

# DATABASE RULE

All previously applied migrations are immutable.

In particular:

`20261011003800_p6_qa.sql`

`20261011003900_p6_approval_release.sql`

`20261011004000_p6_cr6_01_manifest_baseline_ids.sql`

MUST NOT be edited.

Use new forward-only migrations.

Determine the correct migration identifiers from the actual repository state.

Do not guess them from this instruction.

---

# DATA / SECURITY RULE

Phase 7 is limited to:

- public OSINT;
- synthetic data;
- authorised historical public-source replay material.

Do not use:

- classified material;
- non-public military information;
- protected operational data;
- internal credentials;
- secrets in prompts.

Real external model providers may be used only within this data boundary.

---

# REAL PROVIDER REQUIREMENT

Phase 7 must include real-provider evidence.

Do not treat scripted test doubles as empirical evidence of semantic model quality.

Use the actual configured provider path for representative M07, M08, M09 and M10-S workloads.

Record:

- provider;
- model;
- configuration;
- prompt version/hash;
- model_run;
- latency;
- token usage;
- cost where available;
- schema failures;
- repairs;
- quality findings.

Real-provider calls do not need to run in CI.

They must be reproducibly documented from the controlled DEV/pilot environment.

---

# PILOT MEASUREMENT PRIORITY

Prioritise measurement of:

- analyst active time;
- report cycle time;
- source throughput;
- analyst corrections;
- model corrections;
- QA findings;
- QA false positives;
- QA false negatives;
- provenance completeness;
- human override rate;
- model cost;
- provider latency;
- UX blockers;
- analyst-hours released.

Do not fabricate missing measurements.

Do not retrospectively infer active analyst time when reliable timing evidence does not exist.

---

# ECONOMIC MEASUREMENT

Implement support for calculating:

`analyst_hours_saved`

`capacity_release_percent`

`FTE-equivalent capacity released`

`capacity value`

where supported by evidence.

Capacity value is not automatically cash saving.

The result must distinguish:

- released internal capacity;
- avoided overtime;
- avoided contractor expenditure;
- avoided hiring;
- actual cash saving.

Loaded analyst cost and work-week assumptions must be explicit configuration or analysis inputs.

No default salary assumption shall be presented as universal truth.

---

# PILOT SIZE

Target:

**6 complete end-to-end pilot cycles**

with:

- at least 2 REPLAY;
- at least 2 LIVE / near-live public OSINT;
- 2 additional cycles of either mode.

Do not fabricate completion.

If the real-world pilot requires calendar time, implement all required instrumentation and then allow the actual cycles to be accumulated over time.

The Phase 7 gate remains open until sufficient evidence exists or the PO explicitly accepts an early-stop evidence set.

---

# UX

Perform real browser-based use of the application.

Automated tests are not sufficient evidence of usability.

The pilot must generate structured UX findings.

Classify them as:

- BLOCKING
- MAJOR
- MINOR
- ENHANCEMENT

Do not automatically implement MINOR or ENHANCEMENT findings during Phase 7.

---

# NEXT.JS ITEM

The existing Next.js security dependency remains separately tracked.

It does not reopen CG6.

A controlled local/DEV Phase 7 pilot may proceed if the system is not externally exposed.

Before any externally exposed or operational deployment, the relevant security dependency must be resolved.

If the actual Phase 7 environment makes the issue directly exploitable, escalate immediately.

---

# SELF-HOSTED AI

A dedicated LFHÉ self-hosted/local model is NOT authorised in Phase 7.

However, preserve evidence useful for a future local-model programme, including:

- human corrections;
- task-specific performance;
- token requirements;
- latency;
- model suitability;
- model-independent evaluation cases.

Do not train a dedicated LFHÉ model under this authorisation.

---

# ACCEPTANCE

Phase 7 shall be evaluated against the 40 CG7 acceptance criteria in:

`LFHE_Phase7_Authoritative_Baseline_v1.0.md`

Do not silently add new CG7 criteria after implementation.

Any genuinely necessary new criterion requires explicit PO decision.

The goal of CG7 is to determine whether the pilot was validly executed.

The business/operational outcome is separately classified as:

- OPERATIONAL VALUE VALIDATED
- OPERATIONAL VALUE PARTIALLY VALIDATED
- OPERATIONAL VALUE NOT YET VALIDATED
- OPERATIONAL VALUE NOT VALIDATED

Do not force a positive capability verdict merely to close Phase 7.

---

# FINAL DELIVERABLES

Before requesting CONTROL GATE 7:

provide at minimum:

- Phase 7 implementation summary;
- files changed;
- migrations added;
- automated test results;
- Phase 1–6 regression result;
- DEV smoke result;
- real-provider trial result;
- provider cost/latency metrics;
- browser UX validation result;
- pilot-cycle summary;
- benchmark result;
- M10-S empirical quality;
- analyst-time measurements;
- throughput measurements;
- capacity-release measurements;
- economic assumptions;
- provenance status;
- security status;
- audit status;
- specification deviations;
- change requests;
- known failures;
- open items;
- recommended capability verdict;
- all 40 CG7 criteria with PASS / FAIL / NOT YET EVIDENCED.

Do not report a criterion PASS without evidence.

---

# STOP

After P7-09:

STOP.

Do not self-approve CONTROL GATE 7.

Do not begin another phase.

Do not begin production deployment.

Do not begin commercialisation.

Do not train a dedicated LFHÉ model.

Do not expand to additional intelligence domains.

Return the complete CONTROL GATE 7 evidence package to the Product Owner.

Only the Product Owner may decide:

`CONTROL GATE 7 — APPROVED`

or

`CONTROL GATE 7 — HOLD`

or

`CONTROL GATE 7 — REJECTED`

and separately determine the capability verdict.

---

**PHASE 7 — AUTHORISED.**

Proceed with P7-00.

**END OF PRODUCT OWNER DECISION**