"""P1-04 — authentication, RBAC and human-only enforcement (F9)."""
import uuid

import psycopg
import pytest

from conftest import new_user

pytestmark = pytest.mark.db

Denied = psycopg.errors.InsufficientPrivilege


def test_admin_can_grant_and_revoke_role(pg, make_user):
    admin = make_user("ADMIN")
    target = new_user(pg)
    with pg.as_user(admin) as c:
        c.execute("SELECT lfhe.grant_user_role(%s, 'ANALYST')", (target,))
        roles = [r["role_code"] for r in c.execute(
            "SELECT role_code FROM lfhe.user_roles WHERE user_id = %s", (target,))]
        assert roles == ["ANALYST"]
        c.execute("SELECT lfhe.revoke_user_role(%s, 'ANALYST')", (target,))
        assert c.execute("SELECT count(*) AS n FROM lfhe.user_roles WHERE user_id=%s",
                         (target,)).fetchone()["n"] == 0


def test_analyst_cannot_grant_roles(pg, make_user):
    analyst = make_user("ANALYST")
    target = new_user(pg)
    with pg.as_user(analyst) as c:
        with pytest.raises(Denied, match="USER_ROLE_MANAGE"):
            c.execute("SELECT lfhe.grant_user_role(%s, 'ADMIN')", (target,))


def test_worker_cannot_execute_human_function(pg, make_user):
    target = new_user(pg)
    with pg.worker() as c:
        with pytest.raises(Denied):
            c.execute("SELECT lfhe.grant_user_role(%s, 'ADMIN')", (target,))


def test_worker_cannot_impersonate_authenticated_role(pg):
    with pg.worker() as c:
        with pytest.raises(Denied):
            c.execute("SET ROLE authenticated")


def test_service_role_and_anon_cannot_execute_human_function(pg):
    target = new_user(pg)
    with pg.as_service_role() as c:
        with pytest.raises(Denied):
            c.execute("SELECT lfhe.grant_user_role(%s, 'ADMIN')", (target,))
    with pg.as_anon() as c:
        with pytest.raises(Denied):
            c.execute("SELECT lfhe.grant_user_role(%s, 'ADMIN')", (target,))


def test_authenticated_without_valid_identity_is_rejected(pg, make_user):
    target = new_user(pg)
    # no claims at all
    with pg.as_role("authenticated", None) as c:
        with pytest.raises(Denied, match="human authentication required"):
            c.execute("SELECT lfhe.grant_user_role(%s, 'ADMIN')", (target,))
    # claims for a user that does not exist in auth.users
    with pg.as_user(uuid.uuid4()) as c:
        with pytest.raises(Denied, match="human authentication required"):
            c.execute("SELECT lfhe.grant_user_role(%s, 'ADMIN')", (target,))
    # claims whose role is not 'authenticated'
    admin = make_user("ADMIN")
    with pg.as_role("authenticated", {"sub": str(admin), "role": "service_role"}) as c:
        with pytest.raises(Denied, match="human authentication required"):
            c.execute("SELECT lfhe.grant_user_role(%s, 'ADMIN')", (target,))


def test_has_permission_and_my_permissions(pg, make_user):
    viewer = make_user("VIEWER")
    with pg.as_user(viewer) as c:
        assert c.execute("SELECT lfhe.has_permission('SOURCE_READ') AS p").fetchone()["p"] is True
        assert c.execute("SELECT lfhe.has_permission('SOURCE_CREATE') AS p").fetchone()["p"] is False
        perms = [r["p"] for r in c.execute("SELECT lfhe.my_permissions() AS p")]
        assert perms == ["ARTICLE_READ", "SOURCE_READ"]


def test_last_admin_cannot_be_revoked(pg, make_user):
    # Work in an isolated database state: count admins, then try to revoke all but none.
    admin = make_user("ADMIN")
    with pg.admin() as c:
        others = [r["user_id"] for r in c.execute(
            "SELECT user_id FROM lfhe.user_roles WHERE role_code='ADMIN' AND user_id <> %s", (admin,))]
    with pg.as_user(admin) as c:
        for other in others:
            c.execute("SELECT lfhe.revoke_user_role(%s, 'ADMIN')", (other,))
        with pytest.raises(psycopg.Error, match="last ADMIN"):
            c.execute("SELECT lfhe.revoke_user_role(%s, 'ADMIN')", (admin,))


def test_rls_user_sees_only_own_roles(pg, make_user):
    a = make_user("VIEWER")
    b = make_user("ANALYST")
    with pg.as_user(a) as c:
        ids = {r["user_id"] for r in c.execute("SELECT user_id FROM lfhe.user_roles")}
    assert ids == {a}
    assert b not in ids


def test_no_direct_writes_to_user_roles(pg, make_user):
    admin = make_user("ADMIN")
    with pg.as_user(admin) as c:
        with pytest.raises(Denied):
            c.execute("INSERT INTO lfhe.user_roles (user_id, role_code) VALUES (%s, 'ADMIN')", (admin,))
    with pg.worker() as c:
        with pytest.raises(Denied):
            c.execute("INSERT INTO lfhe.user_roles (user_id, role_code) VALUES (%s, 'ADMIN')", (admin,))
