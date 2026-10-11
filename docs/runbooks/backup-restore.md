# Backup and restore

The PostgreSQL database is the system of record (ADR-0002). Raw snapshot bytes
live in the write-once object store, addressed by SHA-256.

## Backup
1. Supabase managed backups / PITR are enabled for PROD (platform setting).
2. Logical backup (also used by the round-trip test):
   `pg_dump -Fc -d <db> -f lfhe-<env>-<date>.dump` with an operator role.
3. Export the verified audit chain head next to the backup:
   `python scripts/audit_tool.py export <url> audit-heads.jsonl`
   (refuses to export a broken chain).
4. Object store: bucket versioning / replication per provider; objects are
   never overwritten (`put_if_absent`).

## Restore
1. Create an empty database in the **same environment** (never restore PROD
   data into DEV/TEST); roles `lfhe_worker`, `lfhe_registrar`, `lfhe_evaluator`
   and the Supabase roles must exist.
2. `pg_restore --exit-on-error -d <new db> lfhe-<env>-<date>.dump`
3. `python scripts/audit_tool.py verify <url>` — the chain must verify and its
   head must match (or extend) the exported head for that backup.
4. Spot-check `lfhe.deployment_environment` and `public.lfhe_schema_migrations`.

`tests/integration/test_backup_restore.py` performs steps 2–4 automatically:
identical audit head, identical row counts, immutability triggers present,
original-language text intact.

There are no down-migrations: a faulty migration is corrected by a new
fix-forward migration; data recovery uses the backups above.
