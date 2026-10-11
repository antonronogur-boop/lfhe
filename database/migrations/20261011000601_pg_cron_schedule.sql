-- ============================================================================
-- P1-07/P1-08  pg_cron schedule (Supabase only)
--
-- pg_cron must be enabled by the operator in the Supabase dashboard; this
-- migration never creates the extension. Where pg_cron is absent (plain
-- PostgreSQL, local tests) it is a no-op, and a worker-side scheduler calls
-- lfhe.enqueue_due_collections() instead. Exactly one scheduling layer is
-- active per environment.
-- ============================================================================
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
    PERFORM cron.schedule('lfhe-enqueue-due-collections', '*/5 * * * *',
                          'SELECT lfhe.enqueue_due_collections()');
  ELSE
    RAISE NOTICE 'pg_cron not installed: schedule lfhe.enqueue_due_collections() from the worker scheduler';
  END IF;
END $$;
