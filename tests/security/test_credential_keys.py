"""CG1-03 — recursive credential-key rejection, authoritative at the database."""
import json
import uuid

import psycopg
import pytest
from psycopg.types.json import Jsonb

from lfhe_shared.credentials import credential_key_paths, is_credential_key

SECRET = "sk-SYNTHETIC-DO-NOT-STORE-0123456789"
KEYS = {
    # rejected
    "token": True, "Token": True, "access_token": True, "accessToken": True, "api_key": True, "apiKey": True,
    "APIKey": True, "x-api-key": True, "X-Api-Key": True, "apikey": True, "key": True, "private_key": True,
    "secret": True, "client_secret": True, "password": True, "passwd": True, "headers": True,
    "Authorization": True, "auth": True, "auth_mode": True, "cookie": True, "cookies": True,
    "bearer_value": True, "credentials": True, "keys": True,
    # allowed (documented decisions)
    "max_tokens": False, "keyword": False, "feed_url": False, "items_path": False, "monkey": False,
    "sort_field": False, "temperature": False, "author": False, "excerpt_max_chars": False,
}
pytestmark = pytest.mark.db


def test_python_rule_matches_expectations():
    assert {k: is_credential_key(k) for k in KEYS} == KEYS


def test_database_rule_matches_python_mirror(pg):
    with pg.admin() as c:
        db = {k: c.execute("SELECT lfhe.is_credential_key(%s) AS r", (k,)).fetchone()["r"] for k in KEYS}
        doc = {"a": {"b": [{"ok": 1}, {"token": SECRET}], "Api-Key": "x"}, "items": [[{"x": {"secret": 1}}]],
               "fine": {"max_tokens": 5}}
        db_paths = c.execute("SELECT lfhe.credential_key_paths(%s::jsonb) AS p", (Jsonb(doc),)).fetchone()["p"]
    assert db == KEYS
    assert sorted(db_paths) == sorted(credential_key_paths(doc)) == \
        ["$.a.Api-Key", "$.a.b[1].token", "$.items[0][0].x.secret"]


def _payload(config):
    return {"name": f"cred-{uuid.uuid4().hex[:8]}", "canonical_domain": "example.org",
            "source_type": "OFFICIAL_GOVERNMENT", "primary_language": "en",
            "collection_method": "RSS_ATOM", "collection_config": config}


@pytest.mark.parametrize("config,path", [
    ({"feed_url": "https://example.org/f.xml", "token": SECRET}, "$.token"),
    ({"feed_url": "https://example.org/f.xml", "options": {"token": SECRET}}, "$.options.token"),
    ({"feed_url": "https://example.org/f.xml", "endpoints": [{"url": "x", "auth": {"password": SECRET}}]},
     "$.endpoints[0].auth"),
    ({"feed_url": "https://example.org/f.xml", "x": [[{"apiKey": SECRET}]]}, "$.x[0][0].apiKey"),
])
def test_direct_rpc_rejects_credentials_at_any_depth_without_echoing_or_auditing(pg, make_user, config, path):
    admin = make_user("ADMIN")
    with pg.as_user(admin) as c:
        with pytest.raises(psycopg.errors.CheckViolation, match="CREDENTIAL_KEY_REJECTED") as exc:
            c.execute("SELECT lfhe.create_source(%s::jsonb)", (json.dumps(_payload(config)),))
    assert path in str(exc.value) and SECRET not in str(exc.value)
    with pg.admin() as c:
        assert c.execute("SELECT count(*) AS n FROM lfhe.audit_log WHERE new_state::text LIKE %s OR "
                         "previous_state::text LIKE %s", (f"%{SECRET}%",) * 2).fetchone()["n"] == 0
        assert c.execute("SELECT count(*) AS n FROM lfhe.sources WHERE collection_config::text LIKE %s",
                         (f"%{SECRET}%",)).fetchone()["n"] == 0


def test_update_and_direct_table_writes_are_also_rejected(pg, make_user):
    admin = make_user("ADMIN")
    benign = {"feed_url": "https://example.org/f.xml", "options": {"max_items": 5, "tags": [{"name": "a"}]}}
    with pg.as_user(admin) as c:
        sid = c.execute("SELECT lfhe.create_source(%s::jsonb) AS id", (json.dumps(_payload(benign)),)).fetchone()["id"]
        with pytest.raises(psycopg.errors.CheckViolation, match="CREDENTIAL_KEY_REJECTED"):
            c.execute("SELECT lfhe.update_source(%s, %s::jsonb, 'add nested secret')",
                      (sid, json.dumps({"collection_config": {**benign, "options": {"cookie": SECRET}}})))
    with pg.admin() as c:  # even the owner cannot bypass the database rule
        with pytest.raises(psycopg.errors.CheckViolation, match="CREDENTIAL_KEY_REJECTED"):
            c.execute("UPDATE lfhe.sources SET collection_config = %s WHERE id = %s",
                      (Jsonb({"nested": {"secret": SECRET}}), sid))
        c.execute("ALTER TABLE lfhe.sources DISABLE TRIGGER sources_reject_credential_keys")
        try:  # backstop CHECK constraint holds even without the trigger
            with pytest.raises(psycopg.errors.CheckViolation, match="sources_config_has_no_credentials"):
                c.execute("UPDATE lfhe.sources SET collection_config = %s WHERE id = %s",
                          (Jsonb({"nested": {"secret": "x"}}), sid))
        finally:
            c.execute("ALTER TABLE lfhe.sources ENABLE TRIGGER sources_reject_credential_keys")


def test_model_settings_and_job_payloads_are_checked_recursively(pg):
    with pg.registrar() as c:
        ok = c.execute("SELECT lfhe.register_model_configuration('fake', 'm-benign', %s::jsonb) AS id",
                       (Jsonb({"temperature": 0, "max_tokens": 1000, "stop": ["x"], "tools": [{"name": "t"}]}),)
                       ).fetchone()["id"]
        assert ok is not None
        with pytest.raises(psycopg.errors.CheckViolation, match=r"CREDENTIAL_KEY_REJECTED.*\$\.provider\.api_key"):
            c.execute("SELECT lfhe.register_model_configuration('fake', 'm', %s::jsonb)",
                      (Jsonb({"provider": {"api_key": SECRET}}),))
    with pg.worker() as c:
        with pytest.raises(psycopg.errors.CheckViolation, match="CREDENTIAL_KEY_REJECTED"):
            c.execute("SELECT lfhe.enqueue_job('COLLECT_SOURCE', 'source', 'x', %s, %s::jsonb)",
                      (f"cred-test:{uuid.uuid4()}", Jsonb({"http": [{"headers": {"X": "y"}}]})))
