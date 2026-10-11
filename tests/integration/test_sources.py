"""P1-06 — Source Registry (F1, F2, F7)."""
import json

import psycopg
import pytest

pytestmark = pytest.mark.db

Denied = psycopg.errors.InsufficientPrivilege


def source_payload(name: str, **over) -> dict:
    p = {
        "name": name,
        "canonical_domain": "feeds.example.org",
        "owner_organisation": "Example Ministry (synthetic)",
        "owner_country": "xx",
        "source_type": "OFFICIAL_GOVERNMENT",
        "official_status": "OFFICIAL",
        "primary_language": "en",
        "collection_method": "RSS_ATOM",
        "collection_config": {"feed_url": "https://feeds.example.org/rss.xml"},
        "collection_frequency": "1 hour",
        "retention_mode": "FULL",
    }
    p.update(over)
    return p


def create(conn, payload) -> str:
    return conn.execute("SELECT lfhe.create_source(%s::jsonb) AS id", (json.dumps(payload),)).fetchone()["id"]


def audit_events(pg, source_id):
    with pg.admin() as c:
        return [r["event_type"] for r in c.execute(
            "SELECT event_type FROM lfhe.audit_log WHERE object_type='source' AND object_id=%s ORDER BY seq",
            (str(source_id),))]


def test_f1_authorised_user_can_create_source_inactive_by_default(pg, make_user):
    analyst = make_user("ANALYST")
    with pg.as_user(analyst) as c:
        sid = create(c, source_payload("F1 synthetic ministry"))
        row = c.execute("SELECT * FROM lfhe.sources WHERE id=%s", (sid,)).fetchone()
    assert row["active"] is False and row["collection_method_approved"] is False
    assert row["created_by"] == analyst and row["owner_country"] == "XX"
    assert audit_events(pg, sid) == ["SOURCE_CREATED"]


def test_f1_unauthorised_users_cannot_create_source(pg, make_user):
    viewer = make_user("VIEWER")
    with pg.as_user(viewer) as c:
        with pytest.raises(Denied, match="SOURCE_CREATE"):
            create(c, source_payload("viewer attempt"))
    with pg.worker() as c:
        with pytest.raises(Denied):
            create(c, source_payload("worker attempt"))
    with pg.as_service_role() as c:
        with pytest.raises(Denied):
            create(c, source_payload("service attempt"))


def test_f2_activation_requires_approved_method_and_permission(pg, make_user):
    analyst, reviewer = make_user("ANALYST"), make_user("REVIEWER")
    with pg.as_user(analyst) as c:
        sid = create(c, source_payload("F2 synthetic source"))
        with pytest.raises(Denied, match="SOURCE_ACTIVATE"):
            c.execute("SELECT lfhe.set_source_active(%s, true, 'analyst tries')", (sid,))
    with pg.as_user(reviewer) as c:
        with pytest.raises(psycopg.errors.CheckViolation, match="not approved"):
            c.execute("SELECT lfhe.set_source_active(%s, true, 'too early')", (sid,))
        c.execute("SELECT lfhe.set_collection_method_approval(%s, true, 'public RSS, terms reviewed')", (sid,))
        c.execute("SELECT lfhe.set_source_active(%s, true, 'start collection')", (sid,))
        assert c.execute("SELECT active FROM lfhe.sources WHERE id=%s", (sid,)).fetchone()["active"]
        c.execute("SELECT lfhe.set_source_active(%s, false, 'pause collection')", (sid,))
    assert audit_events(pg, sid) == [
        "SOURCE_CREATED", "SOURCE_COLLECTION_METHOD_APPROVED", "SOURCE_ACTIVATED", "SOURCE_DEACTIVATED"]
    with pg.admin() as c:
        reasons = [r["metadata"].get("reason") for r in c.execute(
            "SELECT metadata FROM lfhe.audit_log WHERE object_id=%s ORDER BY seq", (str(sid),))]
    assert reasons[1:] == ["public RSS, terms reviewed", "start collection", "pause collection"]


def test_config_change_revokes_approval_and_deactivates(pg, make_user):
    admin = make_user("ADMIN")
    with pg.as_user(admin) as c:
        sid = create(c, source_payload("reapproval synthetic"))
        c.execute("SELECT lfhe.set_collection_method_approval(%s, true, 'terms reviewed ok')", (sid,))
        c.execute("SELECT lfhe.set_source_active(%s, true, 'go live')", (sid,))
        c.execute("SELECT lfhe.update_source(%s, %s::jsonb, 'new feed url')",
                  (sid, json.dumps({"collection_config": {"feed_url": "https://feeds.example.org/v2.xml"}})))
        row = c.execute("SELECT active, collection_method_approved FROM lfhe.sources WHERE id=%s", (sid,)).fetchone()
        assert row == {"active": False, "collection_method_approved": False}
        # metadata-only edits do not revoke approval
        c.execute("SELECT lfhe.set_collection_method_approval(%s, true, 'terms reviewed again')", (sid,))
        c.execute("SELECT lfhe.update_source(%s, %s::jsonb, NULL)", (sid, json.dumps({"analyst_notes": "note"})))
        assert c.execute("SELECT collection_method_approved FROM lfhe.sources WHERE id=%s",
                         (sid,)).fetchone()["collection_method_approved"]
    events = audit_events(pg, sid)
    assert events.count("SOURCE_COLLECTION_METHOD_REVOKED") == 1
    assert "SOURCE_DEACTIVATED" in events and events[-1] == "SOURCE_UPDATED"


def test_browser_automation_cannot_be_approved(pg, make_user):
    admin = make_user("ADMIN")
    with pg.as_user(admin) as c:
        sid = create(c, source_payload("browser synthetic", collection_method="BROWSER_AUTOMATION",
                                       collection_config={"url": "https://feeds.example.org/"}))
        with pytest.raises(psycopg.errors.CheckViolation):
            c.execute("SELECT lfhe.set_collection_method_approval(%s, true, 'should fail here')", (sid,))


def test_credentials_in_collection_config_rejected(pg, make_user):
    admin = make_user("ADMIN")
    with pg.as_user(admin) as c:
        with pytest.raises(psycopg.errors.CheckViolation):
            create(c, source_payload("creds synthetic", collection_config={
                "feed_url": "https://feeds.example.org/rss.xml", "headers": {"Authorization": "x"}}))


def test_unknown_fields_and_direct_writes_rejected(pg, make_user):
    admin = make_user("ADMIN")
    with pg.as_user(admin) as c:
        with pytest.raises(psycopg.errors.InvalidParameterValue):
            create(c, source_payload("unknown field", active=True))
        with pytest.raises(Denied):
            c.execute("UPDATE lfhe.sources SET active = true")
        with pytest.raises(Denied):
            c.execute("DELETE FROM lfhe.sources")
    with pg.worker() as c:
        with pytest.raises(Denied):
            c.execute("UPDATE lfhe.sources SET active = true")


def test_read_access_follows_permissions(pg, make_user):
    viewer = make_user("VIEWER")
    nobody = make_user()
    with pg.as_user(viewer) as c:
        assert c.execute("SELECT count(*) AS n FROM lfhe.sources").fetchone()["n"] > 0
    with pg.as_user(nobody) as c:
        assert c.execute("SELECT count(*) AS n FROM lfhe.sources").fetchone()["n"] == 0
    with pg.worker() as c:
        assert c.execute("SELECT count(*) AS n FROM lfhe.sources").fetchone()["n"] > 0
