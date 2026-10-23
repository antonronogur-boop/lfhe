<!-- PO-supplied Phase 7 baseline received 2026-10-23 20:38 (Europe/Budapest). Stored verbatim (SD-12). -->

# LFHÉ — PHASE 7 AUTHORITATIVE BASELINE v1.0

**Phase:** Phase 7 — Controlled Operational Pilot & Validation  
**Control Gate:** CONTROL GATE 7  
**Status on creation:** BASELINE ONLY — implementation requires separate Product Owner authorisation  
**Date:** 2026-10-23

---

# 1. PURPOSE

Phase 7 shall determine whether the closed Phase 1–6 LFHÉ system provides measurable operational value in a realistic analyst workflow.

Phase 7 is not primarily a feature-development phase.

The central question is no longer:

**“Was the system built correctly?”**

The central question is:

**“Does the completed system materially improve intelligence-production work under controlled, measurable conditions?”**

Phase 7 shall therefore validate five dimensions:

1. **Operational usability** — can an analyst actually perform the complete LFHÉ workflow through the application?
2. **Analytical performance** — does the system preserve or improve analytical quality while maintaining human authority?
3. **AI performance** — do real configured model providers perform adequately on the tasks assigned to them?
4. **Efficiency** — does LFHÉ measurably reduce analyst effort and/or increase processing capacity?
5. **Decision-product value** — does the resulting report provide useful, traceable and timely decision support?

The Phase 7 result may be positive, mixed or negative.

A successful Phase 7 means the evaluation is valid and complete.

It does **not** require the system to demonstrate a predetermined positive business or operational outcome.

---

# 2. AUTHORITY AND BASELINE HIERARCHY

Phase 7 inherits all closed Phase 1–6 requirements.

The authoritative hierarchy remains:

1. explicit current Product Owner instruction;
2. LFHÉ System Concept v1.0;
3. Claude Master Specification v1.0;
4. Specification Enforcement Addendum v1.0;
5. Development Specification v1.0;
6. cumulative Module Prompt Pack baseline v1.1 + v1.2 + v1.2.1 + v1.2.2;
7. approved CG0 architecture;
8. closed Phase 1–6 baselines and PO decisions;
9. this Phase 7 Authoritative Baseline v1.0 for Phase 7-specific behaviour;
10. implementation preference.

This Phase 7 baseline may add pilot instrumentation, measurement and validation workflows.

It MUST NOT silently alter closed Phase 1–6 analytical, provenance, confidence, likelihood, approval, security, release or audit semantics.

Any change that would modify closed Phase 1–6 semantics requires a separate Change Request and explicit Product Owner approval.

---

# 3. PRECONDITION

Phase 7 may begin only after:

- CONTROL GATE 6 = APPROVED;
- PHASE 6 = ACCEPTED AND CLOSED;
- CR6-01 = RESOLVED AND CLOSED;
- the Phase 7 baseline is versioned under `docs/specs/`;
- explicit Product Owner authorisation for Phase 7 is stored under `docs/specs/`.

These conditions shall be checked and recorded in P7-00.

No closed gate may be reopened merely because Phase 7 discovers a usability or performance weakness.

---

# 4. PHASE 7 OPERATING PRINCIPLE

The core Phase 1–6 system is considered **frozen for pilot purposes**.

The default Phase 7 loop is:

**USE → MEASURE → ANALYSE → LEARN**

and not:

**USE → IMMEDIATELY REBUILD**

Pilot findings shall first be recorded as evidence.

A finding may result in a future Change Request, but Phase 7 MUST distinguish between:

- measurement;
- usability defect;
- software defect;
- analytical defect;
- model-performance limitation;
- configuration problem;
- feature request;
- future capability opportunity.

Feature requests discovered during the pilot do not become Phase 7 requirements automatically.

---

# 5. SECURITY AND DATA BOUNDARY

Phase 7 is authorised only for:

- public OSINT;
- synthetic test material;
- authorised historical public-source replay material.

Phase 7 does NOT authorise:

- classified information;
- restricted operational information;
- non-public military data;
- credentials or secrets inside model input;
- uploading protected information to public AI providers;
- autonomous classification decisions;
- operational deployment into accredited military systems.

A locally hosted model does not by itself make the system suitable for classified information.

Any future use of protected or classified information requires a separate security architecture, accreditation and explicit authorisation outside Phase 7.

---

# 6. HUMAN AUTHORITY

All previously defined HUMAN_ONLY controls remain unchanged.

AI shall not become the authority for:

- final relevance;
- final analytical judgment;
- likelihood ownership;
- analytic confidence ownership;
- report inclusion;
- warning acknowledgement;
- report content approval;
- security review;
- release decision.

Phase 7 shall measure human overrides and corrections.

It shall not remove them in order to improve speed metrics.

---

# 7. PILOT MODES

Phase 7 shall support two validation modes.

## 7.1 REPLAY

Historical public-source material is evaluated using a defined cutoff.

Only information available by the replay cutoff is eligible.

Later-known outcomes shall not enter the analytical context.

REPLAY is used for:

- repeatable benchmarking;
- seeded error scenarios;
- provider comparison;
- analyst workflow comparison;
- retrospective quality measurement without hindsight contamination.

## 7.2 LIVE / NEAR-LIVE OSINT

Current public-source material may be processed in a controlled pilot.

LIVE mode is used to measure:

- real workflow behaviour;
- source throughput;
- latency;
- analyst effort;
- operational usability;
- report-production cycle time.

LIVE Phase 7 output remains a pilot product unless separately authorised.

Phase 7 does not authorise formal operational dissemination.

---

# 8. MINIMUM PILOT EVIDENCE

The target evidence set is **six complete end-to-end LFHÉ cycles**.

Minimum composition:

- at least 2 REPLAY cycles;
- at least 2 LIVE or near-live public-OSINT cycles;
- the remaining 2 may be REPLAY or LIVE according to pilot feasibility.

A cycle is complete only when the relevant workflow reaches its defined terminal pilot state and all required metrics are recorded.

The Product Owner may stop the pilot early for safety, methodological invalidity, cost, provider failure or discovered architectural defect.

An early stop does not erase collected evidence.

---

# 9. CONTROL / COMPARATOR

Phase 7 shall not claim productivity improvement without a defensible baseline.

At least one of the following comparator methods must be available for each productivity claim:

- prior documented manual workflow;
- matched manual-control exercise;
- matched historical cycle;
- controlled analyst benchmark;
- equivalent task performed without LFHÉ assistance.

The comparison method shall be recorded with the result.

Where exact comparison is impossible, the metric must be labelled observational rather than controlled.

No marketing or ROI claim may convert an observational result into a controlled experimental result.

---

# 10. PRIMARY PHASE 7 METRICS

Phase 7 shall measure, where applicable:

### A. Analyst effort

- total analyst active time per cycle;
- active time by workflow stage;
- review time;
- correction time;
- report-production time;
- QA-resolution time;
- number of human interactions;
- number of required manual corrections.

### B. Throughput

- sources processed;
- articles retained;
- claims created;
- events created;
- assessments created;
- candidate report items;
- final report items;
- sources processed per analyst-hour;
- accepted report items per analyst-hour.

### C. Analytical quality

- unsupported fact rate;
- attribution-loss rate;
- epistemic-strength violation rate;
- post-cutoff/hindsight violations;
- provenance completeness;
- contradiction handling;
- source-independence correctness;
- likelihood consistency;
- confidence consistency;
- human rejection/correction rate.

### D. QA performance

For M10-D and M10-S separately:

- findings produced;
- true positives;
- false positives;
- false negatives on labelled scenarios;
- precision;
- recall;
- critical miss count;
- schema-valid response rate;
- provider failure rate;
- repair-run rate.

Deterministic QA and semantic QA must remain separately measurable.

### E. AI execution

For every model-backed module where technically available:

- provider;
- model identifier;
- model configuration;
- prompt version;
- input tokens;
- output tokens;
- latency;
- model cost;
- successful structured-output rate;
- schema-repair count;
- provider errors;
- retry count.

### F. Usability

- workflow completion rate;
- blocked workflows;
- user confusion points;
- unnecessary clicks;
- navigation failures;
- manually recorded UX observations;
- severity of UX issues;
- analyst subjective workload.

### G. Report performance

- time from cutoff to usable draft;
- time from cutoff to final approved report;
- number of substantive human edits;
- number of QA-induced revisions;
- traceability completeness;
- report length;
- number of Key Judgements;
- number of developments;
- number of indicators;
- number of What-to-Watch items.

---

# 11. ECONOMIC / CAPACITY METRICS

Phase 7 shall explicitly distinguish:

**capacity released**

from

**cash cost saved**.

These MUST NOT be treated as identical.

Core calculations:

`analyst_hours_saved = baseline_analyst_hours - lfhe_analyst_hours`

`capacity_release_percent = analyst_hours_saved / baseline_analyst_hours`

`weekly_fte_equivalent = analyst_hours_saved_per_week / configured_weekly_work_hours`

`capacity_value = analyst_hours_saved × configured_loaded_hourly_cost`

Where annualisation is used:

`annual_capacity_value = validated_weekly_capacity_value × configured_working_weeks_per_year`

The following may be separately estimated only when supported:

- avoided overtime;
- avoided contractor expenditure;
- avoided future hiring;
- reduced external research cost.

No pilot result shall automatically be described as headcount reduction.

The preferred wording is:

**“analyst capacity released for higher-value work.”**

The loaded hourly cost and working-week assumptions shall be explicit configuration inputs and shall never be hardcoded as universal values.

---

# 12. PRODUCTIVITY CLAIM RULE

LFHÉ may claim a measured productivity improvement only when:

- the comparison method is documented;
- the workload scope is comparable;
- timing data is complete;
- human quality controls were not removed;
- output quality was not materially degraded;
- no prohibited data was used.

Phase 7 must not optimise time by bypassing required review, QA, security or human authority.

---

# 13. CAPABILITY OUTCOME

CONTROL GATE 7 and capability validation are separate concepts.

CG7 determines whether Phase 7 was correctly executed and evidenced.

A separate capability outcome shall state one of:

- **OPERATIONAL VALUE VALIDATED**
- **OPERATIONAL VALUE PARTIALLY VALIDATED**
- **OPERATIONAL VALUE NOT YET VALIDATED**
- **OPERATIONAL VALUE NOT VALIDATED**

A negative capability result does NOT mean Phase 7 failed if the evaluation itself was valid.

This separation is mandatory.

---

# 14. REAL MODEL PROVIDER VALIDATION

Phase 7 shall include a real-provider trial for the model-backed analytical chain where technically supported.

At minimum the pilot shall exercise real-provider operation for representative tasks in:

- M07;
- M08;
- M09;
- M10-S.

Earlier model-backed modules may also be tested where useful.

The real-provider trial shall verify:

- actual prompt bundle use;
- actual model-run persistence;
- schema validation;
- repair behaviour;
- provenance;
- provider failure behaviour;
- latency;
- approximate cost;
- semantic quality.

A scripted or rule-based test double is not sufficient evidence of real-provider quality.

Test doubles remain valid for deterministic regression testing.

---

# 15. PROVIDER COMPARISON

Phase 7 may compare multiple model providers or model versions through the existing provider abstraction.

Provider comparison must use equivalent task envelopes wherever practical.

Provider results shall not silently change analytical truth.

Provider comparison is advisory to later model-selection decisions.

No provider shall become mandatory merely because it wins a single benchmark.

---

# 16. SELF-HOSTED MODEL BOUNDARY

Development or training of a dedicated LFHÉ local/self-hosted model is NOT part of Phase 7.

Phase 7 may, however:

- preserve training-relevant human corrections;
- measure tasks suitable for future local-model replacement;
- estimate inference requirements;
- identify candidate modules for future self-hosted execution.

A future local or sovereign LFHÉ model requires a separate baseline and Product Owner authorisation.

---

# 17. UX VALIDATION

Phase 7 shall include real browser-based end-to-end interaction.

Automated tests alone are insufficient for pilot usability validation.

The analyst must be able to navigate the workflow through the UI for representative tasks.

The Phase 7 UX review shall include at minimum:

- source/review workflow where available;
- event/assessment workflow where available;
- report workspace;
- QA view;
- warning handling;
- content approval;
- security review;
- release workflow;
- released-report provenance inspection.

UX findings shall be recorded by severity:

- BLOCKING;
- MAJOR;
- MINOR;
- ENHANCEMENT.

Only BLOCKING defects automatically stop the relevant pilot path.

Enhancement requests do not become implementation requirements without PO approval.

---

# 18. TRACEABILITY REQUIREMENT

Every pilot product shall preserve the existing provenance chain.

The target remains:

SOURCE  
→ ARTICLE_SNAPSHOT  
→ ORIGINAL-LANGUAGE EVIDENCE  
→ CLAIM  
→ EVENT  
→ ASSESSMENT_STATEMENT  
→ REPORT_ITEM_STATEMENT  
→ REPORT VERSION + HASH  
→ QA  
→ HUMAN APPROVALS  
→ RELEASE MANIFEST  
→ RELEASED REPORT

Phase 7 may add pilot measurements around this chain.

It must not weaken it.

---

# 19. PILOT INSTRUMENTATION

New Phase 7 instrumentation may be introduced for measurement.

Permitted examples include:

- pilot cycle;
- pilot scenario;
- workflow session;
- timing event;
- user action metric;
- provider metric;
- benchmark result;
- quality label;
- UX finding;
- pilot observation;
- cycle summary;
- capability metric;
- pilot comparison result.

Pilot instrumentation must be distinguishable from authoritative analytical records.

Pilot measurement data must not become analytical evidence.

---

# 20. DATABASE CHANGE RULE

All Phase 7 database changes shall be forward-only.

Previously applied migrations MUST NOT be edited.

In particular:

- migrations through `20261011004000_p6_cr6_01_manifest_baseline_ids.sql` are immutable;
- Phase 7 shall use new migration files;
- migration numbers shall be assigned from actual repository state and MUST NOT be guessed from this baseline.

Phase 7 instrumentation should prefer additive tables/views/functions rather than semantic changes to closed Phase 1–6 objects.

---

# 21. AUDIT

Human decisions affecting analytical or release state remain subject to the existing audit model.

Pilot measurement events may use a separate measurement/event log where appropriate.

Measurement logging shall not pollute the analytical audit trail with high-volume non-authoritative telemetry unless explicitly justified.

Any new security-sensitive decision remains auditable.

---

# 22. PILOT QUALITY LABELS

Phase 7 evaluation data shall distinguish:

- observed truth;
- analyst judgement;
- benchmark label;
- seeded synthetic error;
- model finding;
- deterministic finding;
- human correction;
- pilot interpretation.

The evaluation framework must never treat model output as ground truth.

---

# 23. GOLD STANDARD / BENCHMARK ISOLATION

Existing Gold Standard isolation requirements remain in force.

Where benchmark datasets are used:

- model input must not expose answer keys;
- labels must remain isolated from production prompts;
- benchmark material must be clearly marked;
- leakage tests remain mandatory.

K-11 / GS-001 may be exercised in Phase 7 as part of benchmark validation.

---

# 24. PHASE 7 WORK PACKAGES

## P7-00 — Baseline Lock & Phase Initialisation

Deliverables:

- Phase 7 baseline stored verbatim;
- PO authorisation stored verbatim;
- SPEC_INDEX updated;
- PROJECT_STATUS updated;
- Phase 7 branch/status recorded;
- previous migrations verified immutable;
- CG1–CG6 remain CLOSED.

No functional implementation before P7-00 is complete.

---

## P7-01 — Pilot Data Model & Instrumentation

Implement the minimum additive data model necessary to record:

- pilot cycles;
- pilot mode;
- scenario/corpus identity;
- comparison method;
- workflow timings;
- analyst interactions;
- provider metrics;
- quality metrics;
- UX findings;
- cycle outcomes.

Requirements:

- measurement records trace to the exact LFHÉ objects involved;
- measurement data cannot modify analytical truth;
- no duplication of authoritative fields already owned elsewhere;
- deterministic metric calculations where possible.

---

## P7-02 — Pilot Workspace / Measurement UX

Implement the minimum analyst-facing UI necessary to:

- start a pilot cycle;
- identify REPLAY/LIVE mode;
- record/control timing;
- display cycle status;
- record structured UX observations;
- display key pilot metrics;
- identify incomplete measurement.

Do not redesign the entire LFHÉ UI.

Fix only pilot-blocking defects automatically.

Other findings go to the pilot backlog.

---

## P7-03 — Real Provider Trial

Exercise real provider execution for representative M07–M10-S workflows.

Record:

- provider/model;
- exact model configuration;
- prompt version/hash;
- latency;
- tokens;
- cost where available;
- structured-output success;
- repairs;
- provider errors;
- model-run traceability;
- quality results.

Real provider input remains public/synthetic only.

Provider secrets remain environment-only.

---

## P7-04 — Browser End-to-End Validation

Perform actual browser-based execution of the representative workflow.

At minimum validate the usable human path through:

analytical review  
→ assessment  
→ report workspace  
→ QA  
→ warning handling where applicable  
→ content approval  
→ security review  
→ release decision  
→ released artifact inspection.

Record all blocking/major/minor/enhancement findings.

Automation cannot substitute for this step.

---

## P7-05 — Controlled Benchmark

Construct or select a controlled benchmark that permits measurement of:

- analyst time;
- processing throughput;
- analytical error;
- provenance;
- M10-S semantic detection;
- false positive / false negative behaviour.

The benchmark shall contain sufficient labelled/seeded cases to evaluate semantic QA without exposing labels to the model.

The benchmark may use synthetic or historical public-source material.

---

## P7-06 — Operational Pilot Cycles

Execute the defined Phase 7 cycles.

Target: 6 complete cycles.

For each cycle record:

- mode;
- cutoff;
- input scope;
- analyst;
- model/provider configuration;
- start/end;
- active analyst time;
- sources processed;
- major pipeline counts;
- human corrections;
- QA findings;
- output status;
- relevant cost;
- UX findings;
- deviations.

The system shall not fabricate missing measurements.

---

## P7-07 — Performance & Capacity Analysis

Produce deterministic or reproducible calculations for:

- hours saved;
- capacity release percentage;
- FTE-equivalent capacity;
- throughput improvement;
- report cycle-time change;
- model cost;
- analyst effort;
- quality changes;
- provenance completeness;
- QA performance.

Economic values require explicit cost assumptions.

Separate:

**capacity value**

from

**cash saving**.

---

## P7-08 — Pilot Findings & Capability Assessment

Produce a Phase 7 evidence report containing:

- methodology;
- pilot population;
- limitations;
- metrics;
- comparison method;
- positive findings;
- negative findings;
- UX findings;
- model limitations;
- analytical limitations;
- provider results;
- capacity results;
- cost results;
- security observations;
- recommended future changes.

No recommendation shall silently modify Phase 1–6 semantics.

---

## P7-09 — CG7 Evidence Pack & STOP

Prepare:

- `docs/control-gate-7-report.md`;
- Phase 7 test traceability;
- pilot metrics export;
- provider results;
- UX findings;
- capability assessment;
- open items;
- specification deviations;
- change requests;
- recommended capability outcome.

Then STOP.

CONTROL GATE 7 is a Product Owner decision.

Do not start any later phase without explicit PO authorisation.

---

# 25. MINIMUM AUTOMATED TEST REQUIREMENTS

Phase 7 must preserve all Phase 1–6 regression tests.

New tests shall cover at minimum:

1. pilot records cannot alter authoritative analytical state;
2. pilot records bind to valid referenced objects;
3. REPLAY cutoff preserved;
4. LIVE/REPLAY clearly distinguished;
5. timing records valid and ordered;
6. negative durations impossible;
7. missing required pilot metrics detected;
8. provider metrics bind to exact model_run;
9. benchmark labels do not enter model input;
10. model output cannot become benchmark truth;
11. loaded hourly cost is explicit configuration;
12. capacity value calculation deterministic;
13. cash-saving and capacity-value semantics separated;
14. pilot comparison method recorded;
15. Phase 1–6 regression unchanged;
16. human-only controls unchanged;
17. audit integrity preserved;
18. no secrets in pilot exports;
19. pilot exports contain no prohibited benchmark answer keys;
20. new migrations are forward-only.

Exact test count is implementation-dependent and shall not be artificially fixed.

---

# 26. REAL-PROVIDER ACCEPTANCE

Before a real-provider result is considered valid Phase 7 evidence:

- provider call must be genuine;
- exact model identifier/configuration must be stored;
- exact prompt/version/hash must be traceable;
- model_run must exist;
- response must pass the normal ingestion path;
- any repair run must be separately recorded;
- provider failure must not be converted into success;
- input must remain within Phase 7 data boundary.

A real-provider smoke run is not required in normal CI when secrets are unavailable.

It must instead be reproducibly recorded in the controlled DEV/pilot environment.

---

# 27. PILOT STOP CONDITIONS

The pilot path shall STOP if any of the following occurs:

- prohibited/non-public data reaches an unauthorised provider;
- analytical provenance is materially lost;
- human authority can be bypassed;
- release controls can be bypassed;
- pilot instrumentation corrupts authoritative state;
- benchmark answer-key leakage occurs;
- a newly discovered critical security issue makes continued pilot use unsafe;
- measurement integrity becomes materially invalid.

The Product Owner may also stop the pilot manually.

---

# 28. PHASE 7 NON-GOALS

Phase 7 does NOT authorise:

- classified-data operation;
- production deployment;
- external operational dissemination;
- NATO system integration;
- military network integration;
- autonomous intelligence decisions;
- autonomous release;
- removal of human gates;
- new analytical confidence semantics;
- new likelihood vocabulary;
- new intelligence doctrine;
- expansion to Ground/Maritime/Cyber/Space domains;
- commercial product fork;
- company formation;
- commercial sales;
- dedicated self-hosted LFHÉ model training;
- foundation-model training;
- mobile application;
- chatbot functionality;
- 3D map/globe;
- speculative feature expansion.

These may be considered in later separately authorised work.

---

# 29. NEXT.JS SECURITY DEPENDENCY

The known Next.js security dependency item remains separately tracked.

It does not retroactively reopen CG6.

For Phase 7:

- controlled local/DEV pilot may proceed under the existing PO decision if the application is not exposed externally;
- the dependency issue MUST be resolved before any externally exposed or operational deployment.

Any evidence of an exploitable condition relevant to the actual pilot environment must be escalated immediately.

---

# 30. CONTROL GATE 7 ACCEPTANCE CRITERIA

CG7 requires evidence that:

1. Phase 7 baseline and PO authorisation are stored verbatim.
2. CG1–CG6 remain CLOSED.
3. No closed migration was modified.
4. All new migrations are forward-only.
5. Phase 1–6 regression remains green.
6. Pilot instrumentation cannot modify authoritative analytical truth.
7. REPLAY/LIVE mode is explicit.
8. Pilot cutoff semantics are preserved.
9. Analyst-time measurement exists and is traceable.
10. Workflow-stage timing exists where required.
11. Throughput metrics are reproducible.
12. Quality metrics are reproducible.
13. Capacity metrics are reproducible.
14. Capacity value and cash saving are not conflated.
15. Cost assumptions are explicit.
16. Real-provider execution has been performed.
17. Real-provider model/config/prompt traceability is complete.
18. Provider errors and repair runs are preserved.
19. M10-S real-provider quality has been empirically measured.
20. Deterministic QA and semantic QA remain separately measurable.
21. Browser-based end-to-end workflow has been performed.
22. UX findings are recorded.
23. Blocking UX defects are resolved or the affected path is declared unusable.
24. Benchmark answer keys remain isolated.
25. K-11/GS isolation remains intact.
26. No prohibited data entered a provider.
27. Human analytical authority remains intact.
28. Human security authority remains intact.
29. Human release authority remains intact.
30. Provenance remains complete.
31. Pilot measurements do not weaken release protection.
32. At least the minimum required pilot evidence set is complete OR the PO explicitly accepts a documented early-stop dataset as sufficient.
33. Pilot limitations are explicitly documented.
34. Positive and negative findings are both reported.
35. No unsupported commercial productivity claim is made.
36. A capability outcome recommendation is produced.
37. Remaining open items are identified.
38. Phase 7 specification deviations are listed.
39. Phase 7 change requests are listed.
40. No later phase has started.

CG7 approval requires Product Owner decision.

---

# 31. CAPABILITY SUCCESS INDICATORS

The following are desirable outcomes, not automatic CG7 pass/fail thresholds:

- reduced analyst active time;
- increased source throughput;
- reduced report-production time;
- low substantive human correction rate;
- high traceability completeness;
- low unsupported-fact rate;
- low false-negative rate for critical QA scenarios;
- manageable false-positive rate;
- acceptable model-provider cost;
- acceptable latency;
- reduced repetitive analyst work;
- increased time available for human analytical judgement.

The actual measured values shall determine the capability verdict.

No desired percentage improvement is hardcoded before evidence exists.

---

# 32. COMMERCIAL RELEVANCE OUTPUT

Phase 7 may calculate evidence useful for future business planning, including:

- analyst-hours saved per cycle;
- analyst-hours saved per month;
- FTE-equivalent capacity released;
- annualised capacity value;
- estimated payback under configurable licence cost;
- provider operating cost;
- infrastructure cost.

These results are analytical outputs only.

Phase 7 does not authorise commercial sale or external marketing claims.

---

# 33. FINAL PHASE 7 OUTPUT

At completion, the repository shall contain sufficient evidence for the Product Owner to answer:

1. Does LFHÉ work end-to-end for a real analyst?
2. Does it preserve analytical integrity?
3. Does the real AI layer perform adequately?
4. How much analyst time does it consume?
5. How much analyst time does it save?
6. How much additional information can the same analyst capacity process?
7. What types of errors does it catch?
8. What types of errors does it miss?
9. What is the approximate operating cost?
10. What is the resulting capacity value?
11. What UX problems remain?
12. What changes should be considered next?
13. Is operational value validated?

The phase shall finish with:

**CONTROL GATE 7 — PO DECISION REQUIRED**

and one recommended capability verdict.

---

# 34. STOP RULE

After P7-09:

**STOP.**

Do not:

- start a later phase;
- begin production deployment;
- begin commercialisation;
- train a dedicated LFHÉ model;
- expand analytical domains;
- modify closed Phase 1–6 semantics;

without separate Product Owner authorisation.

---

**END OF LFHÉ PHASE 7 AUTHORITATIVE BASELINE v1.0**