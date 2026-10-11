# Prompt versions and model runs — source of truth (PO guardrail 3)

## Roles of Git and the database

| Concern | Authority | Mechanism |
| --- | --- | --- |
| Authoring, review, history of prompt text | **Git** | `packages/prompts/<MODULE>/<semver>/` bundles, reviewed by PR |
| "This semver never changes after release" | **Git CI** | `packages/prompts/prompt-lock.json` + `scripts/prompt_registry.py check-lock` (fails if a locked bundle is edited or deleted) |
| Exact content that was registered and can run | **Database** | `lfhe.prompt_versions`: full file contents + DB-computed `content_hash`; immutable |
| Which version is active in an environment | **Database** | `lfhe.prompt_activations` append-only log; human-only, audited |
| What a model call actually used | **Database** | `lfhe.model_runs` with composite FKs to the registered prompt and model configuration |

The database never trusts a hash supplied by a client: `content_hash` is
computed by `lfhe.prompt_bundle_sha256()` and enforced by a CHECK constraint.
`lfhe_shared.prompts.bundle_sha256()` is an independent re-implementation;
registration fails (`PROMPT_HASH_MISMATCH`) if the two disagree.

## Bundle format

```
packages/prompts/M04/1.0.0/
  manifest.json       {"format": "lfhe-prompt-manifest/1", "module_code": "M04",
                       "semver": "1.0.0", "module_version": "<spec module version>",
                       "test_fixture": false, "description": "..."}
  system.md
  task.md
  output_schema.json  JSON Schema draft 2020-12 (checked at load time)
```
Files must be UTF-8, NFC, regular files with names `[a-z0-9][a-z0-9_.-]*`.
Hash `lfhe-prompt-bundle/1`:
`sha256("lfhe-prompt-bundle/1\n<module>\n<semver>" + "\n<name> <sha256(file)>"…)`
with files sorted bytewise by name.

## Invariants (enforced in the database)

1. `prompt_versions` rows are immutable (UPDATE/DELETE blocked for every role, including the owner).
2. `UNIQUE (module_code, semver)`; re-registering identical content is idempotent,
   different content → `PROMPT_VERSION_CONFLICT`. **One immutable record can never refer to different content.**
3. `content_hash = prompt_bundle_sha256(module, semver, files)` (CHECK).
4. The manifest inside the stored files must agree with the row's module, semver, module version and fixture flag.
5. Activation (`lfhe.activate_prompt_version`, `lfhe.deactivate_prompt_module`) is HUMAN_ONLY, needs
   `PROMPT_ACTIVATE` and a reason, is appended to `prompt_activations` and audited
   (`PROMPT_VERSION_ACTIVATED` / `PROMPT_VERSION_DEACTIVATED`). The active version is derived from the
   latest log entry per module (no mutable flag).
6. In PROD, activation is refused for test fixtures and for bundles not registered from a clean, committed Git tree.
7. `lfhe.start_model_run` accepts only the currently active version of the module, and copies
   `prompt_semver`, `prompt_content_hash`, `module_version`, provider, model and `model_config_hash` from the
   registries; composite foreign keys make any disagreement impossible.
8. Terminal model runs are immutable; raw output is stored with its SHA-256; `SCHEMA_VALIDATION_FAILED` and
   `PROVIDER_ERROR` are recorded, never silently repaired.
9. Model configurations are immutable; `config_hash` is a generated column
   (`sha256("lfhe-model-config/1\n<provider>\n<model>\n<settings::jsonb::text>")`); credential-like keys are rejected.

## Release / sync procedure

1. Author a **new** semver directory (never edit a released one); open a PR.
2. `python3 scripts/prompt_registry.py lock` updates `prompt-lock.json`; CI runs `check-lock` and the tests.
3. After merge, the deployment pipeline (login role in `lfhe_registrar`, connection string in
   `LFHE_REGISTRAR_DATABASE_URL` from the secret manager) runs
   `python3 scripts/prompt_registry.py register packages/prompts/<MODULE>/<semver>`
   from the merged commit. The commit SHA and tree cleanliness are recorded.
4. A human with `PROMPT_ACTIVATE` activates the version (with a reason) per environment.
5. `python3 scripts/prompt_registry.py verify` (scheduled / before releases) re-hashes every registered
   version against Git and reports drift or missing artifacts.

## Phase 1 scope

No M02–M10 prompts exist yet. The test-suite uses the synthetic fixture
`tests/fixtures/prompts/T00_ECHO` (manifest `test_fixture: true`, refused in PROD)
and the `FakeProvider`. Real provider adapters, prompt envelopes with
untrusted-content delimiting and per-module model selection are Phase 2.
