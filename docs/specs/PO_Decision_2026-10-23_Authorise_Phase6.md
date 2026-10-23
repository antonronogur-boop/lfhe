<!-- PO decision received 2026-10-23 15:40 (Europe/Budapest). Stored verbatim (SD-12). -->

PRODUCT OWNER DECISION — AUTHORISE PHASE 6

LFHÉ — PHASE 6: QA, APPROVAL & RELEASE

Date: 2026-10-23

CONTROL GATE 5 is APPROVED.
PHASE 5 is ACCEPTED AND CLOSED.

The current repository state contains the completed and accepted Phase 1–5 implementation. The current main branch includes the CG5 closure decision recorded in:

`docs/specs/PO_Decision_2026-10-23_Control_Gate_5.md`

The Phase 5 closure commit is:

`8c9472c`

Phase 6 has not yet started.

This Product Owner decision now explicitly AUTHORISES PHASE 6.

You are authorised to create the Phase 6 authoritative baseline described below and then proceed directly with Phase 6 implementation without requesting a separate approval of that baseline.

Do not stop after drafting the baseline.
Do not ask for permission between P6 steps.
Do not begin Phase 7.

==================================================
0. AUTHORITATIVE ACTION
==================================================

FIRST:

1. Save the complete AUTHORITATIVE PHASE 6 BASELINE contained in this decision verbatim as:

`docs/specs/LFHE_Phase6_Authoritative_Baseline_Addendum_v1.0.md`

2. Save this Product Owner decision verbatim using the established naming convention as:

`docs/specs/PO_Decision_2026-10-23_Authorise_Phase6.md`

3. Update:

- `docs/SPEC_INDEX.md`
- `docs/PROJECT_STATUS.md`

4. Commit the baseline / PO-authorisation state before substantive Phase 6 implementation, consistent with the established phase workflow.

This decision itself constitutes explicit Product Owner approval of the Phase 6 baseline.

No second baseline-approval round is required.

After P6-00 is complete, proceed immediately through P6-01 … P6-10.

==================================================
1. AUTHORITY / SPECIFICATION HIERARCHY
==================================================

The existing LFHÉ authority hierarchy remains unchanged.

Use, in order:

1. explicit current Product Owner decision;
2. System Concept v1.0;
3. Claude Master Specification v1.0;
4. Specification Enforcement Addendum v1.0;
5. Development Specification v1.0;
6. cumulative approved Module Prompt baseline, including v1.2 / v1.2.1 / v1.2.2 semantics;
7. approved CG0 architecture;
8. approved phase-specific baselines and PO decisions;
9. implementation preference.

This Phase 6 baseline is a phase-specific operationalisation of the already-approved M10 / QA / approval / security / release architecture.

Do NOT reopen CG1–CG5.

Do NOT perform a generic architecture audit.

Do NOT reinterpret already closed Phase 1–5 semantics unless a genuine implementation incompatibility is discovered.

If a genuine contradiction is found:

- stop only the affected subpart;
- document the exact conflict as a Change Request;
- continue unaffected Phase 6 work;
- do not use a minor implementation preference to reopen closed architecture.

==================================================
2. PHASE 6 PURPOSE
==================================================

Phase 6 converts an immutable Phase 5 DRAFT report version into a formally QA-checked, human-approved, security-reviewed and releasable intelligence product.

Authoritative chain:

DRAFT REPORT VERSION
→ M10-D DETERMINISTIC QA
→ M10-S SEMANTIC QA
→ COMBINED QA RESULT
→ WARNING ACKNOWLEDGEMENT IF REQUIRED
→ HUMAN CONTENT APPROVAL
→ HUMAN SECURITY / HANDLING REVIEW
→ PDF RELEASE ARTIFACT
→ DETERMINISTIC RELEASE ELIGIBILITY CHECK
→ HUMAN RELEASE DECISION
→ ATOMIC RELEASE MANIFEST + RELEASED STATE

The final product must preserve the entire LFHÉ traceability chain:

SOURCE
→ ORIGINAL-LANGUAGE ARTICLE SNAPSHOT
→ ORIGINAL-LANGUAGE EXACT EVIDENCE SPAN
→ CLAIM
→ ASSESSMENT STATEMENT
→ REPORT ITEM STATEMENT
→ REPORT VERSION + HASH
→ M10-D / M10-S QA
→ HUMAN APPROVALS
→ SECURITY REVIEW
→ RELEASE DECISION
→ RELEASE MANIFEST
→ RELEASED PDF

Phase 6 is not a new analytical stage.

M10 checks integrity.
M10 does not become an analytical authority.
M10 does not rewrite the report.
Human accountability remains outside M10.

==================================================
3. PHASE 6 IN SCOPE
==================================================

Implement:

- M10-D deterministic QA engine;
- M10-S semantic QA auditor;
- exact report-version/hash-bound QA runs;
- QA findings;
- deterministic combined QA status;
- PASS / PASS_WITH_WARNINGS / FAIL;
- warning acknowledgement;
- human content approval;
- human security / handling review;
- deterministic release eligibility;
- final PDF release artifact;
- PDF SHA-256;
- release decisions;
- immutable release manifest;
- manifest canonicalisation and SHA-256;
- RELEASED state;
- Phase 6 audit events;
- Phase 6 RBAC enforcement;
- Phase 6 analyst/reviewer/security/release workspace;
- post-QA invalidation semantics;
- correction semantics for a previously released report;
- Phase 6 tests;
- Phase 1–5 regression;
- DEV smoke extensions;
- Control Gate 6 report.

==================================================
4. PHASE 6 OUT OF SCOPE
==================================================

Do NOT implement:

- Phase 7 pilot operations;
- operational deployment to a real unit;
- classified / restricted ingestion;
- automatic classification marking by AI;
- external dissemination integrations;
- email dissemination;
- NATO system integration;
- new collection modules;
- new analytical M07/M08 semantics;
- new reporting M09 semantics;
- autonomous security approval;
- autonomous release;
- AI-generated release decisions;
- AI-generated authoritative warning acknowledgements;
- AI-generated authoritative content approval;
- AI-generated authoritative security approval;
- any pathway allowing worker / scheduler / service_role to create RELEASED;
- Gold Standard answer-key access by M10;
- any Phase 7 usability or operational-effectiveness experiment.

Existing non-blocking items remain non-blocking unless the Product Owner explicitly changes them:

- `/reports` browser click-through on DEV;
- K-11 / GS-001 Patriot-trap channel;
- real-provider trial;
- Phase 4 review UI.

Do not convert these into CG6 blockers.

The real-provider trial remains NON-BLOCKING for CG6 unless the Product Owner explicitly changes that decision.

==================================================
5. PHASE 6 DESIGN DECISIONS
==================================================

The following are explicit Product Owner Phase 6 decisions resolving implementation ambiguity.

### DC6-01 — IMMUTABLE REPORT VERSION REMAINS IMMUTABLE

Do not mutate the Phase 5 canonical `report_versions` object in place.

A report version remains the immutable content artifact created in Phase 5.

Phase 6 workflow state must be represented through separate exact:

`(report_version_id, report_version_hash)`

bound QA / approval / security / release records and, if useful, a derived workflow-state view.

Do not weaken Phase 5 immutability merely to implement the Phase 6 state machine.

### DC6-02 — SECURITY STATE IS NOT M10 CONTENT QA

QA-15 / security status is not part of normal M10 content QA.

Security review occurs only after a final QA-acceptable report version and content approval.

Security status is checked by the deterministic pre-release eligibility gate.

### DC6-03 — MANIFEST CHECK SEQUENCING

QA-16 / D25 must not require a final release manifest to exist before content QA.

During M10-D, validate manifest prerequisites / structural readiness where applicable.

The definitive manifest-structure and manifest-completeness validation occurs deterministically immediately before / during the atomic release transaction.

Do not ask M10-S to judge manifest correctness.

### DC6-04 — PDF IDENTITY

The authoritative released PDF is identified by the exact stored PDF bytes and their SHA-256.

Do not claim byte-for-byte PDF reproducibility unless the implemented Chromium stack actually guarantees it.

The required guarantees are:

- PDF generated from the exact report version/hash;
- exact template version;
- exact template hash;
- exact renderer version;
- exact renderer hash;
- stored PDF bytes;
- stored PDF SHA-256;
- immutable released artifact.

The deterministic HTML foundation from Phase 5 remains authoritative input to PDF rendering.

### DC6-05 — WARNING POLICY

PASS_WITH_WARNINGS may become release-eligible only when:

- no CRITICAL finding exists;
- every warning requiring acknowledgement is explicitly acknowledged by an authorised human;
- acknowledgement is bound to the exact QA result and exact report version/hash.

A warning acknowledgement cannot:

- convert FAIL to PASS;
- override a CRITICAL finding;
- modify report text;
- modify QA findings.

### DC6-06 — RELEASED REPORT CORRECTION

A released report must never be altered in place.

If a human later corrects released content:

- create a new report version;
- preserve the released predecessor;
- emit `REPORT_CORRECTION_CREATED`;
- run the complete Phase 6 QA / approval / security / release sequence again;
- create a new release decision and new manifest.

Previous release artefacts remain immutable historical records.

==================================================
6. PHASE 6 STATE MODEL
==================================================

The logical workflow is:

DRAFT_VERSION
→ QA_RUNNING
→ QA_FAILED

or:

DRAFT_VERSION
→ QA_RUNNING
→ QA_PASSED

or:

DRAFT_VERSION
→ QA_RUNNING
→ QA_PASSED_WITH_WARNINGS
→ WARNING_ACKNOWLEDGED

Then:

→ CONTENT_APPROVED
→ SECURITY_REVIEW_PENDING

Security decision:

PENDING
→ APPROVED

or:

PENDING
→ RETURN_FOR_REVISION

or:

PENDING
→ REJECTED

Only an exact version/hash with:

- acceptable QA;
- required warning acknowledgements;
- content approval;
- APPROVED security review;

may enter deterministic release eligibility.

Release decisions:

- APPROVE_FOR_RELEASE
- RETURN_FOR_REVISION
- REJECT_RELEASE

Only:

APPROVE_FOR_RELEASE

may lead to:

RELEASED

RELEASED + release manifest must be created atomically.

A RETURN_FOR_REVISION does not mutate the report.

The analyst returns to the existing Phase 5 human-edit flow, which creates a new immutable report version.

That new version requires new QA.

==================================================
7. PHASE 6 DATA MODEL
==================================================

Use the approved CG0 object names where already specified.

Implement at minimum:

### `qa_runs`

Bound by composite identity to:

- report_version_id;
- report_version_hash.

Required distinctions:

- kind = D / S;
- created_at;
- status;
- model_run_id where applicable;
- prompt_version_id where applicable.

M10-D must not have an LLM model_run.

M10-S must have full model-run provenance.

### `qa_check_results`

Immutable findings belonging to a QA run.

Every finding must preserve the approved M10 finding schema:

- check_id;
- status;
- severity;
- affected_object_id;
- affected_statement_id;
- details;
- evidence_refs;
- recommended_action.

`recommended_action` is advisory.

It must never itself execute a workflow action.

### combined QA result

Use either:

- a minimal additional immutable table; or
- a deterministic derived object/view/function;

whichever fits the existing architecture most cleanly.

It must bind the exact D and S QA runs and exact report version/hash.

### `warning_acknowledgements`

Exact:

- report_version_id;
- report_version_hash;
- QA result / finding identity;
- authorised user;
- acknowledgement;
- rationale;
- timestamp.

Immutable.

### `content_approvals`

Exact:

- report_version_id;
- report_version_hash;
- final combined QA identity;
- decision;
- reviewer;
- rationale;
- timestamp.

Immutable.

### `security_reviews`

Exact:

- report_version_id;
- report_version_hash;
- content approval reference;
- status;
- reviewer;
- rationale;
- timestamp.

Statuses:

- PENDING
- APPROVED
- RETURN_FOR_REVISION
- REJECTED

Immutable.

### release PDF artifact

Add the minimum persistence required to bind an immutable candidate/released PDF to:

- report_version_id;
- report_version_hash;
- template_version;
- template_hash;
- renderer_version;
- renderer_hash;
- storage identity;
- MIME type;
- byte size;
- PDF SHA-256;
- creation time.

Do not modify the Phase 5 PREVIEW row to pretend it is a released PDF.

### `release_decisions`

Exact:

- report_version_id;
- report_version_hash;
- D QA run;
- S QA run;
- combined QA state;
- required acknowledgement references;
- content approval;
- security review;
- PDF artifact;
- decision;
- human release authority;
- timestamp.

### `release_manifests`

At minimum:

- release_decision_id;
- manifest_json;
- manifest_hash.

The release manifest is immutable after release.

All Phase 6 authoritative tables must be:

- RLS protected;
- directly unwritable by ordinary roles;
- append-only / immutable where appropriate;
- written only through the authorised workflow functions.

Use forward-only migrations.

Do not edit already-applied migrations 3500–3700.

Begin Phase 6 migrations after the existing sequence.

==================================================
8. M10-D — DETERMINISTIC QA ENGINE
==================================================

M10-D is ordinary deterministic software.

Do not use an LLM for questions whose answer exists in structured state.

M10-D must cover the deterministic portions of the approved QA architecture, including at minimum:

### QA-01 deterministic portion
- report statement source mappings exist;
- referenced statement IDs resolve;
- required evidence links resolve.

### QA-02 SOURCE EXISTENCE
- all referenced sources / snapshots / evidence objects exist.

### QA-03 DATE FIELD CONSISTENCY
- structured date relationships are valid.

### QA-04 CUTOFF ELIGIBILITY
- LIVE / REPLAY eligibility uses the approved cutoff semantics;
- event time must not become a cutoff criterion;
- post-cutoff evidence is rejected.

### QA-05 deterministic source-independence portion
- known lineage;
- independence groups;
- referenced corroboration state.

### QA-06 deterministic numerical support
- exact number support where structurally decidable;
- derived values require traceable deterministic calculation provenance.

### QA-07 deterministic epistemic-state consistency
- authoritative status / object category consistency.

### QA-08 CONFIDENCE VALUE INTEGRITY
- report confidence equals approved `final_analytic_confidence`;
- `ai_recommended_confidence` cannot become release authority.

### QA-10 APPROVAL STATUS
- every analytical source object used by the report is appropriately approved.

### QA-11 VERSION PINNING
- all required exact version/hash references resolve;
- no floating/latest-only reference may replace a pin.

### QA-12 MODEL / PROMPT TRACEABILITY
- every model-authored object requiring provenance has a valid model_run;
- model configuration and prompt version/hash resolve.

### QA-13 deterministic duplication portion
- known event IDs;
- event relationships;
- explicit merge / split / supersede / keep-separate state.

### QA-14 OSINT BOUNDARY
- deterministic source/meta rules;
- no prohibited internal/classified source category enters the OSINT-only product;
- ambiguous content may be flagged for human handling but must not be auto-approved.

### QA-17 deterministic hindsight portion
- report cutoff;
- evidence eligibility;
- baseline eligibility;
- reference-context knowledge_as_of eligibility.

### REPORT STRUCTURE
- canonical schema valid;
- section vocabulary valid;
- item counts / hard limits;
- required mappings;
- confidence fields;
- likelihood fields;
- selected statement coverage;
- human removals;
- no provenance gaps.

### D18
Original-language claim grounding remains valid.

The authoritative grounding is the original-language article snapshot and exact original-language evidence span.

Translation is auxiliary only.

### D19
Attribution omission rules.

### D20
Required high-impact human validations exist.

### D21
Baseline eligibility.

### D22
Reference-context eligibility.

### D23
QA is bound to exact report_version_id + report_version_hash.

### D24
Human approvals are bound to exact version/hash.

### D25
Manifest prerequisites / and, at final release gate, actual manifest completeness.

M10-D must fail closed on:

- missing object;
- missing mapping;
- bad hash;
- stale/non-current version where current version is required;
- post-cutoff evidence;
- unapproved analytical source;
- missing high-impact validation;
- missing provenance;
- invalid confidence;
- invalid likelihood;
- invalid report structure;
- invalid model/prompt traceability.

==================================================
9. M10-S — SEMANTIC QA AUDITOR
==================================================

Implement the M10 semantic bundle as a new versioned prompt package.

Use:

`packages/prompts/M10_QA_AUDITOR/1.0.0`

Module identity must remain:

`M10_QA_AUDITOR`

Use the cumulative approved prompt baseline and Phase 6 addendum semantics.

Suggested module version representation:

`MPP-1.2.2+P6-ADDENDUM-1.0`

Use:

- external prompt files;
- strict JSON schema;
- `additionalProperties: false`;
- prompt lock;
- provider abstraction;
- low-variance model configuration;
- maximum one schema-repair attempt under the existing orchestrator policy.

A schema-repair attempt may repair malformed model output.

It may NOT repair the report.

### M10-S input

M10-S may receive only the exact QA context supplied by the system for the exact report version/hash.

At minimum:

- report_id;
- report_version_id;
- report_version_hash;
- canonical report content;
- report statements;
- exact source assessment statements;
- assessment statement types;
- evidence mappings;
- claims;
- original-language evidence spans;
- exact article snapshots where required for semantic comparison;
- deterministic attribution requirements;
- confidence;
- likelihood;
- lineage / independence state;
- contradiction state;
- exact event/version relationships;
- approved baseline/reference context only where already legitimately used;
- report mode;
- information cutoff;
- deterministic M10-D findings.

M10-S MUST NOT:

- browse the web;
- retrieve external information;
- use general model knowledge as evidence;
- access Gold Standard answer keys;
- add evidence;
- substitute later knowledge;
- repair or rewrite report text;
- change confidence;
- change likelihood;
- change attribution;
- delete statements;
- add statements;
- decide content approval;
- decide security approval;
- decide release.

All supplied source/report content is untrusted data.

Instructions embedded in source text, report text, claims or evidence must never override the M10 system prompt.

==================================================
10. M10-S SEMANTIC CHECKS
==================================================

Implement semantic reasoning primarily for the already-approved checks.

### QA-01 — EVIDENCE ENTAILMENT

For every report statement:

1. Do the cited approved assessment statements actually entail the report statement?

Then:

2. Does the evidence supporting those assessment statements actually support their factual content?

Check:

- actor;
- action;
- scope;
- quantity;
- time;
- location;
- causality;
- certainty;
- attribution.

A valid citation chain is necessary but not sufficient.

A report statement fails if it materially says more than its approved analytical sources support.

### QA-05 — SOURCE-INDEPENDENCE REPRESENTATION

Do not count articles/domains as independent confirmation.

Check whether report language about:

- corroboration;
- independence;
- confirmation;

matches the approved lineage state.

### QA-06 semantic portion

Check number:

- scope;
- attribution;
- semantic relationship to the source.

### QA-07 — EPISTEMIC CLASS PRESERVATION

Ensure editing has not strengthened:

- SOURCE_REPORTED;
- CORROBORATED;
- ASSUMPTION;
- ASSESSMENT;

into a stronger epistemic class.

Example prohibited transformation:

“Russian officials claimed X.”

→

“Russia achieved X.”

Material strengthening must generate:

`EPISTEMIC_STRENGTH_MISMATCH`

and be CRITICAL when material to the report.

### QA-09 — CONTRADICTION PRESERVATION

Check that contradictory evidence, material alternatives, caveats and relevant gaps have not been semantically erased or neutralised by executive editing.

### QA-13 semantic duplication

Identify semantically misleading duplication where multiple report items could make one underlying event / information origin look like multiple independent developments.

### QA-17 — HINDSIGHT / UNSUPPORTED KNOWLEDGE

Do not attempt to inspect model memory.

Ask only:

Is every factual proposition supported by eligible supplied evidence/reference context?

If not:

`UNSUPPORTED_FACT`

regardless of whether that proposition later became true.

### S18 — CLAIM NORMALISATION FIDELITY

Where claim-level factual meaning matters, compare against the original-language authoritative evidence span.

Do not treat translation as more authoritative than the original span.

### S19 — ATTRIBUTION PRESERVATION

Check that source attribution required upstream still exists with the same epistemic meaning.

### S20 — REFERENCE-CONTEXT SEMANTIC SCOPE

If reference context contributes to a statement, check that the report has not extended it beyond its approved scope.

==================================================
11. M10 FINDING / OUTPUT RULES
==================================================

Every finding must contain:

- `check_id`
- `status`
- `severity`
- `affected_object_id`
- `affected_statement_id`
- `details`
- `evidence_refs`
- `recommended_action`

Finding evidence references must resolve to objects supplied in the QA envelope.

Unknown invented evidence references must fail ingestion.

The authoritative M10 output remains bound to:

- report_id;
- report_version_id;
- report_version_hash;
- deterministic_qa_run_id;
- semantic_qa_run_id;
- QA status;
- findings;
- errors;
- warnings;
- release_blocked;
- human_review_required.

The database/orchestrator — not the LLM — determines the final combined QA state.

==================================================
12. AUTOMATIC FAIL CONDITIONS
==================================================

At minimum the approved automatic fail conditions remain:

- `UNSUPPORTED_FACT`
- `FABRICATED_CITATION`
- `MISSING_REQUIRED_PROVENANCE`
- `POST_CUTOFF_EVIDENCE`
- `UNAPPROVED_ASSESSMENT`
- `UNAUTHORISED_CONFIDENCE_CHANGE`
- `PROHIBITED_INFORMATION`
- `UNPINNED_REQUIRED_VERSION`
- `MATERIAL_EPISTEMIC_STRENGTH_INCREASE`

Any CRITICAL finding blocks release.

A CRITICAL deterministic failure may allow M10-S to run only for diagnostic purposes.

Semantic output can never turn a deterministic CRITICAL failure into a passing result.

==================================================
13. COMBINED QA STATUS
==================================================

The combined QA status is computed deterministically.

Closed final states:

- PASS
- PASS_WITH_WARNINGS
- FAIL

Rules:

### FAIL

If:

- any automatic-fail condition is present;
- any CRITICAL failure exists;
- either required QA run is invalid;
- version/hash binding fails;
- required QA provenance is missing.

### PASS_WITH_WARNINGS

Only if:

- no FAIL condition exists;
- no CRITICAL finding exists;
- one or more non-critical warnings remain.

### PASS

Only if:

- both required QA layers completed;
- no failing finding exists;
- no warning remains.

M10-S never assigns authoritative release eligibility.

==================================================
14. QA RERUN / INVALIDATION
==================================================

QA records are immutable.

Never delete a prior QA run.

If QA is rerun for the same report version/hash:

- create new QA run records;
- preserve old runs;
- identify the current complete QA pair deterministically;
- emit `QA_RESULT_CHANGED_BY_RERUN` if the authoritative combined result changes.

If substantive report content changes:

- Phase 5 creates a new report version/hash;
- all QA / warning acknowledgement / content approval / security review / release eligibility belonging to the previous version cease to be applicable to the new version;
- do not delete them;
- the new version must run QA from the beginning.

==================================================
15. M10 DOES NOT REPAIR
==================================================

M10-D and M10-S must never silently:

- edit report text;
- change confidence;
- change likelihood;
- delete content;
- add content;
- substitute citations;
- substitute evidence;
- change lineage;
- change assessment statements;
- acknowledge warnings;
- approve content;
- approve security;
- release the report.

A finding returns the issue to the appropriate human workflow.

==================================================
16. WARNING ACKNOWLEDGEMENT
==================================================

Warning acknowledgement is HUMAN_ONLY.

Permission:

`QA_WARNING_ACKNOWLEDGE`

Use the already-seeded role model.

Authoritative role:

REVIEWER.

Every acknowledgement must bind:

- exact report_version_id;
- exact report_version_hash;
- exact combined QA result;
- exact warning/finding;
- user;
- timestamp;
- rationale.

A CRITICAL finding cannot be acknowledged into release eligibility.

A warning from an older QA run does not count as acknowledged for a newer authoritative QA result unless the exact finding identity is still valid under the new run and the implementation deliberately preserves that identity safely.

Default safest implementation:

new authoritative QA result → new acknowledgement requirement.

Audit:

`QA_WARNING_ACKNOWLEDGED`

==================================================
17. HUMAN CONTENT APPROVAL
==================================================

Content approval is HUMAN_ONLY.

Permission:

`REPORT_CONTENT_APPROVE`

Authoritative role:

REVIEWER.

A content approval must bind:

- exact report_version_id;
- exact report_version_hash;
- current combined QA result;
- all required warning acknowledgements.

Content may be approved only when:

- QA = PASS;

or:

- QA = PASS_WITH_WARNINGS and every required warning has been properly acknowledged.

FAIL cannot be content-approved.

Content approval decisions must support at minimum:

- APPROVE;
- RETURN_FOR_REVISION;
- REJECT.

If current higher-authority vocabulary already defines exact equivalent codes, use that vocabulary rather than creating synonyms.

Do not allow AI or worker to produce authoritative content approval.

If the existing audit catalogue has no dedicated content-approval event, add the minimum clear Phase 6 audit event in a forward-only migration rather than abusing an unrelated audit code.

==================================================
18. SECURITY / HANDLING REVIEW
==================================================

Security review is HUMAN_ONLY.

Permission:

`SECURITY_REVIEW`

Authoritative role:

SECURITY_REVIEWER.

Security review must start only after valid content approval.

Statuses:

- PENDING
- APPROVED
- RETURN_FOR_REVISION
- REJECTED

The review is bound to:

- exact report_version_id;
- exact report_version_hash;
- content approval.

AI may assist UI display of existing metadata only.

AI must not generate an authoritative APPROVED security decision.

Audit:

`SECURITY_REVIEW_DECIDED`

If report content changes:

the previous security review remains historical but is not valid for the new report version.

==================================================
19. PDF RELEASE ARTIFACT
==================================================

Phase 6 must create the final PDF artifact.

Use the approved Phase 5 rendering foundation:

canonical report JSON
→ deterministic HTML
→ approved template
→ approved renderer
→ headless Chromium PDF.

The PDF must derive from the exact:

- report_version_id;
- report_version_hash;
- canonical JSON;
- template version;
- template hash;
- renderer version;
- renderer hash.

Persist:

- artifact identity;
- storage identity;
- MIME type;
- byte size;
- PDF SHA-256;
- creation timestamp;
- exact version/hash binding.

The PDF must not contain content not present in the canonical report / deterministic rendering source.

The released PDF bytes become immutable.

Do not overwrite a released PDF in place.

If regenerated before release, each materially different byte artifact must have its own identity/hash.

Only the artifact selected by the approved release transaction becomes the released artifact.

==================================================
20. DETERMINISTIC RELEASE ELIGIBILITY
==================================================

Release eligibility is deterministic software.

It is NOT an AI decision.

Immediately before release, re-check all authoritative prerequisites.

At minimum:

1. the report version exists;
2. the supplied report hash equals the stored report hash;
3. the version is the report's current intended release version;
4. current QA belongs to that exact version/hash;
5. M10-D is complete;
6. M10-S is complete;
7. combined QA = PASS;

or:

8. combined QA = PASS_WITH_WARNINGS and all required warnings are validly acknowledged;
9. no CRITICAL finding exists;
10. content approval exists for the exact version/hash and current QA;
11. security review = APPROVED for the exact version/hash;
12. no substantive newer report version invalidates the release candidate;
13. release PDF exists;
14. PDF is bound to exact version/hash;
15. stored PDF SHA-256 matches the actual stored bytes;
16. template and renderer identities/hashes resolve;
17. required prompt / model-run provenance resolves;
18. required analytical provenance resolves;
19. manifest inputs are complete;
20. release caller is an authenticated human with `RELEASE_DECIDE`.

Any failure:

`release_eligible = false`

Fail closed.

==================================================
21. HUMAN RELEASE DECISION
==================================================

Release decision is HUMAN_ONLY.

Permission:

`RELEASE_DECIDE`

Authoritative role:

RELEASE_AUTHORITY.

Allowed decisions:

- APPROVE_FOR_RELEASE
- RETURN_FOR_REVISION
- REJECT_RELEASE

No AI module, worker, scheduler, service_role or ordinary application principal may create authoritative APPROVE_FOR_RELEASE.

Audit at minimum:

- `REPORT_RELEASE_APPROVED`
- `REPORT_RELEASE_REJECTED`
- `RELEASE_RETURNED_FOR_REVISION`

if already available under the approved catalogue.

==================================================
22. RELEASED PROTECTION
==================================================

RELEASED may be created only through a dedicated database release function equivalent to:

`release_report(report_version_id, report_version_hash, ...)`

The function must:

- require an authenticated human;
- require `RELEASE_DECIDE`;
- re-check release eligibility internally;
- verify all version/hash bindings;
- verify PDF hash;
- construct the release manifest deterministically;
- calculate manifest hash;
- create release decision;
- create release manifest;
- create RELEASED state;
- bind the released PDF;

in one atomic transaction.

The worker must not have EXECUTE.

The scheduler must not have EXECUTE.

`service_role` must not have EXECUTE.

anon must not have EXECUTE.

ANALYST must not have release authority.

REVIEWER must not have release authority merely because they can approve content.

SECURITY_REVIEWER must not have release authority merely because they can approve handling.

ADMIN must not automatically gain release authority.

RLS and function-level checks must enforce this.

Direct status writes must not create RELEASED.

==================================================
23. RELEASE MANIFEST
==================================================

The release manifest is the immutable hash-bound inventory of exactly what was released.

At minimum the canonical manifest must contain stable references to:

- manifest schema version;
- report_id;
- report_version_id;
- report_version_hash;
- report mode;
- information cutoff;
- selection-set identity/hash where applicable;
- deterministic QA run ID;
- semantic QA run ID;
- combined QA status;
- M10-S model_run identity;
- M10 prompt version/hash;
- required warning acknowledgement IDs;
- content approval ID;
- security review ID;
- release decision ID;
- released_by;
- release timestamp;
- template version;
- template hash;
- renderer version;
- renderer hash;
- PDF artifact identity;
- PDF SHA-256;
- PDF byte size;
- PDF MIME type.

If a higher-authority manifest specification contains additional required fields, preserve them.

Do not silently omit a higher-authority manifest field.

Canonicalise manifest JSON using the approved JCS approach.

Store:

`manifest_hash = SHA-256(JCS(manifest_json))`

The manifest is immutable after release.

A manifest/hash mismatch is release-blocking.

==================================================
24. RBAC / SEPARATION OF DUTIES
==================================================

Use the already-seeded Phase 6 permissions.

Expected authoritative ownership:

- `QA_WARNING_ACKNOWLEDGE` → REVIEWER
- `REPORT_CONTENT_APPROVE` → REVIEWER
- `SECURITY_REVIEW` → SECURITY_REVIEWER
- `RELEASE_DECIDE` → RELEASE_AUTHORITY

Do not grant Phase 6 authority to ADMIN merely because ADMIN is technical administrator.

Do not grant Phase 6 human authority to `lfhe_worker`.

Do not grant it to service_role.

Do not introduce new broad permissions if the existing permissions suffice.

Existing K-06 separation-of-duties policy remains:

the prototype may allow one human user to hold multiple explicit roles.

Do not invent a mandatory distinct-person rule unless required by higher authority.

Every human authority still requires the relevant explicit role/permission.

==================================================
25. PHASE 6 WORKSPACE UI
==================================================

Extend the existing `/reports` workspace into a functional end-to-end QA/release workspace.

Do not redesign Phase 5 merely for cosmetics.

At minimum an authorised user must be able to see, according to role:

### QA view

- exact report version;
- report hash;
- M10-D status;
- M10-S status;
- combined QA status;
- findings grouped by severity/check;
- affected report statement;
- evidence refs;
- recommended action;
- whether a finding blocks release;
- QA run history / reruns.

### Warning view

An authorised REVIEWER can:

- inspect warning;
- inspect evidence;
- acknowledge with rationale where allowed.

### Content approval view

An authorised REVIEWER can:

- approve;
- return for revision;
- reject;
- see exact version/hash and QA state before acting.

### Security review view

An authorised SECURITY_REVIEWER can:

- see exact report version/hash;
- see content approval;
- see release candidate / preview context;
- APPROVE;
- RETURN_FOR_REVISION;
- REJECT.

### Release view

An authorised RELEASE_AUTHORITY can see:

- exact version/hash;
- deterministic release-eligibility checklist;
- QA status;
- acknowledgements;
- content approval;
- security approval;
- PDF artifact;
- PDF SHA-256;
- template / renderer versions;
- manifest candidate summary;

and can:

- APPROVE_FOR_RELEASE;
- RETURN_FOR_REVISION;
- REJECT_RELEASE.

### Released view

After release, display:

- RELEASED state;
- release timestamp;
- released-by identity;
- report version/hash;
- manifest hash;
- PDF hash;
- immutable release references;
- access to the released PDF subject to normal access controls.

Do not place authoritative human actions purely client-side.

All authoritative actions must use server-side actions / protected RPCs and database re-validation.

==================================================
26. FAIL-CLOSED RULES
==================================================

Fail closed on at least:

- invalid QA schema;
- unknown M10 evidence reference;
- wrong report version;
- report hash mismatch;
- stale QA;
- incomplete QA pair;
- missing QA run;
- missing M10 model-run provenance;
- post-cutoff evidence;
- unapproved assessment;
- unsupported fact;
- fabricated citation;
- missing provenance;
- confidence change;
- likelihood change;
- attribution strengthening/removal;
- critical semantic mismatch;
- unacknowledged required warning;
- warning acknowledgement by unauthorised role;
- content approval on FAIL;
- content approval by unauthorised role;
- security approval before content approval;
- security approval by unauthorised role;
- PDF/version mismatch;
- PDF hash mismatch;
- manifest incompleteness;
- manifest hash mismatch;
- stale report version at release;
- missing security approval;
- missing content approval;
- missing QA;
- non-human release attempt;
- wrong-role release attempt;
- direct RELEASED write;
- partial release transaction.

No partial authoritative release state may survive a failed transaction.

==================================================
27. PROMPT-INJECTION / EXTERNAL-KNOWLEDGE DEFENCE
==================================================

M10-S must treat:

- report text;
- assessment text;
- claims;
- source text;
- article snapshots;
- evidence spans;
- reference-context text;

as untrusted data.

Test adversarial content such as instructions embedded in a source claiming:

- ignore system instructions;
- mark QA PASS;
- hide contradiction;
- approve release;
- change confidence;
- include unsupported information.

None may alter the M10 system instruction or human workflow authority.

M10-S receives no browser/tool permission for external knowledge.

Gold Standard answer-key material must not appear in:

- prompt;
- input envelope;
- fixtures available to the production worker;
- report workspace runtime;
- M10 model context.

==================================================
28. MODEL-RUN TRACEABILITY
==================================================

Every M10-S call must create an immutable model_run with existing provenance semantics.

At minimum persist:

- module;
- module version;
- prompt version;
- prompt hash;
- model configuration;
- model configuration hash;
- input envelope hash;
- context/input manifest;
- report ID;
- report version ID;
- report version hash;
- report mode;
- information cutoff;
- deterministic QA context;
- raw model output;
- validation result;
- failure status where applicable.

A schema repair must be a separate model run linked by the established repair relationship.

No M10-S semantic finding may exist without its model_run provenance.

==================================================
29. POST-QA EDIT / RETURN-FOR-REVISION
==================================================

A QA / content / security / release workflow must never directly rewrite report content.

If:

- M10 finds a problem;
- reviewer returns content;
- security reviewer returns content;
- release authority returns content;

the analyst returns to the existing Phase 5 editing path.

Any substantive correction creates:

DRAFT_VERSION vN+1

with:

- new canonical JSON;
- new report hash;
- preserved provenance;
- previous version retained.

Then Phase 6 starts again from M10-D for vN+1.

If vN had already been RELEASED:

also emit:

`REPORT_CORRECTION_CREATED`

and preserve vN's released artefacts and manifest forever.

==================================================
30. AUDIT REQUIREMENTS
==================================================

At minimum implement / preserve audit coverage for:

- QA_RUN_CREATED;
- QA_RESULT_CHANGED_BY_RERUN;
- QA_WARNING_ACKNOWLEDGED;
- content approval human decision;
- SECURITY_REVIEW_DECIDED;
- REPORT_RELEASE_APPROVED;
- REPORT_RELEASE_REJECTED;
- RELEASE_RETURNED_FOR_REVISION;
- REPORT_CORRECTION_CREATED.

Do not duplicate model_run / operational records unnecessarily into the audit log if established architecture already treats them separately.

All new authoritative human workflow changes must be auditable.

Audit hash-chain integrity must remain intact.

==================================================
31. PDF / STORAGE SECURITY
==================================================

Released PDF storage must:

- contain no credentials in object keys or metadata;
- use the existing approved storage abstraction/policy;
- bind the stored object to exact version/hash;
- verify hash before release;
- never overwrite released bytes;
- remain subject to access control.

Do not put secrets in:

- source code;
- Git;
- prompt files;
- fixtures;
- manifest;
- logs;
- PDF metadata.

Secret scan and gitleaks remain mandatory.

==================================================
32. PHASE 6 ACCEPTANCE COVERAGE
==================================================

Implement sufficient automated tests to prove the following behaviours.

The numbers below are acceptance behaviours, not a mandatory pytest-function count. One well-designed test may prove multiple behaviours, but every behaviour must be traceable.

### M10-D

1. QA-D binds exact report version/hash.
2. wrong hash is rejected.
3. missing report object is rejected.
4. missing statement mapping fails.
5. post-cutoff evidence fails.
6. unapproved assessment fails.
7. confidence mismatch fails.
8. likelihood mismatch fails.
9. missing version pin fails.
10. missing model/prompt provenance fails.
11. invalid original-language grounding fails.
12. baseline after cutoff fails.
13. reference context after cutoff fails.
14. required high-impact validation missing fails.
15. report structure invalid fails.
16. known lineage/independence mismatch is surfaced deterministically where decidable.
17. OSINT boundary violation blocks release.
18. M10-D creates no model_run.

### M10-S

19. supported paraphrase passes semantic entailment.
20. unsupported new fact is CRITICAL/FAIL.
21. unsupported causal claim fails.
22. actor change fails.
23. quantity scope distortion fails.
24. certainty strengthening fails.
25. attribution removal fails.
26. SOURCE_REPORTED → factual assertion strengthening fails.
27. false independent-confirmation wording fails.
28. contradiction deletion fails.
29. misleading semantic duplication is detected.
30. hindsight / later unsupported knowledge fails.
31. original-language semantic mismatch is detected.
32. reference-context scope expansion is detected.
33. prompt-injection text cannot change QA instructions.
34. M10-S cannot repair the report.
35. M10-S cannot change confidence / likelihood.
36. unknown evidence ref in model output is rejected.
37. every M10-S finding has model-run traceability.

### COMBINED QA / WARNINGS

38. D + S clean → PASS.
39. non-critical warning → PASS_WITH_WARNINGS.
40. CRITICAL → FAIL.
41. deterministic CRITICAL cannot be overridden by semantic output.
42. warning acknowledgement requires REVIEWER.
43. warning acknowledgement is exact finding/run/version bound.
44. critical finding cannot be acknowledged into eligibility.
45. new QA run invalidates prior warning handling where appropriate.
46. QA rerun preserves old run history.
47. changed authoritative QA result emits audit.

### CONTENT / SECURITY

48. FAIL cannot be content-approved.
49. PASS can be content-approved by REVIEWER.
50. PASS_WITH_WARNINGS requires required acknowledgements first.
51. ANALYST cannot content-approve merely via REPORT_EDIT.
52. ADMIN cannot content-approve merely through admin role.
53. security review cannot approve before content approval.
54. SECURITY_REVIEWER can decide security review.
55. non-security roles cannot issue authoritative security approval.
56. new report version makes old content/security decisions inapplicable.

### PDF / MANIFEST

57. PDF is bound to exact report version/hash.
58. PDF hash matches stored bytes.
59. PDF hash mismatch blocks release.
60. template version/hash persisted.
61. renderer version/hash persisted.
62. manifest contains required Phase 6 references.
63. manifest JCS/hash is deterministic.
64. manifest mutation is impossible after release.
65. released PDF mutation/overwrite is impossible.

### RELEASE

66. release without QA fails.
67. release with FAIL fails.
68. unacknowledged warnings block release.
69. release without content approval fails.
70. release without security APPROVED fails.
71. stale/non-current report version fails release.
72. worker cannot release.
73. service_role cannot release.
74. anon cannot release.
75. ADMIN cannot release unless explicitly holding RELEASE_AUTHORITY through the normal role system.
76. ANALYST cannot release merely as ANALYST.
77. REVIEWER cannot release merely as REVIEWER.
78. SECURITY_REVIEWER cannot release merely as SECURITY_REVIEWER.
79. RELEASE_AUTHORITY can release only when every deterministic condition passes.
80. APPROVE_FOR_RELEASE creates RELEASED + manifest atomically.
81. failed release creates no partial RELEASED/manifest.
82. RETURN_FOR_REVISION does not modify report.
83. REJECT_RELEASE does not create RELEASED.
84. released version cannot be changed in place.
85. correction after release creates a new version and requires full new QA.

### UI / SECURITY / REGRESSION

86. QA workspace displays exact version/hash and findings.
87. evidence/provenance is inspectable from a QA finding.
88. role-inappropriate buttons/actions do not create authority.
89. release eligibility checklist reflects server/database state.
90. released view displays manifest/PDF hash.
91. XSS-safe rendering remains intact.
92. GS answer-key remains inaccessible.
93. prompt lock passes.
94. secret scan passes.
95. gitleaks passes.
96. all Phase 1–5 regression tests remain green.
97. all Phase 6 tests pass.
98. web tests/typecheck/build pass.
99. DEV smoke contains Phase 6 RBAC/state/hash/release guards.
100. Phase 7 has not started.

Create/update Phase 6 test traceability documentation mapping every behaviour to automated evidence.

==================================================
33. CONTROL GATE 6 ACCEPTANCE CRITERIA
==================================================

CG6 may be recommended APPROVED only if all of the following are PASS:

1. report-version/hash QA binding violations accepted = 0;
2. unsupported report facts accepted by M10 = 0;
3. material epistemic-strength violations accepted = 0;
4. attribution-loss violations accepted = 0;
5. post-cutoff/hindsight violations accepted = 0;
6. provenance gaps accepted = 0;
7. M10 report repairs = 0;
8. CRITICAL findings acknowledged into eligibility = 0;
9. unacknowledged required warnings released = 0;
10. content approvals by unauthorised principals = 0;
11. security approvals by unauthorised principals = 0;
12. releases by non-RELEASE_AUTHORITY principals = 0;
13. releases without valid QA = 0;
14. releases without content approval = 0;
15. releases without security approval = 0;
16. stale-version releases = 0;
17. PDF/version/hash mismatches released = 0;
18. manifest completeness/hash failures released = 0;
19. partial/nonatomic RELEASED states = 0;
20. released report/version/PDF/manifest mutations = 0;
21. M10-S model-run traceability gaps = 0;
22. GS answer-key leakage = 0;
23. audit hash-chain integrity failures = 0;
24. Phase 1–5 regressions = 0;
25. all Phase 6 acceptance behaviours PASS;
26. prompt lock PASS;
27. secret scan / gitleaks clean;
28. web typecheck/tests/build PASS;
29. DEV smoke PASS;
30. Phase 7 implementation NOT STARTED.

==================================================
34. PHASE 6 IMPLEMENTATION ORDER
==================================================

Execute in this order.

### P6-00
Baseline + PO authorisation

- save this baseline;
- save PO decision;
- SPEC_INDEX;
- PROJECT_STATUS;
- commit.

### P6-01
Phase 6 persistence / RBAC foundation

- QA tables;
- warning acknowledgements;
- content approvals;
- security reviews;
- PDF release artifact persistence;
- release decisions;
- manifests;
- exact version/hash bindings;
- RLS;
- immutable rules;
- HUMAN_ONLY functions.

### P6-02
M10-D deterministic QA

- deterministic check engine;
- findings;
- QA run persistence;
- fail-closed behaviour;
- test coverage.

### P6-03
M10-S

- prompt bundle;
- schema;
- prompt lock;
- input builder;
- provider abstraction;
- ingestion;
- semantic tests;
- injection tests;
- model-run traceability.

### P6-04
Combined QA + warnings

- deterministic combined status;
- reruns;
- warning acknowledgement;
- invalidation/applicability rules.

### P6-05
Content approval + security review

- reviewer workflow;
- security workflow;
- RBAC;
- audit.

### P6-06
PDF release artifact

- headless Chromium release rendering;
- storage;
- PDF hash;
- exact version binding;
- immutability.

### P6-07
Release eligibility + release decision + manifest

- deterministic eligibility;
- human release decision;
- manifest JCS/hash;
- atomic RELEASED transaction;
- release protections;
- correction-from-released handling.

### P6-08
Phase 6 report workspace UI

- QA;
- findings/provenance;
- warnings;
- content approval;
- security review;
- release checklist;
- release;
- released product/manifest view.

### P6-09
Acceptance / adversarial / security / regression

- Phase 6 acceptance corpus;
- RBAC negative sweep;
- prompt injection;
- fail-closed cases;
- release atomicity;
- regressions;
- prompt lock;
- secret scan;
- gitleaks;
- web;
- CI.

### P6-10
DEV smoke extension + docs + CG6 report

- extend `scripts/supabase_dev_smoke.py`;
- Phase 6 smoke checks;
- update architecture/workflow docs;
- update permission matrix;
- update audit catalogue;
- update PROJECT_STATUS;
- update SPEC_INDEX if required;
- create `docs/phase6-test-traceability.md`;
- create `docs/control-gate-6-report.md`.

Do not ask for permission between these steps.

==================================================
35. DEV RULE
==================================================

Do not guess the final total migration count in advance.

After Phase 6 implementation, report:

- exact new migration filenames;
- resulting total migration count;
- expected DEV smoke count;
- exact command for the Product Owner to run.

The Product Owner will apply Phase 6 migrations to DEV and return the smoke JSON.

Do not require the Product Owner to send:

- database passwords;
- access tokens;
- service-role keys;
- secrets.

The optional service-role smoke path remains NON-BLOCKING unless the Product Owner explicitly changes it.

==================================================
36. CONTROL GATE 6 REPORT
==================================================

At the end create:

`docs/control-gate-6-report.md`

The report must include at minimum:

- PHASE / GATE;
- IMPLEMENTED;
- FILES CHANGED;
- DATABASE MIGRATIONS;
- PHASE 6 STATE MODEL;
- QA DATA MODEL;
- M10-D RESULTS;
- M10-S PROMPT / SCHEMA;
- SEMANTIC ENTAILMENT RESULTS;
- ATTRIBUTION / EPISTEMIC RESULTS;
- SOURCE-INDEPENDENCE RESULTS;
- HINDSIGHT / CUTOFF RESULTS;
- COMBINED QA RESULTS;
- WARNING ACKNOWLEDGEMENT;
- CONTENT APPROVAL;
- SECURITY REVIEW;
- PDF RELEASE ARTIFACT;
- PDF HASH / VERSION BINDING;
- RELEASE ELIGIBILITY;
- RELEASE DECISIONS;
- RELEASE MANIFEST / MANIFEST HASH;
- RELEASED PROTECTION;
- POST-QA EDIT INVALIDATION;
- RELEASED CORRECTION PATH;
- RBAC RESULTS;
- AUDIT RESULTS;
- PROMPT-INJECTION RESULTS;
- MODEL_RUN TRACEABILITY;
- WORKSPACE UI;
- FAIL-CLOSED RESULTS;
- ACCEPTANCE CORPUS;
- TESTS ACTUALLY RUN;
- TEST RESULTS;
- PHASE 1–5 REGRESSION STATUS;
- CG6 ACCEPTANCE CRITERIA PASS/FAIL;
- DEV SMOKE STATUS;
- KNOWN FAILURES;
- SECURITY NOTES;
- ANALYTICAL-INTEGRITY NOTES;
- SPECIFICATION DEVIATIONS;
- CHANGE REQUESTS;
- OPEN ITEMS;
- RECOMMENDED NEXT ACTION.

For every genuine specification deviation:

- assign SD6-xx;
- state exact rule;
- state implementation;
- state justification;
- do not self-approve it.

For every unresolved material contradiction:

- assign CR6-xx;
- explain why it blocks the affected subpart.

==================================================
37. STOP CONDITION
==================================================

After:

- P6-00 … P6-10 implementation;
- local tests;
- full Phase 1–5 regression;
- web tests;
- production build;
- prompt lock;
- secret scan;
- gitleaks;
- CI;
- CG6 report;

STOP.

Return:

1. concise Phase 6 completion summary;
2. exact test results;
3. exact migration count;
4. exact DEV smoke instructions;
5. CG6 acceptance result;
6. any SD6 deviations;
7. any CR6 change requests;
8. remaining NON-BLOCKING items.

Do not begin Phase 7.

Do not declare CG6 approved yourself.

Only the Product Owner may approve CONTROL GATE 6.

==================================================
38. PRODUCT OWNER AUTHORISATION
==================================================

PHASE 6 — QA, APPROVAL & RELEASE:

AUTHORISED.

The Phase 6 authoritative baseline contained in this decision is APPROVED for implementation.

Proceed directly through:

P6-00 → P6-10.

Do not request a separate baseline approval.

Do not reopen CG1–CG5.

Do not begin Phase 7.

At completion, STOP at Control Gate 6 and wait for the Product Owner decision.