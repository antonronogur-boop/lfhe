# Phase 6 — QA, approval & release (design)

Baseline: `docs/specs/LFHE_Phase6_Authoritative_Baseline_Addendum_v1.0.md` (SPEC_INDEX 22), PO
authorisation `docs/specs/PO_Decision_2026-10-23_Authorise_Phase6.md` (SPEC_INDEX 23), Module Prompt Pack
v1.2 §34–§55, CG0 E.16–E.19, F (REPORT / SECURITY REVIEW / RELEASE state machines), G (RELEASED
protection), H (QA architecture). Migrations `20261011003800_p6_qa.sql`, `20261011003900_p6_approval_release.sql`.

Phase 6 does not add analytical semantics (M07 / M08 / M09 unchanged) and does not start Phase 7.

## 1. Chain

```
report_versions (DRAFT_VERSION, immutable, Phase 5)          ← never modified (DC6-01)
  → qa_requests        HUMAN (REPORT_EDIT | REPORT_CONTENT_APPROVE) on the LATEST version → RUN_REPORT_QA job
  → qa_runs D          M10-D lfhe.run_m10d (deterministic SQL, no model_run) + qa_check_results
  → qa_runs S          M10-S (M10_QA_AUDITOR 1.0.0, one model_run per call, ≤ 1 schema repair) + findings
  → qa_results         combined PASS / PASS_WITH_WARNINGS / FAIL, computed by lfhe.record_qa_result
  → warning_acknowledgements   HUMAN (QA_WARNING_ACKNOWLEDGE) per WARNING finding of the CURRENT result
  → content_approvals  HUMAN (REPORT_CONTENT_APPROVE) APPROVE / RETURN_FOR_REVISION / REJECT on the CURRENT result
  → security_reviews   PENDING opened by APPROVE; HUMAN (SECURITY_REVIEW) APPROVED / RETURN_FOR_REVISION / REJECTED
  → release_pdf_artifacts   worker (RENDER_RELEASE_PDF): release HTML → headless Chromium → write-once storage
  → lfhe.p6_release_checklist   deterministic eligibility (21 checks), re-run inside the release transaction
  → release_decisions  HUMAN (RELEASE_DECIDE): RETURN_FOR_REVISION / REJECT_RELEASE (decide_release) or
                       APPROVE_FOR_RELEASE (release_report only)
  → release_manifests + report_releases (RELEASED)   written together with the APPROVE decision, atomically
```

Every Phase 6 row carries a composite FK to `(report_version_id, report_version_hash)`; the derived
state of a version is the security-invoker view `report_version_workflow` (DRAFT_VERSION, QA_RUNNING,
QA_FAILED, QA_PASSED, QA_PASSED_WITH_WARNINGS, WARNING_ACKNOWLEDGED, CONTENT_RETURNED_FOR_REVISION,
CONTENT_REJECTED, SECURITY_REVIEW_PENDING, SECURITY_APPROVED, SECURITY_RETURNED_FOR_REVISION,
SECURITY_REJECTED, RELEASE_RETURNED_FOR_REVISION, RELEASE_REJECTED, RELEASED, SUPERSEDED).

"Current" always means: the latest report version of the report, its latest `qa_results` row, the
content decision on THAT result, the latest security review of THAT content approval. A rerun or a new
version therefore makes every earlier acknowledgement / approval / review inapplicable without deleting it.

## 2. M10-D (lfhe.run_m10d, engine `lfhe-m10d/1.0.0`)

Raises (records nothing) on an unknown version, a hash mismatch or a request for another version.
Otherwise records one D run with a finding per problem and one PASS row per check without a finding
(`qa_checks` lists the 25 deterministic checks). Rules (all fail closed):

| Check | Deterministic rule |
| --- | --- |
| D23 | canonical JSON hashes to the stored hash; header = report (id / mode / cutoff); version is the latest (`VERSION_NOT_CURRENT`) |
| STRUCTURE, QA-01/07/08/09/17, D19 | the Phase 5 validator `report_content_problems` re-run on the stored content (mapped to M10 codes); > 3 KJs; unknown section; canonical vs table statement mismatch; undecided length review; instruction-like text (`EMBEDDED_INSTRUCTION_IN_CONTENT`, CRITICAL) |
| QA-01 | every statement has ≥ 1 mapping; canonical sources = stored mappings; cited statements belong to the item's selected candidate; evidence-required statements have supporting evidence |
| QA-02 | cited statements / assessment versions / claims / snapshots / articles / sources / baselines / reference contexts resolve |
| QA-03 | approval after assessment creation and before the report version; evidence retrieved before the report version |
| QA-04 | every claim `claim_cutoff_eligible`, every source assessment `assessment_version_eligible` for the report's mode / cutoff (event time never a criterion) |
| QA-05 | corroboration / independence wording must be in the approved sources; with approved wording, validated lineage must show ≥ 2 groups and no unknown lineage, else WARNING |
| QA-06 | every number in a report statement occurs in its own sources or their evidence claims |
| QA-07 | source assessment state APPROVED; category = type; contested flag = contradicting-evidence state |
| QA-08 | item and statement confidence = approved `final_analytic_confidence` (never `ai_recommended_confidence`); likelihood = the single approved term |
| QA-10 | every source assessment version is the approved, current version as of the cutoff; indicator / trend candidates eligible |
| QA-11 | selection set, candidate object hashes, item pins (canonical = stored = resolved), event version hashes |
| QA-12 | MODEL version / statements: succeeded M09 run, prompt hash, model configuration hash; AI assessments: succeeded M07 run |
| QA-13 | one event in several KJ / SD / IW items → WARNING; merged / superseded event reported with its successor → FAIL |
| QA-14 | classification / handling markings in report, assessment or evidence text → `PROHIBITED_INFORMATION`; source with declared access restrictions → WARNING (human handling) |
| QA-17 | aggregate of cutoff / baseline / reference-context failures (hindsight) |
| D18 | `claim_grounding_problems` on every evidence claim (exact original-language span) |
| D19 | required attribution present; omitted attribution must be justified by as-of corroboration (`p4_attribution_required`) |
| D20 | high-impact evidence claims: human review completed, no pending revalidation |
| D21 / D22 | baseline / reference-context versions usable as of the cutoff |
| QA-16, D24, D25 | prerequisites only (DC6-03); the manifest is checked in the release transaction |

## 3. M10-S (M10_QA_AUDITOR 1.0.0)

Bundle `packages/prompts/M10_QA_AUDITOR/1.0.0` (module_version `MPP-1.2.2+P6-ADDENDUM-1.0`, prompt-locked,
low-variance, strict schema with `additionalProperties: false`; output = findings only, no report text).
Input builder `qa_inputs.py` (database only): the exact version (statements with ids), cited approved
assessment statements, evidence claims with the original-language span, as-of status and independence,
event relationships, used reference contexts, the deterministic findings. Ingestion
`lfhe.ingest_qa_semantic` audits the STORED parsed output of the model run (a caller-supplied result that
differs is rejected), and rejects the whole output (S run INVALID, no findings stored) on: wrong version /
hash / D run, non-semantic check ids, inconsistent status / severity, an affected statement outside the
version, any evidence reference not present in the run's input / context manifest, repair / approval /
confidence / likelihood keys. The model's own `qa_status` / `release_blocked` are stored as advisory only.
M10-S also runs after a deterministic CRITICAL (diagnostic only).

## 4. Combined status (lfhe.record_qa_result)

FAIL if either run is INVALID, the S run lacks provenance, the hash binding fails, any finding is FAIL or
CRITICAL, or any non-PASS finding has an automatic-fail code (Prompt Pack §47). PASS_WITH_WARNINGS if
only WARNING findings remain; PASS otherwise. `warning_finding_ids` are the findings that need an
acknowledgement (all WARNING findings; never a FAIL / CRITICAL). `QA_RESULT_CHANGED_BY_RERUN` is audited
when the status of the current result changes.

## 5. Release PDF, eligibility, manifest

`report_pdf.py`: the release HTML is the Phase 5 deterministic rendering of the same canonical JSON with the
RELEASE banner instead of the draft-preview banner (the preview must re-render byte-identically first);
headless Chromium prints it offline; bytes go to write-once content-addressed storage
(`release-pdf/sha256/…`) and to `release_pdf_artifacts` (bytes, SHA-256, size, MIME, version / hash,
preview render, template version / hash, renderer identity / hash). CHECKs bind SHA-256 = digest(bytes),
size, `%PDF-` magic, storage key = hash, HTML contains the version hash. Byte reproducibility of Chromium
output is not claimed (DC6-04).

`lfhe.p6_release_checklist` (also `lfhe.release_eligibility` for the UI) evaluates: VERSION_EXISTS,
HASH_MATCHES, VERSION_CURRENT, NOT_ALREADY_RELEASED, QA_BOUND_TO_VERSION, M10D_COMPLETE, M10S_COMPLETE,
QA_ACCEPTABLE, NO_CRITICAL_FINDING, CONTENT_APPROVED, SECURITY_APPROVED, NOT_RETURNED_OR_REJECTED,
PDF_EXISTS, PDF_BOUND_TO_VERSION, PDF_HASH_VALID, TEMPLATE_RENDERER_RESOLVE, MODEL_PROVENANCE_RESOLVES,
ANALYTICAL_PROVENANCE_RESOLVES, MANIFEST_INPUTS_COMPLETE, CALLER_HUMAN_RELEASE_AUTHORITY.

`lfhe.release_report` (HUMAN_ONLY, RELEASE_DECIDE): locks the report, re-evaluates the checklist, sets a
transaction-local release token, writes the APPROVE_FOR_RELEASE decision, builds the manifest
(`p6_build_manifest`, Addendum §23 fields + item pins with analytical approval ids + authoring M09
run), checks completeness (`p6_manifest_problems`), stores `manifest_hash = SHA-256(JCS(manifest))`
(CHECK), writes `report_releases` (RELEASED) and the audit entries — one transaction; any failure leaves
nothing. A guard trigger refuses APPROVE decisions, manifests and RELEASED rows outside that token.

## 6. Corrections

A released version stays immutable forever. An analyst edit (Phase 5 path) creates vN+1; the trigger
`report_versions_p6_invalidation` audits `REPORT_CORRECTION_CREATED` (with the released predecessor and
its manifest hash) and the invalidation of the predecessor's QA / security approval; vN+1 needs the full
sequence again and gets its own decision, manifest and PDF. `request_report_qa` refuses a released version.

## 7. Jobs and configuration

`RUN_REPORT_QA` (object: report version; payload: hash, qa_request_id; enqueued only by
`request_report_qa`) and `RENDER_RELEASE_PDF` (payload: hash, security_review_id; enqueued by an APPROVED
security review or `request_release_pdf`). Configuration: `LFHE_M10_MODEL_CONFIGURATION_ID`, object
storage settings, `LFHE_CHROMIUM_PATH` / `LFHE_CHROMIUM_NO_SANDBOX`.

## 8. Workspace

`/reports/[id]?view=qa` — version / hash, workflow state, combined status, D / S run status, findings
grouped by severity with affected statement, evidence references, advisory action and blocking flag, QA
history, request-QA, per-warning acknowledgement (REVIEWER) and content decision (REVIEWER).
`?view=release` — security decision (SECURITY_REVIEWER), PDF artifacts (hash, size, template / renderer),
the database eligibility checklist, APPROVE_FOR_RELEASE with typed confirmation, RETURN / REJECT
(RELEASE_AUTHORITY), and the released view (timestamp, released by, manifest hash and JSON, PDF hash and
download via `/reports/[id]/pdf/[artifact]`, which re-checks the SHA-256 before serving the bytes).
