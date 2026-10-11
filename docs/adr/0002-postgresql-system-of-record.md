# ADR-0002 — PostgreSQL as the structured system of record

**Status:** Accepted

## Decision
PostgreSQL holds every analytical object as structured, typed rows. Vector
similarity (later) is a retrieval aid only, never evidence (DS §5).

## Consequences
- All application objects live in the dedicated `lfhe` schema.
- Version, approval and audit tables are append-only; immutability is enforced
  by triggers and by revoking UPDATE / DELETE / TRUNCATE, not by convention.
- Schema changes only through versioned migrations in `database/migrations`.
