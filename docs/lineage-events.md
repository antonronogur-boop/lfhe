# Phase 3 — Lineage (M04) and Events (M05)

Authority: `docs/specs/LFHE_Phase3_Authoritative_Baseline_Addendum_v1.0.md`
(PO decision `docs/specs/PO_Decision_2026-10-19_Authorise_Phase3.md`).
Migrations: `20261011001800_lineage.sql`, `20261011001900_events.sql`,
`20261011002000_phase3_jobs.sql`, `20261011002100_event_ai_update_carry_forward.sql`,
`20261011002200_external_origin_reuse.sql`.

## 1. Principle

The models propose; the database validates; a human decides. No model output
changes a claim status, validates lineage, establishes independence or performs
a structural event action. Every rule below is enforced in PostgreSQL
(SECURITY DEFINER functions with a pinned `search_path`, `block_mutation`
triggers, CHECK constraints), not only in Python.

## 2. M04 — lineage

### Vocabulary
- `lineage_relationship_type`: `COMMON_ORIGINAL_SOURCE`, `DERIVED_REPORTING` (only).
- `corroboration_recommendation`: `NO_CHANGE`, `POTENTIAL_PARTIAL_CORROBORATION`,
  `POTENTIAL_CORROBORATION`, `POTENTIAL_SOURCE_DEPENDENCE`, `POTENTIAL_CONTESTED`.

### Flow
1. `build_m04_inputs` (deterministic) supplies the cutoff-eligible claims, their
   articles and the validated lineage among them.
2. `run_lineage` → model → schema validation (one separate repair run if invalid)
   → `lfhe.ingest_lineage` (worker only).
3. `ingest_lineage` checks every reference: claims are run inputs and
   cutoff-eligible, articles are inputs, exactly one parent, no self-lineage,
   an allowed relationship type, and an evidenced external origin (the name must
   occur in the claim's original-language evidence span; a URL must occur in the
   source text). **Any problem rejects the whole output** (`OUTPUT_REJECTED`);
   nothing partial is stored.
4. The output becomes `lineage_proposals` and `corroboration_recommendations`,
   both `human_review_required = true`.
5. A human with `CLAIM_REVIEW` decides:
   `decide_lineage_proposal`, `record_claim_lineage`, `retract_claim_lineage`,
   `decide_corroboration_recommendation` (STATUS_STALE-checked; writes a
   `HUMAN_DECISION` status-history row that names the recommending model run).

`claim_lineage` is append-only; corrections are retractions plus new rows.

### External origins
`external_origins` rows exist only when a validated lineage row needs one, and
only when explicitly evidenced. Since migration 2200 an accepted origin reuses
the earliest existing origin with the same normalised name — collapsing is the
conservative direction (found by the acceptance corpus, scenario L3). A human
who needs two distinct same-named origins passes an explicit `external_origin_id`.

### Independence groups (derived, never inferred)
`lfhe.claim_independence_group(claim)` computes connected components over
**human-validated** lineage edges (claim ↔ claim, claim ↔ article, claim ↔
origin). `lfhe.independence_summary(claim_ids)` returns:

```
claims, distinct_groups_upper_bound, claims_with_validated_lineage,
claims_with_unknown_lineage, independence_established: false,
basis: "VALIDATED_LINEAGE_DEPENDENCE_ONLY"
```

Validated lineage can only **merge** groups; nothing ever splits a group on the
basis of publisher, language, wording or domain. The group count is therefore an
upper bound, and `independence_established` is always `false`: unknown lineage
stays unknown. Both functions run with invoker rights (RLS applies).

### Claim status
M04 only recommends. `claim_status_auto_rules` stays empty (DEV smoke checks it).
High-impact claims cannot change status except by a human decision
(`HIGH_IMPACT_REQUIRES_HUMAN` guard from Phase 2 still applies).

## 3. M05 — events

### Vocabularies
- AI proposals (8): `CREATE_NEW_EVENT`, `UPDATE_EXISTING_EVENT`, `SUGGEST_MERGE`,
  `SUGGEST_SPLIT`, `SUGGEST_SUPERSEDE`, `KEEP_SEPARATE`, `INSUFFICIENT_INFORMATION`,
  `HUMAN_REVIEW_REQUIRED`.
- Human `event_action` (7): `CREATE`, `UPDATE`, `MERGE`, `SPLIT`, `KEEP_SEPARATE`,
  `SUPERSEDE`, `REJECT`.
- `event_state`: `CANDIDATE`, `ACTIVE`, `DEVELOPING`, `CONFIRMED`, `CONTESTED`,
  `CLOSED`, `REJECTED`.
- Event type = the `claim_type` vocabulary (PO decision).
- `event_claim_role`: `SUPPORTS`, `CONTRADICTS`, `UPDATES`, `CONTEXTUALISES`.

### Deterministic application of AI output
| Proposal | Effect |
| --- | --- |
| `CREATE_NEW_EVENT` | new AI event, version 1, state `CANDIDATE` (the only state a worker may write) |
| `UPDATE_EXISTING_EVENT` | new AI-originated version of the **current head**, pending human review; existing claims carried forward with their roles (migration 2100); claims may only be added |
| all others | recorded as `event_proposals` only — no structural effect |

Ingestion (`lfhe.ingest_event_proposals`, worker only) rejects the whole output if:
a claim is not a run input (or, for an update, not already in the head) or not
cutoff-eligible; a referenced event was not supplied as context by its current
head version (`EVENT_NOT_IN_MODEL_RUN_CONTEXT_OR_STALE`); the target is not the
current head or not open; an existing claim would be recast; a date or location
does not come from the claims (`EVENT_DATE_NOT_FROM_CLAIMS`,
`EVENT_LOCATION_NOT_FROM_CLAIMS` — publication date is never event date); the
event type or a role is outside the vocabulary; a claim is placed into two
materialising proposals; or one output updates the same event twice.

### Versions
`event_versions` are immutable and hash-bound:
`content_hash = SHA-256(canonical JSON 'lfhe-event-version/1' of event id,
version_no, previous version, title, description, event type, dates, date
confidence, sorted locations, sorted (claim, role) membership)`. Deferred
constraint triggers verify, at commit, that each version has ≥ 1 claim, that the
stored hash matches, and that the version chain is valid. Membership per version
is in `event_claims` and is reconstructible for every historical version.
Reviews (`event_version_reviews`) bind to `(version_id, content_hash)`.

### Human structural actions (permission `EVENT_ACTION`)
`create_event`, `update_event` (records `removed_claim_ids`), `set_event_state`,
`reject_event`, `review_event_version`, `merge_events`, `split_event`,
`supersede_event`, `keep_events_separate`. All take the expected current head(s)
(`EVENT_HEAD_STALE` otherwise), require a reason, write `event_actions` and audit.

- **MERGE**: the target gets a new version with the union of claims (role
  priority CONTRADICTS > UPDATES > SUPPORTS > CONTEXTUALISES — a contradiction is
  never weakened); sources keep their IDs and all versions, gain a `MERGED_INTO`
  relationship and are no longer open; `resolve_event(old)` → target.
- **SPLIT**: every claim of the parent head must land in the retained version or
  a child (`SPLIT_WOULD_DROP_CLAIMS`), no foreign claims
  (`SPLIT_INTRODUCES_FOREIGN_CLAIMS`); children are new HUMAN events linked by
  `SPLIT_INTO`; `event_claim_redistributions` records where each claim went.
- **SUPERSEDE**: old event keeps its versions, gains `SUPERSEDED_BY`;
  `resolve_event(old)` follows the chain.
- **REJECT**: a state change only; versions and history stay.

`event_relationships` bind both sides to `(version_id, content_hash)`.

### Context for M05 (minimum necessary, cutoff-disciplined)
`build_m05_inputs` supplies the new claims plus at most 20 candidate open events
(not REJECTED, no successor) whose current head shares an event type, a location
or a normalised entity mention, each with only its cutoff-eligible claims
(`claims_withheld_by_cutoff` is reported); events known only through post-cutoff
evidence are not supplied. Clustering quality beyond these guards is a model
property — see the CG3 report (EVENT CLUSTERING RESULTS).

## 4. Cutoff discipline
`lfhe.claim_cutoff_eligible(claim, mode, cutoff)`:
- LIVE: retrieved ≤ cutoff AND (public availability unknown OR ≤ cutoff);
- REPLAY: public availability known AND ≤ cutoff.
Every M04/M05 run must declare `report_mode` and `information_cutoff` in
`task_parameters` (`CUTOFF_NOT_DECLARED` otherwise). Event time is never an
eligibility criterion.

## 5. Jobs
`ANALYSE_LINEAGE` and `BUILD_EVENTS` (payload `claim_ids`, `report_mode`,
`information_cutoff`) are enqueued explicitly — no automatic chaining in Phase 3
(analogue of SD-11). Recorded proposals end the job as `HUMAN_REVIEW`; a missing
model configuration fails the job permanently; a provider error retries within
`max_attempts`. Configuration: `LFHE_M04_MODEL_CONFIGURATION_ID`,
`LFHE_M05_MODEL_CONFIGURATION_ID`.

## 6. Prompts
`packages/prompts/M04_LINEAGE/1.0.0` and `packages/prompts/M05_EVENT_BUILDER/1.0.0`
(module version `MPP-1.2.2+P3-ADDENDUM-1.0`), locked in `prompt-lock.json`,
registered and activated only through the audited registrar + human
`PROMPT_ACTIVATE` path. Schemas mirror the database enums (tested). Low-variance
model settings are enforced for both modules.
