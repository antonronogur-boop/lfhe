# AI providers (P2-01)

| Provider | Adapter | Allow-listed settings (non-secret) | Credential |
| --- | --- | --- | --- |
| `fake` | `FakeProvider` (tests) | temperature [0,1], max_tokens [1,64000] | none |
| `anthropic` | `AnthropicProvider` (Messages API) | temperature [0,1], max_tokens [1,64000], top_p (0,1], timeout_seconds [1,600], provider_fixed_sampling (`true` only; never with temperature / top_p — CR7-01) | `LFHE_ANTHROPIC_API_KEY` env var, injected by the platform secret manager |

* The allow-list is enforced by the database (`lfhe.model_settings_problems`,
  trigger `model_configurations_validate_settings`, CHECK backstop) and mirrored in
  `lfhe_orchestrator.model_settings`. Base URLs, headers, organisation IDs, tools or
  keys can never be part of a model configuration.
* M02/M03 require an explicit `temperature ≤ 0.2` (low-variance extraction /
  classification); the runner refuses otherwise.
* The key is read only from the environment, sent only in the `x-api-key` header,
  never logged, never stored, and excluded from `repr()` and error messages.
* Untrusted-data boundary: the system prompt is exactly the activated, hash-verified
  `system.md`; the envelope (with all source text) is sent in the user message inside
  one `<lfhe_task_envelope>` block as JSON with `<`, `>`, `&` escaped, so source text
  cannot close the block. The model output is never trusted: schema validation and
  deterministic grounding decide what is persisted.
* Every call records `rendered_request_sha256`, provider response id, model and token
  usage in `model_runs.usage.provider`.
* OSINT boundary (TB-7): only collected public source text and closed taxonomies are
  sent; no restricted material is ever placed in an envelope.
* Error mapping: 401/403 → PROVIDER_AUTH_FAILED, 400 → PROVIDER_REQUEST_REJECTED
  (both non-retryable); 429/5xx/network → PROVIDER_UNAVAILABLE (retryable);
  `stop_reason = max_tokens` → PROVIDER_OUTPUT_TRUNCATED (output discarded).

## Claim-pipeline worker (Phase 2)

```
LFHE_ENV=DEV LFHE_DATABASE_URL=<worker login>  \
LFHE_M02_MODEL_CONFIGURATION_ID=<registered id> LFHE_M03_MODEL_CONFIGURATION_ID=<registered id> \
LFHE_ANTHROPIC_API_KEY=<from the secret manager> python -m lfhe_orchestrator.worker --once --enqueue
```
Model configurations are registered by the registrar (`lfhe.register_model_configuration('anthropic',
'<model>', '{"temperature": 0, "max_tokens": 8000}')`); M02/M03 require an explicit temperature ≤ 0.2.
M02/M03 prompt versions must be activated by a human (`PROMPT_ACTIVATE`).

## CR7-01 — models that reject `temperature`

Current Anthropic models (the 5.5 family) answer HTTP 400 "`temperature` is deprecated for this model". Register such a
model with `{"provider_fixed_sampling": true, "max_tokens": 16000, "timeout_seconds": 300}`: the adapter then sends no
sampling parameter, the low-variance rule accepts the explicit marker, and the marker is part of the configuration hash of
every model run. Models that still accept `temperature` keep the original configuration (`temperature ≤ 0.2`).

## CR7-02 — output contract in every request (PO decision 2026-10-25)

`render_messages` sends, after `task.md`, an OUTPUT CONTRACT instruction and the prompt version's registered, hash-verified
`output_schema.json` in an `<lfhe_output_schema>` block (canonical JSON, escaped like the envelope), then the untrusted-data
notice and the envelope (still last). Prompt bundles, versions and hashes are unchanged; validation, ingestion, QA and human
authority are unchanged.
