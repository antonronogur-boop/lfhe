# LFHÉ — Légierő Felderítő Heti Értékelés

**English working name:** Air Domain Weekly Assessment (ADWA)

An AI-assisted, human-governed, source-traceable OSINT intelligence-processing
system. The weekly two-page report is only its output; the product is the
system.

> AI PROCESSES. HUMAN JUDGES. HUMAN RELEASES.

## Status

See [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md). Active authoritative
specifications are listed in [`docs/SPEC_INDEX.md`](docs/SPEC_INDEX.md).

Current phase: **Phase 1 — Foundation** (no analytical AI pipeline yet).

## Repository layout (Phase 1)

| Path | Purpose |
| --- | --- |
| `apps/web` | Next.js analyst workspace (Phase 1: source administration only) |
| `services/shared` | Python: configuration, DB access, jobs, audit verification, object storage |
| `services/collector` | Python: collection adapters, snapshot storage, deterministic text extraction |
| `services/ai-orchestrator` | Python: provider abstraction, prompt registration, model-run records (no LLM modules yet) |
| `packages/prompts` | Version-controlled prompt artifacts + lock file (no modules until Phase 2) |
| `database/migrations` | Versioned SQL migrations (Supabase CLI compatible) |
| `tests/` | Unit, integration, security and F1–F10 acceptance tests (real PostgreSQL) |
| `docs/` | Spec index, project status, ADRs, runbooks |

## Running the tests locally

Requirements: Python ≥ 3.11, PostgreSQL 16 binaries (`initdb`, `pg_ctl`) on
the machine. The test harness starts a throw-away PostgreSQL cluster, applies a
minimal **local-only Supabase shim** (`tests/fixtures/supabase_shim.sql`) and
then the real migrations.

```bash
pip install -e ".[test]"
python3 scripts/prompt_registry.py check-lock
pytest -W error::DeprecationWarning
```

Operational docs: `docs/runbooks/environments.md`, `docs/runbooks/backup-restore.md`,
`docs/prompt-versioning.md`, `docs/audit-catalogue.md`, `docs/permission-matrix.md`.

The shim emulates only what Supabase provides in production (`auth` schema,
`auth.uid()`, the `anon` / `authenticated` / `service_role` roles). It is never
applied to a real Supabase project.

## Security

- OSINT only. No classified, protected or non-public material.
- Never commit secrets. `.env*` files are git-ignored; `scripts/secret_scan.py`
  runs in tests and CI (CI also runs gitleaks).
- Human-authority state transitions are enforced in the database, not only in
  the UI.
