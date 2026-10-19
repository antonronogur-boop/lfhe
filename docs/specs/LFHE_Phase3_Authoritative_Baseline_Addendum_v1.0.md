<!-- Verbatim Product Owner text (2026-10-19), "PRODUCT OWNER DECISION — AUTHORISE PHASE 3", lines 16–550 of the decision: the authoritative Phase 3 baseline. Stored before any Phase 3 implementation (SD-12). The complete decision message, including the execution authorisation, is kept verbatim in PO_Decision_2026-10-19_Authorise_Phase3.md. -->

==================================================
LFHÉ — PHASE 3 AUTHORITATIVE BASELINE ADDENDUM v1.0
==================================================

STATUS:
PRODUCT OWNER / DEVELOPMENT HANDOFF ADDENDUM

SCOPE:
Phase 3 — Lineage & Events only:
M04 Lineage + M05 Event Builder.

This baseline does not supersede System Concept v1.0, Master Spec v1.0,
Enforcement Addendum v1.0, Development Specification v1.0, the cumulative
Module Prompt baseline, approved CG0 architecture, or any CLOSED Phase 1
or Phase 2 invariant.

--------------------------------------------------
1. PHASE 3 OBJECTIVE
--------------------------------------------------

Phase 3 converts grounded claims into:

- claim-level source lineage;
- independence groups;
- corroboration-status recommendations;
- persistent event candidates;
- immutable event versions;
- explicit claim-to-event membership;
- durable event lineage;
- human-controlled merge / split / supersede decisions.

Phase 3 answers:

1. Are claims evidentially related or independent?
2. Do claims describe the same real-world event?
3. Does new evidence create a new event or update an existing event?
4. How is event ancestry preserved after merge/split/supersede?

Phase 3 MUST NOT implement M06, M07, M08, M09, report QA,
trend/indicator assessment or release.

--------------------------------------------------
2. INHERITED HARD RULES
--------------------------------------------------

Preserve all CLOSED Phase 1 and Phase 2 controls.

In particular:

- source/article/snapshot/evidence-span/claim provenance is immutable;
- source text is untrusted data;
- AI proposes; human authority cannot be bypassed;
- uncertainty is a valid output;
- contradictory evidence is preserved;
- multiple republications are not independent confirmation;
- different publisher, language, wording, headline or domain is not
  evidence of independence;
- M04/M05 may not browse or invent missing evidence, URLs, actors,
  dates or origins;
- schema-invalid/provider-failed output fails closed;
- no partial authoritative object may survive failed processing;
- every AI-produced object/proposal is tied to its model_run, prompt
  version/hash, model configuration, input manifest and context
  manifest;
- GS-001 answer-key material remains isolated from pipeline context.

--------------------------------------------------
3. M04 — LINEAGE
--------------------------------------------------

M04 is responsible for claim-level evidentiary lineage and independence.

M04 MAY:

- propose that claims share an original source;
- identify derived reporting;
- propose an explicitly evidenced external origin;
- propose independence grouping;
- propose a claim corroboration-status change;
- return INSUFFICIENT_INFORMATION;
- require HUMAN_REVIEW_REQUIRED.

M04 MUST NOT:

- infer independence merely from different publishers, languages,
  domains, wording or publication count;
- invent external origins;
- treat semantic similarity as proof of common origin;
- treat different wording as proof of independence;
- silently modify claim status;
- delete prior lineage;
- automatically convert reporting into corroborated fact.

For Phase 3 v1.0 the positive lineage relationships explicitly
authorised are:

COMMON_ORIGINAL_SOURCE
DERIVED_REPORTING

Do not invent additional relationship enums silently.

If no positive lineage is established, do not create a false lineage
relationship.

external_origins may exist when the supplied evidence explicitly
identifies an underlying source sufficiently for audit.
Unknown/suspected origins remain unresolved.

Independence groups are evidentiary groups, not publisher groups.

Claims sharing an established original source/origin belong to the
same independence group.

Republications/derived reports do NOT add independent confirmations.

Unknown independence remains unknown.

--------------------------------------------------
4. CLAIM STATUS
--------------------------------------------------

Canonical statuses remain:

UNVERIFIED
PARTIALLY_CORROBORATED
CORROBORATED
CONFIRMED_PRIMARY
CONTESTED
DISPROVEN
SUPERSEDED

M04 only recommends a status.

For Phase 3 v1.0:

- claim_status_auto_rules remain disabled/empty unless an already
  approved deterministic rule exists;
- do not invent an automatic corroboration rule;
- M04 recommendations require the existing human review workflow
  before final status change;
- CONTESTED, DISPROVEN and SUPERSEDED transitions are explicit,
  preserved and audited;
- contradictory/weakening evidence cannot be removed.

HIGH IMPACT:

Keep the Phase 2 object-specific high-impact design.

Until a separate deterministic high-impact classifier is explicitly
approved:

- automatic high-impact classification remains disabled;
- human-marked high-impact state is authoritative;
- high_impact and reasons are object-specific;
- every status change for a high-impact claim requires human
  confirmation;
- HIGH_IMPACT_REVALIDATION_REQUIRED remains mandatory when applicable;
- automatic corroboration may not be used to strengthen attribution
  treatment for a high-impact claim without human confirmation.

Do not invent high-impact criteria in Phase 3.

--------------------------------------------------
5. M05 — EVENT BUILDER
--------------------------------------------------

Canonical M05 AI proposal vocabulary:

CREATE_NEW_EVENT
UPDATE_EXISTING_EVENT
SUGGEST_MERGE
SUGGEST_SPLIT
SUGGEST_SUPERSEDE
KEEP_SEPARATE
INSUFFICIENT_INFORMATION
HUMAN_REVIEW_REQUIRED

Canonical HUMAN EVENT_ACTION:

CREATE
UPDATE
MERGE
SPLIT
KEEP_SEPARATE
SUPERSEDE
REJECT

M05 may propose structural operations.
It may not perform human-only structural decisions.

CG0 interpretation remains authoritative:

CREATE_NEW_EVENT
→ deterministically materialised AI-originated CANDIDATE is permitted.

UPDATE_EXISTING_EVENT
→ new immutable AI-originated event_version pending review is permitted.

These are not final human validation.

MERGE / SPLIT / SUPERSEDE / REJECT remain HUMAN_ONLY.

--------------------------------------------------
6. EVENT STATE MODEL
--------------------------------------------------

Canonical event lifecycle:

CANDIDATE
ACTIVE
DEVELOPING
CONFIRMED
CONTESTED
CLOSED
REJECTED

AI/service roles may create CANDIDATE or pending-review AI versions.

Promotion from CANDIDATE and final lifecycle decisions are HUMAN_ONLY.

Old event IDs and old event versions must never be deleted.

Historical references must remain resolvable.

--------------------------------------------------
7. EVENT TYPE
--------------------------------------------------

Do not create a new event taxonomy.

PRODUCT OWNER IMPLEMENTATION DECISION:

For Phase 3 v1.0 use the existing canonical claim-type vocabulary as
the compatible event-type vocabulary:

OBSERVATION
ANNOUNCEMENT
PROCUREMENT
DEPLOYMENT
OPERATION
LOSS
CAPABILITY
TEST
DELIVERY
PRODUCTION
TRAINING
POLICY
DOCTRINE
ORGANISATION
TECHNOLOGY
ASSESSMENT_BY_SOURCE
OTHER

This is an explicit PO Phase 3 decision, not an inferred taxonomy.

--------------------------------------------------
8. EVENT CLUSTERING
--------------------------------------------------

Cluster conservatively.

The following are NOT independently sufficient for same-event identity:

- same country;
- same service;
- same manufacturer;
- same platform/system;
- same reporting week;
- lexical similarity;
- same taxonomy/topic.

Event identity should use the combined evidence available for:

- actor;
- action/development;
- object/capability;
- event time;
- location;
- programme/operation;
- quantitative details;
- source lineage;
- explicit references to the same occurrence.

If uncertain prefer:

KEEP_SEPARATE
INSUFFICIENT_INFORMATION
HUMAN_REVIEW_REQUIRED

over over-merging.

Publication date != event date.

New reporting on an old event may UPDATE the existing event rather than
create a false new event.

--------------------------------------------------
9. PERSISTENT EVENT MODEL
--------------------------------------------------

Implement:

events
event_versions
event_claims
event_relationships

events:
stable event identity / workflow head.

event_versions:
immutable versions with canonical hash.

A material event update creates a new version.
Never edit an existing event_version in place.

Each version must be reconstructible from the exact contributing claim
set.

AI-created versions carry created_by_model_run_id.

event_claims:
explicit and auditable claim membership.

--------------------------------------------------
10. G-17 — EVENT LINEAGE
--------------------------------------------------

MERGE / SPLIT / SUPERSEDE must preserve ancestry.

event_relationships must preserve at least the semantics of:

merged_into
superseded_by
split parent → child

Do not delete old event IDs or versions.

MERGE:
- preserve source events;
- record target/survivor;
- preserve previous versions and claim membership.

SPLIT:
- preserve parent;
- create child event identities;
- explicitly record claim redistribution;
- no claim may silently disappear.

SUPERSEDE:
- preserve old event;
- link old → replacement;
- do not rewrite historical references.

All structural actions record actor, reason, time and relevant
object/version hashes.

--------------------------------------------------
11. CONTRADICTIONS
--------------------------------------------------

Contradictory claims may belong to the same real-world event.

Do not erase contradiction through clustering.

Preserve competing claims and their provenance.

CONTESTED event state is HUMAN_ONLY.

DISPROVEN is a claim state and does not delete the historical claim.

--------------------------------------------------
12. TIME / CUTOFF
--------------------------------------------------

LIVE/REPLAY discipline remains unchanged.

Only cutoff-eligible claims/evidence may be used for the relevant
historical/current run.

Event time is not information-eligibility time.

No post-cutoff evidence may be silently used to resolve lineage,
event identity or contradiction.

--------------------------------------------------
13. PROMPTS / MODEL RUNS
--------------------------------------------------

Create versioned M04 and M05 prompt bundles outside business logic.

Use constrained JSON schemas and low-variance configuration.

Only minimum necessary context enters the task envelope.

Source-derived text remains untrusted data.

Every run must retain:

- prompt version/hash;
- module version;
- model configuration/hash;
- provider;
- input manifest/hash;
- context manifest/hash;
- envelope hash;
- raw output / failure state according to existing rules.

Repair is a separate model_run.

Real-provider execution remains NON-BLOCKING for CG3 unless the
Product Owner later explicitly changes that requirement.

--------------------------------------------------
14. HUMAN REVIEW / RBAC
--------------------------------------------------

Lineage validation, independence validation, claim status changes and
final event structural actions are protected human operations.

Worker/service/anon/VIEWER or any role without the explicit permission
must not execute them.

At minimum protect:

- lineage validation/correction;
- independence-group validation/correction;
- claim corroboration-status finalisation;
- event candidate validation/rejection;
- EVENT_ACTION finalisation;
- MERGE;
- SPLIT;
- SUPERSEDE.

Preserve SECURITY DEFINER hardening, fixed search_path, version/hash
binding and append-only audit.

--------------------------------------------------
15. REQUIRED PHASE 3 TESTS
--------------------------------------------------

At minimum test:

1. same underlying source in two outlets ≠ two independent confirmations;
2. different language/publisher/wording ≠ independence;
3. explicit common origin → one independence group;
4. DERIVED_REPORTING does not increase independent confirmations;
5. unknown lineage remains uncertain;
6. M04 recommendation alone does not change claim status;
7. human claim-status change is audited and object-bound;
8. high-impact status change requires human confirmation;
9. worker/service cannot finalise lineage/status;
10. CREATE_NEW_EVENT creates only CANDIDATE;
11. UPDATE_EXISTING_EVENT creates a new immutable event_version;
12. old event_version remains unchanged;
13. country/system/week alone does not force merge;
14. older event + new reporting can update rather than create false new event;
15. publication date != event date;
16. contradiction is preserved;
17. SUGGEST_MERGE does not perform MERGE;
18. SUGGEST_SPLIT does not perform SPLIT;
19. SUGGEST_SUPERSEDE does not perform SUPERSEDE;
20. MERGE requires human authority and preserves old IDs;
21. SPLIT requires human authority and preserves parent/child lineage;
22. SUPERSEDE requires human authority and preserves old reference resolution;
23. REJECT does not delete history;
24. event versions are immutable;
25. material changes change canonical event hash;
26. event claim membership is reconstructible per version;
27. schema failure leaves no partial authoritative state;
28. provider failure leaves no partial authoritative state;
29. model-run traceability is complete;
30. Phase 1 + Phase 2 regression suites remain green;
31. GS answer-key isolation remains intact.

--------------------------------------------------
16. CONTROL GATE 3 ACCEPTANCE
--------------------------------------------------

CG3 may be recommended only if:

- republication never inflates independent confirmation in the
  acceptance corpus;
- publisher/language/wording differences alone never establish
  independence;
- M04 cannot silently finalise claim status;
- high-impact status changes require human confirmation;
- AI cannot perform MERGE/SPLIT/SUPERSEDE;
- human-only structural actions are RBAC protected;
- event versions are immutable and hash traceable;
- merge/split/supersede preserve event ancestry and historical IDs;
- no claim silently disappears through structural event operations;
- conservative clustering does not over-merge weakly related claims;
- all Phase 3 tests pass;
- Phase 1 and Phase 2 regression suites remain PASS;
- model-run provenance is complete;
- GS answer-key leakage = 0.

--------------------------------------------------
17. CONTROL GATE 3 REPORT
--------------------------------------------------

At Phase 3 completion return a single CG3 report containing:

PHASE / GATE
IMPLEMENTED
FILES CHANGED
DATABASE MIGRATIONS
PROMPTS / SCHEMAS
M04 LINEAGE MODEL
INDEPENDENCE-GROUP RESULTS
CLAIM-STATUS WORKFLOW RESULTS
HIGH-IMPACT REVIEW RESULTS
M05 EVENT MODEL
EVENT VERSIONING RESULTS
EVENT CLUSTERING RESULTS
MERGE / SPLIT / SUPERSEDE LINEAGE RESULTS
HUMAN REVIEW / RBAC NEGATIVE TEST RESULTS
FAIL-CLOSED RESULTS
REPRODUCIBILITY / MODEL_RUN RESULTS
TESTS ACTUALLY RUN
TEST RESULTS
PHASE 3 ACCEPTANCE CRITERIA — individually PASS/FAIL
REGRESSION STATUS
KNOWN FAILURES
SECURITY NOTES
ANALYTICAL-INTEGRITY NOTES
SPECIFICATION DEVIATIONS
CHANGE REQUESTS
OPEN ITEMS
RECOMMENDED NEXT ACTION

Then STOP.

Do not begin Phase 4 without explicit Product Owner approval.
