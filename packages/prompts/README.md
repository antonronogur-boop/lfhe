# Prompt artifacts

`packages/prompts/<MODULE>/<semver>/` holds one immutable prompt bundle
(`manifest.json`, `system.md`, `task.md`, `output_schema.json`).
Released bundles are never edited in place: any change needs a new semver.
`prompt-lock.json` records each bundle's content hash; CI fails if a locked
bundle changes or disappears. See `docs/prompt-versioning.md`.

Phase 2 adds `M02_CLAIM_EXTRACTOR/1.0.0` and `M03_CLASSIFIER/1.0.0` (module version
`MPP-1.2.2+P2-ADDENDUM-1.0`). Their `output_schema.json` enums are tested against the
database vocabularies and the closed taxonomy (`tests/integration/test_claim_prompts.py`).
M04–M10 prompts are later-phase work.
