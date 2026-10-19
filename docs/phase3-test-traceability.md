# Phase 3 — test traceability (Addendum v1.0 §15 and §16)

Files: `tests/integration/test_lineage.py` (L), `tests/integration/test_events.py` (E),
`tests/integration/test_phase3_pipeline.py` (P), `tests/integration/test_asof_context.py` (R),
`tests/acceptance/test_phase3_acceptance.py` (A, corpus `tests/fixtures/phase3_acceptance/corpus.json`),
`tests/security/test_gs_isolation.py` (G).

## §15 required tests

| # | Requirement | Tests |
|---|---|---|
| 1 | Same underlying source in two outlets ≠ two independent confirmations | L `test_same_underlying_source_in_two_outlets_is_one_independence_group`; A scenario L1 (4 outlets → 1 group) |
| 2 | Different language / publisher / wording ≠ independence | L `test_surface_differences_never_establish_independence`; A scenario L4; P `test_m04_output_cannot_assert_independence` |
| 3 | Explicit common origin → one independence group | L `test_same_underlying_source_in_two_outlets_is_one_independence_group`, `test_same_name_with_explicit_human_selection_is_one_group`; A scenario L3 (common identity by explicit human selection) |
| 4 | DERIVED_REPORTING does not increase independent confirmations | L `test_derived_reporting_does_not_increase_independent_groups`; A scenario L1 |
| 5 | Unknown lineage remains uncertain | L `test_surface_differences_never_establish_independence`, `test_retraction_preserves_history_and_restores_unknown`; A scenarios L2, L4 |
| 6 | M04 recommendation alone does not change claim status | L `test_m04_recommendation_does_not_change_status_until_a_human_decides`; P `test_lineage_pipeline_end_to_end_with_complete_traceability`; A metric `silent_status_finalisation` |
| 7 | Human claim-status change is audited and object-bound | L `test_m04_recommendation_does_not_change_status_until_a_human_decides` (STATUS_STALE, history row with recommending run, `CLAIM_STATUS_CHANGED` HUMAN audit) |
| 8 | High-impact status change requires human confirmation | L `test_high_impact_recommendation_requires_human_confirmation`; A scenario L5, metric `high_impact_changes_without_human` |
| 9 | Worker / service cannot finalise lineage / status | L `test_non_humans_cannot_finalise_lineage_or_status` (worker, service_role, anon, VIEWER, ADMIN); A (worker decision attempt per recommendation); `tests/security/test_security_definer_hardening.py`; DEV smoke P3 checks |
| 10 | CREATE_NEW_EVENT creates only CANDIDATE | E `test_create_new_event_materialises_only_a_candidate`; P `test_event_pipeline_creates_candidate_then_updates_with_context`; A scenario E1 |
| 11 | UPDATE_EXISTING_EVENT creates a new immutable version | E `test_update_creates_a_new_immutable_version_and_keeps_the_old_one`, `test_ai_update_cannot_drop_claims_existing_ones_are_carried_forward`; P `test_event_pipeline_creates_candidate_then_updates_with_context` |
| 12 | Old event_version remains unchanged | E `test_update_creates_a_new_immutable_version_and_keeps_the_old_one`, `test_event_versions_are_immutable_and_hash_verified`; A `ancestry_breaks` |
| 13 | Country / system / week alone does not force merge | E `test_suggestions_never_perform_structural_actions`; A scenarios E1, E2 (over-eager update held for review, corrected by a human, `removed_claim_ids` recorded) |
| 14 | Older event + new reporting → update, not a false new event | E `test_update_creates_a_new_immutable_version_and_keeps_the_old_one`; P `test_event_pipeline_creates_candidate_then_updates_with_context`; A scenario E3 (`old_event_new_reporting_updated`) |
| 15 | Publication date ≠ event date | E `test_publication_date_is_not_event_date`, `test_invalid_ai_updates_reject_the_whole_output` (EVENT_DATE_NOT_FROM_CLAIMS) |
| 16 | Contradiction is preserved | E `test_contradiction_is_preserved_through_versions_and_merge`; A structural chain (CONTRADICTS kept through merge and supersede) |
| 17 | SUGGEST_MERGE does not perform MERGE | E `test_suggestions_never_perform_structural_actions`; A scenario E4 |
| 18 | SUGGEST_SPLIT does not perform SPLIT | E `test_suggestions_never_perform_structural_actions`; A scenario E4 |
| 19 | SUGGEST_SUPERSEDE does not perform SUPERSEDE | E `test_suggestions_never_perform_structural_actions`; A scenario E4 |
| 20 | MERGE requires human authority and preserves old IDs | E `test_merge_is_human_only_and_preserves_ids_versions_and_claims`; A structural chain |
| 21 | SPLIT requires human authority and preserves parent/child lineage | E `test_split_is_human_only_preserves_parent_and_redistributes_every_claim`; A structural chain |
| 22 | SUPERSEDE requires human authority and preserves old reference resolution | E `test_supersede_is_human_only_and_old_references_resolve`; A structural chain |
| 23 | REJECT does not delete history | E `test_reject_keeps_history` |
| 24 | Event versions are immutable | E `test_event_versions_are_immutable_and_hash_verified` |
| 25 | Material changes change the canonical event hash | E `test_material_change_changes_the_canonical_hash` |
| 26 | Event claim membership reconstructible per version | E `test_update_creates_a_new_immutable_version_and_keeps_the_old_one`, `test_split_is_human_only_preserves_parent_and_redistributes_every_claim` |
| 27 | Schema failure leaves no partial authoritative state | E `test_failed_or_rejected_m05_runs_leave_no_authoritative_state`; L `test_invalid_lineage_rejects_the_whole_output`, `test_failed_m04_runs_record_no_proposals`; P `test_schema_and_provider_failures_leave_no_authoritative_state`, `test_m04_output_cannot_assert_independence` |
| 28 | Provider failure leaves no partial authoritative state | P `test_schema_and_provider_failures_leave_no_authoritative_state`; E `test_failed_or_rejected_m05_runs_leave_no_authoritative_state` |
| 29 | Model-run traceability is complete | P `test_lineage_pipeline_end_to_end_with_complete_traceability` (`verify_envelope` = []), `test_bundles_are_locked_and_schemas_match_database`, `test_inputs_respect_cutoff_and_are_deterministic`; A metric `model_runs_incomplete_provenance` |
| 30 | Phase 1 + Phase 2 regression suites remain green | full `pytest` run (all Phase 1/2 tests unchanged except where noted in the CG3 report) + `apps/web` tests + CI |
| 31 | GS answer-key isolation remains intact | G (4 tests: no GS/answer-key markers in prompts, services, fixtures; no gold-standard tree; input builders read only the DB); A metric `gs_leakage` over every envelope and rendered message |

Additional: cutoff / input discipline — L `test_claims_outside_the_input_or_after_the_cutoff_are_rejected`,
E `test_claims_outside_input_or_cutoff_are_rejected`, `test_stale_or_unsupplied_targets_are_rejected`,
P `test_inputs_respect_cutoff_and_are_deterministic`, `test_m05_context_withholds_rejected_events`;
prompt injection — P `test_injection_in_claim_text_does_not_change_instructions`;
jobs — P `test_worker_jobs_analyse_lineage_and_build_events_end_in_human_review`;
review binding — E `test_human_review_of_ai_version_is_hash_bound`.

## CG3 corrective pass (PO decision 2026-10-19, CG3-01…03)

| Required test | Tests |
|---|---|
| CG3-01.1–3 v1 from pre-cutoff evidence; v2 adds a post-cutoff claim and new title/description/location; REPLAY between them sees only v1 | R `test_replay_sees_only_the_cutoff_eligible_version_never_later_fields`; A scenario R1 |
| CG3-01.4 later CONFIRMED / REJECTED does not leak backwards | R `test_later_state_does_not_leak_backwards_but_later_processing_on_eligible_evidence_counts`; A R1 |
| CG3-01.5 later MERGE / SUPERSEDE does not alter the earlier replay | R `test_later_merge_and_supersede_do_not_alter_the_replay` |
| CG3-01.6 lineage established with later evidence stays out of the earlier replay (context and independence groups) | R `test_lineage_from_later_evidence_is_not_used_in_an_earlier_replay`, `test_human_recorded_lineage_needs_a_declared_evidence_bound_for_replay`; A R1 |
| CG3-01.7 processing after the cutoff on eligible evidence remains allowed | R (positive controls in the state, merge and lineage tests) |
| CG3-01 ingestion: only the as-of version is accepted; no update on a later head | R `test_replay_ingestion_accepts_only_the_asof_version_and_never_materialises_on_a_later_head` |
| CG3-02 full split parent not an M05 candidate; update / state change / re-split refused; history and SPLIT_INTO intact; no claim lost; no old membership as current | E `test_full_split_parent_is_no_longer_open_or_current` |
| CG3-02 retained split parent current only with the retained claims | E `test_split_with_retained_parent_stays_current_only_with_the_retained_claims` |
| Final correction A: lineage on eligible evidence, retraction on post-cutoff evidence → lineage still usable in the earlier REPLAY | R `test_retraction_on_post_cutoff_evidence_does_not_alter_the_earlier_replay`; A R1 (`retraction_hindsight_leakage`) |
| Final correction B: once that evidence is eligible (later cutoff) → retraction applies | R `test_retraction_on_post_cutoff_evidence_does_not_alter_the_earlier_replay` |
| Final correction C: retraction recorded after the cutoff on eligible evidence → applies to that REPLAY | R `test_retraction_recorded_after_the_cutoff_on_eligible_evidence_applies` |
| Final correction D: retraction without evidence basis → does not alter REPLAY | R `test_retraction_without_evidence_basis_does_not_rewrite_replay` |
| Final correction E: independence groups follow the same as-of behaviour (no false historical independence) | R (group assertions in the three tests above); A R1 |
| CG3-03.1 same name + explicit human selection → one group | L `test_same_name_with_explicit_human_selection_is_one_group` |
| CG3-03.2 same name + different URLs → distinct (same URL + name → reused) | L `test_same_name_different_urls_remain_distinct_same_url_is_reused`; A scenario L6 |
| CG3-03.3 same name, no URL, no explicit reuse → no collapse | L `test_same_name_without_explicit_reuse_does_not_collapse` |
| CG3-03.4 ambiguous identity → no false dependence (URL vs no URL; unevidenced / conflicting explicit selection refused) | L `test_ambiguous_identity_never_creates_false_dependence`; A metric `false_dependence_collapse` |
| CG3-03.5 L3 common origin through explicit human validation | L `test_same_name_with_explicit_human_selection_is_one_group`; A scenario L3 |

## §16 acceptance metrics

`tests/acceptance/test_phase3_acceptance.py::test_phase3_acceptance_corpus` (set
`LFHE_P3_METRICS_OUT=<file>` to write the metrics). All of these must be 0:
`republication_inflation`, `surface_difference_independence`,
`independence_established_true`, `silent_status_finalisation`,
`high_impact_changes_without_human`, `ai_structural_actions`,
`unvalidated_ai_grouping_promoted`, `over_merge_in_validated_events`,
`claims_lost_in_structural_ops`, `ancestry_breaks`, `gs_leakage`,
`model_runs_incomplete_provenance`, and since the CG3 corrective pass
`false_dependence_collapse` (L6) and `replay_context_leakage` (R1), and since the final
CG3 correction `retraction_hindsight_leakage` (R1).
