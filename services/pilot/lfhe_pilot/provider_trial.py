"""Phase 7 real-provider acceptance checks (Baseline §14, §26; P7-03).

For each model run, verifies — from stored records only — that it is admissible as real-provider
evidence: a genuine provider call (non-test provider, provider response id recorded for every run that
produced output), exact model identifier / configuration hash stored, prompt version / hash traceable
to the registered bundle, the response went through the normal ingestion path, repair runs are
recorded as separate runs linked to their failed original, and failures stay failures."""
from __future__ import annotations

TEST_PROVIDERS = frozenset({"fake"})
INGESTION = {
    "M07_INTELLIGENCE_ASSESSOR": "assessment_ingestion_results",
    "M08_CHALLENGER": "challenge_ingestion_results",
    "M09_EXECUTIVE_EDITOR": "report_edit_ingestion_results",
}


def run_checks(conn, run_id: str) -> dict:
    r = conn.execute("""SELECT r.*, r.status::text AS st, pv.content_hash AS registered_hash, pv.semver AS registered_semver,
                               mc.config_hash AS registered_config_hash, mc.settings
                          FROM lfhe.model_runs r JOIN lfhe.prompt_versions pv ON pv.id = r.prompt_version_id
                          JOIN lfhe.model_configurations mc ON mc.id = r.model_configuration_id WHERE r.id=%s""", (run_id,)).fetchone()
    if r is None:
        return {"model_run_id": run_id, "admissible": False, "problems": ["MODEL_RUN_MISSING"]}
    problems = []
    if r["provider"] in TEST_PROVIDERS:
        problems.append("TEST_DOUBLE_PROVIDER")
    provider_meta = (r["usage"] or {}).get("provider") or {}
    if r["st"] in ("SUCCEEDED", "SCHEMA_VALIDATION_FAILED") and not provider_meta.get("response_id"):
        problems.append("NO_PROVIDER_RESPONSE_ID")
    if r["st"] == "RUNNING":
        problems.append("RUN_NOT_FINISHED")
    if (r["prompt_content_hash"], r["prompt_semver"]) != (r["registered_hash"], r["registered_semver"]):
        problems.append("PROMPT_NOT_TRACEABLE")
    if r["model_config_hash"] != r["registered_config_hash"]:
        problems.append("MODEL_CONFIGURATION_NOT_TRACEABLE")
    ingested = None
    if r["module_code"] in INGESTION:
        ingested = conn.execute(f"SELECT outcome, repair_of_model_run_id FROM lfhe.{INGESTION[r['module_code']]} WHERE model_run_id=%s",
                                (run_id,)).fetchone()
    elif r["module_code"] == "M10_QA_AUDITOR":
        ingested = conn.execute("SELECT status AS outcome, repair_of_model_run_id FROM lfhe.qa_runs WHERE model_run_id=%s",
                                (run_id,)).fetchone()
    if ingested is None:
        problems.append("NOT_THROUGH_INGESTION_PATH")
    if r["st"] == "PROVIDER_ERROR" and ingested and ingested["outcome"] in ("ASSESSMENT_RECORDED", "CHALLENGE_RECORDED",
                                                                             "REPORT_VERSION_RECORDED"):
        problems.append("PROVIDER_FAILURE_RECORDED_AS_SUCCESS")
    repair_of = ingested["repair_of_model_run_id"] if ingested else None
    if repair_of is not None:
        orig = conn.execute("SELECT status::text s FROM lfhe.model_runs WHERE id=%s", (repair_of,)).fetchone()
        if orig is None or orig["s"] != "SCHEMA_VALIDATION_FAILED":
            problems.append("REPAIR_WITHOUT_FAILED_ORIGINAL")
    usage = r["usage"] or {}
    return {"model_run_id": run_id, "module_code": r["module_code"], "provider": r["provider"], "model": r["model"],
            "provider_model": provider_meta.get("model"), "model_config_hash": r["model_config_hash"], "settings": r["settings"],
            "prompt_semver": r["prompt_semver"], "prompt_content_hash": r["prompt_content_hash"], "status": r["st"],
            "error_code": r["error_code"], "ingestion_outcome": ingested["outcome"] if ingested else None,
            "repair_of_model_run_id": str(repair_of) if repair_of else None,
            "input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens"),
            "latency_ms": round((r["completed_at"] - r["started_at"]).total_seconds() * 1000) if r["completed_at"] else None,
            "admissible": not problems, "problems": problems}
