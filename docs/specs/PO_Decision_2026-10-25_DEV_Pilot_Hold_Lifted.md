<!-- PO decision received 2026-10-25 18:13 (Europe/Budapest). Stored verbatim (SD-12). -->

# PRODUCT OWNER DECISION — DEV PILOT HOLD LIFTED

**Date:** 2026-10-25  
**Project:** LFHÉ  
**Phase:** Phase 7 — Controlled Operational Pilot & Validation

## DECISION

The Product Owner accepts the P7-BM-02 real-provider result as sufficient evidence to proceed to the operational DEV pilot.

**CG7 criterion 19 — PASS.**

The temporary hold on DEV pilot cycles is hereby:

**LIFTED.**

---

# BASIS

The accepted P7-BM-02 real-provider run demonstrated:

- 18 / 18 M10-S executions succeeded;
- no schema failures;
- semantic recall: 10 / 11;
- deterministic recall: 13 / 13;
- zero blocking false positives on the three clean cases;
- zero non-seeded FAIL-level findings;
- all 15 seeded defective cases produced the expected blocking outcome.

The single scored critical miss in Q09 is retained as a strict benchmark miss because the finding code differed from the expected code.

However, the underlying material epistemic-strength defect was detected by the model as a CRITICAL FAIL.

The benchmark result is therefore considered sufficient for progression to operational pilot use.

---

# BENCHMARK LIMITATION

Only one valid P7-BM-02 real-provider run currently exists.

This limitation must remain documented.

No additional benchmark repetitions are required before starting the DEV pilot.

Do not represent the current recall or warning behaviour as a statistically stable production estimate.

Operational variability shall continue to be observed during the Phase 7 pilot cycles.

---

# M10-S STATUS

No M10-S calibration Change Request is authorised at this time.

The current evidence does not demonstrate blocking over-alerting on clean material.

PASS_WITH_WARNINGS on clean benchmark material is acceptable for pilot use because:

- no clean case was blocked;
- the warnings were analytically intelligible;
- human authority remains mandatory.

Preserve all M10-S findings during the pilot for later analysis.

---

# AUTHORISED NEXT SEQUENCE

Proceed with the remaining Phase 7 operational work.

Before completing the first measured pilot cycle:

1. configure the required DEV pilot roles;
2. configure explicit analyst loaded-cost assumptions;
3. configure explicit provider pricing where available;
4. perform the real browser-based end-to-end workflow validation;
5. record UX findings.

Then begin the six measured Phase 7 pilot cycles.

Target remains:

- minimum 2 REPLAY;
- minimum 2 LIVE / near-live public-OSINT;
- 6 complete cycles total.

---

# FIRST PILOT CYCLE

The first measured cycle should be:

**REPLAY**

unless a technical reason documented in the runbook makes a LIVE cycle preferable.

Purpose:

- validate end-to-end timing instrumentation;
- validate user workflow;
- validate report/provenance binding;
- validate QA handling;
- validate approvals and release path;
- identify measurement defects before LIVE evidence is accumulated.

Do not modify analytical semantics merely because the first pilot cycle exposes friction.

Record findings first.

---

# MEASUREMENT PRIORITY

During all pilot cycles preserve:

- analyst active time;
- workflow-stage time;
- source throughput;
- claims/events/assessments/report counts;
- human corrections;
- human overrides;
- QA findings;
- provider latency;
- provider tokens and cost;
- warning-resolution effort;
- UX findings;
- provenance completeness;
- report cycle time.

Do not bypass human controls to improve productivity metrics.

---

# GATE STATUS

CONTROL GATE 7 remains OPEN.

Current state:

**PASS 29  
FAIL 0  
NOT YET EVIDENCED 11**

Capability verdict remains:

**OPERATIONAL VALUE NOT YET VALIDATED**

The verdict may change only after operational pilot evidence exists.

---

# NO FURTHER PHASE

This decision authorises Phase 7 pilot execution only.

It does not authorise:

- production deployment;
- external operational dissemination;
- commercial deployment;
- classified data;
- another development phase;
- a self-hosted LFHÉ model programme.

---

## FINAL DECISION

**DEV PILOT HOLD — LIFTED.**

Proceed with browser E2E validation and the six controlled pilot cycles.

No additional P7-BM-02 benchmark repetition is required before pilot start.