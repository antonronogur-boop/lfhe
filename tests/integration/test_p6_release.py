"""P6-06 / P6-07 — release PDF artifact, deterministic release eligibility, human release decision,
atomic manifest + RELEASED, RELEASED protection and the correction path (Phase 6 Addendum §19–§23,
§26, §29; acceptance behaviours 57–85). PDFs are produced by real headless Chromium."""
import base64
import json

import psycopg
import pytest

from lfhe_orchestrator.report_pdf import PDF_RENDERER_VERSION
from lfhe_orchestrator.report_render import RENDERER_VERSION, TEMPLATE_VERSION, template_sha256
from lfhe_shared.canonical_json import canonical_sha256
from lfhe_shared.storage import ObjectIntegrityError
from p5_helpers import content_of, edit
from p6_helpers import (activate, content, drafted, eligibility, make_pdf, park_jobs, qa, release, security, store,
                        through_security, workflow, write_version_unvalidated)

pytestmark = pytest.mark.db
IP = psycopg.errors.InsufficientPrivilege
MANIFEST_KEYS = {"format", "manifest_schema_version", "report", "report_version", "selection_set", "analytical_provenance", "qa",
                 "warning_acknowledgement_ids", "content_approval_id", "security_review_id", "release_decision_id", "released_by",
                 "release_timestamp", "rendering", "pdf"}


@pytest.fixture(scope="module")
def p6(pg):
    yield activate(pg)
    park_jobs(pg)


@pytest.fixture
def people(make_user):
    out = {r: make_user(r) for r in ("ANALYST", "REVIEWER", "SECURITY_REVIEWER", "RELEASE_AUTHORITY", "ADMIN", "VIEWER")}
    out["ADMIN+RA"] = make_user("ADMIN", "RELEASE_AUTHORITY")
    return out


def counts(pg, vid):
    with pg.admin() as x:
        return x.execute("""SELECT (SELECT count(*) FROM lfhe.release_decisions WHERE report_version_id=%(v)s AND decision='APPROVE_FOR_RELEASE') d,
                                   (SELECT count(*) FROM lfhe.release_manifests WHERE report_version_id=%(v)s) m,
                                   (SELECT count(*) FROM lfhe.report_releases WHERE report_version_id=%(v)s) r""", {"v": str(vid)}).fetchone()


def refused(pg, user, rv, pdf, match="RELEASE_NOT_ELIGIBLE"):
    before = counts(pg, rv["id"])
    with pytest.raises(psycopg.Error, match=match):
        release(pg, user, rv, pdf)
    assert counts(pg, rv["id"]) == before                                                              # 81: nothing partial


# --- 57–65: the PDF artifact and the manifest ------------------------------------------------------
def test_pdf_artifact_binding_hashes_manifest_and_immutability(pg, p6, people, tmp_path):
    a, ra = people["ANALYST"], people["RELEASE_AUTHORITY"]
    d, q, c, s = through_security(pg, a, people["REVIEWER"], people["SECURITY_REVIEWER"], "RPT-P6R-1")
    rv, objstore = d.rv, store(tmp_path)
    pdf = make_pdf(pg, rv, objstore)
    with pg.admin() as x:
        art = x.execute("SELECT *, encode(extensions.digest(pdf_bytes, 'sha256'), 'hex') AS recomputed FROM lfhe.release_pdf_artifacts "
                        "WHERE id=%s", (pdf["pdf_artifact_id"],)).fetchone()
    assert (str(art["report_version_id"]), art["report_version_hash"]) == (str(rv["id"]), rv["report_version_hash"])  # 57
    assert str(rv["id"]) in art["source_html"] and rv["report_version_hash"] in art["source_html"]
    assert "Draft preview" not in art["source_html"] and "release candidate" in art["source_html"]
    assert art["recomputed"] == art["pdf_sha256"] == pdf["pdf_sha256"] and art["byte_size"] == len(bytes(art["pdf_bytes"]))   # 58
    assert objstore.get(art["storage_key"]) == bytes(art["pdf_bytes"]) and art["mime_type"] == "application/pdf"
    assert (art["template_version"], art["template_hash"]) == (TEMPLATE_VERSION, template_sha256())                       # 60
    ident = art["renderer_identity"]
    assert art["renderer_version"] == PDF_RENDERER_VERSION and art["renderer_hash"] == canonical_sha256(ident)            # 61
    assert ident["html_renderer_version"] == RENDERER_VERSION and ident["chromium_version"].lower().startswith(("chromium", "google chrome"))
    assert not any(k in bytes(art["pdf_bytes"]) for k in (b"password", b"secret", b"/tmp/", b"file://"))
    # 57: a render of another version / a wrong hash cannot be bound
    other = drafted(pg, a, "RPT-P6R-1B")
    with pg.admin() as x:
        other_render = x.execute("SELECT id FROM lfhe.report_renders WHERE report_version_id=%s", (str(other.rv["id"]),)).fetchone()["id"]
    payload = {"report_version_id": str(rv["id"]), "report_version_hash": rv["report_version_hash"], "preview_render_id": str(other_render),
               "source_html": art["source_html"], "template_version": TEMPLATE_VERSION, "template_hash": art["template_hash"],
               "renderer_version": PDF_RENDERER_VERSION, "renderer_identity": ident, "storage_key": art["storage_key"],
               "pdf_base64": base64.b64encode(bytes(art["pdf_bytes"])).decode(), "worker_id": "p6-test"}
    with pg.worker() as w:
        with pytest.raises(psycopg.Error, match="PDF_RENDER_BINDING_INVALID"):
            w.execute("SELECT lfhe.record_release_pdf(%s::jsonb)", (json.dumps(payload),))
        with pytest.raises(psycopg.Error, match="VERSION_HASH_MISMATCH"):
            w.execute("SELECT lfhe.record_release_pdf(%s::jsonb)", (json.dumps(dict(payload, report_version_hash="0" * 64)),))
        with pytest.raises(psycopg.Error, match="NO_RELEASE_CANDIDATE"):
            w.execute("SELECT lfhe.record_release_pdf(%s::jsonb)", (json.dumps(dict(payload, report_version_id=str(other.rv["id"]),
                                                                                    report_version_hash=other.rv["report_version_hash"])),))
    # 59: stored bytes and hash can never disagree (CHECK holds even with triggers disabled); storage detects tampering
    with pg.admin(autocommit=False) as x, pytest.raises(psycopg.Error):
        x.execute("SET LOCAL session_replication_role = replica")
        x.execute("UPDATE lfhe.release_pdf_artifacts SET pdf_bytes = pdf_bytes || '\\x00'::bytea WHERE id=%s", (pdf["pdf_artifact_id"],))
    path = objstore.root / art["storage_key"]
    path.chmod(0o644)
    path.write_bytes(b"%PDF-1.4 tampered")
    with pytest.raises(ObjectIntegrityError):
        objstore.get(art["storage_key"])
    # a materially different byte artifact gets its own identity
    again = make_pdf(pg, rv, store(tmp_path / "second"))
    assert again["pdf_artifact_id"] == pdf["pdf_artifact_id"] if again["pdf_sha256"] == pdf["pdf_sha256"] else \
        again["pdf_artifact_id"] != pdf["pdf_artifact_id"]
    el = eligibility(pg, ra, rv, pdf["pdf_artifact_id"])
    assert el["eligible"] is True, el["failed"]
    r = release(pg, ra, rv, pdf["pdf_artifact_id"])
    with pg.admin() as x:
        man = x.execute("SELECT * FROM lfhe.release_manifests WHERE id=%s", (r["release_manifest_id"],)).fetchone()
        rebuilt = x.execute("SELECT lfhe.p6_build_manifest(%s) m", (r["release_decision_id"],)).fetchone()["m"]
        sql_hash = x.execute("SELECT lfhe.jcs_sha256(manifest_json) h FROM lfhe.release_manifests WHERE id=%s",
                             (r["release_manifest_id"],)).fetchone()["h"]
    mj = man["manifest_json"]
    assert MANIFEST_KEYS <= set(mj) and mj["report_version"]["report_version_hash"] == rv["report_version_hash"]            # 62
    assert mj["qa"]["deterministic_qa_run_id"] == q.deterministic_qa_run_id and mj["qa"]["semantic_qa_run_id"] == q.semantic_qa_run_id
    assert mj["qa"]["m10_prompt_hash"] and mj["qa"]["m10s_model_run_id"] and mj["content_approval_id"] == c["content_approval_id"]
    assert mj["security_review_id"] == s["security_review_id"] and mj["pdf"]["pdf_sha256"] == pdf["pdf_sha256"]
    assert mj["rendering"]["renderer_hash"] == art["renderer_hash"] and mj["rendering"]["template_hash"] == art["template_hash"]
    assert mj["released_by"] == str(ra) and mj["report"]["information_cutoff"] and mj["selection_set"]["hash"]
    assert mj["analytical_provenance"][0]["assessment_version"]["analytical_approval_id"]
    assert man["manifest_hash"] == sql_hash == canonical_sha256(mj) == r["manifest_hash"] and rebuilt == mj                # 63
    with pg.admin() as x:
        for sql in ("UPDATE lfhe.release_manifests SET manifest_json = '{}'::jsonb WHERE id=%s",                            # 64
                    "DELETE FROM lfhe.release_manifests WHERE id=%s"):
            with pytest.raises(psycopg.Error):
                x.execute(sql, (r["release_manifest_id"],))
        with pytest.raises(psycopg.Error):
            x.execute("TRUNCATE lfhe.release_manifests CASCADE")
        for sql in ("UPDATE lfhe.release_pdf_artifacts SET storage_key = storage_key WHERE id=%s",                         # 65
                    "DELETE FROM lfhe.release_pdf_artifacts WHERE id=%s"):
            with pytest.raises(psycopg.Error):
                x.execute(sql, (pdf["pdf_artifact_id"],))
    assert objstore.put_if_absent is not None


# --- 66–79, 81: eligibility gates and who may release ----------------------------------------------
def test_release_gates_and_release_authority(pg, p6, people, tmp_path):
    a, rev, sec, ra = people["ANALYST"], people["REVIEWER"], people["SECURITY_REVIEWER"], people["RELEASE_AUTHORITY"]
    objstore = store(tmp_path)
    d = drafted(pg, a, "RPT-P6R-2")
    refused(pg, ra, d.rv, None)                                                                        # 66: no QA
    el = eligibility(pg, ra, d.rv)
    assert {"QA_BOUND_TO_VERSION", "M10D_COMPLETE", "M10S_COMPLETE", "CONTENT_APPROVED", "SECURITY_APPROVED", "PDF_EXISTS"} <= set(el["failed"])
    bad = write_version_unvalidated(pg, d.rv, lambda c: (c["key_judgments"][0]["statements"][0].__setitem__("text", "NATO SECRET note."), c)[1],
                                    user=a)
    qf = qa(pg, a, bad)
    assert qf.status == "FAIL"
    refused(pg, ra, bad, None)                                                                         # 67
    assert "QA_ACCEPTABLE" in eligibility(pg, ra, bad)["failed"]
    dup = write_version_unvalidated(pg, d.rv, lambda c: (c["key_judgments"].append(dict(
        c["key_judgments"][0], item_local_id="KJDUP", statements=[dict(s, report_statement_local_id=f"RS{70 + n}")
                                                                  for n, s in enumerate(c["key_judgments"][0]["statements"])])), c)[1],
                                    user=a)
    qw = qa(pg, a, dup)
    assert qw.status == "PASS_WITH_WARNINGS"
    el = eligibility(pg, ra, dup)
    assert "QA_ACCEPTABLE" in el["failed"] and el["checks"][7]["unacknowledged_warnings"]               # 68
    good = write_version_unvalidated(pg, d.rv, lambda c: c, user=a)
    q = qa(pg, a, good)
    refused(pg, ra, good, None)                                                                        # 69: no content approval
    assert "CONTENT_APPROVED" in eligibility(pg, ra, good)["failed"]
    c = content(pg, rev, good, q.qa_result_id)
    refused(pg, ra, good, None)                                                                        # 70: security PENDING
    assert "SECURITY_APPROVED" in eligibility(pg, ra, good)["failed"]
    s = security(pg, sec, good, c["security_review_id"])
    pdf = make_pdf(pg, good, objstore)
    pid = pdf["pdf_artifact_id"]
    # 72–74: non-human principals have no EXECUTE at all
    for conn in (pg.worker, pg.as_service_role, pg.as_anon):
        with conn() as cx, pytest.raises(IP):
            cx.execute("SELECT lfhe.release_report(%s, %s, %s, 'automated release attempt here')",
                       (str(good["id"]), good["report_version_hash"], pid))
    # 75–78: human roles without RELEASE_DECIDE
    for role in ("ADMIN", "ANALYST", "REVIEWER", "SECURITY_REVIEWER", "VIEWER"):
        before = counts(pg, good["id"])
        with pytest.raises(IP):
            release(pg, people[role], good, pid)
        assert counts(pg, good["id"]) == before
    # direct writes cannot create RELEASED (guard trigger refuses even the owner outside release_report)
    with pg.admin() as x:
        with pytest.raises(psycopg.Error, match="RELEASED_WRITE_PROHIBITED"):
            x.execute("INSERT INTO lfhe.release_decisions (report_id, report_version_id, report_version_hash, decision, eligibility, "
                      "decided_by, rationale) VALUES (%s, %s, %s, 'APPROVE_FOR_RELEASE', '{\"eligible\": true}', %s, 'forged release decision')",
                      (d.rid, str(good["id"]), good["report_version_hash"], str(ra)))
    with pg.as_user(ra) as h, pytest.raises(psycopg.Error):
        h.execute("INSERT INTO lfhe.report_releases (report_id, report_version_id, report_version_hash, release_decision_id, "
                  "release_manifest_id, manifest_hash, pdf_artifact_id, pdf_sha256, released_by, released_at) "
                  "VALUES (%s, %s, %s, gen_random_uuid(), gen_random_uuid(), 'x', %s, 'x', %s, now())",
                  (d.rid, str(good["id"]), good["report_version_hash"], pid, str(ra)))
    # 71: a newer version makes this candidate stale
    stale_probe = write_version_unvalidated(pg, good, lambda c: c, user=a)
    refused(pg, ra, good, pid)
    assert "VERSION_CURRENT" in eligibility(pg, ra, good, pid)["failed"]
    assert stale_probe["version_no"] == good["version_no"] + 1
    # 75 / 79 / 80: a human with RELEASE_AUTHORITY (here also ADMIN — K-06) releases once every condition passes
    d2, q2, c2, s2 = through_security(pg, a, rev, sec, "RPT-P6R-3")
    pdf2 = make_pdf(pg, d2.rv, objstore)
    el2 = eligibility(pg, people["ADMIN+RA"], d2.rv, pdf2["pdf_artifact_id"])
    assert el2["eligible"] is True and el2["failed"] == []
    assert "CALLER_HUMAN_RELEASE_AUTHORITY" in eligibility(pg, people["ADMIN"], d2.rv, pdf2["pdf_artifact_id"])["failed"]
    r = release(pg, people["ADMIN+RA"], d2.rv, pdf2["pdf_artifact_id"])
    assert r["state"] == "RELEASED" and counts(pg, d2.rv["id"]) == {"d": 1, "m": 1, "r": 1}            # 80: atomically together
    with pg.admin() as x:
        rel = x.execute("SELECT * FROM lfhe.report_releases WHERE id=%s", (r["report_release_id"],)).fetchone()
        dec = x.execute("SELECT * FROM lfhe.release_decisions WHERE id=%s", (r["release_decision_id"],)).fetchone()
    assert rel["released_at"] == dec["created_at"] and str(rel["released_by"]) == str(people["ADMIN+RA"])
    assert str(dec["qa_result_id"]) == q2.qa_result_id and str(dec["security_review_id"]) == s2["security_review_id"]
    refused(pg, people["ADMIN+RA"], d2.rv, pdf2["pdf_artifact_id"])                                  # second release refused
    assert workflow(pg, d2.rv)["workflow_state"] == "RELEASED"
    assert s["status"] == "APPROVED"


# --- 82, 83: RETURN / REJECT never modify the report and never release ------------------------------
def test_return_and_reject_release(pg, p6, people, tmp_path):
    a, rev, sec, ra = people["ANALYST"], people["REVIEWER"], people["SECURITY_REVIEWER"], people["RELEASE_AUTHORITY"]
    objstore = store(tmp_path)
    for decision, state, event in (("RETURN_FOR_REVISION", "RELEASE_RETURNED_FOR_REVISION", "RELEASE_RETURNED_FOR_REVISION"),
                                   ("REJECT_RELEASE", "RELEASE_REJECTED", "REPORT_RELEASE_REJECTED")):
        d, q, c, s = through_security(pg, a, rev, sec, f"RPT-P6R-{decision[:3]}")
        pdf = make_pdf(pg, d.rv, objstore)
        with pg.admin() as x:
            n_before = x.execute("SELECT count(*) n FROM lfhe.report_versions WHERE report_id=%s", (d.rid,)).fetchone()["n"]
        with pytest.raises(psycopg.Error, match="RELEASE_DECISION_NOT_ALLOWED_HERE"):
            with pg.as_user(ra) as h:
                h.execute("SELECT lfhe.decide_release(%s, %s, 'APPROVE_FOR_RELEASE', 'approve via the wrong door')",
                          (str(d.rv["id"]), d.rv["report_version_hash"]))
        with pg.as_user(ra) as h:
            h.execute("SELECT lfhe.decide_release(%s, %s, %s, 'release authority decision with reasons')",
                      (str(d.rv["id"]), d.rv["report_version_hash"], decision))
        with pg.admin() as x:
            n_after = x.execute("SELECT count(*) n FROM lfhe.report_versions WHERE report_id=%s", (d.rid,)).fetchone()["n"]
            same = x.execute("SELECT report_version_hash h FROM lfhe.report_versions WHERE id=%s", (str(d.rv["id"]),)).fetchone()["h"]
            ev = x.execute("SELECT count(*) n FROM lfhe.audit_log WHERE event_type=%s AND object_id=%s", (event, str(d.rv["id"]))).fetchone()["n"]
        assert n_before == n_after and same == d.rv["report_version_hash"] and ev == 1
        assert workflow(pg, d.rv)["workflow_state"] == state and counts(pg, d.rv["id"]) == {"d": 0, "m": 0, "r": 0}
        refused(pg, ra, d.rv, pdf["pdf_artifact_id"])                                                  # 82 / 83
        assert "NOT_RETURNED_OR_REJECTED" in eligibility(pg, ra, d.rv, pdf["pdf_artifact_id"])["failed"]
        with pytest.raises(psycopg.Error, match="RELEASE_ALREADY_DECIDED"):
            with pg.as_user(ra) as h:
                h.execute("SELECT lfhe.decide_release(%s, %s, 'REJECT_RELEASE', 'second decision on the same candidate')",
                          (str(d.rv["id"]), d.rv["report_version_hash"]))


# --- 84, 85: released versions are immutable; a correction is a new version through everything ------
def test_released_version_is_immutable_and_correction_needs_the_full_sequence(pg, p6, people, tmp_path):
    a, rev, sec, ra = people["ANALYST"], people["REVIEWER"], people["SECURITY_REVIEWER"], people["RELEASE_AUTHORITY"]
    objstore = store(tmp_path)
    d, q, c, s = through_security(pg, a, rev, sec, "RPT-P6R-6")
    pdf = make_pdf(pg, d.rv, objstore)
    r = release(pg, ra, d.rv, pdf["pdf_artifact_id"])
    with pg.admin() as x:                                                                              # 84
        for sql in ("UPDATE lfhe.report_versions SET canonical_json = canonical_json WHERE id=%s",
                    "UPDATE lfhe.report_releases SET released_at = now() WHERE report_version_id=%s",
                    "DELETE FROM lfhe.report_releases WHERE report_version_id=%s",
                    "UPDATE lfhe.release_decisions SET rationale = 'rewritten after release' WHERE report_version_id=%s"):
            with pytest.raises(psycopg.Error):
                x.execute(sql, (str(d.rv["id"]),))
        snap = x.execute("SELECT m.manifest_hash, a.pdf_sha256, v.report_version_hash FROM lfhe.report_releases rr "
                         "JOIN lfhe.release_manifests m ON m.id = rr.release_manifest_id JOIN lfhe.release_pdf_artifacts a ON a.id = rr.pdf_artifact_id "
                         "JOIN lfhe.report_versions v ON v.id = rr.report_version_id WHERE rr.id=%s", (r["report_release_id"],)).fetchone()
    with pytest.raises(psycopg.Error, match="REPORT_VERSION_RELEASED"):
        with pg.as_user(a) as h:
            h.execute("SELECT lfhe.request_report_qa(%s, %s, 'requalify the released version')", (str(d.rv["id"]), d.rv["report_version_hash"]))
    # 85: a human correction creates vN+1, emits REPORT_CORRECTION_CREATED and starts from QA again
    cc = content_of(pg, d.rv["id"])
    st = cc["key_judgments"][0]["statements"][-1]
    st["text"], st["editorial_transform"] = st["text"].rstrip(".") + " at the base.", "PARAPHRASE"
    v2 = edit(pg, a, d.rv, cc, "post-release correction of one sentence")
    with pg.admin() as x:
        r2 = x.execute("SELECT * FROM lfhe.report_versions WHERE id=%s", (v2["report_version_id"],)).fetchone()
        corr = x.execute("SELECT * FROM lfhe.audit_log WHERE event_type='REPORT_CORRECTION_CREATED' AND object_id=%s",
                         (str(r2["id"]),)).fetchone()
    assert corr and corr["new_state"]["released_report_version_id"] == str(d.rv["id"]) and corr["new_state"]["manifest_hash"] == r["manifest_hash"]
    assert workflow(pg, r2)["workflow_state"] == "DRAFT_VERSION" and workflow(pg, d.rv)["workflow_state"] == "RELEASED"
    el = eligibility(pg, ra, r2)
    assert el["eligible"] is False and {"QA_BOUND_TO_VERSION", "CONTENT_APPROVED", "SECURITY_APPROVED"} <= set(el["failed"])
    from lfhe_orchestrator.report_render import render_and_record
    with pg.worker() as w:
        render_and_record(w, str(r2["id"]), r2["report_version_hash"], worker_id="p6-test")
    q2 = qa(pg, a, r2)
    c2 = content(pg, rev, r2, q2.qa_result_id)
    security(pg, sec, r2, c2["security_review_id"])
    pdf2 = make_pdf(pg, r2, objstore)
    rr2 = release(pg, ra, r2, pdf2["pdf_artifact_id"])
    assert rr2["manifest_hash"] != r["manifest_hash"] and rr2["release_decision_id"] != r["release_decision_id"]
    with pg.admin() as x:
        snap2 = x.execute("SELECT m.manifest_hash, a.pdf_sha256, v.report_version_hash FROM lfhe.report_releases rr "
                          "JOIN lfhe.release_manifests m ON m.id = rr.release_manifest_id JOIN lfhe.release_pdf_artifacts a ON a.id = rr.pdf_artifact_id "
                          "JOIN lfhe.report_versions v ON v.id = rr.report_version_id WHERE rr.id=%s", (r["report_release_id"],)).fetchone()
        prev = x.execute("SELECT manifest_json -> 'report_version' ->> 'previous_report_version_id' p FROM lfhe.release_manifests "
                         "WHERE id=%s", (rr2["release_manifest_id"],)).fetchone()["p"]
    assert snap2 == snap and prev == str(d.rv["id"])                                                   # predecessor preserved
