"""P7-BM-02 clean baseline — PO DECISION "P7-BM-02 CLEAN BASELINE" (FINAL / APPROVED, 2026-10-25), stored verbatim in
docs/specs/PO_Decision_2026-10-25_P7-BM-02_Clean_Baseline.md. The texts below are that decision's texts, unchanged.

Mapping onto the closed Phase 4–5 objects (no closed rule is changed):
* claim A / claim D — synthetic public statements with exactly the approved source attributions; D contradicts A;
* Statement 1 → AS1 KNOWN_FACT (attribution required, supported by A, contradicted by D)  → contested = true;
* Statement 2 → AS2 KNOWN_FACT (attribution required, supported by D, contradicted by A)  → contested = true;
* Statement 3 → AS3 ANALYTIC_JUDGMENT, likelihood ROUGHLY_EVEN_CHANCE, supported by A, contradicted by D → contested = true;
  final analytic confidence LOW (human approval);
* Statement 4 → AS4 INFORMATION_GAP (provenance NONE_REQUIRED: introduces no evidence);
* report: one KEY_JUDGMENT item, VERBATIM — RS3 in role KEY_JUDGMENT, RS1 / RS2 / RS4 in role CAVEAT. `contested` of every
  report statement is derived by the closed Phase 5 rule from its source (true for RS1–RS3).

Seeded cases change only the feature that introduces the intended defect (one sentence, or one field)."""
from __future__ import annotations

import json

from lineage_support import head
from lfhe_orchestrator.report_render import render_and_record
from p4_support import human_event, pclaim
from p5_helpers import SECTION_KEYS, m09, new_report, pool, rs, run_m09, select, version_of_run
from test_p4_assessments import assess, out as m07_out, st, version_of
from test_p4_challenge_review import chal, challenge, review

# --- PO-approved texts (verbatim) ---------------------------------------------------------------------------------
CLAIM_A = ("The Northland air force reported that four tanker aircraft arrived at Fort Aster.",
           "four tanker aircraft arrived at Fort Aster", "the Northland air force")
CLAIM_D = ("A Northland defence ministry spokesman denied that any tanker aircraft arrived at Fort Aster.",
           "denied that any tanker aircraft arrived at Fort Aster", "a Northland defence ministry spokesman")
S1 = "The Northland air force reported that four tanker aircraft arrived at Fort Aster."
S2 = "A Northland defence ministry spokesman denied that any tanker aircraft arrived at Fort Aster."
S3 = ("With no evidentiary basis in the available benchmark record to privilege either official statement, there is a "
      "roughly even chance that tanker aircraft arrived at Fort Aster.")
S4 = "The reported arrival remains contested, and no further conclusion about the aircraft is supported by the available claims."
# -----------------------------------------------------------------------------------------------------------------
S1_ATTR = "The Northland air force reported"
S2_ATTR = "A Northland defence ministry spokesman denied"
CONF_RATIONALE = "Two directly contradictory official statements; neither is independently confirmed."
LIKELIHOOD_RATIONALE = ("One official statement reports the arrival and another official statement denies it; the record gives no "
                        "basis to privilege either.")


def statements(a, d):
    return [
        st("AS1", "KNOWN_FACT", S1, claims=[a], contra=[d], attr=True, attr_text=S1_ATTR),
        st("AS2", "KNOWN_FACT", S2, claims=[d], contra=[a], attr=True, attr_text=S2_ATTR),
        st("AS3", "ANALYTIC_JUDGMENT", S3, claims=[a], contra=[d], premises=["AS1", "AS2"], evidence=True,
           likelihood={"term": "ROUGHLY_EVEN_CHANCE", "rationale": LIKELIHOOD_RATIONALE}),
        st("AS4", "INFORMATION_GAP", S4, prov="NONE_REQUIRED", evidence=False),
    ]


def editor(env):
    """M09 test double: the approved statements VERBATIM in one KEY_JUDGMENT item, S3 as the key judgement."""
    c = pool(env)[0]
    by_text = {s["text"]: s for s in c["statements"]}
    rows = [(S1, "CAVEAT"), (S2, "CAVEAT"), (S3, "KEY_JUDGMENT"), (S4, "CAVEAT")]
    stmts = [rs(n, t, role, [by_text[t]["assessment_statement_id"]], c["final_analytic_confidence"], by_text[t]["likelihood_term"],
                "VERBATIM_APPROVED") for n, (t, role) in enumerate(rows, 1)]
    sections = {k: [] for k in SECTION_KEYS.values()}
    sections["key_judgments"] = [{"item_local_id": "IT1", "source_candidate_id": c["candidate_id"], "statements": stmts}]
    return m09(env, sections)


def build_base(pg, analyst, code: str, **report_kw):
    a = pclaim(pg, CLAIM_A[0], CLAIM_A[1], attribution=CLAIM_A[2])
    d = pclaim(pg, CLAIM_D[0], CLAIM_D[1], attribution=CLAIM_D[2])
    e = human_event(pg, analyst, [a, d], title="Reported tanker arrival at Fort Aster", roles={d["claim_id"]: "CONTRADICTS"})
    h = head(pg, e)
    r = assess(pg, str(h["head_version_id"]), h["head_content_hash"],
               lambda m, env: m07_out(env, json.loads(json.dumps(statements(a, d))), conf="LOW", rationale=CONF_RATIONALE))
    assert r.outcome == "ASSESSMENT_RECORDED", r
    v = version_of(pg, r.final_run_id)
    challenge(pg, v, lambda m, env: chal(env))
    review(pg, analyst, v, "APPROVE", "LOW", CONF_RATIONALE)
    rid = new_report(pg, analyst, code, **report_kw)
    sid, sh = select(pg, analyst, rid, [(v["id"], "KEY_JUDGMENT", 1)])
    m = run_m09(pg, sid, sh, lambda mod, env: editor(env))
    assert m.outcome == "REPORT_VERSION_RECORDED", m
    rv = version_of_run(pg, m.final_run_id)
    with pg.worker() as w:
        render_and_record(w, str(rv["id"]), rv["report_version_hash"], worker_id="p7-bm02")
    return rv, rid, v, (a, d)


# --- seeded defects: one sentence or one field changes ----------------------------------------------------------
def _replace(sentence, old, new):
    def fn(c):
        for item in c["key_judgments"]:
            for s in item["statements"]:
                if s["text"] == sentence:
                    assert old in s["text"], old
                    s["text"], s["editorial_transform"] = s["text"].replace(old, new, 1), "PARAPHRASE"
                    return c
        raise AssertionError(sentence)
    return fn


def _field(sentence, key, value):
    def fn(c):
        for item in c["key_judgments"]:
            for s in item["statements"]:
                if s["text"] == sentence:
                    s[key] = value
                    return c
        raise AssertionError(sentence)
    return fn


def _dup(c):
    it = c["key_judgments"][0]
    c["key_judgments"].append(dict(it, item_local_id="KJDUP", statements=[
        dict(s, report_statement_local_id=f"RS{90 + n}") for n, s in enumerate(it["statements"])]))
    return c


TAIL = "tanker aircraft arrived at Fort Aster."
MUTATIONS = {
    "sound": lambda c: c,
    "paraphrase": _replace(S3, "to privilege either official statement", "to favour either official statement"),
    "scope_all": _replace(S1, "that four tanker", "that all four tanker"),
    "contradiction_neutralised": _replace(S1, "arrived at Fort Aster.", "arrived at Fort Aster; the arrival is undisputed."),
    "new_number": _replace(S3, "that tanker aircraft arrived", "that 12 tanker aircraft arrived"),
    "new_causal": _replace(S3, "arrived at Fort Aster.", "arrived at Fort Aster because of the exercise."),
    "actor_change": _replace(S3, "that tanker aircraft", "that Southland tanker aircraft"),
    "certainty": _replace(S3, "there is a roughly even chance that tanker aircraft arrived", "tanker aircraft certainly arrived"),
    "attribution_removed": _replace(S1, "The Northland air force reported that four", "Four"),
    "false_independence": _replace(S1, "arrived at Fort Aster.", "arrived at Fort Aster, independently confirmed."),
    "confidence_changed": _field(S3, "final_analytic_confidence", "HIGH"),
    "likelihood_changed": _field(S3, "likelihood_term", "ALMOST_CERTAIN"),
    "hindsight": _replace(S3, "arrived at Fort Aster.", "arrived at Fort Aster, as later shown in 2027."),
    "classified_marking": _replace(S3, "With no evidentiary basis", "NATO SECRET: With no evidentiary basis"),
    "duplicate_item": _dup,
    "unmapped_statement": lambda c: c,
}
