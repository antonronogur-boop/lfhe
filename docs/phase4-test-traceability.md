# Phase 4 — test traceability (Addendum v1.0 §23 and §24)

Files: `tests/integration/test_p4_relevance.py` (R), `tests/integration/test_p4_baselines.py` (B),
`tests/integration/test_p4_assessments.py` (AS), `tests/integration/test_p4_challenge_review.py` (CR),
`tests/integration/test_p4_trends_indicators.py` (TI), `tests/integration/test_p4_pipeline.py` (P),
`tests/security/test_p4_rbac.py` (RB), `tests/security/test_gs_isolation.py` (G),
`tests/security/test_security_definer_hardening.py` (SD),
`tests/acceptance/test_phase4_acceptance.py` (A, corpus `tests/fixtures/phase4_acceptance/corpus.json`).

## §23 required tests

| # | Requirement | Tests |
|---|---|---|
| 1 | relevance score is 0–5 only | R `test_scores_are_0_to_5_and_m06_cannot_publish` (schema + repair; DB CHECK) |
| 2 | M06 cannot publish/select a report item | R `test_scores_are_0_to_5_and_m06_cannot_publish` |
| 3 | low-scored event remains visible | R `test_low_score_stays_visible_and_manually_assessable`; A R02, metric `below_threshold_hidden` |
| 4 | low-scored event remains manually assessable | R `test_low_score_stays_visible_and_manually_assessable`; A R02 (REQUEST_ASSESSMENT) |
| 5 | manual promotion/request is HUMAN_ONLY and audited | R `test_low_score_stays_visible_and_manually_assessable`, `test_validate_and_override_are_human_only_and_audited`; RB; A `manual_promotion_failures` |
| 6 | PIR-07 recommended event has explicit non-generic HU/NATO rationale | R `test_recommended_event_needs_concrete_hu_nato_rationale` (6 cases); A R01, R03, metric `recommended_without_concrete_or_not_established_rationale` |
| 7 | unsupported HU/NATO relevance can remain "not established" | R `test_not_established_is_a_valid_result`; A R02, R05 |
| 8 | invalid PIR/taxonomy ID fails closed | R `test_invalid_pir_fails_closed` (schema + DB `PIR_ID_UNKNOWN`); A R04 |
| 9 | M06 cannot change event/claim status | R `test_m06_changes_no_event_or_claim_state` |
| 10 | baseline version is immutable/hash-bound | B `test_baseline_and_reference_context_versions_are_immutable_and_hash_bound` |
| 11 | reference-context version is immutable/hash-bound | B `test_baseline_and_reference_context_versions_are_immutable_and_hash_bound` |
| 12 | knowledge_as_of > cutoff is excluded | B `test_baseline_usability_follows_knowledge_and_evidence_not_decision_time`, `test_reference_context_usability_and_replay_never_receives_a_later_version` |
| 13 | baseline decided after cutoff still usable if its evidence was eligible | B `test_baseline_usability_follows_knowledge_and_evidence_not_decision_time` |
| 14 | post-cutoff factual component prevents historical use | B `test_baseline_usability_follows_knowledge_and_evidence_not_decision_time`, `test_baseline_component_on_an_unusable_reference_context_is_unusable`, `test_unattributed_or_anachronistic_content_is_refused` |
| 15 | REPLAY never receives a later baseline version | B (as-of selection); R `test_inputs_require_exact_eligible_version_and_supply_only_asof_baseline`; A REPLAY block, metric `hindsight_leakage` |
| 16 | REPLAY never receives a later reference-context version | B `test_reference_context_usability_and_replay_never_receives_a_later_version`; AS `test_baseline_and_reference_context_rules`; A REPLAY block |
| 17 | reference context without provenance is unusable | B `test_unattributed_or_anachronistic_content_is_refused` |
| 18 | assessment tied to exact event_version + hash | AS `test_assessment_is_bound_to_exact_event_version_and_is_immutable` |
| 19 | factual statement without evidence mapping is rejected | AS `test_statement_provenance_rules`; A A03, metric `unsupported_factual_statements_persisted` |
| 20 | claim evidence must belong to supplied eligible context | AS `test_statement_provenance_rules`; A A04 |
| 21 | assumption is not persisted as fact | AS `test_statement_provenance_rules`; A A02, metric `category_violations` |
| 22 | analytic judgment exposes supporting premises | AS `test_statement_provenance_rules`; A A12 |
| 23 | contradiction is preserved | AS `test_contradiction_must_stay_visible`; A A07, metric `unlabelled_contradiction_removal` |
| 24 | one lineage repeated by several outlets does not inflate confidence | AS `test_single_lineage_cannot_carry_high_confidence`; A A08, metric `republication_inflation` |
| 25 | source opinion not converted into independent confirmation | AS `test_source_opinion_keeps_attribution_even_when_corroborated`; A A09 |
| 26 | unsupported causal statement is rejected/flagged | AS `test_unsupported_causality_and_negative_evidence_are_rejected_as_fact`; CR (UNSUPPORTED_STATEMENT flag); A A05, metric `unsupported_causal_accepted_as_fact` |
| 27 | negative evidence is not invented from silence | AS `test_unsupported_causality_and_negative_evidence_are_rejected_as_fact`; A A06 |
| 28 | likelihood only on prospective uncertain outcome | AS `test_likelihood_only_on_prospective_statements_and_distinct_from_confidence` (canonical vocabulary, CR4-01) |
| 29 | likelihood and analytic confidence are distinct | AS `test_likelihood_only_on_prospective_statements_and_distinct_from_confidence` |
| 30 | M07 sets ai_recommended_confidence, cannot set final_analytic_confidence | AS `test_m07_cannot_set_final_confidence_and_rationale_is_mandatory`; P `test_phase4_bundles_are_locked_and_schemas_match_database`; A A10, metric `m07_final_confidence_set` |
| 31 | confidence rationale is mandatory | AS `test_m07_cannot_set_final_confidence_and_rationale_is_mandatory` |
| 32 | attribution_required is deterministic | AS `test_attribution_is_deterministic_from_asof_workflow_state` |
| 33 | insufficiently corroborated factual statement retains attribution | AS `test_attribution_is_deterministic_from_asof_workflow_state` |
| 34 | all-corroborated claims may omit attribution only under the deterministic rule | AS `test_attribution_is_deterministic_from_asof_workflow_state` |
| 35 | high-impact restrictions continue to apply | AS `test_high_impact_restrictions_still_apply_to_attribution` |
| 36 | summary/convenience text resolves only to statement IDs | AS `test_summary_is_derived_from_statement_ids_only` |
| 37 | M08 cannot mutate M07 assessment | CR `test_m08_flags_are_bound_to_exact_version_and_never_mutate_m07`, `test_m08_output_that_modifies_or_finalises_is_rejected_and_binding_is_exact`; A metric `m08_modified_m07` |
| 38 | M08 cannot set final_analytic_confidence | CR `test_m08_output_that_modifies_or_finalises_is_rejected_and_binding_is_exact` (schema + DB) |
| 39 | M08 flag bound to exact assessment_version + hash | CR `test_m08_flags_are_bound_to_exact_version_and_never_mutate_m07`, `test_m08_output_that_modifies_or_finalises_is_rejected_and_binding_is_exact` |
| 40 | flag has affected object/field, severity, rationale and action | CR `test_m08_flags_are_bound_to_exact_version_and_never_mutate_m07` (+ FLAG_TARGET_REQUIRED / _UNKNOWN) |
| 41 | unsupported / confidence-inflated assessment is flagged | CR `test_inflation_omitted_contradiction_and_context_contamination_are_flaggable`; A A13 |
| 42 | omitted contradiction is flagged | CR `test_inflation_omitted_contradiction_and_context_contamination_are_flaggable` |
| 43 | baseline/reference-context contamination is flaggable | CR `test_inflation_omitted_contradiction_and_context_contamination_are_flaggable` |
| 44 | strongest alternative/counterargument preserved | CR `test_inflation_omitted_contradiction_and_context_contamination_are_flaggable`, `test_m08_output_that_modifies_or_finalises_is_rejected_and_binding_is_exact` (STRONGEST_COUNTERARGUMENT_REQUIRED) |
| 45 | human disposition separate from model output | CR `test_disposition_is_human_only_and_separate_from_model_output` |
| 46 | worker/service cannot dispose of challenge flags | CR `test_disposition_is_human_only_and_separate_from_model_output`; RB |
| 47 | APPROVE is version/hash-bound | CR `test_approve_is_version_hash_bound_and_final_confidence_is_human_only` |
| 48 | MODIFY_AND_APPROVE creates a new immutable version | CR `test_modify_and_approve_creates_new_version_and_old_one_is_unchanged`; A A02 |
| 49 | old version remains unchanged | CR `test_modify_and_approve_creates_new_version_and_old_one_is_unchanged`; A metric `assessment_version_mutations` |
| 50 | final analytic confidence is human-only | CR `test_approve_is_version_hash_bound_and_final_confidence_is_human_only`; RB; A metric `non_human_final_approvals` |
| 51 | final confidence requires rationale | CR `test_approve_is_version_hash_bound_and_final_confidence_is_human_only`, `test_modify_and_approve_creates_new_version_and_old_one_is_unchanged` |
| 52 | later approved version supersedes old approved version without deleting it | CR `test_later_approved_version_supersedes_without_deleting_and_previous_is_asof` |
| 53 | stale review/version/hash is rejected | CR `test_approve_is_version_hash_bound_and_final_confidence_is_human_only` (VERSION_HASH_MISMATCH, ASSESSMENT_NOT_CHALLENGED, ASSESSMENT_NOT_IN_REVIEW), `test_modify_and_approve_creates_new_version_and_old_one_is_unchanged` (REVIEW_STALE); A metric `hash_mismatch_accepted` |
| 54 | trend and event are separate objects | TI `test_trend_is_separate_versioned_and_preserves_exact_event_versions` |
| 55 | trend version is immutable | TI `test_trend_is_separate_versioned_and_preserves_exact_event_versions` |
| 56 | trend preserves exact event-version membership | TI `test_trend_is_separate_versioned_and_preserves_exact_event_versions`, `test_trend_knowledge_bound_and_cutoff` |
| 57 | one event cannot silently establish a multi-event trend | TI `test_trend_is_separate_versioned_and_preserves_exact_event_versions` (TREND_REQUIRES_MULTIPLE_EVENTS, same event twice) |
| 58 | indicator bound to supporting assessment/claim evidence | TI `test_indicator_is_bound_to_approved_assessment_and_claim_evidence` |
| 59 | vague/non-observable indicator cannot become authoritative without human correction | TI `test_vague_indicator_needs_human_correction_and_operational_is_rejected`; AS `test_operational_recommendations_and_unobservable_indicators_are_rejected` |
| 60 | invalid M06/M07/M08 schema fails closed | P `test_invalid_schema_and_provider_failure_leave_no_authoritative_state[M06/M07/M08]` |
| 61 | provider failure leaves no partial authoritative state | P `test_invalid_schema_and_provider_failure_leave_no_authoritative_state[M06/M07/M08]` |
| 62 | repair is separate model_run | P `test_repair_is_a_separate_model_run_and_provenance_is_complete[M06/M07/M08]` |
| 63 | model-run provenance is complete | P `test_repair_is_a_separate_model_run_and_provenance_is_complete`, `test_phase4_bundles_are_locked_and_schemas_match_database`; A metric `traceability_gaps` |
| 64 | prompt injection does not alter system instruction | P `test_prompt_injection_does_not_alter_instructions_and_no_gs_leakage` (M06, M07, M08) |
| 65 | GS answer-key leakage = 0 | P `test_prompt_injection_does_not_alter_instructions_and_no_gs_leakage`; G (incl. `assessment_inputs.py`, Phase 4 corpus); A metric `gs_leakage` |
| 66 | Phase 1 regressions PASS | full `pytest` run |
| 67 | Phase 2 regressions PASS | full `pytest` run |
| 68 | Phase 3 regressions PASS | full `pytest` run |
| 69 | web/security tests PASS | `apps/web` vitest 21/21; `tests/security/*`; `scripts/secret_scan.py`; gitleaks |
| 70 | all human-only Phase 4 functions reject non-human roles | RB (11 functions × worker, service_role, anon, VIEWER, ADMIN, SECURITY_REVIEWER, RELEASE_AUTHORITY, no-role user); SD `test_human_only_functions_are_closed_to_non_human_roles` |

CR4-01 (PO decision 2026-10-20, migration 3400) — required proofs:

| # | Requirement | Tests |
|---|---|---|
| 1 | exactly seven canonical terms exist | AS `test_canonical_likelihood_vocabulary_is_exactly_the_po_set_in_rank_order`; DEV smoke vocabulary check |
| 2 | rank order exactly 1–7 as specified | AS `test_canonical_likelihood_vocabulary_is_exactly_the_po_set_in_rank_order`; DEV smoke |
| 3 | canonical likelihood accepted on an eligible ANALYTIC_JUDGMENT / IMPLICATION | AS `test_likelihood_only_on_prospective_statements_and_distinct_from_confidence` (LIKELY on AS3, ROUGHLY_EVEN_CHANCE on an IMPLICATION) |
| 4 | unknown term rejected | same test (PROBABLE, UNKNOWN, LIKELY_70_PERCENT → LIKELIHOOD_TERM_UNKNOWN) |
| 5 | non-permitted statement type rejected | same test (KNOWN_FACT, INFORMATION_GAP → LIKELIHOOD_NOT_APPLICABLE) |
| 6 | likelihood without rationale rejected | same test (missing / empty → schema; token rationale → LIKELIHOOD_RATIONALE_REQUIRED) |
| 7 | M07 input receives exactly the seven terms in rank order | same test (`env.task.likelihood_terms`) |
| 8 | likelihood and analytic confidence remain separate | same test (`likelihood_term` column vs `ai_recommended_confidence`; no confidence column on statements) |
| 9 | M07 still cannot set final_analytic_confidence | same test (+ `test_m07_cannot_set_final_confidence_and_rationale_is_mandatory`) |

The synthetic `TEST_PROBABLE` term is no longer inserted or removed by any test.

Additional: worker jobs — P `test_worker_jobs_chain_m07_to_m08_and_end_in_human_review`; REJECT /
ESCALATE / REQUEST_REPROCESSING — CR `test_reject_escalate_and_reprocessing_are_recorded_without_confidence`;
as-of claim status — B `test_claim_status_asof_ignores_later_unbounded_human_decisions_in_replay`;
baseline/RC RBAC — B `test_non_humans_cannot_create_or_approve`.

## §24 acceptance metrics

Computed by A over the corpus (5 relevance + 13 assessment scenarios + a REPLAY block); stored in
`docs/cg4-acceptance-metrics.json`. Every metric below must be 0.

| §24 | Metric |
|---|---|
| 1 | `below_threshold_hidden` |
| 2 | `manual_promotion_failures` |
| 3 | `recommended_without_concrete_or_not_established_rationale` |
| 4 | `hindsight_leakage` |
| 5 | `unsupported_factual_statements_persisted` |
| 6 | `statements_without_provenance` |
| 7 | `category_violations` |
| 8 | `unlabelled_contradiction_removal` |
| 9 | `republication_inflation` |
| 10 | `unsupported_causal_accepted_as_fact` |
| 11 | `m07_final_confidence_set` |
| 12 | `m08_modified_m07` |
| 13 | `non_human_final_approvals` |
| 14 | `hash_mismatch_accepted` |
| 15 | `assessment_version_mutations` |
| 16 | `gs_leakage` |
| 18 | `scenario_expectation_mismatches` (every scenario's labelled outcome) |
| 19 | `traceability_gaps` |
