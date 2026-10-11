# AI providers (P2-01)

| Provider | Adapter | Allow-listed settings (non-secret) | Credential |
| --- | --- | --- | --- |
| `fake` | `FakeProvider` (tests) | temperature [0,1], max_tokens [1,64000] | none |
| `anthropic` | `AnthropicProvider` (Messages API) | temperature [0,1], max_tokens [1,64000], top_p (0,1], timeout_seconds [1,600] | `LFHE_ANTHROPIC_API_KEY` env var, injected by the platform secret manager |

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
