"""PO guardrail 2 — SECURITY DEFINER hardening, verified from the catalogue.

Runs against every function in the lfhe schema, so functions added in later
steps/phases are covered automatically.
"""
import pytest

pytestmark = pytest.mark.db

APP_ROLES = ("anon", "authenticated", "service_role", "lfhe_worker", "lfhe_evaluator", "lfhe_registrar")
OWNER_ONLY = {"set_deployment_environment", "bootstrap_grant_role"}


def _functions(conn):
    return conn.execute(
        """
        SELECT p.oid, p.proname, p.prosecdef,
               coalesce(array_to_string(p.proconfig, ','), '') AS config,
               obj_description(p.oid, 'pg_proc') AS comment,
               pg_get_function_identity_arguments(p.oid) AS args
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'lfhe'
        """
    ).fetchall()


def _can_execute(conn, role, oid):
    return conn.execute("SELECT has_function_privilege(%s, %s, 'EXECUTE') AS ok",
                        (role, oid)).fetchone()["ok"]


def test_every_security_definer_function_pins_search_path(pg):
    with pg.admin() as c:
        bad = [f["proname"] for f in _functions(c)
               if f["prosecdef"] and "search_path=pg_catalog, pg_temp" not in f["config"]]
    assert bad == [], f"SECURITY DEFINER without pinned search_path: {bad}"


def test_no_lfhe_function_is_executable_by_public(pg):
    with pg.admin() as c:
        leaked = [
            f["proname"] for f in _functions(c)
            if c.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_proc p, aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a "
                "WHERE p.oid = %s AND a.grantee = 0 AND a.privilege_type = 'EXECUTE') AS pub",
                (f["oid"],)).fetchone()["pub"]
        ]
    assert leaked == [], f"functions executable by PUBLIC: {leaked}"


def test_human_only_functions_are_closed_to_non_human_roles(pg):
    with pg.admin() as c:
        human_only = [f for f in _functions(c) if (f["comment"] or "") == "HUMAN_ONLY"]
        assert human_only, "expected at least one HUMAN_ONLY function"
        problems = []
        for f in human_only:
            if not f["prosecdef"]:
                problems.append(f"{f['proname']}: not SECURITY DEFINER")
            for role in ("anon", "service_role", "lfhe_worker", "lfhe_evaluator", "lfhe_registrar"):
                if _can_execute(c, role, f["oid"]):
                    problems.append(f"{f['proname']}: executable by {role}")
            if not _can_execute(c, "authenticated", f["oid"]):
                problems.append(f"{f['proname']}: not executable by authenticated")
    assert problems == []


def test_owner_only_functions_are_closed_to_every_application_role(pg):
    with pg.admin() as c:
        problems = [
            f"{f['proname']}: executable by {role}"
            for f in _functions(c) if f["proname"] in OWNER_ONLY
            for role in APP_ROLES if _can_execute(c, role, f["oid"])
        ]
    assert problems == []
