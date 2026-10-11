# ADR-0003 — Canonical report JSON (decided now, implemented in Phase 5)

**Status:** Accepted (implementation deferred to Phase 5)

## Decision
The canonical report representation is structured JSON serialised with
RFC 8785 (JCS) and hashed with SHA-256. Any change to the canonical JSON creates
a new report version and hash and invalidates QA (Prompt Pack v1.2.1 §8).
PDF/HTML are deterministic renderings; template and renderer versions plus the
PDF hash will be recorded in the release manifest.

## Phase 1 consequence
None beyond the shared hashing helper (`lfhe_shared.hashing`), which already
uses SHA-256 over canonical serialisations for prompt artifacts and audit
entries.
