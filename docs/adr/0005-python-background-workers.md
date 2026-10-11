# ADR-0005 — Python background workers with a restricted database role

**Status:** Accepted

## Decision
Collection and (later) AI processing run as Python workers in a container
runtime suited to long-running jobs (not serverless frontend functions).
Phase 1 runs them locally; the hosting provider decision (K-01) is taken
before first deployment.

Workers connect **directly to PostgreSQL** with a login role that is a member
of `lfhe_worker`. That role:
- may INSERT/UPDATE only operational tables (collection runs, jobs, articles,
  snapshots, model runs) through explicit grants;
- has **no** EXECUTE on human-authority functions and no write access to
  sources, roles, approvals or the audit table;
- is additionally rejected inside every human-authority function by an
  explicit role-membership check (defence in depth).

Jobs use a PostgreSQL table queue (`processing_jobs`) with idempotency keys,
`FOR UPDATE SKIP LOCKED`, exponential backoff and a maximum attempt count.
A single scheduling layer enqueues jobs (`lfhe.enqueue_due_collections()`,
invoked by pg_cron in Supabase).
