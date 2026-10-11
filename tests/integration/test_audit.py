"""P1-05 — append-only, tamper-evident audit chain (F7, G-14, PO guardrail 1)."""
import json
import threading

import psycopg
import pytest

from conftest import create_database, new_user
from lfhe_shared.audit import export_chain_head, verify_against_exported_head, verify_chain

pytestmark = pytest.mark.db

Denied = psycopg.errors.InsufficientPrivilege


def test_role_grant_is_audited_with_human_actor(pg, make_user):
    admin = make_user("ADMIN")
    target = new_user(pg)
    with pg.as_user(admin) as c:
        c.execute("SELECT lfhe.grant_user_role(%s, 'VIEWER')", (target,))
    with pg.admin() as c:
        row = c.execute(
            "SELECT * FROM lfhe.audit_log WHERE event_type='USER_ROLE_CHANGED' AND object_id=%s",
            (f"{target}:VIEWER",)).fetchone()
    assert row["actor_type"] == "HUMAN"
    assert row["actor_user_id"] == admin
    assert row["metadata"] == {"operation": "GRANT"}
    assert row["new_state"]["role_code"] == "VIEWER"


def test_deployment_environment_set_was_audited(pg):
    with pg.admin() as c:
        row = c.execute("SELECT actor_type FROM lfhe.audit_log WHERE event_type='DEPLOYMENT_ENVIRONMENT_SET'").fetchone()
    assert row["actor_type"] == "SYSTEM"


def test_audit_log_is_append_only_for_every_role(pg, make_user):
    auditor = make_user("ADMIN")
    with pg.as_user(auditor) as c:
        assert c.execute("SELECT count(*) AS n FROM lfhe.audit_log").fetchone()["n"] > 0
        for stmt in ("UPDATE lfhe.audit_log SET object_id='x'", "DELETE FROM lfhe.audit_log",
                     "INSERT INTO lfhe.audit_log (seq) VALUES (999999)"):
            with pytest.raises(Denied):
                c.execute(stmt)
    with pg.worker() as c:
        for stmt in ("SELECT * FROM lfhe.audit_log", "DELETE FROM lfhe.audit_log",
                     "SELECT lfhe.write_audit('SOURCE_CREATED','x','1',NULL,NULL)"):
            with pytest.raises(Denied):
                c.execute(stmt)
    with pg.as_service_role() as c:
        with pytest.raises(Denied):
            c.execute("SELECT lfhe.write_audit('SOURCE_CREATED','x','1',NULL,NULL)")
    # Even the owner is blocked by the immutability triggers.
    with pg.admin() as c:
        with pytest.raises(Denied, match="append-only"):
            c.execute("UPDATE lfhe.audit_log SET object_id='x' WHERE seq=1")
        with pytest.raises(Denied, match="append-only"):
            c.execute("DELETE FROM lfhe.audit_log WHERE seq=1")
        with pytest.raises(Denied, match="append-only"):
            c.execute("TRUNCATE lfhe.audit_log")


def test_viewer_without_audit_read_sees_nothing(pg, make_user):
    viewer = make_user("VIEWER")
    with pg.as_user(viewer) as c:
        assert c.execute("SELECT count(*) AS n FROM lfhe.audit_log").fetchone()["n"] == 0


def test_concurrent_audited_operations_produce_one_verifiable_chain(pg, make_user):
    """PO guardrail 1: simultaneous audited operations → one gap-free chain."""
    threads_n, per_thread = 8, 12
    admins = [make_user("ADMIN") for _ in range(threads_n)]
    targets = [[new_user(pg) for _ in range(per_thread)] for _ in range(threads_n)]
    with pg.admin() as c:
        before = c.execute("SELECT coalesce(max(seq),0) AS s FROM lfhe.audit_log").fetchone()["s"]

    barrier = threading.Barrier(threads_n)
    errors: list[BaseException] = []

    def worker(i: int):
        try:
            with pg.as_user(admins[i]) as c:
                barrier.wait()
                for t in targets[i]:
                    c.execute("SELECT lfhe.grant_user_role(%s, 'VIEWER')", (t,))
        except BaseException as exc:  # surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(threads_n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert errors == []

    with pg.admin() as c:
        rows = c.execute("SELECT seq, previous_entry_hash, entry_hash FROM lfhe.audit_log "
                         "WHERE seq > %s ORDER BY seq", (before,)).fetchall()
        assert len(rows) == threads_n * per_thread
        assert [r["seq"] for r in rows] == list(range(before + 1, before + 1 + len(rows)))
        # each entry links to exactly its predecessor; no forks
        prev = c.execute("SELECT entry_hash FROM lfhe.audit_log WHERE seq=%s", (before,)).fetchone()
        prev_hash = prev["entry_hash"] if prev else "0" * 64
        for r in rows:
            assert r["previous_entry_hash"] == prev_hash
            prev_hash = r["entry_hash"]
        dup = c.execute("SELECT previous_entry_hash, count(*) FROM lfhe.audit_log "
                        "GROUP BY 1 HAVING count(*) > 1").fetchall()
        assert dup == [], "forked chain: two entries share a predecessor"
        result = verify_chain(c)
    assert result.ok, result
    assert result.entries_checked >= threads_n * per_thread


def test_independent_verifier_detects_owner_tampering(pg_cluster_raw, tmp_path):
    """Tamper-evidence: an owner who disables triggers and edits history is detected."""
    cluster, _, _ = pg_cluster_raw
    create_database(cluster, "lfhe_tamper")
    url = cluster.url("postgres", "lfhe_tamper")
    with psycopg.connect(url, autocommit=True) as c:
        uid = new_user_in(c)
        for role in ("VIEWER", "ANALYST", "REVIEWER"):
            c.execute("SELECT lfhe.bootstrap_grant_role(%s, %s)", (uid, role))
        heads = tmp_path / "audit_heads.jsonl"
        head = export_chain_head(c, heads)
        assert head["head_seq"] >= 4 and head["environment"] == "TEST"
        assert verify_against_exported_head(c, json.loads(heads.read_text().splitlines()[-1])).ok

        c.execute("ALTER TABLE lfhe.audit_log DISABLE TRIGGER audit_log_no_update_delete")
        c.execute("UPDATE lfhe.audit_log SET object_id = 'forged' WHERE seq = 2")
        c.execute("ALTER TABLE lfhe.audit_log ENABLE TRIGGER audit_log_no_update_delete")

        broken = verify_chain(c)
        assert not broken.ok and broken.first_bad_seq == 2
        with pytest.raises(RuntimeError, match="broken at seq 2"):
            export_chain_head(c, heads)
    with psycopg.connect(cluster.url("postgres", "postgres"), autocommit=True) as c:
        c.execute('DROP DATABASE "lfhe_tamper" WITH (FORCE)')


def new_user_in(conn) -> str:
    import uuid
    uid = uuid.uuid4()
    conn.execute("INSERT INTO auth.users (id, email) VALUES (%s, %s)", (uid, f"{uid.hex[:8]}@t.invalid"))
    return uid
