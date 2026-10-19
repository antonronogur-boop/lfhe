"""P4-01 — baselines, reference contexts, as-of claim status (Phase 4 Addendum §5, §6, §19;
required tests 10–17)."""
import json

import psycopg
import pytest

from p4_support import (CUT, FAR, KNOW, LATER, POST, PRE, approve, create_baseline, create_rc, pclaim, ref,
                        version_hash, worker_value)

pytestmark = pytest.mark.db


@pytest.fixture
def analyst(make_user):
    return make_user("ANALYST")


def usable(pg, kind, version, mode="REPLAY", cutoff=CUT):
    fn = {"baseline": "baseline_version_usable", "rc": "reference_context_version_usable"}[kind]
    return worker_value(pg, f"SELECT lfhe.{fn}(%s, %s, %s) r", version, mode, cutoff)


def tank(pg, when=PRE, n=4):
    return pclaim(pg, f"The air force said {n} tanker aircraft are based at Fort Aster.",
                  f"{n} tanker aircraft are based at Fort Aster", when)


# --- 10, 11: immutable and hash-bound ------------------------------------------------
def test_baseline_and_reference_context_versions_are_immutable_and_hash_bound(pg, analyst):
    c = tank(pg)
    bl = create_baseline(pg, analyst, "BL-IMM-1", [("4 tankers at Fort Aster", [("claim", c["claim_id"])])])
    rc = create_rc(pg, analyst, "RC-IMM-1", [c])
    for table, vid in (("baseline_versions", bl), ("reference_context_versions", rc)):
        with pg.admin() as x:
            row = x.execute(f"SELECT * FROM lfhe.{table} WHERE id=%s", (vid,)).fetchone()
            assert len(row["content_hash"]) == 64
            for sql in (f"UPDATE lfhe.{table} SET reason='tampered reason' WHERE id=%s", f"DELETE FROM lfhe.{table} WHERE id=%s"):
                with pytest.raises(psycopg.Error):
                    x.execute(sql, (vid,))
    with pg.admin() as x, pytest.raises(psycopg.errors.CheckViolation):   # content/hash binding is a CHECK
        x.execute("INSERT INTO lfhe.baseline_versions (baseline_id, version_no, previous_version_id, knowledge_as_of,"
                  " content, content_hash, created_by, reason) SELECT baseline_id, 99, id, knowledge_as_of, content,"
                  " content_hash, created_by, reason FROM lfhe.baseline_versions WHERE id=%s", (bl,))
    with pg.as_user(analyst) as h, pytest.raises(psycopg.errors.SerializationFailure, match="VERSION_HASH_MISMATCH"):
        h.execute("SELECT lfhe.decide_baseline_version(%s, %s, 'APPROVE', 'stale hash approval')", (bl, "0" * 64))


def test_unattributed_or_anachronistic_content_is_refused(pg, analyst):
    c = tank(pg)
    late = tank(pg, POST, 5)
    with pg.as_user(analyst) as h:
        with pytest.raises(psycopg.errors.CheckViolation, match="BASELINE_COMPONENT_UNATTRIBUTED"):
            h.execute("SELECT lfhe.create_baseline_version(%s::jsonb, 'free text baseline')", (json.dumps({
                "code": "BL-FREE-1", "title": "Free", "scope": "free text", "knowledge_as_of": KNOW,
                "components": [{"text": "Northland has many tankers", "evidence": []}]}),))
        with pytest.raises(psycopg.errors.CheckViolation, match="EVIDENCE_POSTDATES_KNOWLEDGE_AS_OF"):
            h.execute("SELECT lfhe.create_baseline_version(%s::jsonb, 'anachronistic baseline')", (json.dumps({
                "code": "BL-ANA-1", "title": "Ana", "scope": "x", "knowledge_as_of": KNOW,
                "components": [{"text": "5 tankers", "evidence": [ref("claim", late["claim_id"])]}]}),))
        with pytest.raises(psycopg.errors.CheckViolation, match="REFERENCE_CONTEXT_PROVENANCE_REQUIRED"):   # 17
            h.execute("SELECT lfhe.create_reference_context_version(%s::jsonb, 'no provenance given')", (json.dumps({
                "code": "RC-NOPROV-1", "context_type": "CAPABILITY_BASELINE", "title": "No provenance",
                "text": "Northland air force general background.", "knowledge_as_of": KNOW, "provenance_refs": []}),))
        with pytest.raises(psycopg.errors.CheckViolation, match="EVIDENCE_REFERENCE_INVALID"):
            h.execute("SELECT lfhe.create_reference_context_version(%s::jsonb, 'invented provenance')", (json.dumps({
                "code": "RC-FAKE-1", "context_type": "CAPABILITY_BASELINE", "title": "Fake", "text": "Invented background text.",
                "knowledge_as_of": KNOW, "provenance_refs": [ref("claim", "00000000-0000-4000-8000-000000000001")]}),))
    assert c


# --- 12, 13, 14, 15: baseline usability is knowledge-bound ---------------------------
def test_baseline_usability_follows_knowledge_and_evidence_not_decision_time(pg, analyst):
    c = tank(pg)
    v1 = create_baseline(pg, analyst, "BL-ASOF-1", [("4 tankers at Fort Aster", [("claim", c["claim_id"])])])
    assert usable(pg, "baseline", v1) is False                     # not approved yet
    approve(pg, analyst, "baseline", v1)                          # approved now, i.e. after CUT
    assert usable(pg, "baseline", v1) is True                      # 13: decided after cutoff, evidence eligible
    late_c = tank(pg, POST, 6)
    v2 = create_baseline(pg, analyst, "BL-ASOF-1", [("6 tankers at Fort Aster", [("claim", late_c["claim_id"])])],
                         as_of=LATER, reason="later state")
    approve(pg, analyst, "baseline", v2)
    assert usable(pg, "baseline", v2) is False                     # 12: knowledge_as_of > cutoff
    with pg.worker() as w:
        bl = w.execute("SELECT baseline_id FROM lfhe.baseline_versions WHERE id=%s", (v1,)).fetchone()["baseline_id"]
        assert str(w.execute("SELECT lfhe.baseline_asof(%s, 'REPLAY', %s) r", (bl, CUT)).fetchone()["r"]) == v1   # 15
        assert str(w.execute("SELECT lfhe.baseline_asof(%s, 'LIVE', %s) r", (bl, FAR)).fetchone()["r"]) == v2
    # 14: a factual component not eligible at the run's cutoff prevents use (LIVE: retrieved after the cutoff)
    assert usable(pg, "baseline", v1, "LIVE", KNOW) is False
    rejected = create_baseline(pg, analyst, "BL-REJ-1", [("4 tankers", [("claim", c["claim_id"])])])
    approve(pg, analyst, "baseline", rejected, "REJECT")
    assert usable(pg, "baseline", rejected) is False


def test_baseline_component_on_an_unusable_reference_context_is_unusable(pg, analyst):
    c = tank(pg)
    rc = create_rc(pg, analyst, "RC-DEP-1", [c])                  # not approved
    v = create_baseline(pg, analyst, "BL-DEP-1", [("context-based component", [("reference_context_version", rc)])])
    approve(pg, analyst, "baseline", v)
    assert usable(pg, "baseline", v) is False
    approve(pg, analyst, "rc", rc)
    assert usable(pg, "baseline", v) is True


# --- 16, 17: reference context ----------------------------------------------------------
def test_reference_context_usability_and_replay_never_receives_a_later_version(pg, analyst):
    c = tank(pg)
    v1 = create_rc(pg, analyst, "RC-ASOF-1", [c])
    assert usable(pg, "rc", v1) is False                           # human approval before use
    approve(pg, analyst, "rc", v1)
    assert usable(pg, "rc", v1) is True
    late_c = tank(pg, POST, 7)
    v2 = create_rc(pg, analyst, "RC-ASOF-1", [late_c], as_of=LATER, text="Northland now operates a larger tanker fleet.")
    approve(pg, analyst, "rc", v2)
    with pg.worker() as w:
        rc = w.execute("SELECT reference_context_id FROM lfhe.reference_context_versions WHERE id=%s", (v1,)).fetchone()
        rid = rc["reference_context_id"]
        assert str(w.execute("SELECT lfhe.reference_context_asof(%s, 'REPLAY', %s) r", (rid, CUT)).fetchone()["r"]) == v1
        assert str(w.execute("SELECT lfhe.reference_context_asof(%s, 'LIVE', %s) r", (rid, FAR)).fetchone()["r"]) == v2
    with pg.admin() as x:                                          # provenance rows removed → unusable (defence in depth)
        x.execute("ALTER TABLE lfhe.reference_context_provenance DISABLE TRIGGER reference_context_provenance_immutable")
        x.execute("DELETE FROM lfhe.reference_context_provenance WHERE reference_context_version_id=%s", (v1,))
        x.execute("ALTER TABLE lfhe.reference_context_provenance ENABLE TRIGGER reference_context_provenance_immutable")
    assert usable(pg, "rc", v1) is False


def test_non_humans_cannot_create_or_approve(pg, make_user, analyst):
    c = tank(pg)
    v = create_baseline(pg, analyst, "BL-RBAC-1", [("x tankers", [("claim", c["claim_id"])])])
    viewer, admin = make_user("VIEWER"), make_user("ADMIN")
    spec = json.dumps({"code": "BL-RBAC-2", "title": "t", "scope": "s", "knowledge_as_of": KNOW,
                       "components": [{"text": "x", "evidence": [ref("claim", c["claim_id"])]}]})
    calls = [("SELECT lfhe.create_baseline_version(%s::jsonb, 'not allowed')", (spec,)),
             ("SELECT lfhe.decide_baseline_version(%s, %s, 'APPROVE', 'not allowed')",
              (v, version_hash(pg, "baseline_versions", v))),
             ("SELECT lfhe.create_reference_context_version(%s::jsonb, 'not allowed')", (json.dumps({
                 "code": "RC-RBAC-1", "context_type": "X_TYPE", "title": "t", "text": "background text here",
                 "knowledge_as_of": KNOW, "provenance_refs": [ref("claim", c["claim_id"])]}),))]
    for sql, args in calls:
        for conn in (pg.worker, pg.as_service_role, pg.as_anon, lambda: pg.as_user(viewer), lambda: pg.as_user(admin)):
            with conn() as x, pytest.raises(psycopg.errors.InsufficientPrivilege):
                x.execute(sql, args)


# --- as-of claim status (§10, §19) ----------------------------------------------------
def test_claim_status_asof_ignores_later_unbounded_human_decisions_in_replay(pg, analyst):
    c = tank(pg)
    with pg.as_user(analyst) as h:
        h.execute("SELECT lfhe.set_claim_status(%s, 'UNVERIFIED', 'CORROBORATED', 'analyst corroborates later')",
                  (c["claim_id"],))
    with pg.worker() as w:
        replay = w.execute("SELECT * FROM lfhe.claim_status_asof(%s, 'REPLAY', %s)", (c["claim_id"], CUT)).fetchone()
        live = w.execute("SELECT * FROM lfhe.claim_status_asof(%s, 'LIVE', %s)", (c["claim_id"], FAR)).fetchone()
    assert replay["claim_status"] == "UNVERIFIED" and live["claim_status"] == "CORROBORATED"
