# Runbook — DEV / TEST / PROD separation

## Principles
- One Supabase project **per environment** (separate database, storage,
  auth users and keys). No shared credentials across environments.
- GS-001 and all gold-standard runs execute only in **TEST**.
- Prompt activation is recorded per environment (`lfhe.prompt_activations`);
  an activation in DEV never affects TEST or PROD.

## Two independent guards
1. **Static guard** (`lfhe_shared.config`): startup fails if `LFHE_ENV` is
   missing/unknown, if a non-PROD config points at a URL containing `prod`, if
   PROD uses LOCAL storage or a DEV/TEST-looking database, or if an S3 bucket
   name lacks the environment tag.
2. **Database guard** (`lfhe_shared.db.connect`): each database records its own
   environment in `lfhe.deployment_environment` (set once by the operator
   with the owner role, see below). Workers refuse to run if it differs from
   `LFHE_ENV`.

## Provisioning a new environment (operator, owner role)
```sql
-- after migrations:
SELECT lfhe.set_deployment_environment('TEST');   -- one-time; cannot be changed afterwards
CREATE ROLE lfhe_worker_login LOGIN PASSWORD '<from secret manager>' IN ROLE lfhe_worker;
SELECT lfhe.bootstrap_admin('<auth.users uuid of the first administrator>');
```
Passwords and keys are generated in and stored by the platform secret manager.
They are never written to this repository.

## Supabase settings checklist
- API → exposed schemas: add `lfhe`.
- Do not give the web app the `service_role` key; it uses the anon key plus the
  signed-in user's session.
- pg_cron: schedule `SELECT lfhe.enqueue_due_collections();` (e.g. every 5 min).
- Point-in-time recovery / backups enabled; restore tested before PROD use.
