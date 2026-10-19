# Phase 4 — Relevance, assessment, challenge and human review (design)

Baseline: `docs/specs/LFHE_Phase4_Authoritative_Baseline_Addendum_v1.0.md` (SPEC_INDEX row 15),
PO authorisation `docs/specs/PO_Decision_2026-10-19_Authorise_Phase4.md` (row 16), Module Prompt
Pack v1.2(.2). Migrations `20261011002700` … `20261011003300`.

Phase 4 does **not** implement M09, report selection/composition, report_versions, rendering,
M10, content approval, security review or release (Phase 5/6).

## 1. Subject and knowledge bound

Every Phase 4 analysis is about one **exact** `event_version_id` + `content_hash` that is
eligible under the Phase 3 as-of rules for the run's `report_mode` / `information_cutoff`
(`lfhe.event_version_eligible`). The deterministic input builders
(`services/ai-orchestrator/lfhe_orchestrator/assessment_inputs.py`) read only the database and
supply, for that cutoff: the eligible event version and its claims with their **as-of** claim
status (`lfhe.claim_status_asof`), the as-of lineage / independence summary, the as-of
baseline version, the requested as-of reference-context versions, and (M07 only) a previous
assessment version that was approved as of the cutoff. Processing may happen after the cutoff;
knowledge may not. `created_at` alone is never a knowledge proof.

`lfhe.p4_object_eligible(type, id, mode, cutoff)` is the single dispatcher (claim, article,
event_version, reference_context_version). As-of claim status: an `INITIAL_EXTRACTION` row is
bounded by the claim itself; a row tied to a recommending model run is bounded by that run's
evidence; any other row has no reproducible bound — LIVE only if recorded ≤ cutoff, never REPLAY.

## 2. Baselines and reference contexts (P4-01, migration 2700)

| Object | Rules |
| --- | --- |
| `baselines` (`BL-…`) / `baseline_versions` | immutable, `content_hash = p4_hash('lfhe-baseline-version/1', …)` (CHECK); `knowledge_as_of`; every component carries evidence (`baseline_component_evidence`, claim / event_version / reference_context_version) — `BASELINE_COMPONENT_UNATTRIBUTED`; evidence may not post-date `knowledge_as_of` — `EVIDENCE_POSTDATES_KNOWLEDGE_AS_OF` |
| `reference_contexts` (`RC-…`) / `reference_context_versions` | same pattern, ≥ 1 provenance reference (`REFERENCE_CONTEXT_PROVENANCE_REQUIRED`) |
| decisions | `*_decisions` APPROVE / REJECT, one per version, bound to id + hash (`VERSION_HASH_MISMATCH`), HUMAN_ONLY |

Usable as of (mode, cutoff) ⇔ approved **and** `knowledge_as_of ≤ cutoff` **and** all evidence
eligible at the cutoff. Approval may be recorded after the cutoff. `baseline_asof` /
`reference_context_asof` return the latest usable version, so a later version never leaks
backwards. Timestamps are hashed as epoch seconds (session-timezone independent).

## 3. M06 relevance (P4-02, migration 2800)

Scores are integers 0–5 (schema + CHECK); `priority_score` is the deterministic Prompt Pack
formula `round(0.25·MS + 0.20·NC + 0.25·HN + 0.20·SR + 0.10·TS, 2)` (CHECK). M06 is **never a
gatekeeper**: it cannot publish or select report items (no such field / capability), cannot
change event or claim state, and every event stays in `event_relevance_queue` regardless of
score. The DS-38 threshold is not defined by a higher-authority document, so none is invented:
`automatic_assessment_recommended` is advisory only.

HU/NATO relevance (PIR-07): established ⇔ `hu_nato_relevance_score > 0`; then dimensions (13
structural codes, `hu_nato_dimension`) and evidence claims of the supplied event version are
required and the rationale must be non-generic (`text_is_generic_relevance`). A recommended /
PIR-07 event without established relevance must state "not established" explicitly. Rejection
codes: see §8.

HUMAN_ONLY (`ASSESSMENT_REVIEW`): `decide_relevance` (VALIDATE / OVERRIDE),
`promote_event_version` (PROMOTE / REQUEST_ASSESSMENT, bound to version + hash), all audited.

## 4. M07 statement-centric assessment (P4-03/04, migration 2900)

An assessment (`assessments`) is a chain of immutable, hash-bound `assessment_versions`, each
bound to the exact event version + hash, baseline version (or `BASELINE_UNAVAILABLE`),
reference-context versions, report mode and cutoff. Content lives in
`assessment_statements` (closed `assessment_statement_type`, Prompt Pack §17), with
`assessment_statement_evidence` (SUPPORTS / CONTRADICTS → claim / baseline_version /
reference_context_version) and `assessment_statement_premises`.

* `epistemic_category` (FACT / ASSUMPTION / ASSESSMENT) is derived deterministically from the
  type (`statement_category`), never taken from the model; an ASSUMPTION can never be stored as
  FACT.
* provenance class (`statement_provenance_class`) must match the evidence actually mapped.
* factual statements need supporting evidence from the supplied, eligible context; judgments
  and implications need premises; the contradictions of the event version must stay visible
  (`CONTRADICTION_OMITTED`).
* deterministic lexical guards (heuristics, documented as such): unsupported causality stated as
  fact, negative evidence from silence, operational recommendations.
* **attribution is deterministic**: `p4_attribution_required(type, claims, rcs, mode, cutoff)`
  from the as-of workflow state (CORROBORATED / CONFIRMED_PRIMARY and an eligible observation
  status), high-impact restrictions and source epistemic status; the model's value must agree
  (`ATTRIBUTION_CONTRADICTS_WORKFLOW_STATE`) and the persisted value is the deterministic one.
* likelihood ≠ confidence: likelihood is per statement and allowed only on the prospective
  analytic types ANALYTIC_JUDGMENT / IMPLICATION (`LIKELIHOOD_NOT_APPLICABLE` otherwise), needs a
  rationale and must use an approved term; the vocabulary
  table `likelihood_terms` is deliberately **empty** (CR4-01), so in production any likelihood
  is rejected until the PO supplies the vocabulary.
* `ai_recommended_confidence` + rationale (≥ 20 chars) only. M07 output containing
  `final_analytic_confidence` is rejected by the schema and by ingestion
  (`FINAL_CONFIDENCE_IS_HUMAN_ONLY`); HIGH on a single evidentiary lineage is rejected
  (`CONFIDENCE_INFLATION_SINGLE_LINEAGE`).
* summary text and indicators resolve only to statement IDs (`assessment_derived_summaries`,
  `authoritative = false`; `assessment_indicator_proposals`).

Workflow (`assessment_state_history`, append-only): DRAFT → CHALLENGED → IN_REVIEW →
APPROVED / REJECTED / ESCALATED / REPROCESSING_REQUESTED; SUPERSEDED. The worker may only do
NULL→DRAFT, DRAFT→CHALLENGED, CHALLENGED→IN_REVIEW.

## 5. M08 challenger (P4-05, migration 3000)

`challenge_runs` are bound to the exact assessment version + hash and hold the free-text
`challenge_result` (no higher-authority enum exists), the strongest counterargument (required),
the confidence challenge and the recommended overall action. `challenge_flags` use closed enums
(`challenge_flag_type` 16, `challenge_severity`, `challenge_recommended_action` 11,
`challenge_affected_field`) and name a statement of the challenged version and/or a field.
M08 can never modify M07: output keys that would rewrite or finalise
(`final_analytic_confidence`, `assessment_statements`, `revised_statements`,
`ai_recommended_confidence`) are rejected (`M08_MAY_NOT_MODIFY_ASSESSMENT`), and M08 runs only
on a DRAFT. A recorded challenge moves the version DRAFT → CHALLENGED → IN_REVIEW. Human
disposition (`challenge_flag_dispositions`: ACCEPTED / REJECTED / ACKNOWLEDGED /
REPROCESSING_REQUESTED / ESCALATED) is a separate, HUMAN_ONLY, audited record
(`dispose_challenge_flag`, `ASSESSMENT_REVIEW`).

## 6. Human analytical review and final confidence (P4-06, migration 3100)

`analytical_approvals` is the **single canonical owner of `final_analytic_confidence`** (DC-01):
immutable, one approval per version, bound to version + hash; confidence + rationale (≥ 20)
exist iff the decision is APPROVE / MODIFY_AND_APPROVE.

* `review_assessment(version, hash, decision, final_conf, rationale, reason)` — APPROVE /
  REJECT / ESCALATE / REQUEST_REPROCESSING; APPROVE also needs `FINAL_CONFIDENCE_SET` (ANALYST).
* `modify_and_approve_assessment(version, hash, {statements, summary, indicators}, …)` — writes a
  **new HUMAN version** re-validated with the same provenance rules
  (`STATEMENT_PROVENANCE_INVALID`), approves that version/hash, marks the old one SUPERSEDED
  (never edited).
* Binding: wrong hash → `VERSION_HASH_MISMATCH`; a later version exists → `REVIEW_STALE`; no
  challenge yet → `ASSESSMENT_NOT_CHALLENGED`.
* A later approval supersedes the earlier approved version (history kept).
  `assessment_version_approved_asof` is the as-of view used when a previous assessment is
  supplied as context.

## 7. Trends and indicators (P4-07, migration 3200)

No AI trend-creation action exists in the cumulative prompt baseline (M07 receives
`related_trends` as input only), so Phase 4 implements persistence + the human/manual path.

* `trends` (`TR-…`) / `trend_versions` (immutable, hashed, `knowledge_as_of`) /
  `trend_events` (exact `event_version_id` + hash, ≥ 2 distinct events —
  `TREND_REQUIRES_MULTIPLE_EVENTS`) / `trend_version_assessments` (approved as of the
  knowledge bound). Direction and velocity are separate fields; uncertainty is mandatory. No
  normative direction/velocity vocabulary exists → human free text (CR4-02).
* `indicators` (`IND-…`) / `indicator_versions` / `indicator_claims`: created only by a human,
  only from an APPROVED assessment version (optionally from one of its M07 proposals), bound to
  version + hash, to statements of that version and to claims of its event version (or of the
  bound trend's events). `p4_indicator_problems` rejects non-observable, vague and operational
  indicators; a vague proposal can become authoritative only through a human correction
  (`INDICATOR_REQUIRES_HUMAN_CORRECTION`); `human_corrected` is recorded.

## 8. Fail-closed ingestion

One database call = one transaction per model output; any problem rejects the whole output and
writes only the ingestion-result row (outcome + reasons). Rejection codes:

* M06 — EVENT_VERSION_NOT_IN_MODEL_RUN_INPUT, EVENT_VERSION_NOT_CUTOFF_ELIGIBLE,
  BASELINE_NOT_SUPPLIED_OR_INELIGIBLE, PREVIOUS_ASSESSMENT_NOT_SUPPLIED, PIR_ID_UNKNOWN,
  HU_NATO_DIMENSION_REQUIRED, HU_NATO_EVIDENCE_REQUIRED, HU_NATO_EVIDENCE_NOT_IN_EVENT_VERSION,
  HU_NATO_RATIONALE_GENERIC, HU_NATO_NOT_ESTABLISHED_STATEMENT_REQUIRED,
  HU_NATO_DIMENSIONS_WITHOUT_ESTABLISHED_RELEVANCE.
* M07 — EVENT_VERSION_NOT_SUPPLIED, EVENT_ID_MISMATCH, BASELINE_NOT_AS_SUPPLIED / _INELIGIBLE,
  PREVIOUS_ASSESSMENT_*, FINAL_CONFIDENCE_IS_HUMAN_ONLY, CONFIDENCE_RATIONALE_REQUIRED,
  CONFIDENCE_INFLATION_SINGLE_LINEAGE, plus the statement codes STATEMENT_LOCAL_ID_INVALID_OR_DUPLICATE,
  STATEMENT_ENUM_UNKNOWN, EVIDENCE_NOT_SUPPLIED, POST_CUTOFF_EVIDENCE,
  REFERENCE_CONTEXT_NOT_SUPPLIED / _INELIGIBLE, BASELINE_UNAVAILABLE, CHANGE_WITHOUT_BASELINE,
  PROVENANCE_CLASS_MISMATCH, FACTUAL_STATEMENT_WITHOUT_EVIDENCE, UNSUPPORTED_CAUSALITY_AS_FACT,
  NEGATIVE_EVIDENCE_FROM_SILENCE, JUDGMENT_WITHOUT_PREMISES, PREMISE_UNKNOWN,
  LIKELIHOOD_NOT_APPLICABLE / _TERM_UNKNOWN / _RATIONALE_REQUIRED,
  OPERATIONAL_RECOMMENDATION_PROHIBITED, ATTRIBUTION_CONTRADICTS_WORKFLOW_STATE,
  ATTRIBUTION_MISSING, CONTRADICTION_OMITTED, SUMMARY_UNMAPPED,
  SUMMARY_REFERENCES_UNKNOWN_STATEMENT, INDICATOR_*.
* M08 — ASSESSMENT_VERSION_NOT_SUPPLIED, ASSESSMENT_VERSION_HASH_MISMATCH,
  ASSESSMENT_NOT_IN_DRAFT, M08_MAY_NOT_MODIFY_ASSESSMENT, STRONGEST_COUNTERARGUMENT_REQUIRED,
  FLAG_TARGET_REQUIRED, FLAG_TARGET_UNKNOWN, EVIDENCE_NOT_SUPPLIED.

Schema failure → at most one transparent repair run with identical inputs (separate
`model_run`); provider failure → `PROVIDER_ERROR`; neither leaves authoritative state.

## 9. Prompts, model runs, jobs

Bundles `packages/prompts/{M06_RELEVANCE,M07_INTELLIGENCE_ASSESSOR,M08_CHALLENGER}/1.0.0`
(module_version `MPP-1.2.2+P4-ADDENDUM-1.0`, JSON-schema constrained, `additionalProperties:
false`, locked in `prompt-lock.json`, low-variance configuration required). Every call is one
immutable `model_run` with prompt version/hash, module version, model configuration/hash,
envelope hash, input/context manifests and snapshots, task parameters (`report_mode`,
`information_cutoff`) and raw output / failure state. Source text stays inside the untrusted
data envelope. No GS answer-key material enters any prompt, fixture or context.

Jobs (migration 3300): `ASSESS_RELEVANCE` (M06), `ASSESS_EVENT` (M07; a recorded draft
deterministically enqueues `CHALLENGE_ASSESSMENT` for its exact version + hash),
`CHALLENGE_ASSESSMENT` (M08; ends in `HUMAN_REVIEW`). M06 never enqueues M07. Model
configurations: `LFHE_M06/M07/M08_MODEL_CONFIGURATION_ID`; provider credentials only from
secret management.
