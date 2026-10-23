# Phase 6 — test traceability (Addendum v1.0 §32 and §33)

Files: `tests/integration/test_p6_m10d.py` (D), `tests/integration/test_p6_m10s.py` (S),
`tests/integration/test_p6_approvals.py` (AP), `tests/integration/test_p6_release.py` (R),
`tests/integration/test_p6_workspace.py` (W), `tests/security/test_p6_rbac.py` (RB),
`tests/security/test_security_definer_hardening.py` (SD), `tests/security/test_gs_isolation.py` (G),
`apps/web/tests/release.test.ts` (UI), `tests/acceptance/test_phase6_acceptance.py` (A, corpus
`tests/fixtures/phase6_acceptance/corpus.json`; metrics `docs/cg6-acceptance-metrics.json`).
M10-S is the FakeProvider with the rule-based stand-in `tests/m10s_auditor.py` (reads only the envelope)
or labelled scripted behaviours; real-model detection quality is not measured (real-provider trial is a
non-blocking follow-on item).

## §32 acceptance behaviours

| # | Behaviour | Evidence |
|---|---|---|
| 1 | QA-D binds exact version / hash | D `test_m10d_binds_exact_version_…` (run row, FK refusal); A `qa_binding_violations` |
| 2 | wrong hash rejected | D same test (run_m10d, request_report_qa VERSION_HASH_MISMATCH) |
| 3 | missing report object rejected | D same test (REPORT_VERSION_NOT_FOUND, QA_REQUEST_NOT_FOR_VERSION) |
| 4 | missing statement mapping fails | D `test_m10d_fails_closed_on_corrupted_content` (QA-01 MISSING_REQUIRED_PROVENANCE); A Q23 |
| 5 | post-cutoff evidence fails | D `test_m10d_post_cutoff_evidence_…` (QA-04); A Q21 |
| 6 | unapproved assessment fails | D `test_m10d_unapproved_unpinned_…` (superseded approval → QA-10 UNAPPROVED_ASSESSMENT) |
| 7 | confidence mismatch fails | D `test_m10d_fails_closed_…` (QA-08); A Q11 |
| 8 | likelihood mismatch fails | D same (QA-08 UNAUTHORISED_LIKELIHOOD_CHANGE); A Q12 |
| 9 | missing version pin fails | D `test_m10d_unapproved_unpinned_…` (QA-11 UNPINNED_REQUIRED_VERSION) |
| 10 | missing model / prompt provenance fails | D same (QA-12, MODEL version with a failed M09 run) |
| 11 | invalid original-language grounding fails | D same (D18, tampered span) |
| 12 | baseline after cutoff fails | D `test_m10d_post_cutoff_…` (D21) |
| 13 | reference context after cutoff fails | D same (D22) |
| 14 | required high-impact validation missing fails | D `test_m10d_unapproved_…` (D20) |
| 15 | report structure invalid fails | D `test_m10d_fails_closed_…` (4 KJs → STRUCTURE) |
| 16 | lineage / independence mismatch surfaced | D same (QA-05 FALSE_INDEPENDENT_CONFIRMATION); A Q10 |
| 17 | OSINT boundary violation blocks release | D same (QA-14 PROHIBITED_INFORMATION; eligibility false); R `test_release_gates_…`; A Q14 |
| 18 | M10-D creates no model_run | D `test_m10d_binds_…` (model_runs count unchanged); A `m10d_model_runs` |
| 19 | supported paraphrase passes | S `test_supported_paraphrase_passes_…`; A Q02 |
| 20 | unsupported new fact → CRITICAL / FAIL | S `test_semantic_auditor_fails_…`; A Q05, Q22 |
| 21 | unsupported causal claim fails | S same; A Q06 |
| 22 | actor change fails | S same; A Q07 |
| 23 | quantity scope distortion fails | S `test_supported_paraphrase_…` (validator-accepted edit, semantic FAIL); A Q03 |
| 24 | certainty strengthening fails | S `test_semantic_auditor_…`; A Q08 |
| 25 | attribution removal fails | S same (S19) + D19; A Q09 |
| 26 | SOURCE_REPORTED → factual strengthening fails | S same (QA-07 EPISTEMIC_STRENGTH_MISMATCH) |
| 27 | false independent-confirmation wording fails | S same (QA-05) |
| 28 | contradiction deletion fails | S `test_supported_paraphrase_…` (validator-accepted "undisputed"); A Q04 |
| 29 | misleading semantic duplication detected | S `test_duplication_…` (S QA-13 + D QA-13); A Q16 |
| 30 | hindsight / later knowledge fails | S `test_semantic_auditor_…` ("as later shown in 2027"); A Q13 |
| 31 | original-language semantic mismatch detected | S `test_duplication_…` (S18 TRANSLATION_MATERIAL_MISMATCH, scripted) |
| 32 | reference-context scope expansion detected | S same (S20, scripted) |
| 33 | prompt injection cannot change QA instructions | S `test_prompt_injection_…` (system prompt = bundle file; injection only inside the escaped envelope; obedient model cannot rescue a deterministic CRITICAL); A Q15, Q22 |
| 34 | M10-S cannot repair the report | S `test_m10s_cannot_repair_…` (schema failure + one repair run, both INVALID, report unchanged); A Q18, `m10_report_repairs` |
| 35 | M10-S cannot change confidence / likelihood | S same (ingestion rejects schema-bypassing keys; result must be the stored model output) |
| 36 | unknown evidence ref rejected | S `test_duplication_…` (UNKNOWN_EVIDENCE_REF → S INVALID → FAIL); A Q19 |
| 37 | every M10-S finding traceable | S `test_m10s_cannot_repair_…` (prompt hash, module version, config hash, envelope, manifest, task); A `m10s_traceability_gaps` |
| 38 | D + S clean → PASS | AP `test_combined_status_…`; A Q01, Q17, Q24 |
| 39 | non-critical warning → PASS_WITH_WARNINGS | AP same; A Q16 |
| 40 | CRITICAL → FAIL | AP same (scripted semantic CRITICAL) |
| 41 | deterministic CRITICAL not overridden | S `test_prompt_injection_…`, D `test_m10d_stale_…`; A Q15, Q22 |
| 42 | acknowledgement requires REVIEWER | AP `test_combined_status_…`; RB; A W04 |
| 43 | acknowledgement exact finding / run / version bound | AP same (hash, finding, stale result, composite FK) |
| 44 | CRITICAL cannot be acknowledged | AP same (NOT_ACKNOWLEDGEABLE); UI; A W03, `critical_findings_acknowledged` |
| 45 | new QA run invalidates prior warning handling | AP same (rerun → new result, stale acks / approvals refused) |
| 46 | rerun preserves history | AP same (2 results, 4 runs kept) |
| 47 | changed result emits audit | AP same (QA_RESULT_CHANGED_BY_RERUN) |
| 48 | FAIL cannot be content-approved | AP `test_content_approval_…`; A W01 |
| 49 | PASS approved by REVIEWER | AP same (PENDING security review opened) |
| 50 | PWW requires acknowledgements first | AP `test_combined_status_…`; A W02, W13 |
| 51 | ANALYST cannot content-approve via REPORT_EDIT | AP `test_content_approval_…`; RB; A W05 |
| 52 | ADMIN cannot content-approve | AP same; RB; A W05 |
| 53 | security review cannot approve before content approval | AP same (no PENDING row; direct insert refused); A W06 |
| 54 | SECURITY_REVIEWER decides security review | AP same |
| 55 | non-security roles cannot decide | AP same; RB; A W07 |
| 56 | new version makes old content / security decisions inapplicable | AP `test_new_version_invalidates_…` (kept, SUPERSEDED, stale refused, audits) |
| 57 | PDF bound to exact version / hash | R `test_pdf_artifact_binding_…` (row, HTML, foreign render / hash refused) |
| 58 | PDF hash matches stored bytes | R same (DB digest, object store) |
| 59 | PDF hash mismatch blocks release | R same (CHECK holds with triggers disabled; storage detects tampering); A `pdf_mismatches_released` |
| 60 | template version / hash persisted | R same |
| 61 | renderer version / hash persisted | R same (renderer_hash = JCS SHA-256 of the identity) |
| 62 | manifest contains required references | R same; A `manifest_failures_released` |
| 63 | manifest JCS / hash deterministic | R same (SQL = Python = stored; rebuilt manifest identical) |
| 64 | manifest mutation impossible | R same (UPDATE / DELETE / TRUNCATE refused); A W15 |
| 65 | released PDF overwrite impossible | R same; A W15 |
| 66 | release without QA fails | R `test_release_gates_…` |
| 67 | release with FAIL fails | R same; A W17 |
| 68 | unacknowledged warnings block release | R same (QA_ACCEPTABLE with unacknowledged ids); A `unacknowledged_warnings_released` |
| 69 | release without content approval fails | R same |
| 70 | release without security APPROVED fails | R same (PENDING); A W08 |
| 71 | stale version fails release | R same; A W10, `stale_version_releases` |
| 72 | worker cannot release | R same; RB; A W09 |
| 73 | service_role cannot release | R same; RB; A W09 |
| 74 | anon cannot release | R same; RB; A W09 |
| 75 | ADMIN cannot release without RELEASE_AUTHORITY | R same (ADMIN refused; ADMIN + RELEASE_AUTHORITY releases — K-06) |
| 76 | ANALYST cannot release | R same; RB |
| 77 | REVIEWER cannot release | R same; RB |
| 78 | SECURITY_REVIEWER cannot release | R same; RB |
| 79 | RELEASE_AUTHORITY releases only when every condition passes | R same (checklist eligible / failed lists); A W12 |
| 80 | APPROVE_FOR_RELEASE creates RELEASED + manifest atomically | R same (1 / 1 / 1, same timestamp); A `partial_released_states` |
| 81 | failed release leaves nothing partial | R `refused()` row counts on every refused attempt; guard trigger |
| 82 | RETURN_FOR_REVISION does not modify the report | R `test_return_and_reject_release`; A W11 |
| 83 | REJECT_RELEASE does not create RELEASED | R same |
| 84 | released version cannot be changed in place | R `test_released_version_is_immutable_…`; A W15, `released_mutations` |
| 85 | correction after release → new version, full new QA | R same (REPORT_CORRECTION_CREATED, second release, predecessor unchanged); A W14 |
| 86 | QA workspace shows exact version / hash and findings | W `test_workspace_reads_…`; UI |
| 87 | evidence / provenance inspectable from a finding | W same (refs resolve to version statements) |
| 88 | role-inappropriate buttons create no authority | UI (server actions → HUMAN_ONLY RPCs only, schemas); RB |
| 89 | eligibility checklist reflects database state | W same (per-caller result); UI |
| 90 | released view shows manifest / PDF hash | W same (viewer reads release, manifest, PDF hash) |
| 91 | XSS-safe rendering intact | UI (no `dangerouslySetInnerHTML`); Phase 5 renderer escaping test; PDF route serves bytes as attachment |
| 92 | GS answer key inaccessible | G (incl. `qa_inputs.py`, M10 bundle, Phase 6 corpus); W; A `gs_leakage` |
| 93 | prompt lock passes | `scripts/prompt_registry.py check-lock` (CI step) |
| 94 | secret scan passes | `scripts/secret_scan.py`; `tests/security/test_secret_scan.py` |
| 95 | gitleaks passes | CI `secret-scan` job (pinned gitleaks, full history) |
| 96 | Phase 1–5 regression green | full `pytest` run |
| 97 | all Phase 6 tests pass | full `pytest` run |
| 98 | web tests / typecheck / build pass | `apps/web` vitest, `tsc --noEmit`, `next build`; CI `web` job |
| 99 | DEV smoke has Phase 6 guards | `scripts/supabase_dev_smoke.py` (11 P6 checks) |
| 100 | Phase 7 not started | no Phase 7 object / migration / code; PROJECT_STATUS |

## §33 CG6 criteria → metrics (`docs/cg6-acceptance-metrics.json`, all must be 0)

| §33 | Metric / evidence |
|---|---|
| 1 | `qa_binding_violations` |
| 2 | `unsupported_facts_accepted` |
| 3 | `epistemic_strength_violations_accepted` |
| 4 | `attribution_loss_accepted` |
| 5 | `post_cutoff_hindsight_accepted` |
| 6 | `provenance_gaps_accepted` |
| 7 | `m10_report_repairs` |
| 8 | `critical_findings_acknowledged` |
| 9 | `unacknowledged_warnings_released` |
| 10 | `content_approvals_unauthorised` |
| 11 | `security_approvals_unauthorised` |
| 12 | `releases_by_non_release_authority` |
| 13 | `releases_without_valid_qa` |
| 14 | `releases_without_content_approval` |
| 15 | `releases_without_security_approval` |
| 16 | `stale_version_releases` |
| 17 | `pdf_mismatches_released` |
| 18 | `manifest_failures_released` |
| 19 | `partial_released_states` |
| 20 | `released_mutations` |
| 21 | `m10s_traceability_gaps` |
| 22 | `gs_leakage` |
| 23 | `audit_chain_failures` |
| 24–30 | full test run, prompt lock, secret scan / gitleaks, web, DEV smoke (PO), Phase 7 not started |
| additional | `scenario_expectation_mismatches`, `osint_boundary_violations_accepted`, `injected_instruction_accepted`, `invalid_semantic_runs_accepted`, `m10d_model_runs` |
