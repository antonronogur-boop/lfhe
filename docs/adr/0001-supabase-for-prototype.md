# ADR-0001 — Supabase as the prototype platform

**Status:** Accepted (Control Gate 0, 2026-10-11)

## Decision
Use Supabase (managed PostgreSQL, Auth, Storage) for the DEV / TEST / PROD
prototype, one Supabase project per environment.

## Consequences
- Analytical invariants are implemented in **plain PostgreSQL** (tables,
  constraints, triggers, SECURITY DEFINER functions, RLS) so they remain portable
  if the organisation later moves to self-hosted PostgreSQL.
- Supabase-specific objects (`auth` schema, `auth.uid()`, `anon` /
  `authenticated` / `service_role`) are consumed but never re-implemented in
  migrations. Local tests use a minimal shim (`tests/fixtures/supabase_shim.sql`).
- The `service_role` key bypasses RLS. It is therefore **not** used by workers
  (see ADR-0005) and is explicitly denied EXECUTE on human-authority functions.
- PostgREST must expose the `lfhe` schema (Supabase dashboard → API settings)
  for the web app's RPC calls.
