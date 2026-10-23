"""Phase 7 reproducible pilot metrics (Baseline §10, P7-07).

Every figure is recomputed from stored records — pilot measurement tables plus READ-ONLY queries of
the authoritative Phase 1–6 chain of the cycle's bound report. Nothing is estimated or filled in: an
absent measurement is returned as ``None`` and named in ``missing``. Quality figures are what the
recorded QA layers detected (labelled ``as_detected_by_qa``), not ground truth.

The connection must be able to read the pilot and chain tables (the DB owner in the analysis
environment, or a PILOT_LEAD session through PostgREST-equivalent RLS)."""
from __future__ import annotations

from decimal import Decimal
from statistics import median

QUALITY_CODES = {
    "unsupported_fact": ("UNSUPPORTED_FACT",),
    "attribution_loss": ("ATTRIBUTION_OMITTED", "ATTRIBUTION_LOST", "ATTRIBUTION_REMOVED"),
    "epistemic_strength_violation": ("MATERIAL_EPISTEMIC_STRENGTH_INCREASE", "EPISTEMIC_CLASS_CHANGED"),
    "post_cutoff_or_hindsight": ("POST_CUTOFF_EVIDENCE", "HINDSIGHT_CONTAMINATION", "BASELINE_NOT_ELIGIBLE",
                                 "REFERENCE_CONTEXT_NOT_ELIGIBLE"),
}
QUALITY_CHECKS = {"attribution_loss": ("D19", "S19"), "contradiction_handling": ("QA-09",),
                  "source_independence": ("QA-05",), "likelihood_confidence": ("QA-08",)}


def _one(conn, sql, args=()):
    return conn.execute(sql, args).fetchone()


def _all(conn, sql, args=()):
    return conn.execute(sql, args).fetchall()


def _secs(td) -> float | None:
    return None if td is None else round(td.total_seconds(), 3)


def cycle_metrics(conn, cycle_id: str) -> dict:
    c = _one(conn, "SELECT *, pilot_mode::text AS mode FROM lfhe.pilot_cycles WHERE id=%s", (cycle_id,))
    if c is None:
        raise LookupError(cycle_id)
    missing = list(_one(conn, "SELECT lfhe.pilot_cycle_missing_metrics(%s) m", (cycle_id,))["m"])
    out: dict = {"cycle": {"id": str(c["id"]), "code": c["code"], "mode": c["mode"],
                           "information_cutoff": c["information_cutoff"].isoformat(), "data_boundary": c["data_boundary"],
                           "status": c["status"], "terminal_state": c["terminal_state"], "stop_reason": c["stop_reason"],
                           "started_at": c["started_at"].isoformat(),
                           "closed_at": c["closed_at"].isoformat() if c["closed_at"] else None,
                           "provider_setup": c["provider_setup"], "input_scope": c["input_scope"]},
                 "missing": missing}
    out["comparator"] = _comparator(conn, cycle_id)
    out["effort"] = _effort(conn, c)
    out["provider"] = provider_metrics(conn, cycle_id)
    out["ux"] = _ux(conn, cycle_id)
    out["workload"] = _workload(conn, c)
    if c["report_id"] is None:
        out.update(throughput=None, report=None, quality=None, qa=None, provenance=None, corrections=None)
        return out
    rid = str(c["report_id"])
    out["throughput"] = _throughput(conn, rid, out["effort"]["analyst_active_hours"])
    out["report"] = _report(conn, rid, c)
    out["qa"], out["quality"] = _qa_and_quality(conn, rid)
    out["provenance"] = _provenance(conn, rid)
    out["corrections"] = _corrections(conn, rid)
    return out


def _comparator(conn, cycle_id):
    r = _one(conn, "SELECT method::text AS method, baseline_analyst_seconds, baseline_basis, comparable_scope, reference "
                   "FROM lfhe.pilot_comparators WHERE cycle_id=%s", (cycle_id,))
    return dict(r) if r else None


def _effort(conn, c):
    rows = _all(conn, "SELECT stage::text AS stage, user_id, segments, open_segments, active_seconds "
                      "FROM lfhe.pilot_cycle_timing WHERE cycle_id=%s ORDER BY stage, user_id::text", (c["id"],))
    analyst = [r for r in rows if r["user_id"] == c["analyst_user_id"]]
    total = sum((Decimal(r["active_seconds"]) for r in analyst), Decimal(0))
    everyone = sum((Decimal(r["active_seconds"]) for r in rows), Decimal(0))
    stages: dict[str, float] = {}
    for r in analyst:
        stages[r["stage"]] = float(Decimal(r["active_seconds"]))
    end = c["closed_at"]
    interactions = None
    if end is not None:
        interactions = _one(conn, """SELECT count(*) n FROM lfhe.audit_log WHERE actor_type='HUMAN' AND actor_user_id=%s
                                     AND occurred_at BETWEEN %s AND %s AND event_type NOT LIKE 'PILOT\\_%%'""",
                            (c["analyst_user_id"], c["started_at"], end))["n"]
    timed = bool(analyst) and not any(r["open_segments"] for r in rows)
    return {"analyst_active_seconds": float(total) if analyst else None,
            "analyst_active_hours": float(total / 3600) if analyst else None,
            "all_participants_active_seconds": float(everyone) if rows else None,
            "analyst_seconds_by_stage": stages, "timing_complete": timed,
            "audited_human_interactions": interactions,
            "interactions_basis": "audited human decisions by the cycle analyst inside the cycle window"}


def provider_metrics(conn, cycle_id) -> dict:
    rows = _all(conn, "SELECT * FROM lfhe.pilot_model_run_metrics WHERE cycle_id=%s ORDER BY module_code, started_at", (cycle_id,))
    by_module: dict[str, dict] = {}
    for r in rows:
        m = by_module.setdefault(r["module_code"], {"runs": 0, "succeeded": 0, "schema_validation_failed": 0,
                                                     "provider_errors": 0, "repair_runs": 0, "latency_ms": [],
                                                     "input_tokens": 0, "output_tokens": 0, "tokens_unknown_runs": 0,
                                                     "cost": Decimal(0), "cost_unknown_runs": 0, "currencies": set(),
                                                     "providers": set(), "models": set(), "prompt_versions": set(),
                                                     "model_config_hashes": set(), "error_codes": {}})
        m["runs"] += 1
        m["succeeded"] += r["status"] == "SUCCEEDED"
        m["schema_validation_failed"] += r["status"] == "SCHEMA_VALIDATION_FAILED"
        m["provider_errors"] += r["status"] == "PROVIDER_ERROR"
        m["repair_runs"] += bool(r["is_repair_run"])
        if r["error_code"]:
            m["error_codes"][r["error_code"]] = m["error_codes"].get(r["error_code"], 0) + 1
        if r["latency_ms"] is not None:
            m["latency_ms"].append(int(r["latency_ms"]))
        if r["input_tokens"] is None or r["output_tokens"] is None:
            m["tokens_unknown_runs"] += 1
        else:
            m["input_tokens"] += r["input_tokens"]
            m["output_tokens"] += r["output_tokens"]
        if r["model_cost"] is None:
            m["cost_unknown_runs"] += 1
        else:
            m["cost"] += Decimal(r["model_cost"])
            m["currencies"].add(r["cost_currency"])
        m["providers"].add(r["provider"])
        m["models"].add(r["model"])
        m["prompt_versions"].add(f"{r['prompt_semver']}@{r['prompt_content_hash'][:12]}")
        m["model_config_hashes"].add(r["model_config_hash"])
    for m in by_module.values():
        lat = sorted(m.pop("latency_ms"))
        m["latency_ms_median"] = median(lat) if lat else None
        m["latency_ms_max"] = lat[-1] if lat else None
        m["structured_output_success_rate"] = round(m["succeeded"] / m["runs"], 4) if m["runs"] else None
        m["cost"] = str(m["cost"]) if m["cost_unknown_runs"] < m["runs"] else None
        for k in ("currencies", "providers", "models", "prompt_versions", "model_config_hashes"):
            m[k] = sorted(m[k])
    return {"modules": by_module, "runs_bound": len(rows),
            "real_provider_runs": sum(1 for r in rows if r["provider"] not in ("fake",))}


def _ux(conn, cycle_id):
    rows = _all(conn, """SELECT f.severity::text sev, f.finding_class::text cls,
                           coalesce((SELECT d.disposition FROM lfhe.pilot_ux_finding_dispositions d WHERE d.finding_id=f.id
                                     ORDER BY d.seq DESC LIMIT 1), 'OPEN') disp
                         FROM lfhe.pilot_ux_findings f WHERE f.cycle_id=%s""", (cycle_id,))
    out = {"total": len(rows), "by_severity": {}, "by_class": {}, "open_blocking": 0}
    for r in rows:
        out["by_severity"][r["sev"]] = out["by_severity"].get(r["sev"], 0) + 1
        out["by_class"][r["cls"]] = out["by_class"].get(r["cls"], 0) + 1
        out["open_blocking"] += r["sev"] == "BLOCKING" and r["disp"] in ("OPEN", "REOPENED", "BACKLOG")
    return out


def _workload(conn, c):
    r = _one(conn, "SELECT * FROM lfhe.pilot_workload_ratings WHERE cycle_id=%s AND user_id=%s", (c["id"], c["analyst_user_id"]))
    if r is None:
        return None
    dims = ("mental", "physical", "temporal", "performance", "effort", "frustration")
    return {"instrument": r["instrument"], **{d: r[d] for d in dims},
            "raw_tlx": round(sum(r[d] for d in dims) / 6, 2)}


def _chain_assessments(conn, rid):
    return [r["id"] for r in _all(conn, """
        SELECT DISTINCT i.pinned_assessment_version_id id FROM lfhe.report_items i JOIN lfhe.report_versions v ON v.id=i.report_version_id
         WHERE v.report_id=%s AND i.pinned_assessment_version_id IS NOT NULL""", (rid,))]


def _latest(conn, rid):
    return _one(conn, "SELECT * FROM lfhe.report_versions WHERE report_id=%s ORDER BY version_no DESC LIMIT 1", (rid,))


def _throughput(conn, rid, analyst_hours):
    av = _chain_assessments(conn, rid)
    claims = _all(conn, """SELECT DISTINCT c.id, c.source_id, c.article_id FROM lfhe.assessment_statement_evidence e
                           JOIN lfhe.assessment_statements s ON s.id=e.statement_id JOIN lfhe.claims c ON c.id=e.object_id
                           WHERE e.object_type='claim' AND s.assessment_version_id = ANY(%s)""", (av,))
    events = _one(conn, "SELECT count(DISTINCT ev.event_id) n FROM lfhe.assessment_versions a JOIN lfhe.event_versions ev "
                        "ON ev.id=a.event_version_id WHERE a.id = ANY(%s)", (av,))["n"]
    latest = _latest(conn, rid)
    final_items = _one(conn, "SELECT count(*) n FROM lfhe.report_items WHERE report_version_id=%s", (latest["id"],))["n"] if latest else 0
    cands = _one(conn, "SELECT count(*) n FROM lfhe.report_candidate_pool WHERE report_id=%s", (rid,))["n"]
    sources = len({r["source_id"] for r in claims})
    out = {"sources_contributing": sources, "articles_contributing": len({r["article_id"] for r in claims}),
           "claims_cited": len(claims), "events": events, "assessments": len(av), "candidate_report_items": cands,
           "final_report_items": final_items,
           "basis": "objects in the bound report's analytical chain (not every object collected in the window)"}
    if analyst_hours:
        out["sources_per_analyst_hour"] = round(sources / analyst_hours, 4)
        out["accepted_report_items_per_analyst_hour"] = round(final_items / analyst_hours, 4)
    else:
        out["sources_per_analyst_hour"] = out["accepted_report_items_per_analyst_hour"] = None
    return out


def _report(conn, rid, c):
    versions = _all(conn, "SELECT id, version_no, origin, created_at, canonical_json FROM lfhe.report_versions "
                          "WHERE report_id=%s ORDER BY version_no", (rid,))
    rel = _one(conn, "SELECT released_at FROM lfhe.report_releases WHERE report_id=%s ORDER BY released_at LIMIT 1", (rid,))
    qa_before = 0
    for v in versions[1:]:
        qa_before += bool(_one(conn, """SELECT 1 x FROM lfhe.qa_results q JOIN lfhe.report_versions p ON p.id=q.report_version_id
                                        WHERE p.report_id=%s AND p.version_no=%s AND q.status IN ('FAIL','PASS_WITH_WARNINGS')
                                        LIMIT 1""", (rid, v["version_no"] - 1)))
    latest = versions[-1] if versions else None
    content = (latest["canonical_json"] or {}).get("content") if latest else None
    content = content or (latest["canonical_json"] if latest else {})

    def n(section):
        x = content.get(section) if isinstance(content, dict) else None
        return len(x) if isinstance(x, list) else None
    cutoff = c["information_cutoff"]
    return {"versions": len(versions), "human_versions": sum(v["origin"] == "HUMAN" for v in versions),
            "qa_induced_revisions": qa_before,
            "cutoff_to_first_draft_seconds": _secs(versions[0]["created_at"] - cutoff) if versions else None,
            "cutoff_to_release_seconds": _secs(rel["released_at"] - cutoff) if rel else None,
            "cycle_start_to_release_seconds": _secs(rel["released_at"] - c["started_at"]) if rel else None,
            "report_length_chars": len(str(content)) if latest else None,
            "key_judgments": n("key_judgments"), "significant_developments": n("significant_developments"),
            "indicators": n("indicators"), "what_to_watch": n("what_to_watch"),
            "time_basis": "LIVE: wall clock from cutoff; REPLAY: cutoff is historical, use cycle_start_to_release"}


def _qa_and_quality(conn, rid):
    q = _one(conn, """SELECT q.* FROM lfhe.qa_results q JOIN lfhe.report_versions v ON v.id=q.report_version_id
                      WHERE q.report_id=%s ORDER BY v.version_no DESC, q.result_no DESC LIMIT 1""", (rid,))
    if q is None:
        return None, None
    runs = _one(conn, "SELECT count(*) n FROM lfhe.qa_results WHERE report_id=%s", (rid,))["n"]
    f = _all(conn, "SELECT layer, check_id, finding_code, status, severity::text sev FROM lfhe.qa_check_results "
                   "WHERE qa_run_id IN (%s, %s)", (q["deterministic_qa_run_id"], q["semantic_qa_run_id"]))
    qa = {"qa_results_total": runs, "final_status": q["status"]}
    for layer in ("D", "S"):
        lf = [x for x in f if x["layer"] == layer and x["status"] != "PASS"]
        qa[layer] = {"findings": len(lf), "fail": sum(x["status"] == "FAIL" for x in lf),
                     "warning": sum(x["status"] == "WARNING" for x in lf),
                     "critical": sum(x["sev"] == "CRITICAL" for x in lf)}
    stmts = _one(conn, """SELECT count(*) n FROM lfhe.report_item_statements s JOIN lfhe.report_items i ON i.id=s.report_item_id
                          WHERE i.report_version_id=%s""", (q["report_version_id"],))["n"]
    bad = [x for x in f if x["status"] != "PASS"]
    quality = {"statements": stmts, "basis": "as_detected_by_qa (final QA result); not ground truth"}
    for k, codes in QUALITY_CODES.items():
        cnt = sum(1 for x in bad if x["finding_code"] in codes or x["check_id"] in QUALITY_CHECKS.get(k, ()))
        quality[f"{k}_findings"] = cnt
        quality[f"{k}_rate"] = round(cnt / stmts, 4) if stmts else None
    for k in ("contradiction_handling", "source_independence", "likelihood_confidence"):
        quality[f"{k}_findings"] = sum(1 for x in bad if x["check_id"] in QUALITY_CHECKS[k])
    return qa, quality


def _provenance(conn, rid):
    m = _one(conn, """SELECT m.manifest_json FROM lfhe.release_manifests m JOIN lfhe.report_releases r
                      ON r.release_manifest_id=m.id WHERE r.report_id=%s LIMIT 1""", (rid,))
    if m is None:
        return {"released": False, "manifest_problems": None, "complete": None}
    problems = _one(conn, "SELECT lfhe.p6_manifest_problems(%s::jsonb) p",
                    (__import__("json").dumps(m["manifest_json"]),))["p"]
    return {"released": True, "manifest_problems": problems, "complete": problems == []}


def _corrections(conn, rid):
    av = _chain_assessments(conn, rid)
    appr = _all(conn, "SELECT decision FROM lfhe.analytical_approvals WHERE assessment_version_id = ANY(%s)", (av,))
    flags = _all(conn, """SELECT d.disposition FROM lfhe.challenge_flag_dispositions d JOIN lfhe.challenge_flags f ON f.id=d.flag_id
                          JOIN lfhe.challenge_runs r ON r.id=f.challenge_run_id WHERE r.assessment_version_id = ANY(%s)""", (av,))
    content = _all(conn, "SELECT decision FROM lfhe.content_approvals WHERE report_id=%s", (rid,))
    sec = _all(conn, "SELECT status::text s FROM lfhe.security_reviews WHERE report_id=%s AND status <> 'PENDING'", (rid,))
    rel = _all(conn, "SELECT decision::text d FROM lfhe.release_decisions WHERE report_id=%s", (rid,))
    human_edits = _one(conn, "SELECT count(*) n FROM lfhe.report_versions WHERE report_id=%s AND origin='HUMAN'", (rid,))["n"]
    decisions = len(appr) + len(content) + len(sec) + len(rel)
    overrides = (sum(a["decision"] == "MODIFY_AND_APPROVE" for a in appr) + sum(x["decision"] != "APPROVE" for x in content)
                 + sum(x["s"] != "APPROVED" for x in sec) + sum(x["d"] not in ("APPROVE_FOR_RELEASE",) for x in rel))
    return {"analytical_approvals": len(appr), "modify_and_approve": sum(a["decision"] == "MODIFY_AND_APPROVE" for a in appr),
            "challenge_flag_dispositions": len(flags), "human_report_edits": human_edits,
            "content_decisions": [x["decision"] for x in content], "security_decisions": [x["s"] for x in sec],
            "release_decisions": [x["d"] for x in rel], "human_gate_decisions": decisions,
            "human_override_or_correction_decisions": overrides,
            "human_override_rate": round(overrides / decisions, 4) if decisions else None}
