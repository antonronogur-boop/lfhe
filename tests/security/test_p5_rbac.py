"""Phase 5 Addendum §25 / required test 67: every Phase 5 HUMAN_ONLY function rejects worker,
service_role, anon, VIEWER, ADMIN, REVIEWER, SECURITY_REVIEWER, RELEASE_AUTHORITY and a user without
roles (no REPORT_EDIT). Dummy arguments are well-formed, so a rejection can only come from the
permission gate (or grants), never from argument parsing."""
import psycopg
import pytest

pytestmark = pytest.mark.db
U = "00000000-0000-4000-8000-0000000000bb"
H = "0" * 64
P5_HUMAN_ONLY = {
    "create_report": "'{}'::jsonb, 'x reason'",
    "refresh_report_candidates": f"'{U}'::uuid",
    "decide_report_candidate": f"'{U}'::uuid, '{H}', 'INCLUDE', 'KEY_JUDGMENT', 1, NULL, 'x reason'",
    "freeze_report_selection": f"'{U}'::uuid, 'x reason'",
    "edit_report_version": f"'{U}'::uuid, '{H}', '{{}}'::jsonb, 'x reason'",
    "decide_report_removals": f"'{U}'::uuid, '{H}', '[]'::jsonb, 'x reason'",
}
DENIED_ROLES = ("VIEWER", "ADMIN", "REVIEWER", "SECURITY_REVIEWER", "RELEASE_AUTHORITY")


def test_phase5_human_only_inventory_is_complete(pg):
    with pg.admin() as c:
        rows = {r["proname"] for r in c.execute(
            "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            "WHERE n.nspname='lfhe' AND obj_description(p.oid,'pg_proc')='HUMAN_ONLY'")}
        worker_fns = {r["proname"] for r in c.execute(
            "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='lfhe' "
            "AND p.proname IN ('ingest_report_edit','record_report_render') "
            "AND has_function_privilege('authenticated', p.oid, 'EXECUTE')")}
    assert set(P5_HUMAN_ONLY) <= rows
    assert worker_fns == set()                       # humans cannot call the M09 ingestion / render recorder


@pytest.mark.parametrize("fn", sorted(P5_HUMAN_ONLY))
def test_phase5_human_only_functions_reject_non_human_and_non_editor_roles(pg, make_user, fn):
    sql = f"SELECT lfhe.{fn}({P5_HUMAN_ONLY[fn]})"
    for conn in (pg.worker, pg.as_service_role, pg.as_anon):
        with conn() as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute(sql)
    for role in DENIED_ROLES:
        with pg.as_user(make_user(role)) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute(sql)
    with pg.as_user(make_user()) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
        c.execute(sql)
