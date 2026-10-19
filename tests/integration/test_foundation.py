"""P1-03 — database foundation."""
import shutil

import psycopg
import pytest

from apply_migrations import DEFAULT_DIR, MigrationError, apply_all, migration_files
from lfhe_shared.config import load_settings
from lfhe_shared.db import EnvironmentMismatch, connect

pytestmark = pytest.mark.db


def _enum(conn, name):
    return [r["v"] for r in conn.execute(
        "SELECT e.enumlabel AS v FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
        "JOIN pg_namespace n ON n.oid = t.typnamespace WHERE n.nspname='lfhe' AND t.typname=%s "
        "ORDER BY e.enumsortorder", (name,))]


def test_all_migrations_applied_and_tracked(pg):
    with pg.admin() as c:
        tracked = [r["filename"] for r in c.execute(
            "SELECT filename FROM public.lfhe_schema_migrations ORDER BY filename")]
    assert tracked == [p.name for p in migration_files()]


def test_canonical_decision_enums_match_addendum_a3(pg):
    with pg.admin() as c:
        assert _enum(c, "review_decision") == [
            "APPROVE", "MODIFY_AND_APPROVE", "REJECT", "ESCALATE", "REQUEST_REPROCESSING"]
        assert _enum(c, "event_action") == [
            "CREATE", "UPDATE", "MERGE", "SPLIT", "KEEP_SEPARATE", "SUPERSEDE", "REJECT"]
        assert _enum(c, "release_decision") == [
            "APPROVE_FOR_RELEASE", "RETURN_FOR_REVISION", "REJECT_RELEASE"]
        assert _enum(c, "security_review_status") == [
            "PENDING", "APPROVED", "RETURN_FOR_REVISION", "REJECTED"]
        assert _enum(c, "report_mode") == ["LIVE", "REPLAY"]
        basis = _enum(c, "public_availability_basis")
        for required in ("SOURCE_PUBLISHED_TIMESTAMP", "RSS_TIMESTAMP", "SITEMAP_TIMESTAMP",
                         "HTTP_METADATA", "ARCHIVED_SNAPSHOT", "MANUAL_VERIFICATION", "UNKNOWN",
                         "ARCHIVED_SNAPSHOT_VERIFIED", "CURRENT_PAGE_ONLY"):
            assert required in basis


def test_final_analytic_confidence_has_exactly_one_canonical_owner(pg):
    """PROJECT_STATUS DC-01 / PO guardrail 4: no competing final-confidence store. Phases 1–3
    had none; Phase 4 (§13) adds exactly one owner — the immutable human approval row
    lfhe.analytical_approvals — plus its read-only projection in the security-invoker view
    assessment_version_states. No column may be named plain 'confidence'."""
    with pg.admin() as c:
        cols = c.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema='lfhe' AND column_name ILIKE '%%confidence%%'").fetchall()
        views = {r["table_name"] for r in c.execute(
            "SELECT table_name FROM information_schema.views WHERE table_schema='lfhe'")}
    offending = [r for r in cols if "analytic" in r["column_name"] or r["column_name"] == "confidence"]
    owners = sorted((r["table_name"], r["column_name"]) for r in offending if r["table_name"] not in views)
    assert owners == [("analytical_approvals", "final_analytic_confidence")]
    assert {r["table_name"] for r in offending} - {"analytical_approvals"} <= {"assessment_version_states"}


def test_audit_catalogue_contains_spec_events(pg):
    with pg.admin() as c:
        codes = {r["code"] for r in c.execute("SELECT code FROM lfhe.audit_event_types")}
    for code in ("SOURCE_CREATED", "SOURCE_ACTIVATED", "ARTICLE_SNAPSHOT_CREATED",
                 "PROMPT_VERSION_ACTIVATED", "USER_ROLE_CHANGED", "REVIEW_ESCALATED",
                 "REPORT_RELEASE_MANIFEST_CREATED", "QA_INVALIDATED_BY_REPORT_CHANGE"):
        assert code in codes


def test_anon_has_no_access_to_lfhe_schema(pg):
    with pg.as_anon() as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("SELECT * FROM lfhe.deployment_environment")


def test_deployment_environment_is_set_once_and_immutable(pg):
    with pg.admin() as c:
        with pytest.raises(psycopg.Error):
            c.execute("SELECT lfhe.set_deployment_environment('PROD')")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("UPDATE lfhe.deployment_environment SET environment='PROD'")
        assert c.execute("SELECT environment FROM lfhe.deployment_environment").fetchone()["environment"] == "TEST"


def test_worker_cannot_set_deployment_environment(pg):
    with pg.worker() as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("SELECT lfhe.set_deployment_environment('DEV')")


def test_connect_enforces_environment_match(pg):
    ok = load_settings(env="TEST", database_url=pg.worker_url)
    with connect(ok) as conn:
        assert conn.execute("SELECT 1 AS one").fetchone()["one"] == 1
    wrong = load_settings(env="DEV", database_url=pg.worker_url)
    with pytest.raises(EnvironmentMismatch):
        connect(wrong)


def test_failed_migration_rolls_back_and_modified_migration_refused(pg, tmp_path):
    from conftest import SHIM
    with psycopg.connect(pg.url("postgres", "postgres"), autocommit=True) as c:
        c.execute('DROP DATABASE IF EXISTS "lfhe_migtest" WITH (FORCE)')
        c.execute('CREATE DATABASE "lfhe_migtest"')
    url = pg.url("postgres", "lfhe_migtest")
    with psycopg.connect(url, autocommit=True) as c:
        c.execute(SHIM.read_text())
    mig = tmp_path / "migs"
    shutil.copytree(DEFAULT_DIR, mig)
    bad = mig / "99999999999999_broken.sql"
    bad.write_text("CREATE TABLE lfhe.half_done (id int);\nSELECT * FROM does_not_exist;\n")
    with pytest.raises(MigrationError, match="rolled back"):
        apply_all(url, mig)
    with psycopg.connect(url) as c:
        assert c.execute("SELECT to_regclass('lfhe.half_done')").fetchone()[0] is None
    bad.unlink()
    apply_all(url, mig)
    first = sorted(mig.glob("*.sql"))[0]
    first.write_text(first.read_text() + "\n-- tampered\n")
    with pytest.raises(MigrationError, match="modified"):
        apply_all(url, mig)
    with psycopg.connect(pg.url("postgres", "postgres"), autocommit=True) as c:
        c.execute('DROP DATABASE "lfhe_migtest" WITH (FORCE)')
