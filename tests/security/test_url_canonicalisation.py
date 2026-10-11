"""CG1-08A — canonicalise before credential inspection; database-authoritative
validation of the known source URL fields (before row, update and audit)."""
import json
import uuid
from pathlib import Path

import psycopg
import pytest

from conftest import REPO_ROOT
from lfhe_collector.adapters import AdapterConfigError, build_adapter
from lfhe_shared.credentials import source_config_problems, url_credential_problems, url_inspection_form

pytestmark = pytest.mark.db
SECRET = "SYNTHETIC-CANON-SECRET-41d2"  # synthetic test value only  gitleaks:allow

# (method, config, expected path+code that must appear in the error)
REJECT = [
    ("A", "RSS_ATOM", {"feed_url": f" https://example.org/feed?api_key={SECRET}"},
     "$.feed_url (CREDENTIAL_PARAMETER:api_key)"),
    ("B", "RSS_ATOM", {"feed_url": f"https://example.org/feed?token={SECRET} "},
     "$.feed_url (CREDENTIAL_PARAMETER:token)"),
    ("C", "RSS_ATOM", {"feed_url": f"\thttps://user:{SECRET}@example.org/feed\n"}, "$.feed_url (USERINFO)"),
    ("D", "RSS_ATOM", {"feed_url": f"/feed?api_key={SECRET}"}, "$.feed_url (CREDENTIAL_PARAMETER:api_key)"),
    ("E", "STRUCTURED_FEED", {"sitemap_url": f"sitemap.xml?token={SECRET}"},
     "$.sitemap_url (CREDENTIAL_PARAMETER:token)"),
    ("F", "OFFICIAL_API", {"endpoint": f"/v1/items?access_token={SECRET}"},
     "$.endpoint (CREDENTIAL_PARAMETER:access_token)"),
    ("G", "HTTP_FETCH", {"urls": ["https://example.org/a.html", f"/b.html?secret={SECRET}"]},
     "$.urls[1] (CREDENTIAL_PARAMETER:secret)"),
    ("tab-inside", "RSS_ATOM", {"feed_url": f"https://example.org/f?api_\t_key={SECRET}"},
     "$.feed_url (CREDENTIAL_PARAMETER:api__key)"),
    ("special-scheme-no-slashes", "RSS_ATOM", {"feed_url": f"https:reader:{SECRET}@example.org/feed"},
     "$.feed_url (USERINFO)"),
    ("backslashes", "RSS_ATOM", {"feed_url": f"https:\\\\reader:{SECRET}@example.org\\feed"},
     "$.feed_url (USERINFO)"),
    ("protocol-relative", "OFFICIAL_API", {"endpoint": f"//svc:{SECRET}@api.example.org/v1"},
     "$.endpoint (USERINFO)"),
]
# structurally invalid known fields without any secret
INVALID = [
    ("RSS_ATOM", {"feed_url": "/feed.xml"}, "$.feed_url (NOT_CANONICAL_ABSOLUTE_HTTP_URL)"),
    ("RSS_ATOM", {"feed_url": " https://example.org/feed.xml"}, "$.feed_url (NOT_CANONICAL_ABSOLUTE_HTTP_URL)"),
    ("RSS_ATOM", {}, "$.feed_url (MISSING)"),
    ("RSS_ATOM", {"feed_url": ["https://example.org/f.xml"]}, "$.feed_url (NOT_A_STRING)"),
    ("STRUCTURED_FEED", {"sitemap_url": "ftp://example.org/s.xml"}, "$.sitemap_url (NOT_CANONICAL_ABSOLUTE_HTTP_URL)"),
    ("OFFICIAL_API", {"endpoint": 42}, "$.endpoint (NOT_A_STRING)"),
    ("HTTP_FETCH", {"urls": []}, "$.urls (NOT_A_NON_EMPTY_ARRAY)"),
    ("HTTP_FETCH", {"urls": "https://example.org/a"}, "$.urls (NOT_A_NON_EMPTY_ARRAY)"),
    ("HTTP_FETCH", {"urls": ["https://example.org/a", "relative/b.html"]}, "$.urls[1] (NOT_CANONICAL_ABSOLUTE_HTTP_URL)"),
]
ACCEPT = [
    ("RSS_ATOM", {"feed_url": "https://example.org/feed.xml?lang=en&page=2"}),
    ("STRUCTURED_FEED", {"sitemap_url": "https://www.example.org/sitemap.xml"}),
    ("OFFICIAL_API", {"endpoint": "https://api.example.org:8443/v1/items?format=json&category=keynotes"}),
    ("HTTP_FETCH", {"urls": ["https://example.org/a.html", "http://news.example.org/b?id=7#top"]}),
]


def payload(method, config):
    return {"name": f"cg108a-{uuid.uuid4().hex[:8]}", "canonical_domain": "example.org",
            "source_type": "OFFICIAL_GOVERNMENT", "primary_language": "en",
            "collection_method": method, "collection_config": config}


def counts(pg):
    with pg.admin() as c:
        return (c.execute("SELECT count(*) AS n FROM lfhe.sources").fetchone()["n"],
                c.execute("SELECT count(*) AS n FROM lfhe.audit_log").fetchone()["n"])


def assert_secret_nowhere(pg):
    with pg.admin() as c:
        audit = c.execute("SELECT count(*) AS n FROM lfhe.audit_log WHERE coalesce(new_state::text,'') LIKE %s "
                          "OR coalesce(previous_state::text,'') LIKE %s OR metadata::text LIKE %s",
                          (f"%{SECRET}%",) * 3).fetchone()["n"]
        rows = c.execute("SELECT count(*) AS n FROM lfhe.sources WHERE collection_config::text LIKE %s",
                         (f"%{SECRET}%",)).fetchone()["n"]
    assert (audit, rows) == (0, 0)


@pytest.mark.parametrize("case,method,config,expected", REJECT, ids=[r[0] for r in REJECT])
def test_I_J_direct_rpc_rejects_before_row_and_audit(pg, make_user, case, method, config, expected):
    admin = make_user("ADMIN")
    before = counts(pg)
    with pg.as_user(admin) as c:
        with pytest.raises(psycopg.errors.CheckViolation) as exc:
            c.execute("SELECT lfhe.create_source(%s::jsonb)", (json.dumps(payload(method, config)),))
    message = f"{exc.value} {exc.value.diag.message_detail or ''} {exc.value.diag.message_hint or ''}"
    assert expected in message and SECRET not in message
    assert counts(pg) == before, "no source row and no audit entry"
    assert_secret_nowhere(pg)
    assert expected in source_config_problems(method, config), "Python mirror agrees"
    with pytest.raises(AdapterConfigError) as aexc:
        build_adapter(method, config)
    assert SECRET not in str(aexc.value)


@pytest.mark.parametrize("method,config,expected", INVALID)
def test_known_url_fields_must_be_canonical_absolute_http(pg, make_user, method, config, expected):
    admin = make_user("ADMIN")
    before = counts(pg)
    with pg.as_user(admin) as c:
        with pytest.raises(psycopg.errors.CheckViolation, match="SOURCE_CONFIG_INVALID") as exc:
            c.execute("SELECT lfhe.create_source(%s::jsonb)", (json.dumps(payload(method, config)),))
    assert expected in str(exc.value)
    assert counts(pg) == before
    assert expected in source_config_problems(method, config)


def test_update_cannot_introduce_invalid_or_credential_url(pg, make_user):
    admin = make_user("ADMIN")
    with pg.as_user(admin) as c:
        sid = c.execute("SELECT lfhe.create_source(%s::jsonb) AS id",
                        (json.dumps(payload("RSS_ATOM", {"feed_url": "https://example.org/feed.xml"})),)).fetchone()["id"]
        before = counts(pg)
        for bad in ({"feed_url": f" https://example.org/feed?api_key={SECRET}"}, {"feed_url": f"/feed?api_key={SECRET}"}):
            with pytest.raises(psycopg.errors.CheckViolation) as exc:
                c.execute("SELECT lfhe.update_source(%s, %s::jsonb, 'cg1-08a test')",
                          (sid, json.dumps({"collection_config": bad})))
            assert SECRET not in str(exc.value)
        with pytest.raises(psycopg.errors.CheckViolation, match="SOURCE_CONFIG_INVALID"):
            c.execute("SELECT lfhe.update_source(%s, %s::jsonb, 'cg1-08a method switch')",
                      (sid, json.dumps({"collection_method": "HTTP_FETCH"})))  # urls missing for new method
    assert counts(pg) == before
    assert_secret_nowhere(pg)


@pytest.mark.parametrize("method,config", ACCEPT)
def test_H_clean_absolute_urls_with_harmless_queries_accepted(pg, make_user, method, config):
    admin = make_user("ADMIN")
    with pg.as_user(admin) as c:
        assert c.execute("SELECT lfhe.create_source(%s::jsonb) AS id",
                         (json.dumps(payload(method, config)),)).fetchone()["id"]
    assert source_config_problems(method, config) == []
    build_adapter(method, config)


FAKE = "fake"  # low-entropy placeholder: the parity fixture must not look like a secret
CANON_CASES = [
    f" https://example.org/feed?api_key={FAKE}", f"https://example.org/feed?token={FAKE} ",
    f"\thttps://user:{FAKE}@example.org/feed\n", f"/feed?api_key={FAKE}", f"sitemap.xml?token={FAKE}",
    f"https:reader:{FAKE}@example.org/x", f"https:\\\\u:{FAKE}@example.org\\x", f"//u:{FAKE}@example.org/",
    f"https://example.org/f?api_\t_key={FAKE}", "https://example.org/f?lang=en&page=2", "plain text",
    "mailto:someone@example.org", "note: meet at 10", "https://example.org/a#section-2", "\x01https://e.org/?key=1\x20",
    "HTTPS://Example.ORG/?Authorization=x", "https://example.org/?q=a%26token%3Dx",
]


FIXTURE = Path(REPO_ROOT) / "tests" / "fixtures" / "url_canonicalisation_cases.json"


def test_K_python_postgresql_and_fixture_agree(pg):
    """The same fixture is asserted by apps/web/tests/sources.test.ts (TypeScript)."""
    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
    assert [c["input"] for c in cases] == CANON_CASES
    with pg.admin() as c:
        for case in cases:
            db = c.execute("SELECT lfhe.url_credential_problems(%s) AS p, lfhe.url_inspection_form(%s) AS f",
                           (case["input"], case["input"])).fetchone()
            assert db["p"] == url_credential_problems(case["input"]) == case["problems"], case["input"]
            assert db["f"] == url_inspection_form(case["input"]) == case["inspection_form"], case["input"]
