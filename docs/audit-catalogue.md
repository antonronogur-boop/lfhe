# Audit catalogue and mechanism (Enforcement Addendum G-14)

## Mechanism
- `lfhe.audit_log` is append-only: UPDATE / DELETE / TRUNCATE are blocked by
  triggers for every role including the owner, and no application role has
  INSERT. Entries are written only by `lfhe.write_audit()`, which no role may
  call directly; it runs from SECURITY DEFINER **triggers on the audited
  tables**. An audited change therefore cannot skip or forge its entry.
- **Hash chain** (`v1`): `entry_hash = sha256(canonical_v1(entry, previous_entry_hash))`;
  genesis predecessor = 64 × `0`. Canonical form: `lfhe.audit_canonical_v1`
  (SQL) ≡ `lfhe_shared.audit.canonical_v1` (Python, independent verifier).
- **Concurrency:** a transaction-scoped advisory lock serialises the audit
  step; `seq` is assigned under the lock, gap-free and equal to chain order.
  Verified by `test_concurrent_audited_operations_produce_one_verifiable_chain`.
- **Actor classification:** HUMAN (signed-in `authenticated` session, user id
  recorded) · WORKER (login role in `lfhe_worker`, not superuser) · SYSTEM
  (owner / operator / migrations).
- **Tamper evidence, not tamper-proofing:** an owner/superuser can disable
  triggers. `verify_chain()` detects any rewrite; `export_chain_head()`
  appends verified heads to an external write-once location so later rewrites
  are provable. This is stated as a limitation, per G-14.
- Seed data inserted by migrations *before* the audit triggers existed
  (role / permission matrix) is version-controlled in the migration files
  instead of the audit log.

## Mandatory audited transitions — Phase 1

| Event | Trigger point |
| --- | --- |
| `DEPLOYMENT_ENVIRONMENT_SET` | insert into `deployment_environment` |
| `USER_ROLE_CHANGED` | insert / delete on `user_roles` (metadata.operation GRANT / REVOKE) |
| `PERMISSION_CHANGED` | any change to `role_permissions` |
| `SOURCE_CREATED` / `SOURCE_UPDATED` | `sources` insert / metadata update |
| `SOURCE_ACTIVATED` / `SOURCE_DEACTIVATED` | `sources.active` change |
| `SOURCE_COLLECTION_METHOD_APPROVED` / `_REVOKED` | `sources.collection_method_approved` change |
| `ARTICLE_CREATED` | insert into `articles` |
| `ARTICLE_SNAPSHOT_CREATED` | insert into `article_snapshots` |
| `TEXT_REPRESENTATION_CREATED` | insert into `text_representations` |
| `PROMPT_VERSION_CREATED` | insert into `prompt_versions` |
| `PROMPT_VERSION_ACTIVATED` / `PROMPT_VERSION_DEACTIVATED` | insert into `prompt_activations` |
| `MODEL_CONFIGURATION_REGISTERED` (Phase 1 impl.) | insert into `model_configurations` |

## Mandatory audited transitions — Phase 2

| Event | Trigger point |
| --- | --- |
| `CLAIM_CREATED` | insert into `claims` |
| `CLAIM_EXTRACTION_RECORDED` (P2 impl.) | insert into `claim_extraction_results` (one per M02 model run) |
| `CLAIM_EXTRACTION_GROUNDING_FAILED` / `CLAIM_EXTRACTION_REJECTED` (P2 impl.) | insert into `claim_extraction_rejections` (grounding vs other reasons) |
| `CLAIM_STATUS_CHANGED` | insert into `claim_status_history` |
| `CLAIM_HIGH_IMPACT_SET` (P2 impl.) / `CLAIM_MARKED_HIGH_IMPACT_BY_HUMAN` | insert into `claim_high_impact` |
| `HIGH_IMPACT_REVALIDATION_REQUIRED` / `_APPROVED` / `_REJECTED` | `claim_revalidations` / `claim_revalidation_decisions` |
| `CLAIM_REVIEW_RECORDED` (P2 impl.), `HIGH_IMPACT_CLAIM_REVIEWED`, `CLAIM_MODIFIED`, `REVIEW_ESCALATED`, `REPROCESSING_REQUESTED` | insert into `claim_reviews` (by decision; metadata carries review id, claim hash, previous review) |
| `CLAIM_STATUS_AUTO_RULE_CONFIGURED` (P2 impl.) | insert into `claim_status_auto_rules` |
| `ENTITY_CREATED`, `ENTITY_ALIAS_CREATED`, `ENTITY_MENTION_LINKED`, `ENTITY_RELATIONSHIP_CREATED` (P2 impl.) | entity tables |
| `TAXONOMY_ITEM_CREATED`, `TAXONOMY_ASSIGNMENT_CREATED`, `CLAIM_CLASSIFICATION_RECORDED` (P2 impl.) | taxonomy tables (the v1.2 seed is inserted before the trigger exists) |


## Mandatory audited transitions — Phase 3

| Event | Trigger point |
| --- | --- |
| `LINEAGE_INGESTION_RECORDED` | insert into `lineage_ingestion_results` (one per M04 model run) |
| `LINEAGE_RECOMMENDATION_CREATED` | insert into `lineage_proposals` / `corroboration_recommendations` |
| `LINEAGE_PROPOSAL_DECIDED` | insert into `lineage_proposal_decisions` |
| `LINEAGE_VALIDATED` + `INDEPENDENCE_GROUP_CHANGED` | insert into `claim_lineage` |
| `CLAIM_LINEAGE_RETRACTED` + `INDEPENDENCE_GROUP_CHANGED` | insert into `claim_lineage_retractions` |
| `EXTERNAL_ORIGIN_CREATED` | insert into `external_origins` |
| `CORROBORATION_RECOMMENDATION_DECIDED` | insert into `corroboration_recommendation_decisions` (the status change itself is `CLAIM_STATUS_CHANGED`, HUMAN) |
| `EVENT_CREATED` | insert into `events` |
| `EVENT_VERSION_CREATED` (version 1) / `EVENT_UPDATED` (later versions) | insert into `event_versions` |
| `EVENT_STATE_CHANGED`; `EVENT_MANUALLY_PROMOTED` when a human moves an event out of `CANDIDATE` | `event_state_history` / `set_event_state` |
| `EVENT_RELATIONSHIP_CREATED` | insert into `event_relationships` |
| `EVENT_PROPOSAL_RECORDED` | insert into `event_proposals` |
| `EVENT_INGESTION_RECORDED` | insert into `event_ingestion_results` (one per M05 model run) |
| `EVENT_VERSION_REVIEWED` | insert into `event_version_reviews` |
| `EVENT_MERGED`, `EVENT_SPLIT`, `EVENT_SUPERSEDED`, `EVENT_KEEP_SEPARATE_DECISION`, `EVENT_REJECTED`, `EVENT_ACTION_RECORDED` (CREATE / UPDATE) | insert into `event_actions` (by action) |


## Mandatory audited transitions — Phase 4

| Event | Trigger point |
| --- | --- |
| `REFERENCE_CONTEXT_CREATED` / `REFERENCE_CONTEXT_VERSION_CREATED` | insert into `reference_contexts` / `reference_context_versions` |
| `REFERENCE_CONTEXT_APPROVED` / `REFERENCE_CONTEXT_REJECTED` | insert into `reference_context_decisions` |
| `BASELINE_CREATED` / `BASELINE_VERSION_CREATED` | insert into `baselines` / `baseline_versions` |
| `BASELINE_VERSION_APPROVED` / `BASELINE_VERSION_REJECTED` | insert into `baseline_version_decisions` |
| `RELEVANCE_INGESTION_RECORDED` / `RELEVANCE_RESULT_RECORDED` | insert into `relevance_ingestion_results` (one per M06 run) / `relevance_results` |
| `EXECUTIVE_RELEVANCE_VALIDATED`, `RELEVANCE_SCORE_OVERRIDDEN`, `EVENT_MANUALLY_PROMOTED`, `MANUAL_ASSESSMENT_REQUESTED` | insert into `relevance_decisions` (by action) |
| `ASSESSMENT_INGESTION_RECORDED` | insert into `assessment_ingestion_results` (one per M07 run) |
| `ASSESSMENT_VERSION_CREATED` (AI) / `ASSESSMENT_MODIFIED` (HUMAN, MODIFY_AND_APPROVE) | insert into `assessment_versions` |
| `ASSESSMENT_STATE_CHANGED`; `ASSESSMENT_SUPERSEDED` when the new state is SUPERSEDED | insert into `assessment_state_history` |
| `CHALLENGE_INGESTION_RECORDED` / `CHALLENGE_RECORDED` | insert into `challenge_ingestion_results` (one per M08 run) / `challenge_runs` |
| `CHALLENGER_FLAG_DISPOSITIONED` | insert into `challenge_flag_dispositions` |
| `ASSESSMENT_APPROVED` (APPROVE and MODIFY_AND_APPROVE), `ASSESSMENT_REJECTED`, `REVIEW_ESCALATED`, `REPROCESSING_REQUESTED`; plus `FINAL_CONFIDENCE_SET` when an approval carries final analytic confidence | insert into `analytical_approvals` |
| `TREND_CREATED` / `TREND_VERSION_CREATED` | insert into `trends` / `trend_versions` |
| `INDICATOR_CREATED` / `INDICATOR_VERSION_CREATED` | insert into `indicators` / `indicator_versions` |

`ASSESSMENT_REVIEW_RECORDED` is registered by migration 3100 but not emitted (the decision-specific
codes above are used); it is kept, because audit codes are append-only.


## Mandatory audited transitions — Phase 5

| Event | Trigger point |
| --- | --- |
| `REPORT_CREATED` | insert into `reports` |
| `REPORT_CANDIDATE_ADDED` | insert into `report_candidate_pool` |
| `REPORT_CANDIDATE_SELECTED` / `REPORT_CANDIDATE_REMOVED` / `REPORT_CANDIDATE_RETURNED_FOR_REVISION` | insert into `report_selection_decisions` (INCLUDE / EXCLUDE / RETURN_FOR_ANALYTICAL_REVISION) |
| `REPORT_SELECTION_FROZEN` | insert into `report_selection_sets` |
| `REPORT_EDIT_INGESTION_RECORDED` | insert into `report_edit_ingestion_results` (one per M09 run) |
| `REPORT_VERSION_CREATED` | insert into `report_versions` (MODEL and HUMAN) |
| `REPORT_TEXT_EDITED` / `REPORT_CONTENT_REORDERED` | `edit_report_version` (content change / pure reorder), with previous version, hashes, reason and removed source statements |
| `REPORT_REMOVAL_PROPOSED` | insert into `report_removal_proposals` |
| `REPORT_REMOVAL_DECIDED` | insert into `report_removal_decisions` |
| `REPORT_PREVIEW_RENDERED` | insert into `report_renders` |

`REPORT_VERSION_HASH_CHANGED`, `QA_INVALIDATED_BY_REPORT_CHANGE` and the release codes in the
catalogue belong to Phase 6.

Text and prompt contents are not copied into the audit log: the audit entry
records their SHA-256 (the rows themselves are immutable and hash-checked).

Later phases attach triggers for the remaining catalogue entries (Prompt Pack
v1.2 §55, v1.2.1 §10) as their tables are introduced. Collection runs, jobs,
system errors and model runs are themselves operational records and are not
duplicated into the audit log.

## Operations
```bash
python scripts/audit_tool.py verify  <owner-url>
python scripts/audit_tool.py export  <owner-url> <heads.jsonl>
```
