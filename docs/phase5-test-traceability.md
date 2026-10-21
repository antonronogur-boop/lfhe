# Phase 5 — test traceability (Addendum v1.0 §26 and §27)

Files: `tests/integration/test_p5_reports.py` (R), `tests/integration/test_p5_render_pipeline.py` (P),
`tests/integration/test_p5_workspace.py` (W), `apps/web/tests/reports.test.ts` (UI),
`tests/security/test_p5_rbac.py` (RB), `tests/security/test_gs_isolation.py` (G),
`tests/security/test_security_definer_hardening.py` (SD),
`tests/acceptance/test_phase5_acceptance.py` (A, corpus `tests/fixtures/phase5_acceptance/corpus.json`).

## §26 required tests

| # | Requirement | Tests |
|---|---|---|
| 1 | only eligible APPROVED assessment versions enter the selectable pool | R `test_only_eligible_approved_current_versions_enter_the_pool` |
| 2 | rejected / unapproved assessments cannot enter authoritative selection | R `test_only_eligible_approved_current_versions_enter_the_pool` (draft, REJECTED absent; no direct pool insert) |
| 3 | superseded assessment not selected as current source | R `test_only_eligible_approved_current_versions_enter_the_pool` (CANDIDATE_NOT_ELIGIBLE after supersession) |
| 4 | selection is HUMAN_ONLY | R `test_selection_is_human_only_audited_and_m09_cannot_use_unselected_material`; RB; W |
| 5 | selection is audit logged | R `test_selection_is_human_only_audited_and_m09_cannot_use_unselected_material` (SELECTED / REMOVED / RETURNED) |
| 6 | selected object / version / hash pinned | R `test_only_eligible_…` (VERSION_HASH_MISMATCH, decision hash), `test_selection_…` (selection set items) |
| 7 | worker / M09 cannot include an unselected candidate | R `test_selection_…` (SOURCE_CANDIDATE_NOT_SELECTED, SOURCE_STATEMENT_NOT_IN_SELECTED_CANDIDATE); A E03, metric `unselected_candidate_included` |
| 8 | every report statement maps to ≥ 1 approved assessment statement | R `test_every_report_statement_maps_to_approved_statements_and_items_pin_versions`; A `report_statements_without_mapping` |
| 9 | unknown assessment_statement id fails closed | R `test_every_report_statement_…`; A E22 |
| 10 | statement from unselected assessment fails closed | R `test_selection_…` (foreign statement) |
| 11 | unsupported new fact fails closed | R `test_new_facts_judgments_strengthening_and_attribution_loss_fail_closed` (number, name); A E05, E06 |
| 12 | unsupported new judgment fails closed | R same test (causal, strengthening, operational); A E07, E09, E19 |
| 13 | required attribution cannot be removed | R same test (ATTRIBUTION_REMOVED); A E08, E20, metric `attribution_strength_violations` |
| 14 | material contradiction cannot be silently removed | R `test_contradiction_and_caveats_cannot_disappear`; A E13 |
| 15 | material caveat cannot be silently removed | R `test_contradiction_and_caveats_cannot_disappear`, `test_caveats_cannot_be_removed_for_length_…`; A H02 |
| 16 | M09 cannot change final analytic confidence | R `test_m09_cannot_change_confidence_or_likelihood`; A E10 |
| 17 | M09 cannot change likelihood | R same test (LIKELIHOOD_REMOVED / _CHANGED); A E12 |
| 18 | M09 cannot create likelihood | R same test (LIKELIHOOD_ADDED, field and wording) |
| 19 | republication cannot become stronger confidence | R same test (CONFIDENCE_CHANGED, EPISTEMIC_STRENGTHENING); A E21 |
| 20 | merged statements preserve all source mappings | R `test_every_report_statement_…` (two sources persisted); A E02 |
| 21 | M09 may propose removal | R `test_removal_is_proposed_by_m09_and_decided_only_by_a_human`; A E15 |
| 22 | substantive removal not applied automatically | R same test (item still present); A `automatic_substantive_removals` |
| 23 | substantive removal decision is HUMAN_ONLY | R same test (worker, service_role, VIEWER refused; ACCEPT → new human version); A H08 |
| 24 | REPORT_LENGTH_REVIEW_REQUIRED raised where required | R same test (`length_review_required` / `_pending`), `test_caveats_cannot_be_removed_for_length_and_length_status_is_deterministic` |
| 25 | caveats cannot be selected for deletion to satisfy length | R `test_caveats_cannot_be_removed_for_length_…` (proposal and human removal refused); A E14 |
| 26 | insufficient content does not cause fabricated filler | R `test_structure_limits_sections_and_no_filler` (coverage `below_target`, unsourced filler refused); A E20 |
| 27 | maximum 3 KJs enforced | R `test_structure_…`; A E16 |
| 28 | Supporting Development target handled without fabrication | R `test_structure_…` (coverage), `test_caveats_…` (EXCEEDS above 5) |
| 29 | Indicator target handled without fabrication | R `test_structure_…` |
| 30 | What-to-Watch target handled without fabrication | R `test_structure_…`, `test_caveats_…` (EXCEEDS above 3) |
| 31 | invalid / unknown section fails closed | R `test_structure_…` (schema, STATEMENT_ROLE_INVALID, SECTION_NOT_AUTHORISED); A E17 |
| 32 | ordering deterministic once human decisions fixed | R `test_structure_…` (reversed model order → identical sections) |
| 33 | canonical JSON is RFC 8785 JCS | R `test_canonical_json_is_jcs_and_versions_are_immutable` (SQL ≡ Python incl. Unicode / control chars / bounds) |
| 34 | same canonical object → deterministic hash | R same test; A `canonical_hash_nondeterminism` |
| 35 | changed canonical content → new hash / version | R same test |
| 36 | report version cannot UPDATE / DELETE | R same test; A `report_version_mutations` |
| 37 | human canonical edit creates new version | R same test |
| 38 | prior version byte-for-byte unchanged | R same test (JCS bytes before / after) |
| 39 | stale version / hash human action rejected | R same test (REPORT_VERSION_STALE, VERSION_HASH_MISMATCH, REPORT_EDIT_NO_CHANGE), `test_selection_…` (SELECTION_STALE); A H03, H07 |
| 40 | report_item pins exact event / assessment version | R `test_every_report_statement_…` |
| 41 | human report statement retains source mappings | R `test_human_edits_keep_provenance_are_audited_and_cannot_be_impersonated`; UI `rewording keeps sources` |
| 42 | unmapped human statement rejected | R same test; A H01 |
| 43 | human removal / inclusion audited | R same test, `test_removal_is_…`, `test_selection_…` |
| 44 | worker / service cannot impersonate a human editor | R same test (worker, service_role, anon; direct insert); RB; A H04, H05 |
| 45 | same version + template / renderer → deterministic HTML | P `test_preview_rendering_is_deterministic_bound_and_never_released`; A `preview_render_nondeterminism` |
| 46 | preview visibly derives from canonical JSON | P same test (version id / hash, every statement ref) |
| 47 | render does not change canonical content | P same test |
| 48 | rendered preview cannot be marked RELEASED | P same test (status PREVIEW only; no RELEASED state for versions) |
| 49 | template / renderer version persisted | P same test |
| 50 | authorised analyst can view the candidate pool | W `test_workspace_reads_actions_and_provenance` |
| 51 | select / exclude via server-side guarded actions | W same test; UI `binds selection decisions to the candidate hash` |
| 52 | provenance links resolve report statement → assessment statement | W same test (→ evidence → claims under RLS); UI |
| 53 | version comparison works | W same test; UI `compares versions statement by statement` |
| 54 | unauthorised VIEWER cannot select / edit | W same test; RB |
| 55 | workspace never exposes GS answer-key material | W `test_workspace_code_never_touches_gold_standard_material`; G |
| 56 | M09 provider failure leaves no partial version | P `test_failures_leave_no_partial_report_and_repair_is_a_separate_run` |
| 57 | schema failure leaves no partial version | P same test |
| 58 | repair is a separate model_run | P same test |
| 59 | model_run traceability complete | P same test; A `m09_traceability_gaps` |
| 60 | prompt injection cannot alter M09 instructions | P `test_prompt_injection_in_approved_text_does_not_alter_m09_and_no_gs_leakage` |
| 61 | GS leakage = 0 | P same test; G (incl. `report_inputs.py`, Phase 5 corpus); A `gs_leakage` |
| 62–65 | Phase 1–4 regressions PASS | full `pytest` run |
| 66 | web / security tests PASS | `apps/web` vitest; `tests/security/*`; secret scan; gitleaks |
| 67 | human-only Phase 5 functions reject non-human roles | RB (6 functions × worker, service_role, anon, VIEWER, ADMIN, REVIEWER, SECURITY_REVIEWER, RELEASE_AUTHORITY, no-role); SD |

Additional: worker chain EDIT_REPORT → RENDER_REPORT — P `test_worker_runs_edit_report_then_render_report`;
renderer escaping / uncertainty encoding — P `test_renderer_escapes_untrusted_text_and_encodes_uncertainty`.

## §27 acceptance metrics (`docs/cg5-acceptance-metrics.json`, all must be 0)

| §27 | Metric |
|---|---|
| 1 | `unselected_candidate_included` |
| 2 | `report_statements_without_mapping` |
| 3 | `unsupported_new_facts_accepted` |
| 4 | `unsupported_new_judgments_accepted` |
| 5 | `attribution_strength_violations` |
| 6 | `confidence_changes_by_m09` |
| 7 | `likelihood_changes_by_m09` |
| 8 | `silent_caveat_contradiction_deletion` |
| 9 | `automatic_substantive_removals` |
| 10 | `fabricated_filler_accepted` |
| 11 | `report_version_mutations` |
| 12 | `human_statements_without_provenance` |
| 13 | `non_human_authoritative_decisions` (+ `human_adversarial_accepted`) |
| 14 | `canonical_hash_nondeterminism` |
| 15 | `statement_provenance_gaps` |
| 16 | `gs_leakage` |
| 18 | `scenario_expectation_mismatches` |
| 19 | `m09_traceability_gaps` |
| 20 | `preview_render_nondeterminism` |
