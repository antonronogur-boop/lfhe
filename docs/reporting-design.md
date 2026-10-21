# Phase 5 — Executive reporting (design)

Baseline: `docs/specs/LFHE_Phase5_Authoritative_Baseline_Addendum_v1.0.md` (SPEC_INDEX 19), PO
authorisation `docs/specs/PO_Decision_2026-10-21_Authorise_Phase5.md` (SPEC_INDEX 20), Module Prompt
Pack v1.2 §26–§33, CG0 architecture (table names, REPORT state machine, rendering). Migrations
`20261011003500` … `20261011003700`.

Phase 5 does **not** implement M10-D / M10-S, warning acknowledgement, content approval, security
review, release decision / manifest or any RELEASED state (Phase 6).

## 1. Chain

```
APPROVED assessment / indicator / trend versions (as of the report's mode + cutoff)
  → report_candidate_pool            (deterministic refresh; nothing is ever removed)
  → report_selection_decisions       (HUMAN_ONLY: INCLUDE + section + priority / EXCLUDE / RETURN_FOR_ANALYTICAL_REVISION)
  → report_selection_sets            (HUMAN freeze → immutable, JCS/SHA-256 hashed; enqueues EDIT_REPORT)
  → M09_EXECUTIVE_EDITOR             (sees only the frozen set's approved statements)
  → report_versions (DRAFT_VERSION)  (canonical_json + report_version_hash; items / statements / sources)
  → report_renders (PREVIEW)         (deterministic HTML from canonical JSON + template + renderer)
```

Provenance never skips a layer: SOURCE → SNAPSHOT → EVIDENCE SPAN → CLAIM → ASSESSMENT_STATEMENT →
REPORT_ITEM_STATEMENT → REPORT_VERSION + HASH.

## 2. Vocabularies (higher authority first)

* Sections — Prompt Pack §29, closed: `KEY_JUDGMENT`, `SIGNIFICANT_DEVELOPMENT`, `INDICATOR_WARNING`,
  `TREND_WATCH`, `WHAT_TO_WATCH`, `CAVEAT`. The baseline's "Supporting Developments" / "Indicators" are
  these codes (SD5-01). §10 targets in `report_section_targets`: KJ ≤ 3 (hard), SD 4–5, IW 4–6, WTW 3.
* Editorial transforms — Prompt Pack §30: `VERBATIM_APPROVED`, `PARAPHRASE`, `COMPRESSION`,
  `NON_ANALYTIC_FORMATTING`. Length status — §32: `WITHIN_LIMIT`, `NEAR_LIMIT`, `EXCEEDS_LIMIT`.
* Likelihood — the PO's canonical CR4-01 vocabulary (Phase 4, migration 3400).

## 3. Candidate pool and HUMAN selection

`lfhe.report_candidate_eligible(type, id, mode, cutoff)` decides eligibility:
* assessment version — `assessment_version_approved_asof` (approved, knowable at the cutoff, not
  superseded by a later knowable approval — so a superseded version is never the current source);
* indicator version — usable as of the cutoff and the latest usable version of its indicator;
* trend version — `trend_asof` and ≥ 1 approved assessment (otherwise there is no statement to map).

`refresh_report_candidates` (HUMAN_ONLY trigger of deterministic logic) only adds; every candidate
stays visible. `decide_report_candidate` (HUMAN_ONLY, REPORT_EDIT) is bound to the candidate's
object hash and to the expected previous decision (`SELECTION_STALE`), re-checks eligibility for
INCLUDE (`CANDIDATE_NOT_ELIGIBLE`) and the allowed section per candidate type
(`SECTION_NOT_ALLOWED_FOR_CANDIDATE`; CAVEAT is never assignable — caveats are derived).
`freeze_report_selection` re-checks eligibility, writes the immutable selection set and enqueues the
`EDIT_REPORT` job — this is the human "request M09" action. M09 and the worker never decide inclusion.

## 4. M09 Executive Editor

Bundle `packages/prompts/M09_EXECUTIVE_EDITOR/1.0.0` (module_version `MPP-1.2.2+P5-ADDENDUM-1.0`,
strict schema, prompt-locked, low-variance). Output = Prompt Pack §31 sections, each item with
`source_candidate_id` (SD5-03) and statements per §30 plus `likelihood_term` (SD5-04). The input
builder (`report_inputs.py`) re-checks every selected candidate and supplies only approved statements
with their deterministic attribution, likelihood, contested and caveat flags and the approved
`final_analytic_confidence` (never `ai_recommended_confidence`).

## 5. One validator for M09 and human content — `lfhe.report_content_problems`

| Rule | Code(s) |
| --- | --- |
| item derives from one selected candidate | `SOURCE_CANDIDATE_NOT_SELECTED` |
| human section authority (KJ / SD / IW / TW need the candidate's assigned section; WTW / CAVEAT from any selected candidate) | `SECTION_NOT_AUTHORISED` |
| every statement ≥ 1 source; sources exist and belong to the item's candidate | `REPORT_STATEMENT_WITHOUT_SOURCE`, `UNKNOWN_SOURCE_STATEMENT`, `SOURCE_STATEMENT_NOT_IN_SELECTED_CANDIDATE` |
| role ∈ {item section, CAVEAT}; closed transform; verbatim really verbatim | `STATEMENT_ROLE_INVALID`, `EDITORIAL_TRANSFORM_UNKNOWN`, `VERBATIM_MISMATCH` |
| confidence = approved final confidence; required on KJ statements; no merge across levels; no conflicting confidence phrase | `CONFIDENCE_CHANGED`, `CONFIDENCE_MISSING_ON_KEY_JUDGMENT`, `MERGE_ACROSS_CONFIDENCE_LEVELS` |
| likelihood = the approved source term only (field and wording) | `LIKELIHOOD_ADDED`, `LIKELIHOOD_REMOVED`, `LIKELIHOOD_CHANGED`, `MERGE_ACROSS_LIKELIHOOD` |
| required upstream attribution text survives | `ATTRIBUTION_REMOVED` |
| no new numbers / names, causality, strengthening, operational wording (heuristics, SD5-06) | `UNSUPPORTED_NEW_FACT`, `UNSUPPORTED_NEW_JUDGMENT`, `EPISTEMIC_STRENGTHENING`, `OPERATIONAL_RECOMMENDATION_PROHIBITED` |
| KJ item has an approved judgment; WTW forward-looking; IW from approved indicators; TW from trends; caveat role needs a caveat source | `KEY_JUDGMENT_WITHOUT_APPROVED_JUDGMENT`, `WHAT_TO_WATCH_NOT_FORWARD_LOOKING`, `INDICATOR_NOT_FROM_APPROVED_INDICATOR`, `TREND_NOT_FROM_ELIGIBLE_TREND`, `CAVEAT_WITHOUT_CAVEAT_SOURCE` |
| at most 3 Key Judgments | `MAX_KEY_JUDGMENTS_EXCEEDED` |
| coverage: every selected statement mapped unless removed by a HUMAN decision | `SELECTED_STATEMENT_OMITTED` |
| caveat-class statements (gap, alternative, assumption, contradicted) stay while their assessment is reported | `CAVEAT_REMOVAL_PROHIBITED`, `CAVEAT_REMOVAL_FOR_LENGTH_PROHIBITED` |
| M09 may only propose removal of existing targets; no human-only keys; header not editable | `REMOVAL_TARGET_UNKNOWN`, `M09_HUMAN_ONLY_ACTION`, `REPORT_HEADER_NOT_EDITABLE` |

M09 ingestion also checks the run input, the selection hash and the as-of eligibility of every
selected source (`REPORT_SELECTION_NOT_SUPPLIED`, `SELECTION_HASH_MISMATCH`,
`SOURCE_NOT_APPROVED_OR_INELIGIBLE`). Any problem rejects the whole output; only the ingestion
result row is written.

## 6. Versions, canonical JSON, hash

`report_versions` are immutable; `canonical_json` holds report metadata, version number, previous
version, selection set id + hash, the six sections in fixed order (items with exact pins:
assessment / event / indicator / trend version + hash; statements with role, text, sorted sources,
final confidence, likelihood, transform, contested flag), §10 coverage (counts, `below_target` /
`above_target` — no filler), `human_removals` and `length_status`. `report_version_hash =
SHA-256(JCS(canonical_json))` is a CHECK; `lfhe.jcs` (SQL) and `lfhe_shared.canonical_json` (Python)
are parity-tested. State is `DRAFT_VERSION` only (CHECK). DC-01: no report table has a confidence
column — confidence lives only in the canonical JSON, validated equal to `analytical_approvals`
(SD5-08). Model items are ordered by human priority; human versions keep the human order.

## 7. Length / removal review and human edits

* M09 must keep everything and may only *propose* removals (`report_removal_proposals`); a version
  with `EXCEEDS_LIMIT` (deterministic §10 counts or the model's status) or proposals has
  `length_review_required` and stays `length_review_pending` until `decide_report_removals`
  (HUMAN_ONLY) records a decision for every proposal (ACCEPT / REJECT) or `KEEP_LENGTH`. Accepted
  removals create a NEW human version; removed sources are listed in `human_removals`.
* `edit_report_version` (HUMAN_ONLY): version + hash bound, latest only (`REPORT_VERSION_STALE`),
  same validator, never a no-op (`REPORT_EDIT_NO_CHANGE`); unchanged statements keep their original
  author (MODEL + run), changed ones are HUMAN + user. Audit: `REPORT_TEXT_EDITED` or
  `REPORT_CONTENT_REORDERED`, plus `REPORT_VERSION_CREATED`.

## 8. Rendering (preview foundation)

`report_render.py` renders HTML as a pure function of canonical JSON + version id/hash + template
`LFHE-EXECUTIVE-REPORT/1.0.0` (`packages/report-templates/…/template.css`, print layout, A4) +
renderer `lfhe-report-renderer/1.0.0`. Low confidence is dashed and labelled; contested statements
are marked; empty sections say that no approved material was selected (never "none"). The HTML
escapes all text and embeds the version id, hash, template and renderer versions. `report_renders`
persists template / renderer versions and SHA-256s for Phase 6 (K-09); status is `PREVIEW` only;
`RENDER_NONDETERMINISTIC` guards re-renders. PDF is Phase 6 (SD5-10).

## 9. Workspace

`apps/web/app/reports` — list / create; per report: pool (context: M06 priority, approved confidence,
state, decision; guarded include / exclude / return; refresh; freeze → M09), draft (sections,
coverage, confidence / caveat / contested encoding, per-statement provenance down to claims, removal
decisions, provenance-preserving reword / reorder / human removal — each a new version), versions
(statement-level compare), preview (stored render in a sandboxed iframe). Every decision is a
server action calling a HUMAN_ONLY RPC; the database re-validates everything.

## 10. Jobs

`EDIT_REPORT` (object: selection set; enqueued only by `freeze_report_selection`) → M09 → version;
every new version enqueues `RENDER_REPORT` (object: version; payload: hash) → preview.
Configuration: `LFHE_M09_MODEL_CONFIGURATION_ID`.
