# Changelog

All material project changes are recorded here.

## [Unreleased] — Phase 1 Foundation

### Added
- P1-01 Repository skeleton, CI workflow (gitleaks + repository secret scan +
  tests), SPEC_INDEX, PROJECT_STATUS, ADRs 0001–0007.
- P1-02 Environment separation: static settings rules + database-recorded
  deployment environment checked at connect time.
- P1-03 Database foundation: `lfhe` schema, canonical enums, migration runner
  with checksums.
- P1-04 Authentication and RBAC: roles/permissions, HUMAN_ONLY SECURITY DEFINER
  functions with negative tests (guardrail 2).
- P1-05 Audit foundation: serialised SHA-256 hash chain, concurrency proof,
  independent verifier, chain-head export (guardrail 1).
- P1-06 Source registry (DB + web UI): approval and activation workflow.
- P1-07 Jobs: idempotent table queue, leases, backoff, scheduler entry point.
- P1-08 Collection framework: polite HTTP client, RSS/Atom, sitemap, official
  API and HTTP-fetch adapters, collection runs and error logging.
- P1-09 Articles, versioned immutable original-language snapshots, canonical
  clean text (`lfhe-clean-text` 1.0.0), write-once object store, span primitives.
- P1-10 Prompt-version source of truth and model-run traceability (guardrail 3),
  canonical JSON, prompt registry tooling, FakeProvider runner.
- P1-11 F1–F10 acceptance suite, backup/restore round-trip test, documentation.
