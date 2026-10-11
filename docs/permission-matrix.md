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
