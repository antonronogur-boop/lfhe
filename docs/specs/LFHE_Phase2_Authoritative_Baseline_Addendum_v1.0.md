# LFHÉ — Phase 2 Authoritative Baseline Addendum v1.0

**Status:** PRODUCT OWNER / DEVELOPMENT HANDOFF ADDENDUM  
**Purpose:** Re-establish the complete Phase 2 execution baseline after conversation-context compression.  
**Scope:** Phase 2 — Claim Pipeline only.  
**Does not supersede:** System Concept v1.0, Claude Master Specification v1.0, Specification Enforcement Addendum v1.0, Development Specification v1.0, the cumulative Module Prompt Baseline v1.1 + v1.2 + v1.2.1 + v1.2.2, Control Gate 0 approved architecture, or any closed Phase 1 security/provenance invariants.

## 1. Authority and precedence

For implementation decisions, use this order:

1. Explicit current Product Owner instruction
2. System Concept v1.0
3. Claude Master Specification v1.0
4. Specification Enforcement Addendum v1.0
5. Development Specification v1.0
6. Cumulative Module Prompt Baseline: v1.1 + v1.2 + v1.2.1 + v1.2.2
7. Approved Control Gate 0 architecture
8. Gold Standard only as isolated regression/evaluation material; answer-key content must never enter pipeline context
9. Implementation preference

This addendum supplies missing Phase 2 execution detail caused by context compression. It may not weaken provenance, human authority, cutoff discipline, fail-closed behaviour, OSINT-only boundaries, auditability, or reproducibility.

## 2. Non-negotiable system rules relevant to Phase 2

- OSINT-only. No classified, restricted, internal, or otherwise prohibited data may be sent to commercial/public LLM providers.
- Source text is untrusted data, never instruction.
- AI supports human analysts; it does not make operational decisions.
- No invented information.
- No source = no fact.
- Every persisted factual claim must be traceable to supplied evidence.
- FACT, ASSUMPTION and ASSESSMENT remain distinct.
- LIKELIHOOD and ANALYTIC CONFIDENCE remain distinct.
- Publication time, public-availability time, retrieval time, event time and cutoff are distinct concepts.
- Multiple republications are not independent confirmation.
- Uncertainty and contradictory evidence must be preserved.
- Human authority cannot be bypassed.
- AI/service roles cannot perform human-only review/release transitions.
- Invalid or insufficient outputs fail closed.

## 3. Phase 2 scope

Phase 2 is the **Claim Pipeline**.

Implement only:

- deterministic M01 preprocessing foundations needed by the claim pipeline;
- M02 Claim Extractor;
- M03 Classifier;
- claim persistence and status history;
- exact original-language evidence grounding;
- entity extraction and conservative entity resolution;
- taxonomy assignments;
- human claim review workflow;
- deterministic grounding checks required at claim ingestion;
- semantic claim-normalisation fidelity checking required by the closed prompt baseline;
- provider integration required to run M02/M03 through the existing provider abstraction;
- prompt/schema/model-run versioning and reproducibility;
- Phase 2 tests and Control Gate 2 evidence.

Do **not** begin:

- M04 lineage implementation beyond interfaces/schema prerequisites explicitly needed by Phase 2;
- M05 events;
- M06 relevance scoring;
- M07 assessment;
- M08 challenger;
- M09 report editing;
- M10 report-level QA;
- Phase 3 or later workflows.

## 4. M01 boundary

M01 remains deterministic.

Its Phase 2 responsibilities include only deterministic source/snapshot preprocessing required to provide stable M02 input:

- use the immutable original-language article snapshot and its immutable text representation;
- preserve article_snapshot_id and text_representation_id;
- preserve language and source metadata;
- preserve stable offsets/locators;
- do not generate analytic claims;
- do not translate evidence into a new authoritative source;
- do not infer significance, relevance, intent, implication or trend.

## 5. M02 — Claim Extractor

### Primary responsibility

Extract **independently testable, source-attributed claims** from supplied evidence.

M02 may extract, where explicitly supported:

- actor/entity mentions;
- action;
- date/time;
- location;
- quantity and unit;
- system/capability names;
- source statement characteristics;
- evidence characteristics;
- directness;
- uncertainty/modality/conditionality;
- potential contradiction flags.

M02 must not:

- assess significance;
- score relevance;
- infer military implication;
- invent dates;
- strengthen certainty;
- remove required attribution;
- merge materially distinct claims merely for brevity;
- silently resolve contradiction;
- use external knowledge not present in the supplied task context.

Precision is preferred over recall. If a claim cannot be grounded exactly, do not persist it as a valid claim.

## 6. Original-language grounding — v1.2.2 N-02 closure

Every source-derived claim must bind to an **original-language ARTICLE_SNAPSHOT**.

Canonical field name:

`evidence_span_original`

The persisted grounding must identify at minimum:

- article_snapshot_id;
- text_representation_id;
- original source language;
- exact_text;
- stable start/end offsets or equivalent exact locator;
- locator_type.

The evidence span must be resolvable against the immutable original-language text representation.

A working or machine translation is auxiliary only and can never replace the original-language evidence span.

Where technically feasible, preserve:

- `claim_text_original` in the source language;
- `claim_text_normalised` as a separate representation.

### Deterministic grounding check — QA-D18 foundation

Before a claim becomes GROUNDED, deterministic code must verify:

- referenced original snapshot exists;
- referenced text representation belongs to that snapshot;
- evidence span resolves exactly;
- exact_text matches the referenced original-language text;
- language relationship is valid;
- locator/offsets are valid.

Translation-only grounding must fail with:

`CLAIM_NOT_GROUNDED_IN_ORIGINAL_SOURCE`

For a material claim this is a blocking failure / human-review condition, not a warning that can be silently ignored.

### Semantic normalisation fidelity — QA-S18 foundation

Compare the normalized claim against the **original-language evidence span**, not merely against a translation.

The normalized claim must preserve materially relevant:

- actor;
- action;
- attribution;
- uncertainty;
- modality;
- quantity;
- unit;
- time;
- location;
- negation;
- conditionality;
- source-assessment/reporting language.

Material discrepancy:

`TRANSLATION_MATERIAL_MISMATCH`

and:

`human_review_required = true`

If the source language cannot be interpreted reliably:

`SOURCE_LANGUAGE_INTERPRETATION_UNCERTAIN`

and:

`human_review_required = true`

The valid outcome may be `INSUFFICIENT_INFORMATION` or `HUMAN_REVIEW_REQUIRED`. Do not guess.

If human translation validation is later added, preserve the original text, machine translation and human-validated translation as separate auditable objects/representations.

An official multilingual version published by the source is its own original source snapshot; it is not a working translation of another snapshot.

## 7. Claim data model — minimum Phase 2 requirements

A claim record must support the approved architecture and future lineage/event layers.

At minimum preserve or model:

- claim_id;
- article_id where applicable;
- article_snapshot_id;
- text_representation_id;
- claim_text_original where technically feasible;
- claim_text_normalised;
- `evidence_span_original`;
- claim_type;
- claim_status;
- entities;
- location;
- event_date / candidate date plus confidence where applicable;
- quantity;
- unit;
- source_statement_type/status fields already defined in the cumulative prompt baseline;
- evidence_type;
- directness;
- source reliability assessment where supplied by the approved system model;
- claim credibility fields where applicable;
- independent-confirmation fields only as workflow-compatible placeholders if lineage is not yet implemented;
- fact/assumption marker where applicable;
- created_by_model_run_id;
- human validation/review reference;
- created_at / immutable provenance metadata.

### Canonical claim types

Use the already approved closed enum:

- OBSERVATION
- ANNOUNCEMENT
- PROCUREMENT
- DEPLOYMENT
- OPERATION
- LOSS
- CAPABILITY
- TEST
- DELIVERY
- PRODUCTION
- TRAINING
- POLICY
- DOCTRINE
- ORGANISATION
- TECHNOLOGY
- ASSESSMENT_BY_SOURCE
- OTHER

Do not invent new claim-type IDs during Phase 2.

### Canonical claim statuses

Use the approved workflow vocabulary:

- UNVERIFIED
- PARTIALLY_CORROBORATED
- CORROBORATED
- CONFIRMED_PRIMARY
- CONTESTED
- DISPROVEN
- SUPERSEDED

Phase 2 must not falsely manufacture corroboration. M04 lineage remains the later authority for evidence independence.

## 8. v1.2.1 corrections relevant to Phase 2

The cumulative prompt baseline is **not** “v1.2 alone”. v1.1 remains effective wherever later deltas do not explicitly override it.

### Epistemic status and attribution

`source_epistemic_status` must be derived from authoritative workflow state, not freely invented by M02/M03.

Attribution may be omitted only when the governing closed rule permits it. In particular, automatic low-impact processing must not cause a high-impact claim to appear more certain.

Where the later workflow determines that attribution may be omitted, the condition must be deterministic/auditable. A claim that is not sufficiently corroborated must retain required attribution.

### High-impact state

High-impact context must be object-specific, not one global boolean.

Use object-ID-bound representation conceptually equivalent to:

`claim_id -> high_impact + reasons`

If a claim becomes high-impact after an automatic status was assigned, it requires revalidation.

For a high-impact claim, corroboration-status changes require human confirmation before that strengthened status can be used to justify stronger epistemic treatment or attribution omission.

### Human review / escalation

Human-review decisions use the canonical closed enum:

- APPROVE
- MODIFY_AND_APPROVE
- REJECT
- ESCALATE
- REQUEST_REPROCESSING

AI may recommend or flag; it may not manufacture a human decision.

## 9. Entity handling

Entity resolution is conservative.

Required principles:

- extract entity mentions separately from canonical entity resolution;
- preserve the original mention text;
- do not merge entities solely because names are similar;
- aliases require evidence/rules;
- uncertain resolution stays unresolved;
- no forced entity identity;
- entity relationships must remain auditable;
- M02 may identify mentions; deterministic/conservative resolution creates canonical links only when justified.

Entity resolution errors are preferable as unresolved cases rather than false merges.

## 10. M03 — Classifier

M03 performs taxonomy assignment only.

It may assign multiple approved:

- topic IDs;
- horizontal tag IDs;
- PIR IDs;
- geographic-priority IDs;
- relevant target/entity IDs where the approved schema requires them.

It must:

- use only the supplied closed taxonomy;
- return the target object ID for every assignment;
- preserve uncertainty where classification is ambiguous;
- allow multiple classifications when justified.

It must not:

- invent new taxonomy IDs;
- perform intelligence assessment;
- determine strategic significance;
- generate implications;
- use keyword matching alone as sufficient classification logic.

## 11. PIR definitions for M03

PIR-01 — Capability change  
Combat aviation, air defence, UAS/UCAV, C-UAS, ISR, AEW&C, EW, tanker/mobility, precision/long-range strike, C2, sensor/data fusion and other approved air-domain/supporting capability change.

PIR-02 — Methods / adaptation  
Operational methods, tactics, procedures, doctrine-related adaptation and employment change.

PIR-03 — Readiness / operational capability  
Readiness, deployment, exercises, force availability, operational capability and posture.

PIR-04 — Technology / industrial evolution  
Technology, procurement and defence-industrial development. Preserve maturity distinctions such as intention -> announcement -> contract -> production -> delivery -> IOC -> FOC.

PIR-05 — UAS / C-UAS  
UAS, UCAV, autonomy, swarm, navigation resilience, sensors, AI, EW resilience, detection, soft-kill/hard-kill, cost exchange and scale.

PIR-06 — ISR / data / decision support  
ISR, AEW&C, sensing, data fusion, decision-support and sensor-to-decision developments.

PIR-07 — Hungary / NATO relevance  
Why the development matters to Hungary and/or NATO. Phase 2 M03 may classify relevance to the PIR; it must not yet write the later M06/M07 assessment.

PIR-08 — Indicators / warning  
Observable developments relevant to warning, monitoring and future change.

## 12. Approved topic taxonomy — Phase 2 classification scope

The closed Phase 2 taxonomy must cover at least:

- Combat Air Power
- Integrated Air and Missile Defence / Air Defence
- UAS / UCAV
- C-UAS
- ISR
- AEW&C
- Electronic Warfare
- Air C2 / sensor fusion
- AI / autonomy
- Long-range / precision strike
- Air-launched weapons
- Readiness
- Deployment
- Exercises / training
- Procurement / capability development
- Defence industry where capability-affecting
- Doctrine / concepts / organisation where real capability change is involved
- Air infrastructure
- Conflict lessons / adaptation

Approved horizontal tags include:

- AI / ML
- autonomy
- mass / attritable systems
- sensor-to-decision
- EW resilience
- industrial scalability
- interoperability
- lessons
- human-machine teaming
- cost-effectiveness

Do not silently create adjacent categories. Taxonomy extension requires an explicit controlled change.

## 13. Geographic priorities

GEO_PRIORITY_1:

- Russia
- Ukraine
- Belarus
- NATO eastern flank
- Central / Eastern Europe where relevant to the eastern-flank air picture

GEO_PRIORITY_2:

- United States
- major NATO allies

GEO_PRIORITY_3:

- selective Middle East
- selective Indo-Pacific
- other locations only when directly relevant to the approved intelligence requirement

Also support:

`GLOBAL_WATCH`

Do not force a geographic priority where evidence does not justify one.

## 14. Prompt / provider / run requirements

M02 and M03 prompts:

- live outside business logic;
- are version controlled;
- use structured JSON schemas;
- use low-variance settings appropriate to extraction/classification;
- are activated through the existing audited prompt-version mechanism;
- bind every model run to exact prompt hash/version, module version and model configuration;
- bind model runs to the existing envelope/input/context hashes;
- treat source text as delimited untrusted data.

Real provider credentials must come only from approved secret management.

Before real providers are introduced, implement provider-specific allow-listed non-secret model configuration schemas as required by open item L-13.

## 15. Required Phase 2 tests

At minimum test:

1. Exact original-language span resolution.
2. Wrong offset -> fail.
3. Wrong exact_text -> fail.
4. Translation-only grounding -> fail.
5. Wrong snapshot/text-representation relationship -> fail.
6. Unsupported extracted claim -> not persisted as valid.
7. Attribute/uncertainty/negation loss in normalization -> flagged.
8. Material translation mismatch -> human review.
9. Source-language interpretation uncertainty -> human review / insufficient information.
10. Prompt injection in source text does not change system instructions.
11. Claim type constrained to closed enum.
12. Claim status constrained to closed enum.
13. High-impact revalidation guard works.
14. Worker/service role cannot perform human review decision.
15. Human review decision is audited and version/object bound.
16. Entity ambiguous -> unresolved, not forced merge.
17. M03 cannot invent taxonomy IDs.
18. M03 returns target object IDs for assignments.
19. Multi-label classification works.
20. PIR / topic / geography assignments use only supplied taxonomy.
21. Schema-invalid LLM output -> `SCHEMA_VALIDATION_FAILED`, no silent persistence.
22. Retry/repair logic does not silently alter evidence.
23. model_run contains complete reproducibility metadata.
24. provider failure leaves no partial authoritative claim.
25. original-language Unicode/code-point offsets remain stable through the claim path.

Use normal, edge, failure and adversarial fixtures.

## 16. Phase 2 acceptance criteria

Control Gate 2 may be recommended only if all of the following are demonstrated:

- no valid persisted factual claim without an original-language evidence binding;
- unsupported valid extracted claims in the acceptance corpus: **0**;
- translation-only grounding accepted as authoritative evidence: **0**;
- claim/evidence provenance failures: **0** in acceptance tests;
- schema-invalid outputs silently persisted: **0**;
- non-human execution of human-only claim-review transitions: **0**;
- forced resolution of deliberately ambiguous entity fixtures: **0**;
- invented taxonomy IDs accepted: **0**;
- all Phase 2 migrations, unit, integration and security tests pass;
- prompt/model/run traceability is complete;
- the Phase 1 security/provenance test suite continues to pass;
- K-05 real-source collection validation is completed before final Control Gate 2 approval, but does not block Phase 2 implementation work.

Precision is more important than recall for M02. Missing an ambiguous claim is preferable to persisting an unsupported claim.

## 17. Control Gate 2 evidence package

At the end of Phase 2 return one Control Gate 2 report containing:

- PHASE / GATE
- IMPLEMENTED
- FILES CHANGED
- DATABASE MIGRATIONS
- PROMPTS / SCHEMAS ADDED OR CHANGED
- MODEL / PROVIDER CONFIGURATION
- TESTS ACTUALLY RUN
- TEST RESULTS
- PHASE 2 ACCEPTANCE CRITERIA: PASS / FAIL individually
- UNSUPPORTED CLAIM COUNT
- CLAIM GROUNDING RESULTS
- ENTITY RESOLUTION RESULTS
- TAXONOMY CLASSIFICATION RESULTS
- HUMAN REVIEW / RBAC NEGATIVE TEST RESULTS
- PROMPT-INJECTION TEST RESULTS
- REPRODUCIBILITY / MODEL_RUN RESULTS
- K-05 STATUS
- KNOWN FAILURES
- SECURITY NOTES
- ANALYTICAL-INTEGRITY NOTES
- SPECIFICATION DEVIATIONS
- CHANGE REQUESTS
- OPEN ITEMS
- RECOMMENDED NEXT ACTION

Then STOP.

Do not begin Phase 3 without explicit Product Owner approval.

## 18. Gold Standard isolation

Do not put the GS-001 answer key, curated expected events, expected claims, expected judgments, KJs, trend narrative, failure notes, or evaluation material into:

- prompts;
- few-shot examples;
- fixtures visible to the pipeline;
- reference context;
- baseline context;
- model context;
- developer documentation that is packaged into model input.

GS-001 may be used only through the isolated evaluator/test architecture after the relevant run is complete.

## 19. Closed provenance chain target

The architectural target remains:

SOURCE
→ ORIGINAL-LANGUAGE ARTICLE_SNAPSHOT
→ ORIGINAL-LANGUAGE EXACT EVIDENCE SPAN
→ CLAIM
→ later ASSESSMENT_STATEMENT
→ later REPORT_ITEM_STATEMENT
→ canonical report version + hash
→ QA
→ human approvals
→ release manifest
→ released report version

Phase 2 owns the chain only through CLAIM and must make that portion exact, immutable, reproducible and auditable.

## 20. Execution instruction

Proceed incrementally with **Phase 2 only**.

For each implementation step:

1. state the immediate goal;
2. implement only the required scope;
3. add tests;
4. run them;
5. report failures accurately;
6. update documentation;
7. do not silently alter the approved architecture.

If a genuine conflict is discovered, stop the affected work and submit a CHANGE REQUEST.

Do not treat missing wording from an earlier compressed chat as permission to invent architecture. This addendum is the Product Owner's authoritative replacement for the missing Phase 2 execution wording.

After Phase 2 is complete, submit the Control Gate 2 evidence package and STOP.
