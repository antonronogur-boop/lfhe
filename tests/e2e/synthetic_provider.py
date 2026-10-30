"""SYNTHETIC_TEST_ONLY scripted model for the browser E2E worker.

A deterministic stand-in for the model behind M02–M10 so that the real worker handlers, input builders, envelopes,
schema validation and ingestion run end to end without a provider. It reads only the envelope it receives and
answers in each module's output schema, reusing the scripted outputs of the closed Phase 2–6 test suites. It is never
used outside the throw-away E2E stack, never touches DEV, and nothing it produces enters pilot measurement.
All material is synthetic ('Northland', 'Fort Aster')."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "tests", ROOT / "tests" / "integration"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from m10s_auditor import audit_output  # noqa: E402
from p5_helpers import m09  # noqa: E402
from pipeline_support import m02_claim, m02_output, m03_output, source_text  # noqa: E402
from test_p4_assessments import out as m07_out, st  # noqa: E402
from test_p4_challenge_review import chal  # noqa: E402
from test_p4_relevance import out as m06_out  # noqa: E402

MARK = "SYNTHETIC_TEST_ONLY"

# the synthetic corpus the E2E stack seeds (text -> exact evidence span)
CORPUS = {
    "The air force said 4 tanker aircraft arrived at Fort Aster.": "4 tanker aircraft arrived at Fort Aster",
    "A spokesman denied that any tanker aircraft arrived at Fort Aster.": "denied that any tanker aircraft arrived at Fort Aster",
}


def _m02(env):
    text = source_text(env)
    exact = next((v for k, v in CORPUS.items() if k in text), None)
    if exact is None:
        return m02_output(env, [])
    attribution = "the air force" if "air force" in text else "a spokesman"
    return m02_output(env, [m02_claim(text, exact, claim_type="DEPLOYMENT", attribution=attribution)])


def _m05(env):
    claims = [i for i in env["inputs"] if i["object_type"] == "claim"]
    ids = [c["object_id"] for c in claims]
    roles = [{"claim_id": c["object_id"],
              "role": "CONTRADICTS" if "denied" in (c["content"].get("claim_text_original") or "") else "SUPPORTS"}
             for c in claims]
    return json.dumps({"module": "M05_EVENT_BUILDER", "status": "SUCCESS", "warnings": [], "human_review_required": False,
                       "result": {"proposals": [{
                           "proposal": "CREATE_NEW_EVENT", "target_event_id": None, "target_event_version_id": None,
                           "related_event_ids": [], "claim_ids": ids, "reason": f"{MARK}: one reported arrival",
                           "confidence": "MODERATE",
                           "event_candidate": {"title": "Reported tanker arrival at Fort Aster",
                                               "description": "The air force reported the arrival; a spokesman denied it.",
                                               "event_type": "DEPLOYMENT", "event_date_start": None, "event_date_end": None,
                                               "event_date_confidence": "UNKNOWN", "locations": [], "claims": roles}}]}})


def _m07(env):
    claims = env["inputs"][0]["content"]["claims"]
    a = next(c for c in claims if "denied" not in (c.get("claim_text_original") or ""))
    d = next((c for c in claims if "denied" in (c.get("claim_text_original") or "")), None)
    statements = [st("AS1", "KNOWN_FACT", "The air force reported that 4 tanker aircraft arrived at Fort Aster.",
                     claims=[a["claim_id"]], contra=[d["claim_id"]] if d else [], attr_text="The air force reported")]
    if d:
        statements.append(st("AS2", "ALTERNATIVE_EXPLANATION", "The arrival may not have happened; a spokesman denied it.",
                             claims=[a["claim_id"]], contra=[d["claim_id"]], evidence=False))
    statements.append(st("AS3", "ANALYTIC_JUDGMENT",
                         "There is a roughly even chance that tanker aircraft arrived at Fort Aster; the two official statements conflict.",
                         claims=[a["claim_id"]], contra=[d["claim_id"]] if d else [], premises=["AS1"] + (["AS2"] if d else []), evidence=True,
                         likelihood={"term": "ROUGHLY_EVEN_CHANCE",
                                     "rationale": f"{MARK}: one official statement reports the arrival, another denies it."}))
    statements.append(st("AS4", "INFORMATION_GAP", "It is unknown how long the aircraft will remain.", prov="NONE_REQUIRED",
                         evidence=False))
    return m07_out(env, statements, conf="LOW",
                   rationale=f"{MARK}: single official source contradicted by a denial; no independent confirmation.")


def _m10(env):
    # the scripted model adds one non-blocking semantic warning so the E2E exercises warning acknowledgement
    report = next(i["content"] for i in env["inputs"] if i["object_type"] == "report_version")
    stmt = report["items"][0]["statements"][0]["report_item_statement_id"] if report["items"] else None
    warning = {"check_id": "QA-13", "status": "WARNING", "severity": "WARNING", "finding_code": "OTHER_SEMANTIC_CONCERN",
               "affected_object_id": None, "affected_statement_id": stmt,
               "details": f"{MARK}: the contested arrival rests on one official source; keep the caveat visible.",
               "evidence_refs": [{"object_type": "report_item_statement", "object_id": stmt}] if stmt else [],
               "recommended_action": "NO_ACTION"}
    return audit_output(env, extra=[warning])


def _m09(env):
    """VERBATIM items in the human-assigned section; in a KEY_JUDGMENT item the approved analytic judgement carries the
    KEY_JUDGMENT role (also when contested — the conflict stays in its text and in the caveats), the rest are caveats."""
    from p5_helpers import SECTION_KEYS, pool, rs
    sections = {k: [] for k in SECTION_KEYS.values()}
    n = 0
    for i, c in enumerate(pool(env), 1):
        stmts = []
        for s in c["statements"]:
            n += 1
            if c["section"] == "KEY_JUDGMENT":
                role = "KEY_JUDGMENT" if s["statement_type"] == "ANALYTIC_JUDGMENT" else "CAVEAT"
            else:
                role = "CAVEAT" if s["caveat_class"] else c["section"]
            stmts.append(rs(n, s["text"], role, [s["assessment_statement_id"]], c["final_analytic_confidence"], s["likelihood_term"],
                            "VERBATIM_APPROVED"))
        sections[SECTION_KEYS[c["section"]]].append({"item_local_id": f"IT{i}", "source_candidate_id": c["candidate_id"], "statements": stmts})
    return m09(env, sections)


def responder(module, env):
    code = module.module_code
    if code == "M02_CLAIM_EXTRACTOR":
        return _m02(env)
    if code == "M03_CLASSIFIER":
        return m03_output([("TOPIC", "TOPIC_AERIAL_REFUELLING", i["object_id"], "MODERATE")
                           for i in env["inputs"] if i["object_type"] == "claim"][:1] or [], status="SUCCESS")
    if code == "M05_EVENT_BUILDER":
        return _m05(env)
    if code == "M06_RELEVANCE":
        return m06_out(env)
    if code == "M07_INTELLIGENCE_ASSESSOR":
        return _m07(env)
    if code == "M08_CHALLENGER":
        return chal(env)
    if code == "M09_EXECUTIVE_EDITOR":
        return _m09(env)
    if code == "M10_QA_AUDITOR":
        return _m10(env)
    raise RuntimeError(f"{MARK}: no scripted output for {code}")
