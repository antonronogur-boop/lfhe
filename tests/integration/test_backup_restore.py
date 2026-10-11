"""P1-11 — backup / restore round-trip (Handoff: restorability of the system of record).

pg_dump (custom format) of the live test database → pg_restore into a fresh
database → the audit chain verifies with the same head, record counts match,
and immutability / RBAC triggers and policies are present in the restore.
"""
import subprocess

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import _pg_bin, make_collectable_source
from lfhe_collector.collector import collect_source
from lfhe_collector.snapshots import DatabaseSnapshotSink
from lfhe_shared.audit import verify_chain
from lfhe_shared.storage import LocalObjectStore

pytestmark = pytest.mark.db
TABLES = ("sources", "articles", "article_snapshots", "text_representations", "collection_runs",
          "audit_log", "user_roles", "prompt_versions", "prompt_activations", "model_runs")


def counts(conn):
    return {t: conn.execute(f"SELECT count(*) AS n FROM lfhe.{t}").fetchone()["n"] for t in TABLES}


def test_backup_restore_round_trip(pg, site, http_client, tmp_path):
    src = make_collectable_source(pg, "HTTP_FETCH", {"urls": [site.url("/news/navchannia-uk.html")]}, language="uk")
    with pg.worker() as c:
        collect_source(c, src, http_client, DatabaseSnapshotSink(c, LocalObjectStore(tmp_path / "o")),
                       worker_id="backup-test")
    dump = tmp_path / "lfhe.dump"
    base = ["-h", "127.0.0.1", "-p", str(pg.port), "-U", "postgres"]
    subprocess.run([_pg_bin("pg_dump"), *base, "-d", pg.dbname, "-Fc", "-f", str(dump)], check=True,
                   capture_output=True)
    with psycopg.connect(pg.url("postgres", "postgres"), autocommit=True) as c:
        c.execute('DROP DATABASE IF EXISTS "lfhe_restore" WITH (FORCE)')
        c.execute('CREATE DATABASE "lfhe_restore"')
    restore = subprocess.run([_pg_bin("pg_restore"), *base, "-d", "lfhe_restore", "--exit-on-error", str(dump)],
                             capture_output=True, text=True)
    assert restore.returncode == 0, restore.stderr

    with pg.admin() as live, psycopg.connect(pg.url("postgres", "lfhe_restore"), autocommit=True,
                                             row_factory=dict_row) as restored:
        live_chain, restored_chain = verify_chain(live), verify_chain(restored)
        assert live_chain.ok and restored_chain.ok
        assert (restored_chain.head_seq, restored_chain.head_hash) == (live_chain.head_seq, live_chain.head_hash)
        assert counts(restored) == counts(live)
        assert restored.execute("SELECT environment FROM lfhe.deployment_environment").fetchone()["environment"] == "TEST"
        assert restored.execute("SELECT count(*) AS n FROM public.lfhe_schema_migrations").fetchone()["n"] == \
            live.execute("SELECT count(*) AS n FROM public.lfhe_schema_migrations").fetchone()["n"]
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="append-only"):
            restored.execute("DELETE FROM lfhe.text_representations")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            restored.execute("UPDATE lfhe.audit_log SET event_type = event_type")
        text = restored.execute("SELECT t.text_content FROM lfhe.text_representations t JOIN lfhe.article_snapshots s "
                                "ON s.id=t.snapshot_id JOIN lfhe.articles a ON a.id=s.article_id WHERE a.source_id=%s",
                                (src["id"],)).fetchone()["text_content"]
        assert "заявили" in text
