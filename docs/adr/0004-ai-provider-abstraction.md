# ADR-0004 — AI-provider abstraction

**Status:** Accepted

## Decision
All LLM calls go through `run_structured_task(module, envelope, model_config)`
(`services/ai-orchestrator/lfhe_orchestrator/provider.py`). Provider adapters
sit behind a small interface. No provider-specific code elsewhere.

Every call creates a `model_runs` row (module/version, provider, model,
settings, prompt_version_id + semantic version + content hash, input and
context snapshot hashes, raw and parsed output, status, usage). Output is
schema-validated; invalid output becomes `SCHEMA_VALIDATION_FAILED` and never
enters analytical tables.

## Phase 1 scope
Interface, model-run recording and a deterministic **fake** adapter for tests.
No real provider adapter and no analytical module (M02–M10) is implemented in
Phase 1 (PO decision, Control Gate 0).


## Amendment (CG1-05)

The runner entry point is `run_structured_task(conn, module_code, task, inputs, context, …)`;
the provider receives the canonical `lfhe-task-envelope/1` dict. Input (evidence) and context
objects are recorded as separately hashed manifests — see `docs/model-run-traceability.md`.
