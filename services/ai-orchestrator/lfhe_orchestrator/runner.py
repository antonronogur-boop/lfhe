"""Structured-task runner: one call = one immutable, fully traceable model_run.

    resolve ACTIVE prompt version for the module (database, per environment)
    → verify its content hash locally → start_model_run (copies semver, hash,
    module version, model config hash) → provider call → JSON parse → JSON
    Schema validation → finish_model_run (SUCCEEDED | SCHEMA_VALIDATION_FAILED
    | PROVIDER_ERROR).

No automatic repair or re-prompting: a schema failure is recorded as such.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from jsonschema import Draft202012Validator
from psycopg.types.json import Jsonb

from lfhe_shared.envelopes import EnvelopeItem, TaskEnvelope
from lfhe_shared.prompts import bundle_sha256

from .providers import ModelConfig, PromptModule, Provider, ProviderError

MAX_VALIDATION_ERRORS = 50


class NoActivePromptVersion(RuntimeError):
    pass


class PromptIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelRunResult:
    run_id: str
    status: str
    parsed_output: dict | None
    validation_errors: list | None
    error_code: str | None = None


def load_active_module(conn, module_code: str) -> tuple[str, PromptModule]:
    row = conn.execute(
        "SELECT * FROM lfhe.prompt_versions WHERE id = lfhe.current_prompt_version(%s)", (module_code,)).fetchone()
    if row is None:
        raise NoActivePromptVersion(f"no active prompt version for module {module_code}")
    if bundle_sha256(row["module_code"], row["semver"], row["files"]) != row["content_hash"]:
        raise PromptIntegrityError(f"{module_code} {row['semver']}: content does not match content_hash")
    files = row["files"]
    return str(row["id"]), PromptModule(row["module_code"], row["semver"], row["content_hash"],
                                        row["module_version"], files["system.md"], files["task.md"],
                                        json.loads(files["output_schema.json"]))


def validate_output(schema: dict, raw_text: str) -> tuple[dict | None, list | None]:
    try:
        parsed = json.loads(raw_text)
    except ValueError as exc:
        return None, [{"path": "", "message": f"output is not valid JSON: {exc}"}]
    errors = sorted(Draft202012Validator(schema).iter_errors(parsed), key=lambda e: list(map(str, e.path)))
    if errors:
        return None, [{"path": "/".join(map(str, e.path)), "message": e.message}
                      for e in errors[:MAX_VALIDATION_ERRORS]]
    if not isinstance(parsed, dict):
        return None, [{"path": "", "message": "output must be a JSON object"}]
    return parsed, None


class TraceIntegrityError(RuntimeError):
    pass


def run_structured_task(conn, *, module_code: str, task: dict, inputs: list[EnvelopeItem],
                        context: list[EnvelopeItem], model_configuration_id: str,
                        provider: Provider, worker_id: str, job_id: str | None = None) -> ModelRunResult:
    """``inputs`` = evidence/input objects, ``context`` = supplied context
    objects (CG1-05); both are recorded as separately hashed manifests."""
    envelope = TaskEnvelope(module_code, task, inputs, context)
    prompt_version_id, module = load_active_module(conn, module_code)
    mc = conn.execute("SELECT * FROM lfhe.model_configurations WHERE id=%s", (model_configuration_id,)).fetchone()
    if mc is None:
        raise ValueError(f"unknown model configuration {model_configuration_id}")
    if mc["provider"] != provider.name:
        raise ValueError(f"model configuration is for provider {mc['provider']!r}, not {provider.name!r}")
    config = ModelConfig(mc["provider"], mc["model"], mc["settings"])

    run_id = str(conn.execute(
        "SELECT lfhe.start_model_run(%s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s) AS id",
        (prompt_version_id, model_configuration_id, envelope.envelope_sha256, Jsonb(task),
         Jsonb(envelope.input_manifest), Jsonb(envelope.context_manifest), worker_id, job_id)).fetchone()["id"])
    stored = conn.execute("SELECT input_snapshot_sha256, context_snapshot_sha256 FROM lfhe.model_runs WHERE id=%s",
                          (run_id,)).fetchone()
    if (stored["input_snapshot_sha256"], stored["context_snapshot_sha256"]) != (
            envelope.input_snapshot_sha256, envelope.context_snapshot_sha256):
        conn.execute("SELECT lfhe.finish_model_run(%s, 'PROVIDER_ERROR', NULL, NULL, NULL, "
                     "'TRACE_INTEGRITY_ERROR', 'set hash mismatch', '{}'::jsonb)", (run_id,))
        raise TraceIntegrityError("database and runner disagree on input/context set hashes")

    def finish(status, raw=None, parsed=None, errors=None, code=None, message=None, usage=None):
        conn.execute("SELECT lfhe.finish_model_run(%s, %s::lfhe.model_run_status, %s, %s::jsonb, %s::jsonb, %s, %s, %s::jsonb)",
                     (run_id, status, raw, Jsonb(parsed) if parsed is not None else None,
                      Jsonb(errors) if errors is not None else None, code, message, Jsonb(usage or {})))

    try:
        response = provider.run_structured_task(module, envelope.as_dict(), config)
    except ProviderError as exc:
        finish("PROVIDER_ERROR", code=exc.code, message=str(exc))
        return ModelRunResult(run_id, "PROVIDER_ERROR", None, None, exc.code)
    except Exception as exc:  # never leave a run RUNNING
        finish("PROVIDER_ERROR", code="UNEXPECTED_PROVIDER_EXCEPTION", message=f"{type(exc).__name__}: {exc}")
        raise

    parsed, errors = validate_output(module.output_schema, response.raw_text)
    if errors:
        finish("SCHEMA_VALIDATION_FAILED", raw=response.raw_text, errors=errors,
               code="SCHEMA_VALIDATION_FAILED", usage=response.usage)
        return ModelRunResult(run_id, "SCHEMA_VALIDATION_FAILED", None, errors, "SCHEMA_VALIDATION_FAILED")
    finish("SUCCEEDED", raw=response.raw_text, parsed=parsed, usage=response.usage)
    return ModelRunResult(run_id, "SUCCEEDED", parsed, None)
