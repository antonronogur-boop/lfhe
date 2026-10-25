"""P7-BM-02 base fixture — an internally consistent synthetic 'Northland' report version (P7-05).

P7-BM-01 reused the Phase 4–6 test chain, whose synthetic claims carry the attribution "the ministry" while the
assessment says "The air force reported" / "a spokesman denied", and whose key judgement ("Northland is probably
expanding air-refuelling support") does not follow from the claims. The real M10-S correctly flagged those, so the
BM-01 false-alarm measure was invalid (CG7 report, 2026-10-25). This base is built so that, to a human evaluator,
every report statement follows from its cited approved statement and claims:

* claim A — attributed to "the Northland air force": 4 tanker aircraft arrived at Fort Aster;
* claim D — attributed to "a Northland defence ministry spokesman": denies that any tanker aircraft arrived;
* AS1 (KNOWN_FACT, attribution required) — the air force's report, attributed exactly, contradicted by claim D;
* AS2 (ALTERNATIVE_EXPLANATION) — the spokesman's denial, attributed exactly, supported by claim D;
* AS3 (ANALYTIC_JUDGMENT, likelihood ROUGHLY_EVEN_CHANCE) — only what the two conflicting statements together support; it
  states the conflict in its own wording and cites both claims as its evidence (a contested judgement cannot be a key
  judgement under the closed Phase 5 rule, so the conflict is carried by the wording and by the AS2 caveat);
* AS4 (INFORMATION_GAP).

The seeded mutations reproduce the P7-BM-01 error classes on these texts. Nothing here is model input except through
the normal envelope of the report chain; labels live only in evaluation/p7-bm-02/benchmark.json."""
from __future__ import annotations

import json

from p4_support import human_event, pclaim
from p5_helpers import new_report, run_m09, select, version_of_run, m09
from test_p4_assessments import assess, out as m07_out, st, version_of
from test_p4_challenge_review import chal, challenge, review
from lineage_support import head
from lfhe_orchestrator.report_render import render_and_record

CLAIM_A = ("The Northland air force said 4 tanker aircraft arrived at Fort Aster.", "4 tanker aircraft arrived at Fort Aster",
           "the Northland air force")
CLAIM_D = ("A Northland defence ministry spokesman denied that any tanker aircraft arrived at Fort Aster.",
           "denied that any tanker aircraft arrived at Fort Aster", "a Northland defence ministry spokesman")
AS1 = "The Northland air force reported that 4 tanker aircraft arrived at Fort Aster."
AS1_ATTR = "The Northland air force reported"
AS2 = "A Northland defence ministry spokesman denied that any tanker aircraft arrived at Fort Aster."
AS2_ATTR = "A Northland defence ministry spokesman denied"
AS3 = "There is a roughly even chance that tanker aircraft arrived at Fort Aster; the two official Northland statements conflict."
AS4 = "It is unknown whether any aircraft arrived and, if so, how long they would remain."
CONF_RATIONALE = "Two conflicting official statements from the same government; no independent confirmation."


def statements(a, d):
    return [
        st("AS1", "KNOWN_FACT", AS1, claims=[a], contra=[d], attr=True, attr_text=AS1_ATTR),
        st("AS2", "ALTERNATIVE_EXPLANATION", AS2, claims=[d], attr_text=AS2_ATTR, evidence=True),
        st("AS3", "ANALYTIC_JUDGMENT", AS3, claims=[a, d], premises=["AS1", "AS2"], evidence=True,
           likelihood={"term": "ROUGHLY_EVEN_CHANCE",
                       "rationale": "One official statement reports the arrival and another official statement denies it; "
                                    "neither is independently confirmed."}),
        st("AS4", "INFORMATION_GAP", AS4, prov="NONE_REQUIRED", evidence=False),
    ]


def build_base(pg, analyst, code: str, **report_kw):
    """Approved, consistent assessment → report → selection → M09 draft (deterministic test-double editor, VERBATIM)."""
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
    m = run_m09(pg, sid, sh, lambda mod, env: m09(env))
    assert m.outcome == "REPORT_VERSION_RECORDED", m
    rv = version_of_run(pg, m.final_run_id)
    with pg.worker() as w:
        render_and_record(w, str(rv["id"]), rv["report_version_hash"], worker_id="p7-bm02")
    return rv, rid, v, (a, d)


def _set(prefix, text, transform="PARAPHRASE"):
    def fn(c):
        for item in c["key_judgments"]:
            for s in item["statements"]:
                if s["text"].startswith(prefix):
                    s["text"], s["editorial_transform"] = text, transform
                    return c
        raise AssertionError(prefix)
    return fn


def _field(prefix, key, value):
    def fn(c):
        for item in c["key_judgments"]:
            for s in item["statements"]:
                if s["text"].startswith(prefix):
                    s[key] = value
                    return c
        raise AssertionError(prefix)
    return fn


def _dup(c):
    it = c["key_judgments"][0]
    c["key_judgments"].append(dict(it, item_local_id="KJDUP", statements=[
        dict(s, report_statement_local_id=f"RS{90 + n}") for n, s in enumerate(it["statements"])]))
    return c


J = "There is a roughly even chance"
MUTATIONS = {
    "sound": lambda c: c,
    "paraphrase": _set(J, "There is a roughly even chance that tanker aircraft arrived at Fort Aster; the two official "
                          "Northland statements contradict each other."),
    "scope_all": _set("The Northland air force reported",
                      "The Northland air force reported that all 4 tanker aircraft arrived at Fort Aster."),
    "contradiction_neutralised": _set("The Northland air force reported",
                                      "The Northland air force reported that 4 tanker aircraft arrived at Fort Aster; the arrival "
                                      "is undisputed."),
    "new_number": _set(J, "There is a roughly even chance that 12 more tanker aircraft arrived at Fort Aster; the two "
                          "official Northland statements conflict."),
    "new_causal": _set(J, "There is a roughly even chance that tanker aircraft arrived at Fort Aster because of the "
                          "exercise; the two official Northland statements conflict."),
    "actor_change": _set(J, "There is a roughly even chance that Southland tanker aircraft arrived at Fort Aster; the two "
                            "official Northland statements conflict."),
    "certainty": _set(J, "Tanker aircraft certainly arrived at Fort Aster; the two official Northland statements conflict."),
    "attribution_removed": _set("The Northland air force reported", "4 tanker aircraft arrived at Fort Aster."),
    "false_independence": _set("The Northland air force reported",
                               "The Northland air force reported that 4 tanker aircraft arrived at Fort Aster, independently confirmed."),
    "confidence_changed": _field(J, "final_analytic_confidence", "HIGH"),
    "likelihood_changed": _field(J, "likelihood_term", "ALMOST_CERTAIN"),
    "hindsight": _set(J, "There is a roughly even chance that tanker aircraft arrived at Fort Aster, as later shown in 2027."),
    "classified_marking": _set(J, "NATO SECRET: " + AS3),
    "duplicate_item": _dup,
    "unmapped_statement": lambda c: c,
}
