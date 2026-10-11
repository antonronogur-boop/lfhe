# Phase 2 — test traceability (Addendum v1.0 §15 and §16)

## §15 required tests

| # | Requirement | Tests (pytest node ids) |
|---|---|---|
| 1 | Exact original-language span resolution | `tests/integration/test_claims_schema.py::test_exact_original_language_span_is_persisted_and_resolvable`, `tests/unit/test_grounding_fidelity.py::test_exact_offsets_resolve`, `tests/integration/test_grounding_parity.py` |
| 2 | Wrong offset → fail | `test_claims_schema.py::test_invalid_spans_are_rejected_not_persisted` (offset +1, end out of range, negative start), `test_grounding_fidelity.py::test_wrong_offset_fails_and_is_never_relocated`, acceptance case A3 |
| 3 | Wrong exact_text → fail | `test_claims_schema.py::test_invalid_spans_are_rejected_not_persisted` (12→21), `test_grounding_fidelity.py::test_grounding_failures`, `test_claims_schema.py::test_non_nfc_exact_text_fails` |
| 4 | Translation-only grounding → fail | `test_claims_schema.py::test_translation_only_grounding_fails`, `test_grounding_fidelity.py::test_translation_only_grounding_fails`, acceptance case A2 |
| 5 | Wrong snapshot / text-representation relationship → fail | `test_claims_schema.py::test_wrong_snapshot_text_representation_relationship_fails`, `::test_claims_require_a_succeeded_m02_run_that_had_the_text_as_input`, `::test_metadata_only_snapshot_cannot_ground` |
| 6 | Unsupported extracted claim → not persisted as valid | `test_claim_pipeline.py::test_unsupported_claims_are_never_persisted`, `test_claims_schema.py::test_claim_text_original_must_lie_inside_the_span`, `::test_direct_insert_of_ungrounded_claim_is_blocked_even_for_owner`, acceptance metric `unsupported_valid_claims` |
| 7 | Attribution / uncertainty / negation loss → flagged | `test_grounding_fidelity.py::test_fidelity_losses_are_flagged`, `::test_faithful_normalisations_pass`, acceptance cases E2–E4 |
| 8 | Material translation mismatch → human review | `test_claim_pipeline.py::test_material_translation_mismatch_and_language_uncertainty_route_to_human`, `test_claims_schema.py::test_review_flags_are_closed_and_force_human_review`, acceptance case E5 |
| 9 | Source-language interpretation uncertainty → human review / insufficient information | `test_claim_pipeline.py::test_material_translation_mismatch_and_language_uncertainty_route_to_human`, `::test_uninterpretable_source_yields_insufficient_information_without_claims`, `test_claim_prompts.py::test_m02_inputs_fail_closed`, acceptance case F3 |
| 10 | Prompt injection in source text does not change system instructions | `test_claim_pipeline.py::test_prompt_injection_in_source_does_not_change_instructions`, `::test_clean_source_is_not_flagged_as_injection`, `tests/unit/test_providers.py::test_untrusted_source_text_cannot_escape_the_data_block`, `test_grounding_fidelity.py::test_instruction_like_source_detection`, acceptance case A1 |
| 11 | Claim type constrained to closed enum | `test_claims_schema.py::test_closed_enums_reject_unknown_values`, `test_claim_prompts.py::test_m02_schema_enums_match_database_vocabularies`, `::test_m02_schema_rejects_out_of_contract_claims` |
| 12 | Claim status constrained to closed enum | `test_claims_schema.py::test_closed_enums_reject_unknown_values` (enum_range), `apps/web/tests/claims.test.ts` |
| 13 | High-impact revalidation guard works | `test_claims_schema.py::test_low_to_high_impact_after_automatic_status_requires_revalidation`, `::test_revalidation_approval_makes_strengthened_status_usable`, `::test_high_impact_claim_cannot_be_changed_automatically`, `::test_human_marked_high_impact_cannot_be_removed_by_worker`, `::test_high_impact_status_change_by_human_is_usable`, `::test_automatic_status_requires_configured_rule` |
| 14 | Worker / service role cannot perform a human review decision | `test_claims_schema.py::test_non_human_roles_cannot_review_or_set_status` (worker, service_role, anon, VIEWER, ADMIN), `tests/security/test_security_definer_hardening.py` (all HUMAN_ONLY functions), acceptance metric `non_human_review_transitions`, DEV smoke P2 checks |
| 15 | Human review decision audited and version/object bound | `test_claims_schema.py::test_human_review_is_audited_and_bound_to_object_and_version` |
| 16 | Ambiguous entity → unresolved, not forced merge | `test_claims_schema.py::test_entity_resolution_is_conservative`, `::test_alias_requires_a_basis_and_relationships_are_human_and_audited`, acceptance metric `forced_ambiguous_entity_resolution` |
| 17 | M03 cannot invent taxonomy IDs | `test_claim_pipeline.py::test_m03_invented_taxonomy_id_is_never_accepted`, `test_claims_schema.py::test_invalid_assignment_rejects_the_whole_output`, acceptance case A5 |
| 18 | M03 returns target object IDs | `test_claims_schema.py::test_multi_label_assignments_with_target_ids`, `test_claim_pipeline.py::test_end_to_end_extraction_and_classification`, `::test_m03_target_must_be_a_supplied_claim` |
| 19 | Multi-label classification | `test_claims_schema.py::test_multi_label_assignments_with_target_ids`, `test_claim_pipeline.py::test_end_to_end_extraction_and_classification` |
| 20 | PIR / topic / geography use only the supplied taxonomy | `test_claims_schema.py::test_classification_requires_supplied_taxonomy_and_m03_run`, `::test_taxonomy_is_closed_and_seeded_from_v12`, `test_claim_prompts.py::test_m03_schema_taxonomy_matches_database`, `::test_m03_inputs_use_claim_ids_and_full_closed_taxonomy` |
| 21 | Schema-invalid output → SCHEMA_VALIDATION_FAILED, no silent persistence | `test_claim_pipeline.py::test_schema_invalid_output_is_recorded_and_repaired_transparently`, `::test_schema_invalid_twice_persists_nothing`, `test_claims_schema.py::test_failed_runs_are_recorded_without_claims`, acceptance case F1 |
| 22 | Retry / repair does not silently alter evidence | `test_claim_pipeline.py::test_schema_invalid_output_is_recorded_and_repaired_transparently` (identical input manifest + set hash, linked runs), `test_grounding_fidelity.py::test_wrong_offset_fails_and_is_never_relocated` |
| 23 | model_run reproducibility metadata | `test_claim_pipeline.py::test_end_to_end_extraction_and_classification` (prompt version / semver / hash, module version, model config + hash, provider, environment, input manifest, `verify_envelope` = []), `tests/integration/test_prompts_model_runs.py`, `tests/integration/test_model_settings.py` |
| 24 | Provider failure leaves no partial authoritative claim | `test_claim_pipeline.py::test_provider_failure_leaves_no_partial_claim` (ProviderError and unexpected exception), acceptance case F2 |
| 25 | Unicode code-point offsets stable through the claim path | `test_claims_schema.py::test_unicode_code_point_offsets_are_stable` (emoji + Cyrillic; DB `substr` = Python slice ≠ byte offset), `test_grounding_parity.py`, `apps/web/tests/claims.test.ts` (UI uses code points) |

## §16 acceptance metrics

Computed from the database by `tests/acceptance/test_phase2_acceptance.py::test_phase2_acceptance_metrics`
over 17 synthetic cases (normal N1–N4, edge E1–E5, failure F1–F3, adversarial A1–A5; en/uk/hu/pl +
an uninterpretable script). All seven must be 0:
`unsupported_valid_claims`, `translation_only_grounding_accepted`, `provenance_failures`,
`schema_invalid_outputs_persisted`, `non_human_review_transitions`,
`forced_ambiguous_entity_resolution`, `invented_taxonomy_ids_accepted`.
