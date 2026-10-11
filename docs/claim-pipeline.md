# Claim pipeline (Phase 2)

Authority: Phase 2 Authoritative Baseline Addendum v1.0 (`docs/specs/`), Module Prompt
Pack v1.2 (cumulative baseline v1.1 + v1.2 + v1.2.1 + v1.2.2), CG0 architecture.

```
SOURCE → ORIGINAL-LANGUAGE ARTICLE_SNAPSHOT → TEXT_REPRESENTATION (immutable, NFC, code points)
      → M01 input (deterministic) → M02 model run → schema validation (+ ≤1 transparent repair run)
      → QA-D18 grounding (Python mirror, then DATABASE) + QA-S18 fidelity flags
      → lfhe.ingest_claim_extraction  (one transaction: claims, UNVERIFIED status,
                                       mentions, conservative entity links, rejections)
      → M03 model run → lfhe.ingest_classification (all-or-nothing)
      → human review (HUMAN_ONLY functions, audited)
```

## Invariants (all enforced in PostgreSQL)

| # | Invariant | Mechanism |
|---|---|---|
| 1 | No claim without an exact original-language evidence span | `claims_before_insert` trigger → `lfhe.claim_grounding_problems` → `CLAIM_NOT_GROUNDED_IN_ORIGINAL_SOURCE`; applies to every role incl. the owner |
| 2 | Span = `substr(text_content, start+1, end-start)` of the referenced text representation, which belongs to the referenced snapshot / article / source, is original language, language known and equal, not METADATA_ONLY (K-04), exact text NFC; `claim_text_original` lies verbatim inside the span | same function; reason codes mirrored by `lfhe_shared.grounding` (parity-tested) |
| 3 | A claim comes from a SUCCEEDED `M02_CLAIM_EXTRACTOR` run whose input manifest contains its text representation | trigger + FK to `claim_extraction_results` |
| 4 | Claims, mentions, entities, aliases, relationships, taxonomy items/assignments, rejections, results are immutable; status / high-impact / review / link logs are append-only | `lfhe.block_mutation()` triggers |
| 5 | Closed vocabularies | PostgreSQL enums (claim_type, claim_status, source_statement_status, review_decision, …), taxonomy table, review-flag list |
| 6 | Any review flag ⇒ `human_review_required` | CHECK `claim_flags_force_review` |
| 7 | Automatic status only for LOW-impact claims and only by an owner-configured rule (`claim_status_auto_rules`, empty by default) with a recommending model run | `lfhe.apply_automatic_claim_status` (`HIGH_IMPACT_REQUIRES_HUMAN`, `AUTO_RULE_NOT_CONFIGURED`) |
| 8 | Low→high impact after an automatic status ⇒ `claim_revalidations` row + `HIGH_IMPACT_REVALIDATION_REQUIRED`; the strengthened status is unusable (`claim_status_usability.status_usable = false`) until a human approves; rejection reverts the status | `lfhe.record_claim_high_impact`, `lfhe.decide_high_impact_revalidation` |
| 9 | High impact is object specific (`claim_high_impact` log: claim → flag + closed reasons); only a human can record or remove `HUMAN_MARKED_HIGH_IMPACT` | CHECK + `set_claim_high_impact` guard |
| 10 | Review decisions are human-only, permission `CLAIM_REVIEW`, bound to claim id + claim content hash (`lfhe-claim/1`) + the expected previous review (`REVIEW_OBJECT_MISMATCH`, `REVIEW_STALE`) | `lfhe.review_claim` (HUMAN_ONLY), composite FK `(claim_id, claim_hash)` |
| 11 | MODIFY_AND_APPROVE can change only normalised text, claim type, attribution — never the evidence span; the original claim stays immutable, the effective values are derived (`claim_state`) | `review_claim` + `claim_state` view |
| 12 | Entity resolution: automatic only by a unique, type-compatible, exact normalised alias match (`EXACT_ALIAS_RULE`); 0 → UNRESOLVED, ≥2 → AMBIGUOUS (candidates kept); never similarity; a human link is never overridden by the worker | `lfhe.auto_resolve_mention` |
| 13 | Entities, aliases (basis ≥ 10 chars), relationships (closed relation types, no SAME_AS) and links by humans need `ENTITY_MANAGE` | HUMAN_ONLY functions |
| 14 | M03 assignments must name an item of the taxonomy version the run declared and carried as context, and a claim that was an input of the run; otherwise the WHOLE output is rejected | `lfhe.ingest_classification` + `taxonomy_assignment_guard` |
| 15 | Ingestion happens once per model run | PK on `claim_extraction_results.model_run_id` / `claim_classification_results.model_run_id` |

## Model runs, repair and failures

* Every provider call is one immutable `model_runs` row (prompt version + content hash, module
  version, model configuration + hash, envelope / input-set / context-set hashes; CG1-05).
* `SCHEMA_VALIDATION_FAILED` → at most **one** repair: a new model run of the same active prompt
  version with the identical input/context objects (same set hashes); task parameters add
  `repair.of_model_run_id` and the validation errors. The failed run keeps its status; the result
  row of the repair names it (`repair_of_model_run_id`). The repaired output is grounded like any
  other output — the repair logic never edits evidence.
* `PROVIDER_ERROR`, exhausted repair, model status `FAILED` → an extraction result is recorded,
  no claim exists.
* Offsets: model offsets must resolve exactly (a wrong offset is a rejection, never relocated);
  null offsets are filled only if `exact_text` occurs exactly once (`EXACT_TEXT_AMBIGUOUS` otherwise).

## QA-S18 fidelity (foundation)

`lfhe_orchestrator.fidelity` adds review flags (never removes): model `normalisation_check`
(12 dimensions + translation mismatch + language uncertainty); deterministic quantity check;
negation / uncertainty / attribution / conditionality markers for en, uk, ru, pl, hu, de, fr
(other languages: quantity only + warning); introduced negation; high-impact potential
contradiction; model-requested review; source text with instruction-like content
(`SOURCE_CONTAINS_INSTRUCTION_LIKE_TEXT`). These are a safety net, not a semantic oracle.

## High impact in Phase 2

The orchestrator supplies `high_impact_context` to M02, but Phase 2 has no authoritative rule
that makes a claim high impact (the v1.2 reasons refer to assessments, report candidates, events
and indicators — Phase 3+). Default is `false`; humans can mark claims high impact. See OPEN items.

## Jobs

`EXTRACT_CLAIMS` (text representation) → on persisted claims enqueues `CLASSIFY_CLAIMS`.
`lfhe.enqueue_pending_claim_extractions(n)` enqueues extraction for original-language texts
without a result from the active M02 version (idempotency key = text representation + prompt
version). Worker: `python -m lfhe_orchestrator.worker --once --enqueue` with
`LFHE_M02_MODEL_CONFIGURATION_ID`, `LFHE_M03_MODEL_CONFIGURATION_ID` and the provider key from
the secret-managed environment (`docs/providers.md`).
