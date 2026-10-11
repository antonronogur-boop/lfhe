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
| CLAIM_REVIEW | 2 | | ✔ | | | | |
| EVENT_ACTION | 3 | | ✔ | | | | |
| ASSESSMENT_REVIEW | 4 | | ✔ | ✔ | | | |
| FINAL_CONFIDENCE_SET | 4 | | ✔ | | | | |
| REPORT_EDIT | 5 | | ✔ | | | | |
| REPORT_CONTENT_APPROVE | 6 | | | ✔ | | | |
| QA_WARNING_ACKNOWLEDGE | 6 | | | ✔ | | | |
| SECURITY_REVIEW | 6 | | | | ✔ | | |
| RELEASE_DECIDE | 6 | | | | | ✔ | |

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
