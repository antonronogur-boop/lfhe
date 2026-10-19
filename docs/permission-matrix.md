# Role / permission matrix (Enforcement Addendum G-11)

Source of truth: `lfhe.role_permissions` (migration `20261011000200_rbac.sql`).
Permissions for later phases are seeded now so the matrix can be reviewed as a
whole; no function uses them before its phase.

| Permission | Phase | ADMIN | ANALYST | REVIEWER | SECURITY_REVIEWER | RELEASE_AUTHORITY | VIEWER |
| --- | --- | --- | --- | --- | --- | --- | --- |
| USER_ROLE_MANAGE | 1 | ✔ | | | | | |
| SOURCE_READ | 1 | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| SOURCE_CREATE | 1 | ✔ | ✔ | | | | |
| SOURCE_UPDATE | 1 | ✔ | ✔ | | | | |
| SOURCE_APPROVE_COLLECTION_METHOD | 1 | ✔ | | ✔ | | | |
| SOURCE_ACTIVATE | 1 | ✔ | | ✔ | | | |
| ARTICLE_READ | 1 | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| PROMPT_ACTIVATE | 1 | ✔ | | | | | |
| AUDIT_READ | 1 | ✔ | | ✔ | | | |
| SYSTEM_READ | 1 | ✔ | ✔ | | | | |
| CLAIM_READ | 2 | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| CLAIM_REVIEW | 2 | | ✔ | | | | |
| ENTITY_MANAGE | 2 | | ✔ | | | | |
| EVENT_ACTION | 3 | | ✔ | | | | |
| ASSESSMENT_REVIEW | 4 | | ✔ | ✔ | | | |
| FINAL_CONFIDENCE_SET | 4 | | ✔ | | | | |
| REPORT_EDIT | 5 | | ✔ | | | | |
| REPORT_CONTENT_APPROVE | 6 | | | ✔ | | | |
| QA_WARNING_ACKNOWLEDGE | 6 | | | ✔ | | | |
| SECURITY_REVIEW | 6 | | | | ✔ | | |
| RELEASE_DECIDE | 6 | | | | | ✔ | |

## Phase 2 functions (migration `20261011001600_claims_pipeline.sql`)

| Function | Caller | Permission |
| --- | --- | --- |
| `review_claim`, `set_claim_status`, `mark_claim_high_impact`, `decide_high_impact_revalidation` | human (HUMAN_ONLY) | `CLAIM_REVIEW` |
| `create_entity`, `add_entity_alias`, `link_entity_mention`, `create_entity_relationship` | human (HUMAN_ONLY) | `ENTITY_MANAGE` |
| `ingest_claim_extraction`, `ingest_classification`, `auto_resolve_mention`, `set_claim_high_impact`, `apply_automatic_claim_status`, `enqueue_pending_claim_extractions`, `claim_grounding_problems` | `lfhe_worker` only | — |
| `claim_status_auto_rules` (insert) | owner / migration only | — (empty in Phase 2) |

ADMIN deliberately has **no** `CLAIM_REVIEW` (technical administration is separate from
analytical review); the DEV smoke test checks that ADMIN's review attempt is refused.
Claim, entity and taxonomy tables are readable by humans holding `CLAIM_READ` (RLS) and by
`lfhe_worker`; nobody writes them directly.

## Phase 3 functions (migrations `…1800_lineage.sql`, `…1900_events.sql`, `…2100`, `…2200`)

| Function | Caller | Permission |
| --- | --- | --- |
| `decide_lineage_proposal`, `record_claim_lineage`, `retract_claim_lineage`, `decide_corroboration_recommendation` | human (HUMAN_ONLY) | `CLAIM_REVIEW` |
| `create_event`, `update_event`, `set_event_state`, `reject_event`, `review_event_version`, `merge_events`, `split_event`, `supersede_event`, `keep_events_separate` | human (HUMAN_ONLY) | `EVENT_ACTION` |
| `ingest_lineage`, `ingest_event_proposals` | `lfhe_worker` only | — |
| `claim_cutoff_eligible`, `claim_independence_group`, `independence_summary` | `authenticated`, `lfhe_worker` (invoker rights → RLS applies) | `CLAIM_READ` for the underlying rows |
| internal writers (`write_event_version`, `insert_claim_lineage`, `resolve_external_origin`, `event_proposal_problems`, …) | no grant (called only inside the functions above) | — |

CG3 corrective pass (migrations 2300–2500): `decide_lineage_proposal` takes an optional 4th
argument `p_external_origin_id` (explicit human identity decision; same permission);
`retract_claim_lineage` takes an optional 3rd argument `p_evidence_basis` (migration 2600; same
permission; `lfhe.lineage_retraction_usable` is worker-only; `claim_lineage_retraction_evidence`
is immutable and readable with `CLAIM_READ`);
`lfhe.lineage_usable`, `lfhe.event_version_eligible`, `lfhe.run_evidence_eligible`,
`lfhe.event_asof`, `lfhe.claim_independence_group_asof`, `lfhe.independence_summary_asof` are
SECURITY DEFINER, executable by `lfhe_worker` only (envelope building);
`lfhe.article_cutoff_eligible` (invoker) and `lfhe.event_fully_split` are readable by
`authenticated` and `lfhe_worker`. New tables `claim_lineage_evidence` and
`event_state_version_bindings` are immutable and readable with `CLAIM_READ`; they are written
only inside `record_claim_lineage` and by the state-history trigger.

No new permissions were introduced: lineage / independence / claim-status decisions use
`CLAIM_REVIEW`; event decisions use `EVENT_ACTION` (both ANALYST). ADMIN, VIEWER, anon,
`service_role` and `lfhe_worker` are refused (tests + DEV smoke P3 checks). A worker may
write only the initial `CANDIDATE` state of an AI-created event (CHECK on
`event_state_history`). All Phase 3 tables are readable with `CLAIM_READ` (RLS) and
written by nobody directly (`block_mutation` makes them append-only/immutable).

## Phase 4 functions (migrations `…2700` … `…3300`)

| Function | Caller | Permission |
| --- | --- | --- |
| `create_reference_context_version`, `decide_reference_context_version`, `create_baseline_version`, `decide_baseline_version` | human (HUMAN_ONLY) | `ASSESSMENT_REVIEW` |
| `decide_relevance` (VALIDATE / OVERRIDE), `promote_event_version` (PROMOTE / REQUEST_ASSESSMENT) | human (HUMAN_ONLY) | `ASSESSMENT_REVIEW` |
| `dispose_challenge_flag` | human (HUMAN_ONLY) | `ASSESSMENT_REVIEW` |
| `review_assessment` — REJECT / ESCALATE / REQUEST_REPROCESSING | human (HUMAN_ONLY) | `ASSESSMENT_REVIEW` |
| `review_assessment` — APPROVE; `modify_and_approve_assessment` | human (HUMAN_ONLY) | `ASSESSMENT_REVIEW` **and** `FINAL_CONFIDENCE_SET` (ANALYST only) |
| `create_trend_version`, `create_indicator_version` | human (HUMAN_ONLY) | `ASSESSMENT_REVIEW` |
| `ingest_relevance`, `ingest_assessment`, `ingest_challenge`, `m07_context`, as-of helpers (`baseline_asof`, `reference_context_asof`, `claim_status_asof`, `assessment_version_approved_asof`, `trend_asof`, `trend_version_usable`, `indicator_version_usable`, `p4_object_eligible`, …) | `lfhe_worker` only | — |
| internal writers / checks (`write_assessment_version`, `set_assessment_state`, `assessment_statement_problems`, `require_reviewable_version`, `supersede_previous_approvals`, `p4_refs`, …) | no grant (called only inside the functions above) | — |

No new permissions were introduced; the Phase 4 permissions seeded in Phase 1 are used:
`ASSESSMENT_REVIEW` (ANALYST, REVIEWER) and `FINAL_CONFIDENCE_SET` (ANALYST). A REVIEWER can
reject, escalate or request reprocessing and dispose of M08 flags, but cannot set final
analytic confidence. ADMIN, SECURITY_REVIEWER, RELEASE_AUTHORITY, VIEWER, anon,
`service_role` and `lfhe_worker` are refused by every Phase 4 HUMAN_ONLY function
(`tests/security/test_p4_rbac.py`, DEV smoke P4 checks). All Phase 4 tables are readable with
`CLAIM_READ` (RLS) and by `lfhe_worker`, written by nobody directly, and immutable
(`block_mutation`); `assessment_state_history` is append-only and the worker may write only
NULL→DRAFT, DRAFT→CHALLENGED and CHALLENGED→IN_REVIEW.

## Non-human principals
- `lfhe_registrar` (deployment pipeline): may only register prompt artifacts
  and model configurations (`register_prompt_version`,
  `register_model_configuration`); it can never activate a prompt.
- `lfhe_worker`: collection, queue, snapshot and model-run write paths only.
- `lfhe_worker`, `lfhe_registrar`, `service_role`, `anon`: **no** EXECUTE on any HUMAN_ONLY
  function; additionally rejected inside every such function
  (`lfhe.current_human_user()` requires `role = authenticated`, JWT role
  `authenticated`, an existing `auth.users` id, and no `lfhe_worker`
  membership).
- Separation of duties (K-06) is a policy decision; the prototype allows one
  person to hold several roles. Every grant/revoke is audited
  (`USER_ROLE_CHANGED`).
- The first ADMIN is bootstrapped by the operator with the owner-only
  `lfhe.bootstrap_grant_role()` (see runbooks/environments.md).

## Credential exclusion (CG1-03, CG1-08)
`sources.collection_config`, `model_configurations.settings` and
`processing_jobs.payload` reject, at any depth: credential-like key names, URL
userinfo, and URL query/fragment parameters with credential-like names. The
check runs in a BEFORE trigger (errors list paths/parameter names only) with
CHECK constraints as backstop, so a rejected secret never reaches a row, the
audit log or an error message.

### CG1-08A additions
- Before inspection every string is put into its *inspection form* (tab/LF/CR
  removed, leading/trailing U+0001–U+0020 trimmed, `\` read as `/`) — the way URL
  parsers read it — so whitespace-wrapped or backslash variants cannot evade the rule.
- Userinfo is checked for `scheme://`, for http/https/ws/wss/ftp/file with any
  number of slashes, and for `//authority`; parameter names are checked in every
  string containing `?` or `#`, including relative references.
- Known source URL fields (`feed_url`, `sitemap_url`, `endpoint`, `urls[]`) must be
  present, JSON strings and canonical absolute http(s) URLs
  (`lfhe.source_config_problems`, trigger `sources_validate_config`, error code
  `SOURCE_CONFIG_INVALID`), checked before any row or audit entry exists.
- PostgreSQL, Python and TypeScript share the parity fixture
  `tests/fixtures/url_canonicalisation_cases.json`.
