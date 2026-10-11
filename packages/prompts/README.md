# Prompt artifacts

`packages/prompts/<MODULE>/<semver>/` holds one immutable prompt bundle
(`manifest.json`, `system.md`, `task.md`, `output_schema.json`).
Released bundles are never edited in place: any change needs a new semver.
`prompt-lock.json` records each bundle's content hash; CI fails if a locked
bundle changes or disappears. See `docs/prompt-versioning.md`.

Phase 1 contains no M02–M10 prompts (they are Phase 2+ work).
