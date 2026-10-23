"""Phase 6 Addendum §22, §24, §26 — RBAC / separation-of-duties sweep (acceptance behaviours 42, 51–55,
72–78, 88). Dummy arguments are well-formed, so a rejection of a DENIED principal can only come from
the permission gate or the grants; an ALLOWED role gets past the gate (and then fails on the dummy
object, never with insufficient_privilege)."""
import psycopg
import pytest

pytestmark = pytest.mark.db
U = "00000000-0000-4000-8000-0000000000cc"
H = "0" * 64
P6_HUMAN_ONLY = {
    "request_report_qa": (f"'{U}'::uuid, '{H}', 'x reason'", {"ANALYST", "REVIEWER"}),
    "acknowledge_qa_warning": (f"'{U}'::uuid, '{H}', '{U}'::uuid, '{U}'::uuid, 'x rationale long enough'", {"REVIEWER"}),
    "decide_report_content": (f"'{U}'::uuid, '{H}', '{U}'::uuid, 'APPROVE', 'x rationale long enough'", {"REVIEWER"}),
    "decide_security_review": (f"'{U}'::uuid, '{H}', '{U}'::uuid, 'APPROVED', 'x rationale long enough'", {"SECURITY_REVIEWER"}),
    "request_release_pdf": (f"'{U}'::uuid, '{H}', 'x reason'", {"RELEASE_AUTHORITY"}),
    "decide_release": (f"'{U}'::uuid, '{H}', 'REJECT_RELEASE', 'x rationale long enough'", {"RELEASE_AUTHORITY"}),
    "release_report": (f"'{U}'::uuid, '{H}', '{U}'::uuid, 'x rationale long enough'", {"RELEASE_AUTHORITY"}),
}
ROLES = ("ADMIN", "ANALYST", "REVIEWER", "SECURITY_REVIEWER", "RELEASE_AUTHORITY", "VIEWER")
WORKER_ONLY = ("run_m10d", "ingest_qa_semantic", "record_qa_result", "record_release_pdf")
P6_TABLES = ("qa_checks", "qa_requests", "qa_runs", "qa_check_results", "qa_results", "warning_acknowledgements",
             "content_approvals", "security_reviews", "release_pdf_artifacts", "release_decisions", "release_manifests",
             "report_releases")


def test_phase6_human_only_inventory_and_worker_surface(pg):
    with pg.admin() as c:
        human = {r["proname"] for r in c.execute(
            "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            "WHERE n.nspname='lfhe' AND obj_description(p.oid,'pg_proc')='HUMAN_ONLY'")}
        assert set(P6_HUMAN_ONLY) <= human
        for fn in WORKER_ONLY:
            oid = c.execute("SELECT p.oid FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
                            "WHERE n.nspname='lfhe' AND p.proname=%s", (fn,)).fetchone()["oid"]
            for role in ("authenticated", "service_role", "anon", "lfhe_evaluator", "lfhe_registrar"):
                assert not c.execute("SELECT has_function_privilege(%s, %s, 'EXECUTE') ok", (role, oid)).fetchone()["ok"], (fn, role)
            assert c.execute("SELECT has_function_privilege('lfhe_worker', %s, 'EXECUTE') ok", (oid,)).fetchone()["ok"]
        # no Phase 6 authoritative table is directly writable by any application principal
        for t in P6_TABLES:
            for role in ("authenticated", "service_role", "anon", "lfhe_worker", "lfhe_evaluator", "lfhe_registrar"):
                for priv in ("INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                    assert not c.execute("SELECT has_table_privilege(%s, %s, %s) ok", (role, f"lfhe.{t}", priv)).fetchone()["ok"], \
                        (t, role, priv)
            assert c.execute("SELECT relrowsecurity FROM pg_class WHERE oid = %s::regclass", (f"lfhe.{t}",)).fetchone()["relrowsecurity"]
        # Phase 6 authority is held only by the expected roles (ADMIN gets none of it — §24)
        rows = c.execute("SELECT role_code, permission_code FROM lfhe.role_permissions WHERE permission_code IN "
                         "('QA_WARNING_ACKNOWLEDGE', 'REPORT_CONTENT_APPROVE', 'SECURITY_REVIEW', 'RELEASE_DECIDE')").fetchall()
    assert sorted((r["permission_code"], r["role_code"]) for r in rows) == [
        ("QA_WARNING_ACKNOWLEDGE", "REVIEWER"), ("RELEASE_DECIDE", "RELEASE_AUTHORITY"),
        ("REPORT_CONTENT_APPROVE", "REVIEWER"), ("SECURITY_REVIEW", "SECURITY_REVIEWER")]


@pytest.mark.parametrize("fn", sorted(P6_HUMAN_ONLY))
def test_phase6_human_only_functions_reject_non_human_and_wrong_roles(pg, make_user, fn):
    args, allowed = P6_HUMAN_ONLY[fn]
    sql = f"SELECT lfhe.{fn}({args})"
    for conn in (pg.worker, pg.as_service_role, pg.as_anon):
        with conn() as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute(sql)
    for role in ROLES:
        with pg.as_user(make_user(role)) as c:
            if role in allowed:
                with pytest.raises(psycopg.Error) as exc:
                    c.execute(sql)
                assert not isinstance(exc.value, psycopg.errors.InsufficientPrivilege), (fn, role, exc.value)
            else:
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    c.execute(sql)
    with pg.as_user(make_user()) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
        c.execute(sql)


def test_release_eligibility_read_requires_a_human_reader(pg, make_user):
    sql = f"SELECT lfhe.release_eligibility('{U}'::uuid, '{H}', NULL)"
    for conn in (pg.worker, pg.as_service_role, pg.as_anon):
        with conn() as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute(sql)
    with pg.as_user(make_user()) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
        c.execute(sql)
    with pg.as_user(make_user("VIEWER")) as c:
        out = c.execute(sql).fetchone()
    r = out[next(iter(out))]
    assert r["eligible"] is False and "CALLER_HUMAN_RELEASE_AUTHORITY" in r["failed"] and "VERSION_EXISTS" in r["failed"]
