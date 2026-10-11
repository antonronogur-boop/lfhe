# Audit catalogue and mechanism (Enforcement Addendum G-14)

## Mechanism
- `lfhe.audit_log` is append-only: UPDATE / DELETE / TRUNCATE are blocked by
  triggers for every role including the owner, and no application role has
  INSERT. Entries are written only by `lfhe.write_audit()`, which no role may
  call directly; it runs from SECURITY DEFINER **triggers on the audited
  tables**. An audited change therefore cannot skip or forge its entry.
- **Hash chain** (`v1`): `entry_hash = sha256(canonical_v1(entry, previous_entry_hash))`;
  genesis predecessor = 64 × `0`. Canonical form: `lfhe.audit_canonical_v1`
  (SQL) ≡ `lfhe_shared.audit.canonical_v1` (Python, independent verifier).
- **Concurrency:** a transaction-scoped advisory lock serialises the audit
  step; `seq` is assigned under the lock, gap-free and equal to chain order.
  Verified by `test_concurrent_audited_operations_produce_one_verifiable_chain`.
- **Actor classification:** HUMAN (signed-in `authenticated` session, user id
  recorded) · WORKER (login role in `lfhe_worker`, not superuser) · SYSTEM
  (owner / operator / migrations).
- **Tamper evidence, not tamper-proofing:** an owner/superuser can disable
  triggers. `verify_chain()` detects any rewrite; `export_chain_head()`
  appends verified heads to an external write-once location so later rewrites
  are provable. This is stated as a limitation, per G-14.
- Seed data inserted by migrations *before* the audit triggers existed
  (role / permission matrix) is version-controlled in the migration files
  instead of the audit log.

## Mandatory audited transitions — Phase 1

| Event | Trigger point |
| --- | --- |
| `DEPLOYMENT_ENVIRONMENT_SET` | insert into `deployment_environment` |
| `USER_ROLE_CHANGED` | insert / delete on `user_roles` (metadata.operation GRANT / REVOKE) |
| `PERMISSION_CHANGED` | any change to `role_permissions` |
| `SOURCE_CREATED` / `SOURCE_UPDATED` | `sources` insert / metadata update |
| `SOURCE_ACTIVATED` / `SOURCE_DEACTIVATED` | `sources.active` change |
| `SOURCE_COLLECTION_METHOD_APPROVED` / `_REVOKED` | `sources.collection_method_approved` change |
| `ARTICLE_CREATED` | insert into `articles` |
| `ARTICLE_SNAPSHOT_CREATED` | insert into `article_snapshots` |
| `TEXT_REPRESENTATION_CREATED` | insert into `text_representations` |
| `PROMPT_VERSION_CREATED` | insert into `prompt_versions` |
| `PROMPT_VERSION_ACTIVATED` / `PROMPT_VERSION_DEACTIVATED` | insert into `prompt_activations` |

Later phases attach triggers for the remaining catalogue entries (Prompt Pack
v1.2 §55, v1.2.1 §10) as their tables are introduced. Collection runs, jobs,
system errors and model runs are themselves operational records and are not
duplicated into the audit log.

## Operations
```bash
python scripts/audit_tool.py verify  <owner-url>
python scripts/audit_tool.py export  <owner-url> <heads.jsonl>
```
