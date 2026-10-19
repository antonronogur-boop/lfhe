"""Phase 2 test support: synthetic original-language snapshots, fixture
prompt versions and model runs, M02-shaped claim candidates.

All content is synthetic (OSINT-style, invented); nothing here is GS-001
material.
"""
from __future__ import annotations

import hashlib
import json
import unicodedata
import uuid
from datetime import datetime, timezone

from psycopg.types.json import Jsonb

from conftest import make_collectable_source
from lfhe_shared.canonical_json import canonical_sha256
from lfhe_shared.prompts import bundle_sha256

_FIXTURE_VERSIONS: dict[tuple[str, str], str] = {}
_MODEL_CONFIG: dict[str, str] = {}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_text_snapshot(pg, text: str, *, language: str | None = "en", retention: str = "FULL",
                       title: str = "Synthetic article", available_at: str | None = None) -> dict:
    """Source → article → snapshot → original-language text representation,
    written through the real worker path (lfhe.record_snapshot)."""
    text = unicodedata.normalize("NFC", text)
    path = uuid.uuid4().hex[:12]
    url = f"https://example.org/news/{path}"
    src = make_collectable_source(pg, "HTTP_FETCH", {"urls": [url]}, retention=retention,
                                  language=language or "en", domain="example.org")
    now = datetime.now(timezone.utc).isoformat()
    text_hash = sha(text)
    state = {"format": "lfhe-snapshot-state/1", "final_url": url, "media_type": "text/html",
             "content": {"sha256": text_hash, "basis": "clean_text_sha256"}, "title_original": title,
             "language": language, "language_method": "html_lang", "stated_publication": [],
             "source_updated": None, "discovery": {}, "retention_mode": retention}
    payload = {
        "source_id": str(src["id"]), "canonical_url": url, "requested_url": url, "final_url": url,
        "redirect_chain": [], "http_status": 200, "content_type": "text/html; charset=utf-8",
        "response_headers": {}, "raw_content_sha256": text_hash, "raw_size_bytes": len(text.encode()),
        "raw_storage_key": f"sha256/{text_hash}" if retention == "FULL" else None,
        "retention_mode_applied": retention, "content_identity_sha256": text_hash,
        "title_original": title, "language": language, "language_method": "html_lang" if language else "none",
        "public_availability_basis": "SOURCE_PUBLISHED_TIMESTAMP" if available_at else "UNKNOWN",
        "public_availability_confidence": "HIGH" if available_at else "UNKNOWN",
        "public_availability_datetime": available_at,
        "system_retrieval_datetime": now, "date_status": "DATE_UNCERTAIN", "metadata": {},
        "source_state": state, "source_state_sha256": canonical_sha256(state),
        "text": None if retention == "METADATA_ONLY" else {
            "representation_type": "CANONICAL_CLEAN_TEXT" if retention == "FULL" else "PERMITTED_EXCERPT",
            "preprocessor_name": "lfhe-test", "preprocessor_version": "1.0.0", "language": language,
            "text_content": text, "text_sha256": text_hash, "char_length": len(text)},
    }
    with pg.worker() as c:
        run = c.execute("SELECT lfhe.start_collection_run(%s, NULL, 'claims-test') AS id", (src["id"],)).fetchone()["id"]
        payload["collection_run_id"] = str(run)
        out = c.execute("SELECT lfhe.record_snapshot(%s::jsonb) AS r", (Jsonb(payload),)).fetchone()["r"]
        c.execute("SELECT lfhe.finish_collection_run(%s, 'SUCCESS', '{}'::jsonb)", (run,))
        rep = c.execute("SELECT id FROM lfhe.text_representations WHERE snapshot_id=%s",
                        (out["snapshot_id"],)).fetchone()
    return {"source_id": str(src["id"]), "article_id": str(out["article_id"]), "snapshot_id": str(out["snapshot_id"]),
            "rep_id": str(rep["id"]) if rep else None, "text": text, "language": language}


def fixture_prompt_version(pg, module_code: str, semver: str = "0.0.1") -> str:
    """A registered TEST-FIXTURE prompt version for module_code (not activated)."""
    key = (module_code, semver)
    if key in _FIXTURE_VERSIONS:
        return _FIXTURE_VERSIONS[key]
    files = {
        "manifest.json": json.dumps({"format": "lfhe-prompt-manifest/1", "module_code": module_code,
                                     "semver": semver, "module_version": "test-fixture", "test_fixture": True}),
        "system.md": "Synthetic fixture.", "task.md": "Synthetic fixture.",
        "output_schema.json": json.dumps({"type": "object"}),
    }
    with pg.registrar() as c:
        pv = c.execute("SELECT lfhe.register_prompt_version(%s::jsonb) AS id", (Jsonb({
            "module_code": module_code, "semver": semver, "module_version": "test-fixture",
            "is_test_fixture": True, "files": files, "git_path": f"tests/fixtures/prompts/{module_code}/{semver}",
            "git_commit": None, "git_tree_clean": False,
            "expected_content_hash": bundle_sha256(module_code, semver, files)}),)).fetchone()["id"]
    _FIXTURE_VERSIONS[key] = str(pv)
    return str(pv)


def model_configuration(pg) -> str:
    if "fake" not in _MODEL_CONFIG:
        with pg.registrar() as c:
            _MODEL_CONFIG["fake"] = str(c.execute(
                "SELECT lfhe.register_model_configuration('fake', 'fake-model-1', %s::jsonb) AS id",
                (Jsonb({"temperature": 0}),)).fetchone()["id"])
    return _MODEL_CONFIG["fake"]


def make_model_run(pg, module_code: str, inputs: list[tuple[str, str]], context: list[tuple[str, str]] = (),
                   task_parameters: dict | None = None, status: str = "SUCCEEDED",
                   parsed_output: dict | None = None) -> str:
    """Owner-level insert of a finished model run (test setup only; production
    runs are created by lfhe.start_model_run / finish_model_run)."""
    pv = fixture_prompt_version(pg, module_code)
    mc = model_configuration(pg)
    manifest = [{"object_type": t, "object_id": i, "content_sha256": sha(f"{t}:{i}")} for t, i in inputs]
    ctx = [{"object_type": t, "object_id": i, "content_sha256": sha(f"{t}:{i}")} for t, i in context]
    raw = json.dumps(parsed_output or {"status": "SUCCESS"})
    with pg.admin() as c:
        row = c.execute(
            """
            INSERT INTO lfhe.model_runs (module_code, prompt_version_id, prompt_semver, prompt_content_hash,
              module_version, model_configuration_id, provider, model, model_config_hash, environment,
              envelope_sha256, task_parameters, input_manifest, input_snapshot_sha256, context_manifest,
              context_snapshot_sha256, worker_id, status, raw_output, raw_output_sha256, parsed_output,
              validation_errors, error_code, completed_at)
            SELECT pv.module_code, pv.id, pv.semver, pv.content_hash, pv.module_version, mc.id, mc.provider,
                   mc.model, mc.config_hash, 'TEST', %(env)s, %(task)s, %(inp)s,
                   lfhe.object_set_sha256('lfhe-input-set/1', %(inp)s), %(ctx)s,
                   lfhe.object_set_sha256('lfhe-context-set/1', %(ctx)s), 'claims-test',
                   %(status)s::lfhe.model_run_status, %(raw)s, encode(extensions.digest(%(raw)s, 'sha256'), 'hex'),
                   CASE WHEN %(status)s = 'SUCCEEDED' THEN %(parsed)s END,
                   CASE WHEN %(status)s = 'SCHEMA_VALIDATION_FAILED' THEN '[{"path":"","message":"x"}]'::jsonb END,
                   CASE %(status)s WHEN 'SUCCEEDED' THEN NULL WHEN 'SCHEMA_VALIDATION_FAILED'
                     THEN 'SCHEMA_VALIDATION_FAILED' ELSE 'PROVIDER_UNAVAILABLE' END,
                   now()
            FROM lfhe.prompt_versions pv, lfhe.model_configurations mc
            WHERE pv.id = %(pv)s AND mc.id = %(mc)s
            RETURNING id
            """,
            {"env": sha(uuid.uuid4().hex), "task": Jsonb(task_parameters or {}), "inp": Jsonb(manifest),
             "ctx": Jsonb(ctx), "status": status, "raw": raw, "parsed": Jsonb(parsed_output or {"status": "SUCCESS"}),
             "pv": pv, "mc": mc}).fetchone()
    return str(row["id"])


def span_for(text: str, exact: str, language: str = "en") -> dict:
    start = text.index(exact)
    return {"exact_text": exact, "start": start, "end": start + len(exact), "language": language,
            "locator_type": "TEXT_REPRESENTATION_CODE_POINTS"}


def candidate(text: str, exact: str, *, local_id: str = "C1", language: str = "en", original: str | None = None,
              normalised: str | None = None, **overrides) -> dict:
    c = {
        "claim_local_id": local_id, "claim_text_original": original or exact,
        "claim_text_normalised": normalised or exact, "claim_type": "ANNOUNCEMENT",
        "source_statement_status": "FACT_REPORTED_BY_SOURCE", "attribution": "the ministry",
        "event_date": None, "event_date_confidence": "UNKNOWN", "entities": [], "locations": [],
        "quantity": None, "unit": None, "evidence_type": "OFFICIAL_STATEMENT", "evidence_directness": "DIRECT",
        "source_uncertainty_preserved": True, "potential_contradiction": False,
        "evidence_span_original": span_for(text, exact, language), "review_flags": [], "human_review_required": False,
    }
    c.update(overrides)
    return c


def extraction_run(pg, snap: dict, **kw) -> str:
    return make_model_run(pg, "M02_CLAIM_EXTRACTOR",
                          [("article_snapshot", snap["snapshot_id"]), ("text_representation", snap["rep_id"])],
                          task_parameters={"article_snapshot_id": snap["snapshot_id"],
                                           "text_representation_id": snap["rep_id"]}, **kw)


def ingest(pg, snap: dict, run_id: str, claims: list[dict], **extra) -> dict:
    payload = {"model_run_id": run_id, "article_snapshot_id": snap["snapshot_id"],
               "text_representation_id": snap["rep_id"], "output_status": "SUCCESS",
               "human_review_required": False, "warnings": [], "claims": claims, **extra}
    with pg.worker() as c:
        return c.execute("SELECT lfhe.ingest_claim_extraction(%s::jsonb) AS r", (Jsonb(payload),)).fetchone()["r"]
