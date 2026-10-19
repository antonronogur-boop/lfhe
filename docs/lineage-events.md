# Phase 3 — Lineage (M04) and Events (M05)

Authority: `docs/specs/LFHE_Phase3_Authoritative_Baseline_Addendum_v1.0.md`
(PO decision `docs/specs/PO_Decision_2026-10-19_Authorise_Phase3.md`).
Migrations: `20261011001800_lineage.sql`, `20261011001900_events.sql`,
`20261011002000_phase3_jobs.sql`, `20261011002100_event_ai_update_carry_forward.sql`,
`20261011002200_external_origin_reuse.sql`; CG3 corrective pass (PO decision
`docs/specs/PO_Decision_2026-10-19_CG3_Targeted_Corrective_Pass.md`):
`20261011002300_cg3_01_asof_context.sql`, `20261011002400_cg3_02_full_split_terminal.sql`,
`20261011002500_cg3_03_external_origin_identity.sql`; final CG3 correction
(`docs/specs/PO_Decision_2026-10-19_CG3_Final_Correction.md`):
`20261011002600_cg3_knowledge_bound_retractions.sql`.

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
   `decide_lineage_proposal(id, accept, reason [, external_origin_id])`,
   `record_claim_lineage` (optional `evidence_basis`, see §4),
   `retract_claim_lineage(id, reason [, evidence_basis])` (see §4),
   `decide_corroboration_recommendation` (STATUS_STALE-checked; writes a
   `HUMAN_DECISION` status-history row that names the recommending model run).

`claim_lineage` is append-only; corrections are retractions plus new rows.

### External origins (identity never inferred from the name — CG3-03)
`external_origins` rows exist only when a validated lineage row needs one, and
only when explicitly evidenced. Identity of two origins is established only by:
- **explicit human selection** of an existing origin
  (`decide_lineage_proposal(..., p_external_origin_id)` or
  `record_claim_lineage({external_origin_id})`); the selected origin's name must
  be evidenced in the child claim's span, and a proposal URL must not contradict
  the origin's URL (`EXTERNAL_ORIGIN_IDENTITY_CONFLICT`); or
- **unambiguous identity evidence**: the same canonical URL and the same
  normalised name, with exactly one existing origin.

A matching name alone (no URL, different URLs, several candidates) creates a new
origin: the distinction is preserved and no dependence is inferred (migration
2500 replaces the name-only reuse of migration 2200).

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
  - *with retained*: the parent gets the retained version and stays open,
    current only with the retained claim set;
  - *full split* (no retained, CG3-02): the parent keeps its ID, versions and
    `SPLIT_INTO` lineage but is terminal — `event_is_open` false, no M05
    candidate, `update_event` / `set_event_state` / further structural actions
    refused (`EVENT_NOT_OPEN`); `event_heads` shows `structural_status =
    SPLIT_INTO`, `is_current = false`, `current_version_id = NULL`.
    `resolve_event(parent)` stays relationship-based (one-to-many).
- **SUPERSEDE**: old event keeps its versions, gains `SUPERSEDED_BY`;
  `resolve_event(old)` follows the chain.
- **REJECT**: a state change only; versions and history stay.

`event_relationships` bind both sides to `(version_id, content_hash)`.

### Context for M05 (minimum necessary, as-of the cutoff)
`build_m05_inputs` supplies the new claims plus at most 20 candidate events that
are **open as of the cutoff** and whose **as-of version** shares an event type, a
location or a normalised entity mention (`lfhe.event_asof`, §4). Title,
description, dates, locations, membership, state and structural outcome all come
from that as-of representation; events with no provable as-of version are not
supplied. Clustering quality beyond these guards is a model property — see the
CG3 report (EVENT CLUSTERING RESULTS).

M05 ingestion requires each referenced event to have been supplied by exactly its
as-of version for that run, and materialises an `UPDATE_EXISTING_EVENT` only if
the version shown to the model is the current head
(`UPDATE_TARGET_VERSION_NOT_SUPPLIED` / `TARGET_VERSION_NOT_CURRENT_HEAD`): a
replay never writes onto a head that contains later knowledge.

## 4. Cutoff discipline
`lfhe.claim_cutoff_eligible(claim, mode, cutoff)`:
- LIVE: retrieved ≤ cutoff AND (public availability unknown OR ≤ cutoff);
- REPLAY: public availability known AND ≤ cutoff.
Every M04/M05 run must declare `report_mode` and `information_cutoff` in
`task_parameters` (`CUTOFF_NOT_DECLARED` otherwise). Event time is never an
eligibility criterion.

### Knowledge bounds of authoritative objects (CG3-01, migration 2300)
Claims and articles are eligible by the rule above. Derived authoritative objects
are usable for a run only if their **knowledge bound** — the evidence they were
established on, reproducibly computed from immutable stored data — is entirely
eligible. Processing or human decisions after the cutoff are fine when the
evidence itself is eligible; `created_at ≤ cutoff` is never the rule on its own.

| Object | Knowledge bound | Function |
| --- | --- | --- |
| validated lineage | child claim, parent claim / article, origin evidence claim; + `PROPOSAL_ACCEPTED`: every input/context object of the proposing M04 run (context lineage recursively); + `HUMAN_RECORDED`: the declared `evidence_basis` (`claim_lineage_evidence`). No declared basis → no provable bound: never in REPLAY, LIVE only if recorded ≤ cutoff | `lfhe.lineage_usable` |
| lineage retraction | the declared `evidence_basis` of the retraction (`claim_lineage_retraction_evidence`). A retraction affects a run only when that basis is entirely eligible for the run's cutoff — whenever it was recorded. Without a basis it never alters REPLAY (LIVE: applies when recorded ≤ cutoff) | `lfhe.lineage_retraction_usable` (inside `lfhe.lineage_usable`) |
| independence group | connected components over usable lineage only | `lfhe.claim_independence_group_asof`, `lfhe.independence_summary_asof` |
| event version | member claims, every previous version, the AI run's inputs/context (incl. event versions shown), consumed versions (MERGED_INTO sources, SPLIT_INTO parent) | `lfhe.event_version_eligible` |
| event state | the head version current when the state row was written (`event_state_version_bindings`, trigger); unbound rows fail closed | in `lfhe.event_asof` |
| merge / supersede / split outcome | both versions of the relationship | in `lfhe.event_asof` |

`lfhe.event_asof(event, mode, cutoff)` returns the latest eligible version, the
latest usable state, the usable structural outcome and `is_open`; nothing when no
version is provable. Lineage retractions are themselves knowledge-bound: a
retraction affects a historical run only when its supporting evidence is eligible
for that run's cutoff (replaces the earlier unconditional rule). The current-state
view `active_claim_lineage` still excludes every retracted row for present-day
human work. The bound of a human event
version is its evidence set (member claims and consumed versions); its free text
is the analyst's summary of that evidence (SD3-12).

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
