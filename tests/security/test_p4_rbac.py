"""Phase 4 Addendum §22 / required test 70: every Phase 4 HUMAN_ONLY function rejects
worker, service_role, anon, VIEWER, ADMIN, SECURITY_REVIEWER and RELEASE_AUTHORITY
(no analytic permission). Calls use well-formed dummy arguments, so a rejection can
only come from the permission gate (or grants), never from argument parsing."""
import psycopg
import pytest

pytestmark = pytest.mark.db
U = "00000000-0000-4000-8000-0000000000aa"
H = "0" * 64
P4_HUMAN_ONLY = {
    "create_reference_context_version": ("'{}'::jsonb, 'x reason'",),
    "decide_reference_context_version": (f"'{U}'::uuid, '{H}', 'APPROVE', 'x reason'",),
    "create_baseline_version": ("'{}'::jsonb, 'x reason'",),
    "decide_baseline_version": (f"'{U}'::uuid, '{H}', 'APPROVE', 'x reason'",),
    "decide_relevance": (f"'{U}'::uuid, 'VALIDATE', NULL, 'x reason'",),
    "promote_event_version": (f"'{U}'::uuid, '{H}', 'PROMOTE', 'x reason'",),
    "dispose_challenge_flag": (f"'{U}'::uuid, 'ACCEPTED', 'x reason'",),
    "review_assessment": (f"'{U}'::uuid, '{H}', 'APPROVE', 'LOW', 'a long enough rationale text', 'x reason'",),
    "modify_and_approve_assessment": (f"'{U}'::uuid, '{H}', '{{}}'::jsonb, 'LOW', 'a long enough rationale text', 'x reason'",),
    "create_trend_version": ("'{}'::jsonb, 'x reason'",),
    "create_indicator_version": ("'{}'::jsonb, 'x reason'",),
}
DENIED_ROLES = ("VIEWER", "ADMIN", "SECURITY_REVIEWER", "RELEASE_AUTHORITY")


def test_phase4_human_only_inventory_is_complete(pg):
    with pg.admin() as c:
        rows = {r["proname"] for r in c.execute(
            "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            "WHERE n.nspname='lfhe' AND obj_description(p.oid,'pg_proc')='HUMAN_ONLY'")}
    assert set(P4_HUMAN_ONLY) <= rows


@pytest.mark.parametrize("fn", sorted(P4_HUMAN_ONLY))
def test_phase4_human_only_functions_reject_non_human_and_non_analytic_roles(pg, make_user, fn):
    sql = f"SELECT lfhe.{fn}({P4_HUMAN_ONLY[fn][0]})"
    for conn in (pg.worker, pg.as_service_role, pg.as_anon):
        with conn() as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute(sql)
    for role in DENIED_ROLES:
        with pg.as_user(make_user(role)) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute(sql)
    with pg.as_user(make_user()) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):   # no role at all
        c.execute(sql)
