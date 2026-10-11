"""CG1-08 — credentials hidden in URL values never reach source config, audit or errors."""
import json
import uuid

import psycopg
import pytest
from psycopg.types.json import Jsonb

from lfhe_collector.adapters import AdapterConfigError, build_adapter
from lfhe_shared.credentials import credential_url_paths, url_credential_problems

pytestmark = pytest.mark.db
SECRET = "SYNTHETIC-SECRET-7f3a9c"  # synthetic test value only  gitleaks:allow

CASES = [
    ("RSS_ATOM", {"feed_url": f"https://reader:{SECRET}@example.org/feed.xml"}, "$.feed_url (USERINFO)"),
    ("RSS_ATOM", {"feed_url": f"https://example.org/feed.xml?api_key={SECRET}"},
     "$.feed_url (CREDENTIAL_PARAMETER:api_key)"),
    ("STRUCTURED_FEED", {"sitemap_url": f"https://example.org/sitemap.xml?token={SECRET}"},
     "$.sitemap_url (CREDENTIAL_PARAMETER:token)"),
    ("OFFICIAL_API", {"endpoint": f"https://svc:{SECRET}@api.example.org/v1/items"}, "$.endpoint (USERINFO)"),
    ("HTTP_FETCH", {"urls": ["https://example.org/a.html", f"https://example.org/b.html?secret={SECRET}"]},
     "$.urls[1] (CREDENTIAL_PARAMETER:secret)"),
    ("HTTP_FETCH", {"urls": [f"https://example.org/c.html#access_token={SECRET}"]},
     "$.urls[0] (CREDENTIAL_PARAMETER:access_token)"),
    ("RSS_ATOM", {"feed_url": f"https://example.org/f.xml?API%5FKEY={SECRET}"},
     "$.feed_url (CREDENTIAL_PARAMETER:api_key)"),
]


def payload(method, config):
    return {"name": f"cg108-{uuid.uuid4().hex[:8]}", "canonical_domain": "example.org",
            "source_type": "OFFICIAL_GOVERNMENT", "primary_language": "en",
            "collection_method": method, "collection_config": config}


def no_secret_anywhere(pg):
    with pg.admin() as c:
        audit = c.execute("SELECT count(*) AS n FROM lfhe.audit_log WHERE coalesce(new_state::text,'') LIKE %s "
                          "OR coalesce(previous_state::text,'') LIKE %s OR metadata::text LIKE %s",
                          (f"%{SECRET}%",) * 3).fetchone()["n"]
        rows = c.execute("SELECT count(*) AS n FROM lfhe.sources WHERE collection_config::text LIKE %s",
                         (f"%{SECRET}%",)).fetchone()["n"]
    assert (audit, rows) == (0, 0)


@pytest.mark.parametrize("method,config,expected_path", CASES)
def test_direct_rpc_rejects_credential_urls(pg, make_user, method, config, expected_path):
    admin = make_user("ADMIN")
    with pg.admin() as c:
        before = c.execute("SELECT count(*) AS n FROM lfhe.sources").fetchone()["n"]
    with pg.as_user(admin) as c:
        with pytest.raises(psycopg.errors.CheckViolation, match="CREDENTIAL_URL_REJECTED") as exc:
            c.execute("SELECT lfhe.create_source(%s::jsonb)", (json.dumps(payload(method, config)),))
    message = str(exc.value) + str(getattr(exc.value.diag, "message_detail", "") or "")
    assert expected_path in message and SECRET not in message
    with pg.admin() as c:
        assert c.execute("SELECT count(*) AS n FROM lfhe.sources").fetchone()["n"] == before, "no source row"
    no_secret_anywhere(pg)
    assert expected_path in credential_url_paths(config), "Python mirror agrees"
    with pytest.raises(AdapterConfigError) as aexc:
        build_adapter(method, config)
    assert SECRET not in str(aexc.value)


def test_benign_public_query_strings_are_accepted(pg, make_user):
    admin = make_user("ADMIN")
    config = {"urls": ["https://example.org/news?lang=en&page=2&category=keynotes",
                       "https://example.org/search?q=logistics+exercise&sort=date&monkey=1"]}
    with pg.as_user(admin) as c:
        sid = c.execute("SELECT lfhe.create_source(%s::jsonb) AS id",
                        (json.dumps(payload("HTTP_FETCH", config)),)).fetchone()["id"]
    assert sid is not None and credential_url_paths(config) == []
    build_adapter("HTTP_FETCH", config)


def test_update_rpc_and_owner_writes_are_rejected(pg, make_user):
    admin = make_user("ADMIN")
    with pg.as_user(admin) as c:
        sid = c.execute("SELECT lfhe.create_source(%s::jsonb) AS id", (json.dumps(
            payload("RSS_ATOM", {"feed_url": "https://example.org/feed.xml"})),)).fetchone()["id"]
        with pytest.raises(psycopg.errors.CheckViolation, match="CREDENTIAL_URL_REJECTED") as exc:
            c.execute("SELECT lfhe.update_source(%s, %s::jsonb, 'cg1-08 test')", (sid, json.dumps(
                {"collection_config": {"feed_url": f"https://u:{SECRET}@example.org/feed.xml"}})))
        assert SECRET not in str(exc.value)
    with pg.admin() as c:
        with pytest.raises(psycopg.errors.CheckViolation, match="CREDENTIAL_URL_REJECTED"):
            c.execute("UPDATE lfhe.sources SET collection_config = %s WHERE id = %s",
                      (Jsonb({"feed_url": f"https://example.org/f?token={SECRET}"}), sid))
        c.execute("ALTER TABLE lfhe.sources DISABLE TRIGGER sources_reject_credential_keys")
        try:  # backstop CHECK still holds without the trigger
            with pytest.raises(psycopg.errors.CheckViolation, match="sources_config_urls_have_no_credentials"):
                c.execute("UPDATE lfhe.sources SET collection_config = %s WHERE id = %s",
                          (Jsonb({"feed_url": "https://example.org/f?token=x"}), sid))
        finally:
            c.execute("ALTER TABLE lfhe.sources ENABLE TRIGGER sources_reject_credential_keys")
    no_secret_anywhere(pg)


def test_model_settings_and_job_payload_urls_are_checked(pg):
    with pg.registrar() as c:
        with pytest.raises(psycopg.errors.CheckViolation, match="CREDENTIAL_URL_REJECTED") as exc:
            c.execute("SELECT lfhe.register_model_configuration('fake', 'm-url', %s::jsonb)",
                      (Jsonb({"base_url": f"https://acct:{SECRET}@llm.example.org/v1"}),))
        assert SECRET not in str(exc.value)
        assert c.execute("SELECT lfhe.register_model_configuration('fake', 'm-url-ok', %s::jsonb) AS id",
                         (Jsonb({"base_url": "https://llm.example.org/v1?region=eu"}),)).fetchone()["id"]
    with pg.worker() as c:
        with pytest.raises(psycopg.errors.CheckViolation, match="CREDENTIAL_URL_REJECTED"):
            c.execute("SELECT lfhe.enqueue_job('COLLECT_SOURCE', 'source', 'x', %s, %s::jsonb)",
                      (f"cg108:{uuid.uuid4()}", Jsonb({"next": f"https://example.org/x?apikey={SECRET}"})))


def test_database_and_python_url_rules_agree(pg):
    urls = [f"https://a:{SECRET}@example.org/", "https://example.org/?token=x&lang=en",
            "https://example.org/#access_token=x", "https://example.org/?a=1&b=2", "https://example.org/?keyword=x",
            "https://example.org/?X-Api-Key=x", "https://example.org/?client%5Fsecret=x", "ftp://u:p@example.org/",
            "plain text ?token=x", "https://example.org/path/token/x"]
    with pg.admin() as c:
        db = [c.execute("SELECT lfhe.url_credential_problems(%s) AS p", (u,)).fetchone()["p"] for u in urls]
    assert db == [url_credential_problems(u) for u in urls]
    assert [bool(p) for p in db] == [True, True, True, False, False, True, True, True, False, False]
