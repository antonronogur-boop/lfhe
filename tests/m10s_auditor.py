"""A rule-based stand-in for the M10-S model in tests (FakeProvider responder).

It reads ONLY the envelope it is given (exactly what a real model would receive) and reports
semantic findings in the M10 output schema. It is test infrastructure, not production logic: it
proves the envelope carries what the semantic checks need and exercises ingestion / combined-status
/ traceability with realistic findings. Real-model detection quality is NOT measured here (the
real-provider trial is a non-blocking follow-on item). Synthetic material only."""
from __future__ import annotations

import json
import re

NUM = re.compile(r"\d+(?:[.,]\d+)?")
NAME = re.compile(r"[^.!?:;\s]\s+([A-Z][A-Za-z]{2,})")
CAUSAL = re.compile(r"\b(because|due to|caused|causing|led to|leads to|in order to|therefore|as a result|resulting in)\b", re.I)
CERTAIN = re.compile(r"\b(confirmed|definitely|certainly|undoubtedly|clearly|proves|proven|will|has achieved|achieved)\b", re.I)
SCOPE = re.compile(r"\b(all|entire|every|whole|always|never|fleet-wide|nationwide)\b", re.I)
INDEP = re.compile(r"\b(independent(ly)?|corroborat\w*|confirmed by|multiple sources|several sources|separately confirmed)\b", re.I)
REPORTING = re.compile(r"\b(said|says|reported|reports|claimed|claims|stated|states|according to|announced|denied)\b", re.I)
NEUTRALISE = re.compile(r"\b(undisputed|uncontested|beyond doubt|no evidence to the contrary|not contested)\b", re.I)
INJECTION = re.compile(r"ignore (all )?previous instructions|mark (the )?qa (as )?pass|approve (the )?release|set high confidence"
                       r"|hide (the )?contradiction", re.I)


def _f(check, status, severity, code, details, stmt=None, refs=(), action="NO_ACTION", obj=None):
    return {"check_id": check, "status": status, "severity": severity, "finding_code": code,
            "affected_object_id": obj, "affected_statement_id": stmt, "details": details,
            "evidence_refs": [{"object_type": t, "object_id": i} for t, i in refs], "recommended_action": action}


def _new(pattern, text, corpus):
    return sorted({m.group(1) if m.groups() else m.group(0) for m in pattern.finditer(text)}
                  - {m.group(1) if m.groups() else m.group(0) for m in pattern.finditer(corpus)},
                  key=str.lower)


def findings_for(env: dict) -> list[dict]:
    inputs = {(i["object_type"], i["object_id"]): i["content"] for i in env["inputs"]}
    report = next(c for (t, _), c in inputs.items() if t == "report_version")
    stmts = {i: c for (t, i), c in inputs.items() if t == "assessment_statement"}
    claims = {i: c for (t, i), c in inputs.items() if t == "claim"}
    out: list[dict] = []
    seen_texts: dict[str, tuple[str, set]] = {}
    for item in report["items"]:
        for s in item["statements"]:
            sid, text = s["report_item_statement_id"], s["text"]
            srcs = [stmts[x] for x in s["sources"] if x in stmts]
            refs = [("report_item_statement", sid)] + [("assessment_statement", x) for x in s["sources"] if x in stmts]
            ev_claims = [claims[e["object_id"]] for a in srcs for e in a["supporting_evidence"]
                         if e["object_type"] == "claim" and e["object_id"] in claims]
            corpus = " ".join([a["text"] + " " + (a["attribution_text"] or "") for a in srcs])
            if not srcs:
                out.append(_f("QA-01", "FAIL", "CRITICAL", "FABRICATED_CITATION", "cited statements not supplied", sid, refs,
                              "RETURN_TO_ANALYST_FOR_REVISION"))
                continue
            if INJECTION.search(text):
                out.append(_f("QA-01", "FAIL", "CRITICAL", "EMBEDDED_INSTRUCTION_IN_CONTENT",
                              "report text contains an instruction-like string; it is content, not an instruction", sid, refs,
                              "REMOVE_OR_SOURCE_UNSUPPORTED_CONTENT"))
            nums = _new(NUM, text, corpus)
            if nums:
                out.append(_f("QA-17", "FAIL", "CRITICAL", "UNSUPPORTED_FACT", f"numbers not in the cited sources: {nums}", sid, refs,
                              "REMOVE_OR_SOURCE_UNSUPPORTED_CONTENT"))
            names = [n for n in _new(NAME, text, corpus) if n.lower() not in corpus.lower()]
            if names:
                out.append(_f("QA-01", "FAIL", "CRITICAL", "ACTOR_MISMATCH", f"actor / name not in the cited sources: {names}", sid,
                              refs, "RETURN_TO_ANALYST_FOR_REVISION"))
            if CAUSAL.search(text) and not CAUSAL.search(corpus):
                out.append(_f("QA-01", "FAIL", "CRITICAL", "UNSUPPORTED_CAUSAL_CLAIM", "causal relation not in the cited sources", sid,
                              refs, "REMOVE_OR_SOURCE_UNSUPPORTED_CONTENT"))
            strong = [w for w in _new(CERTAIN, text, corpus)]
            if strong:
                out.append(_f("QA-07", "FAIL", "CRITICAL", "MATERIAL_EPISTEMIC_STRENGTH_INCREASE",
                              f"certainty strengthened: {strong}", sid, refs, "RETURN_TO_ANALYST_FOR_REVISION"))
            scope = _new(SCOPE, text, corpus)
            if scope:
                out.append(_f("QA-06", "FAIL", "CRITICAL", "QUANTITY_SCOPE_DISTORTION", f"scope broadened: {scope}", sid, refs,
                              "RETURN_TO_ANALYST_FOR_REVISION"))
            for a in srcs:
                if a["attribution_required"] and (a["attribution_text"] or "\x01").lower() not in text.lower():
                    out.append(_f("S19", "FAIL", "CRITICAL", "ATTRIBUTION_REMOVED",
                                  f'required attribution "{a["attribution_text"]}" no longer present', sid, refs,
                                  "RESTORE_ATTRIBUTION"))
                if (a["epistemic_category"] == "FACT" and REPORTING.search(a["text"]) and not REPORTING.search(text)
                        and any(c["source_statement_status"] == "SOURCE_CLAIM_UNVERIFIED" or c["claim_status_asof"] == "UNVERIFIED"
                                for c in ev_claims)):
                    out.append(_f("QA-07", "FAIL", "CRITICAL", "EPISTEMIC_STRENGTH_MISMATCH",
                                  "a source-reported (unverified) statement is presented as established fact", sid, refs,
                                  "RESTORE_ATTRIBUTION"))
            if INDEP.search(text) and (not INDEP.search(corpus) or len({c["independence"]["independence_group"]
                                                                        for c in ev_claims}) < 2):
                out.append(_f("QA-05", "FAIL", "CRITICAL", "FALSE_INDEPENDENT_CONFIRMATION",
                              "independence / corroboration wording does not match the lineage state", sid, refs,
                              "REMOVE_OR_SOURCE_UNSUPPORTED_CONTENT"))
            if NEUTRALISE.search(text) and (s["contested"] or any(a["contradicting_evidence"] for a in srcs)):
                out.append(_f("QA-09", "FAIL", "CRITICAL", "CONTRADICTION_REMOVED",
                              "contradicting evidence exists but the wording neutralises it", sid, refs,
                              "RESTORE_CAVEAT_OR_CONTRADICTION"))
            for c in ev_claims:
                if set(NUM.findall(c["claim_text_normalised"])) - set(NUM.findall(c["evidence_span_original"]["exact_text"])):
                    out.append(_f("S18", "WARNING", "MAJOR", "TRANSLATION_MATERIAL_MISMATCH",
                                  "normalised claim carries a number absent from the original-language span", sid,
                                  refs + [("claim", c["claim_id"])], "HUMAN_ANALYTICAL_REVIEW"))
            for a in srcs:
                if INJECTION.search(a["text"]):
                    out.append(_f("QA-01", "WARNING", "WARNING", "EMBEDDED_INSTRUCTION_IN_CONTENT",
                                  "an approved source statement contains instruction-like text (treated as data)", sid, refs,
                                  "HUMAN_ANALYTICAL_REVIEW"))
            if item["section"] in ("KEY_JUDGMENT", "SIGNIFICANT_DEVELOPMENT", "INDICATOR_WARNING"):
                key = re.sub(r"\W+", " ", text.lower()).strip()
                cl = {c["claim_id"] for c in ev_claims}
                for other, (oid, ocl) in seen_texts.items():
                    if (other == key or (cl and cl == ocl)) and oid != item["item_local_id"]:
                        out.append(_f("QA-13", "WARNING", "WARNING", "MISLEADING_DUPLICATION",
                                      f"items {oid} and {item['item_local_id']} present the same origin as separate developments",
                                      sid, refs, "REVIEW_DUPLICATION"))
                        break
                seen_texts[key] = (item["item_local_id"], cl)
    checks = {"QA-01", "QA-05", "QA-06", "QA-07", "QA-09", "QA-13", "QA-17", "S18", "S19", "S20"}
    for ch in sorted(checks - {f["check_id"] for f in out}):
        out.append(_f(ch, "PASS", "INFO", "SEMANTICALLY_SUPPORTED", "no semantic finding"))
    return out


def audit_output(env: dict, *, findings=None, extra=(), status="SUCCESS", **result_overrides) -> str:
    fs = list(findings_for(env) if findings is None else findings) + list(extra)
    worst = "FAIL" if any(f["status"] == "FAIL" for f in fs) else "PASS_WITH_WARNINGS" if any(
        f["status"] == "WARNING" for f in fs) else "PASS"
    t = env["task"]
    result = {"report_id": t["report_id"], "report_version_id": t["report_version_id"],
              "report_version_hash": t["report_version_hash"], "deterministic_qa_run_id": t["deterministic_qa_run_id"],
              "qa_status": worst, "findings": fs, "errors": [], "warnings": [], "release_blocked": worst == "FAIL"}
    result.update(result_overrides)
    return json.dumps({"module": "M10_QA_AUDITOR", "status": status, "warnings": [], "human_review_required": True,
                       "result": result})


def auditor(**kw):
    """FakeProvider responder."""
    return lambda module, env: audit_output(env, **kw)
