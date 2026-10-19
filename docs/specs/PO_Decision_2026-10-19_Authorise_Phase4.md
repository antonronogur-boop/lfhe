<!-- PO decision received 2026-10-19 20:05 (Europe/Budapest). Stored verbatim (SD-12). -->

PRODUCT OWNER DECISION — AUTHORISE PHASE 4

CONTROL GATE 3 is CLOSED and APPROVED.

Phase 4 — Relevance, Assessment & Challenge is now AUTHORISED.

Before writing Phase 4 implementation code, create and version:

docs/specs/LFHE_Phase4_Authoritative_Baseline_Addendum_v1.0.md

and add it to docs/SPEC_INDEX.md.

Save the following Phase 4 baseline verbatim.

Do NOT return for a separate baseline-approval round.
After storing the baseline, proceed directly with Phase 4 implementation.

==================================================
LFHÉ — PHASE 4 AUTHORITATIVE BASELINE ADDENDUM v1.0
==================================================

STATUS:
PRODUCT OWNER / DEVELOPMENT HANDOFF ADDENDUM

SCOPE:
Phase 4 — Relevance, Assessment & Challenge

Primary modules:

- M06 Relevance Analyst
- M07 Intelligence Assessor
- M08 Challenger
- analytical human-review workflow

Phase 4 also establishes the P4 persistence/provenance layer for:

- assessment_versions
- assessment_statements
- assessment_statement_evidence
- analytical_approvals
- baseline_versions
- reference_contexts / reference_context_versions
- structured M08 challenge flags and analyst dispositions
- trends / trend_versions / trend_events
- indicators / indicator_claims

This addendum does not supersede:

- System Concept v1.0
- Claude Master Specification v1.0
- Specification Enforcement Addendum v1.0
- Development Specification v1.0
- cumulative Module Prompt Baseline v1.1 + v1.2 + v1.2.1 + v1.2.2
- approved CG0 architecture
- CLOSED Phase 1, Phase 2 and Phase 3 invariants
- approved Product Owner decisions already stored under docs/specs/

If a higher-authority document contains an exact closed enum,
threshold or formula, use that exact definition.

Do not silently replace an existing normative value with a new one.

==================================================
1. PHASE 4 OBJECTIVE
==================================================

Phase 4 moves from:

EVENT

to:

SIGNIFICANCE → ASSESSMENT → CHALLENGE → HUMAN ANALYTIC REVIEW

while preserving the LFHÉ core chain:

INFORMATION
→ CHANGE
→ SIGNIFICANCE
→ ASSESSMENT
→ OUTLOOK

Phase 4 must answer:

1. Which events matter enough to deserve analyst attention?
2. Why do they matter, especially for Hungary and/or NATO?
3. What can legitimately be assessed from the supplied evidence?
4. What remains uncertain?
5. What alternative explanations exist?
6. What observable indicators should be watched?
7. What weaknesses, biases or unsupported reasoning exist in the draft?
8. What is the human analyst's final judgment and analytic confidence?

Phase 4 does NOT create a report.

Do NOT implement:

- M09 Executive Editor
- report selection/final composition
- report_versions
- report rendering
- M10 report QA
- content approval
- security review
- release
- Phase 5 or Phase 6 workflows

==================================================
2. NON-NEGOTIABLE INHERITED RULES
==================================================

All CLOSED Phase 1–3 controls remain authoritative.

In particular:

- OSINT-only.
- Source-derived text remains untrusted DATA, never instruction.
- No source = no fact.
- No evidence = no supported judgment.
- No invented facts.
- No invented provenance.
- No post-cutoff knowledge leakage.
- Every factual claim ultimately remains traceable to an eligible
  original-language snapshot/evidence span.
- Publication count is not independent corroboration.
- FACT / ASSUMPTION / ASSESSMENT remain distinct.
- reported != corroborated.
- LIKELIHOOD != ANALYTIC CONFIDENCE.
- contradictions remain visible.
- uncertainty is a valid output.
- AI proposes.
- Human analysts judge and approve.
- AI/worker/service roles cannot perform human-only analytic approval.
- Invalid output fails closed.
- Historical versions are not overwritten.
- GS answer-key material never enters pipeline/model context.
- Every model output is tied to model_run, prompt/version/hash,
  model configuration, input manifest and context manifest.

Phase 3 as-of / knowledge-bound semantics remain authoritative.

==================================================
3. PHASE 4 INPUT BOUNDARY
==================================================

The authoritative primary subject of M06/M07/M08 is an exact:

event_version_id + event_version content_hash

not a mutable event head.

The exact event version supplied must be eligible for:

report_mode
information_cutoff

according to the CLOSED Phase 3 as-of rules.

M07 may additionally receive only explicitly supplied and eligible:

- contributing claims;
- claim statuses;
- claim lineage / independence summary;
- entity/taxonomy assignments;
- object-specific high-impact context;
- baseline_version;
- previous approved assessment_version where applicable;
- approved reference_context_versions;
- prior trend/indicator context only where explicitly eligible.

No module may silently query external knowledge or browse.

No LLM may decide evidence eligibility.

Eligibility is determined before model invocation.

==================================================
4. M06 — RELEVANCE ANALYST
==================================================

PRIMARY RESPONSIBILITY:

PIR-based triage and relevance assessment.

M06 may:

- score relevance on the approved 0–5 scale;
- identify applicable PIRs;
- provide a concise relevance rationale;
- provide explicit Hungary/NATO relevance;
- recommend whether assessment should be performed;
- identify uncertainty in relevance;
- recommend manual review.

M06 MUST NOT:

- decide publication;
- delete or hide an event;
- create intelligence judgments belonging to M07;
- manufacture Hungary/NATO relevance;
- treat taxonomy matching alone as strategic significance;
- use external knowledge;
- change event/claim status;
- alter provenance.

--------------------------------------------------
4.1 M06 GATEKEEPER CONTROL
--------------------------------------------------

M06 is NOT an exclusion mechanism.

Every scored event remains:

- visible;
- queryable;
- auditable;
- manually promotable;
- manually requestable for assessment.

A low score must never cause deletion or hidden exclusion.

Implement and persist:

- relevance result;
- event_version_id + hash;
- applicable PIR IDs;
- relevance_score 0–5;
- assessment_recommended;
- retain_for_manual_review;
- hu_nato_relevance;
- rationale;
- model_run provenance.

The human analyst must be able to:

- validate the relevance result;
- override it;
- manually promote an event;
- request an M07 assessment regardless of M06 score.

All overrides are audited.

If the higher-authority Development Specification contains the exact
DS-38 recommendation threshold, implement that exact threshold.

If the exact threshold is NOT physically present in the repository,
DO NOT invent a replacement numeric threshold.

In that case:

- relevance_score remains authoritative as a recommendation;
- no event is automatically excluded;
- assessment_recommended remains advisory;
- manual assessment remains available;
- record the absence as a specification note in CG4, not as licence to
  invent a threshold.

--------------------------------------------------
4.2 PIR-07 / HUNGARY-NATO RELEVANCE
--------------------------------------------------

For every event that M06 recommends for assessment, require an explicit
answer to:

"Why should a Hungarian and/or NATO senior military leader care?"

Generic text such as:

"important for NATO"
"strategically significant"
"relevant to European security"

without an evidence-based explanation is invalid.

The rationale must connect the development, where justified, to one or
more concrete dimensions such as:

- capability;
- readiness;
- force protection;
- air defence;
- deterrence;
- interoperability;
- procurement/capability development;
- doctrine or adaptation;
- industrial capacity;
- sensor-to-decision;
- UAS/C-UAS;
- eastern-flank posture;
- warning/monitoring requirement.

Do not force relevance where the evidence does not support it.

"No material HU/NATO relevance established from supplied evidence"
is a valid result.

==================================================
5. BASELINE
==================================================

Phase 4 implements persistent, versioned baseline objects.

A baseline is prior known state against which change is evaluated.

Implement:

baseline_versions

with at minimum:

- stable baseline identity;
- immutable version;
- canonical content/hash;
- knowledge_as_of;
- explicit source/object references;
- previous baseline version where applicable;
- created/approved provenance.

A baseline may not consist of unattributed free text.

Every factual baseline component must resolve to an eligible underlying
object/provenance chain.

For use at cutoff T:

- knowledge_as_of <= T;
- every factual component must itself be eligible for T.

A later baseline must not leak backwards into REPLAY.

M07 must receive the exact baseline_version_id in its context manifest.

If no eligible baseline exists:

- do not fabricate one;
- record BASELINE_UNAVAILABLE / equivalent approved status;
- M07 may still assess current evidence if permitted by the existing
  prompt contract, but must explicitly state that change-vs-baseline
  cannot be established.

==================================================
6. REFERENCE CONTEXT
==================================================

Reference context is curated background knowledge.

Implement:

reference_contexts
reference_context_versions

Required properties:

- immutable versions;
- knowledge_as_of;
- explicit provenance;
- explicit source/object references;
- human approval before use;
- version/hash binding;
- auditable creation/approval/supersession.

Reference context is not model memory.

It may be supplied to M07/M08 only when:

knowledge_as_of <= information_cutoff

AND all factual source components are individually cutoff-eligible.

REFERENCE CONTEXT MUST NOT:

- introduce untraceable facts;
- use model parametric knowledge as evidence;
- bypass cutoff;
- become an unattributed substitute for claims.

Any assessment statement using reference context must link to the exact
reference_context_version_id.

==================================================
7. M07 — INTELLIGENCE ASSESSOR
==================================================

PRIMARY RESPONSIBILITY:

Produce a statement-based intelligence assessment draft using only the
supplied eligible evidence/context.

M07 MAY produce:

- known-fact statements;
- explicit assumptions;
- analytic judgments;
- implications;
- alternative explanations;
- information gaps;
- indicators to watch;
- HU/NATO relevance statements;
- prospective likelihood statements where appropriate;
- AI-recommended analytic confidence + rationale.

M07 MUST NOT:

- browse;
- use unsupplied external knowledge;
- invent facts;
- invent sources;
- convert source opinion into independent corroboration;
- hide contradicting evidence;
- state unsupported causality as fact;
- make targeting recommendations;
- make operational action recommendations;
- produce a final analytic-confidence decision;
- silently omit attribution;
- treat absence of reporting as evidence of absence unless the supplied
  evidence/context establishes a justified collection expectation.

==================================================
8. STATEMENT-CENTRIC ASSESSMENT MODEL
==================================================

Assessment output is statement-centric.

Implement:

assessments
assessment_versions
assessment_statements
assessment_statement_evidence

Do not keep authoritative free-text analytic content in parallel with
unmapped assessment statements.

If convenience summaries exist, they must be DERIVED ONLY from
assessment_statement IDs and remain non-authoritative.

Each assessment statement must have:

- statement_id;
- assessment_version_id;
- exact text;
- statement/provenance class from the approved closed vocabulary;
- evidence references;
- epistemic treatment;
- attribution requirement;
- likelihood only where applicable;
- created provenance.

Use the exact statement/provenance enums already contained in the
cumulative prompt baseline.

Do not silently invent adjacent enum values.

At minimum the implementation must preserve the system-level distinction:

FACT
ASSUMPTION
ASSESSMENT

and must support the existing M07 categories for:

- known facts;
- analytic judgment;
- alternative explanation;
- information gap;
- indicator/watch item;
- HU/NATO relevance.

==================================================
9. STATEMENT PROVENANCE
==================================================

assessment_statement_evidence must bind each statement to one or more of:

- claim_id;
- baseline_version_id;
- reference_context_version_id;

using the approved evidence-role vocabulary.

Every factual statement requires factual provenance.

A factual statement with no evidence mapping is invalid.

An analytic judgment must expose its evidentiary premises.

An assumption must be labelled as assumption.

An alternative explanation must not be presented as known fact.

An information gap must describe what is unknown, not invent an answer.

An indicator must be an observable condition/development.

==================================================
10. SOURCE EPISTEMIC STATUS / ATTRIBUTION
==================================================

M07 may NOT freely choose source epistemic status.

source_epistemic_status is derived deterministically from the
authoritative claim workflow state.

attribution_required is also orchestrator-derived.

Attribution may be omitted only where the approved closed rule allows it.

In particular, attribution may be omitted for a factual statement only
when every governing supporting claim satisfies the approved
corroboration condition:

CORROBORATED
or
CONFIRMED_PRIMARY

and all applicable high-impact human-confirmation rules have been
satisfied.

Otherwise attribution remains required.

The model may not strengthen the apparent certainty of a claim by
removing attribution.

==================================================
11. LIKELIHOOD VS ANALYTIC CONFIDENCE
==================================================

These are separate dimensions.

LIKELIHOOD:

- applies only to uncertain/future outcomes where a probability-type
  judgment is actually being made;
- uses the existing approved likelihood vocabulary;
- must include rationale/evidence;
- must not be used as a generic synonym for confidence.

ANALYTIC CONFIDENCE:

- describes confidence in the analytic judgment given evidence quality,
  independence, consistency and gaps;
- M07 produces only ai_recommended_confidence;
- M07 must provide confidence_rationale;
- final_analytic_confidence is HUMAN_ONLY.

Do not derive final confidence mechanically from source count.

Do not increase confidence merely because several publications repeat
one evidentiary lineage.

==================================================
12. ASSESSMENT VERSIONING
==================================================

Implement immutable:

assessment_versions

At minimum bind:

- assessment_id;
- version_no;
- content_hash;
- event_version_id + hash;
- baseline_version_id where used;
- previous_assessment_version_id where used;
- exact reference-context versions;
- created_by_model_run_id OR human author;
- ai_recommended_confidence;
- final_analytic_confidence;
- workflow state;
- created_at.

No assessment version is edited in place.

Material human modification creates a NEW assessment version.

Historical versions remain available.

An assessment version must be reproducible from its exact:

- event version;
- claims;
- baseline;
- reference contexts;
- prompt/model configuration;
- model_run.

==================================================
13. ASSESSMENT WORKFLOW
==================================================

Preserve the approved state machine:

DRAFT
  -- M07 / AI -->

CHALLENGED
  -- M08 / AI -->

IN_REVIEW
  -- deterministic transition -->

Human review decision:

APPROVE
MODIFY_AND_APPROVE
REJECT
ESCALATE
REQUEST_REPROCESSING

APPROVE:

- binds approval to exact assessment_version_id + content_hash;
- records reviewer;
- records final_analytic_confidence;
- records rationale.

MODIFY_AND_APPROVE:

- creates a new immutable human-authored assessment version;
- preserves statement/evidence mappings;
- requires final_analytic_confidence + rationale;
- approves the NEW version/hash, never mutates the old one.

REJECT / ESCALATE / REQUEST_REPROCESSING are retained and audited.

When a later assessment is approved:

- the prior approved assessment may transition to SUPERSEDED;
- the historical version remains.

Worker/service roles cannot perform these decisions.

==================================================
14. M08 — CHALLENGER
==================================================

M08 is part of Phase 4 and is mandatory.

PRIMARY RESPONSIBILITY:

Independently challenge the M07 draft.

M08 MAY:

- flag unsupported reasoning;
- flag confidence inflation;
- flag contradiction omission;
- flag weak or circular corroboration;
- flag baseline problems;
- flag reference-context contamination;
- flag unsupported causality;
- flag missing plausible alternatives;
- flag assumption/fact confusion;
- flag likelihood/confidence confusion;
- flag weak indicators;
- identify the strongest counterargument;
- recommend LOWER_CONFIDENCE where justified;
- recommend human attention/action using the approved vocabulary.

M08 MUST NOT:

- rewrite M07;
- edit assessment statements;
- delete evidence;
- modify final_analytic_confidence;
- decide analyst disposition;
- browse;
- add external evidence;
- create new facts.

Use the exact CLOSED:

- flag type vocabulary;
- severity vocabulary;
- recommended_action vocabulary

from the cumulative prompt baseline.

Do not invent new enum values if the canonical set exists.

==================================================
15. M08 STRUCTURED STORAGE — G-07
==================================================

Implement structured challenge storage sufficient to preserve:

- challenge run;
- assessment_version_id + hash challenged;
- challenge flag;
- bias/issue category where applicable;
- affected statement_id / affected field;
- severity;
- rationale;
- evidence refs;
- recommended_action;
- model_run_id;
- analyst disposition;
- analyst/disposition timestamp.

M08 output is immutable.

Human disposition is a separate audited record.

An analyst may:

- accept the flag;
- reject the flag;
- acknowledge it without change;
- request reprocessing;
- escalate;

using the existing approved review/disposition vocabulary where defined.

Do not let the M08 model manufacture the analyst disposition.

==================================================
16. HUMAN FINAL CONFIDENCE — G-08
==================================================

Persist separately:

ai_recommended_confidence
final_analytic_confidence

They must never be the same field.

final_analytic_confidence:

- may be set only by authorised human review;
- is bound to assessment version + hash;
- requires confidence rationale;
- is audit logged.

M08 may recommend LOWER_CONFIDENCE.

M08 may never set final_analytic_confidence.

==================================================
17. TRENDS
==================================================

Phase 4 establishes persistent:

trends
trend_versions
trend_events

A trend is a development across multiple events/time states.

Do not collapse EVENT and TREND into one object.

Direction and velocity/speed remain separate concepts.

A single event must not silently become evidence of a multi-event trend.

For Phase 4 v1.0:

- AI may propose trend relationships only if already authorised by the
  cumulative prompt baseline;
- authoritative trend persistence must preserve exact supporting
  event_version references;
- trend versions are immutable;
- historical trend versions remain;
- uncertainty is explicit.

Do NOT create a new autonomous trend-generation model beyond the
approved module architecture.

If the existing higher-authority prompt/specification does not define an
AI trend-creation action, implement the persistence/provenance layer and
human/manual creation/update path only.

This is NOT a blocker for M06/M07/M08.

==================================================
18. INDICATORS
==================================================

Phase 4 establishes persistent:

indicators
indicator_claims

Indicators are observable developments to watch.

An indicator must be:

- observable;
- specific enough to test;
- tied to an assessment/trend/claim as applicable;
- provenance-bound;
- version/audit safe.

An indicator must not be:

- a vague recommendation;
- a hidden analytic conclusion;
- an operational instruction;
- an invented future fact.

M07 may propose indicators_to_watch.

They remain part of the assessment workflow until human approval.

==================================================
19. M06 / M07 / M08 CUTOFF DISCIPLINE
==================================================

Every Phase 4 model run carries:

report_mode
information_cutoff

The deterministic input builder must ensure that:

- event_version is eligible;
- claims are eligible;
- lineage/independence context is as-of;
- baseline knowledge_as_of <= cutoff;
- reference-context knowledge_as_of <= cutoff;
- every factual component behind baseline/reference context is eligible;
- previous assessment context is eligible;
- later assessment/challenge/human decisions do not leak backwards.

Processing may occur after cutoff.

Knowledge/evidence may not.

Never use created_at alone as historical knowledge proof.

==================================================
20. MODEL-RUN / PROMPT REQUIREMENTS
==================================================

Create versioned prompt bundles for:

M06_RELEVANCE
M07_INTELLIGENCE_ASSESSOR
M08_CHALLENGER

Use:

- external prompt files;
- JSON-schema constrained output;
- prompt-lock;
- low-variance model configuration where required;
- existing provider abstraction;
- maximum one transparent repair run;
- exact prompt hash;
- module version;
- model configuration/hash;
- input manifest/hash;
- context manifest/hash;
- envelope hash;
- raw output/failure state.

Source/context material remains inside the untrusted data envelope.

No GS answer-key content may enter any prompt or context.

Real provider execution remains NON-BLOCKING for CG4 unless the
Product Owner explicitly changes this requirement later.

==================================================
21. FAIL-CLOSED REQUIREMENTS
==================================================

Reject the full affected model output where applicable if:

- schema invalid;
- unknown statement enum;
- unknown PIR/taxonomy ID;
- invalid target object;
- event_version was not supplied;
- evidence mapping refers to unsupplied evidence;
- baseline/reference context is cutoff-ineligible;
- attribution treatment contradicts deterministic workflow state;
- model tries to set final_analytic_confidence;
- M08 tries to alter M07;
- model introduces unsupported factual content;
- model references post-cutoff evidence;
- model attempts a human-only action.

No partial authoritative assessment should survive failed ingestion.

==================================================
22. PHASE 4 HUMAN AUTHORITY / RBAC
==================================================

Use minimum necessary permissions.

The following are HUMAN_ONLY:

- M06 relevance override / manual promotion;
- manual request for assessment;
- baseline approval where applicable;
- reference-context approval;
- analytical review;
- final_analytic_confidence;
- M08 flag disposition;
- APPROVE;
- MODIFY_AND_APPROVE;
- REJECT;
- ESCALATE;
- REQUEST_REPROCESSING;
- authoritative trend/manual indicator decisions where implemented.

Worker/service/anon/VIEWER/ADMIN without explicit analytic permission
must not execute them.

Follow existing SECURITY DEFINER hardening:

- fixed search_path;
- minimum grants;
- RLS;
- object/version/hash binding;
- audit event.

==================================================
23. REQUIRED PHASE 4 TESTS
==================================================

At minimum implement tests proving:

M06

1. relevance score is 0–5 only.
2. M06 cannot publish/select a report item.
3. low-scored event remains visible.
4. low-scored event remains manually assessable.
5. manual promotion/request is HUMAN_ONLY and audited.
6. PIR-07 recommended event has explicit non-generic HU/NATO rationale.
7. unsupported HU/NATO relevance can remain "not established".
8. invalid PIR/taxonomy ID fails closed.
9. M06 cannot change event/claim status.

BASELINE / REFERENCE CONTEXT

10. baseline version is immutable/hash-bound.
11. reference-context version is immutable/hash-bound.
12. knowledge_as_of > cutoff is excluded.
13. eligible baseline decided after cutoff may still be used if its
    factual evidence was eligible at cutoff.
14. post-cutoff factual component prevents historical use.
15. REPLAY never receives a later baseline version.
16. REPLAY never receives a later reference-context version.
17. reference context without provenance is unusable.

M07

18. assessment is tied to exact event_version + hash.
19. factual statement without evidence mapping is rejected.
20. claim evidence must belong to supplied eligible context.
21. assumption is not persisted as fact.
22. analytic judgment exposes supporting premises.
23. contradiction is preserved.
24. one evidentiary lineage repeated by several outlets does not inflate
    analytic confidence.
25. source opinion is not converted into independent confirmation.
26. unsupported causal statement is rejected/flagged.
27. negative evidence is not invented from silence.
28. likelihood appears only on prospective uncertain outcome.
29. likelihood and analytic confidence are distinct.
30. M07 can set ai_recommended_confidence but cannot set
    final_analytic_confidence.
31. confidence rationale is mandatory.
32. attribution_required is deterministic, not model-authoritative.
33. insufficiently corroborated factual statement retains attribution.
34. all-correlated/confirmed claims may omit attribution only under the
    approved deterministic rule.
35. high-impact restrictions continue to apply.
36. all summary/convenience text resolves only to statement IDs.

M08

37. M08 cannot mutate M07 assessment.
38. M08 cannot set final_analytic_confidence.
39. M08 flag is bound to exact assessment_version + hash.
40. flag has affected object/field, severity, rationale and action.
41. unsupported/confidence-inflated assessment is flagged.
42. omitted contradiction is flagged.
43. baseline/reference-context contamination is flaggable.
44. strongest alternative/counterargument is preserved.
45. human disposition is separate from model output.
46. worker/service cannot dispose of challenge flags.

HUMAN REVIEW

47. APPROVE is version/hash-bound.
48. MODIFY_AND_APPROVE creates a new immutable version.
49. old version remains unchanged.
50. final analytic confidence is human-only.
51. final confidence requires rationale.
52. later approved version supersedes old approved version without
    deleting it.
53. stale review/version/hash is rejected.

TREND / INDICATOR

54. trend and event are separate objects.
55. trend version is immutable.
56. trend preserves exact event-version membership.
57. one event cannot silently establish a multi-event trend.
58. indicator is bound to supporting assessment/claim evidence.
59. vague/non-observable indicator cannot become authoritative without
    human correction.

SECURITY / REPRODUCIBILITY

60. invalid M06/M07/M08 schema fails closed.
61. provider failure leaves no partial authoritative state.
62. repair is separate model_run.
63. model-run provenance is complete.
64. prompt injection does not alter system instruction.
65. GS answer-key leakage = 0.
66. Phase 1 regressions PASS.
67. Phase 2 regressions PASS.
68. Phase 3 regressions PASS.
69. web/security tests PASS.
70. all human-only Phase 4 functions reject non-human roles.

Use normal, edge, failure and adversarial fixtures.

==================================================
24. PHASE 4 ACCEPTANCE CRITERIA
==================================================

Control Gate 4 may be recommended only when:

1. M06 never hides or deletes below-threshold events.
2. Manual promotion / assessment request works and is human/audited.
3. Every recommended event contains a concrete HU/NATO relevance
   rationale or explicitly states that such relevance is not established.
4. Baseline/reference-context hindsight leakage = 0.
5. Unsupported factual assessment statements persisted = 0.
6. Assessment statements without provenance = 0.
7. FACT / ASSUMPTION / ASSESSMENT category violations = 0 in the
   acceptance corpus.
8. Unlabelled contradiction removal = 0.
9. Independent-evidence inflation from republication = 0.
10. Unsupported causal claims accepted as fact = 0.
11. M07 setting final_analytic_confidence = 0.
12. M08 modifying M07 content = 0.
13. Non-human final analytic approvals = 0.
14. Human approval/version/hash mismatch accepted = 0.
15. Assessment version mutation = 0.
16. GS answer-key leakage = 0.
17. Phase 1–3 regression suites remain green.
18. all Phase 4 unit/integration/security/acceptance tests PASS.
19. model-run traceability is complete.
20. no Phase 5 implementation has started.

The real-provider trial remains non-blocking.

==================================================
25. CONTROL GATE 4 REPORT
==================================================

At Phase 4 completion return one CONTROL GATE 4 report containing:

PHASE / GATE

IMPLEMENTED

FILES CHANGED

DATABASE MIGRATIONS

PROMPTS / SCHEMAS

M06 RELEVANCE RESULTS

M06 GATEKEEPER / MANUAL-PROMOTION RESULTS

HU / NATO RELEVANCE RESULTS

BASELINE MODEL

REFERENCE-CONTEXT MODEL

CUTOFF / AS-OF RESULTS

M07 ASSESSMENT MODEL

ASSESSMENT STATEMENT PROVENANCE RESULTS

FACT / ASSUMPTION / ASSESSMENT RESULTS

ATTRIBUTION / EPISTEMIC STATUS RESULTS

LIKELIHOOD VS ANALYTIC CONFIDENCE RESULTS

M08 CHALLENGER RESULTS

M08 HUMAN-DISPOSITION RESULTS

ANALYTICAL REVIEW / RBAC NEGATIVE TEST RESULTS

ASSESSMENT VERSIONING RESULTS

TREND MODEL

INDICATOR MODEL

FAIL-CLOSED RESULTS

PROMPT-INJECTION RESULTS

REPRODUCIBILITY / MODEL_RUN RESULTS

TESTS ACTUALLY RUN

TEST RESULTS

PHASE 4 ACCEPTANCE CRITERIA — individually PASS / FAIL

PHASE 1–3 REGRESSION STATUS

KNOWN FAILURES

SECURITY NOTES

ANALYTICAL-INTEGRITY NOTES

SPECIFICATION DEVIATIONS

CHANGE REQUESTS

OPEN ITEMS

RECOMMENDED NEXT ACTION

Then STOP.

Do not begin Phase 5.

==================================================
26. EXECUTION AUTHORISATION
==================================================

First:

1. save this complete baseline verbatim as

docs/specs/LFHE_Phase4_Authoritative_Baseline_Addendum_v1.0.md

2. add it to docs/SPEC_INDEX.md;

3. save this Product Owner authorisation under docs/specs/ using the
   established PO-decision naming convention.

That satisfies SD-12.

Then proceed directly with PHASE 4 IMPLEMENTATION.

Expected implementation order:

P4-00
baseline + PO decision + SPEC_INDEX

P4-01
baseline_versions + reference_context versions + cutoff eligibility

P4-02
M06 relevance persistence, prompt/schema, manual override/promotion

P4-03
assessment / assessment_versions / assessment_statements /
statement evidence / version hashing

P4-04
M07 prompt/schema + deterministic input builder + ingestion

P4-05
M08 structured challenge model + prompt/schema + analyst disposition

P4-06
human analytical review, final analytic confidence, immutable
MODIFY_AND_APPROVE workflow

P4-07
trend / indicator persistence and approved Phase 4 interfaces

P4-08
acceptance corpus, security/adversarial tests, regression suite

P4-09
DEV smoke extension + documentation + CG4 evidence report

Do not return merely to ask permission between these P4 steps.

Do not reopen CG1, CG2 or CG3.

Do not perform another generic architecture audit.

Do not change CLOSED Phase 1–3 semantics except where a genuine,
demonstrated compatibility defect requires a forward-only fix.

Do not silently invent missing normative enums or formulas where an
exact higher-authority value already exists.

If a genuine material contradiction with a higher-authority
specification is found:

- stop only the affected sub-part;
- record a CHANGE REQUEST;
- continue unaffected Phase 4 work.

Otherwise complete Phase 4, run the full test suite, prepare the CG4
evidence package and STOP.

Phase 5 remains NOT AUTHORISED.