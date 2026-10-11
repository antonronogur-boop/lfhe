# Model-run traceability (CG1-05)

Each `lfhe.model_runs` row proves, independently verifiable:

| Question | Field(s) | How it is computed / enforced |
| --- | --- | --- |
| Exactly what was sent? | `envelope_sha256` | RFC 8785 SHA-256 of the task envelope `lfhe-task-envelope/1` (runner) |
| Which evidence / input objects, with which exact content? | `input_manifest`, `input_snapshot_sha256` | manifest = `[{object_type, object_id, content_sha256}]`; set hash computed **and CHECKed by the database** |
| Which context objects, with which exact content? | `context_manifest`, `context_snapshot_sha256` | same, format `lfhe-context-set/1` |
| Which task parameters? | `task_parameters` | stored verbatim (part of the envelope) |
| Which prompt? | `prompt_version_id`, `prompt_semver`, `prompt_content_hash`, `module_version` | composite FK to the immutable prompt registry |
| Which model configuration? | `model_configuration_id`, `provider`, `model`, `model_config_hash` | composite FK to the immutable configuration registry |

## Formats

```
item.content_sha256     = sha256(RFC8785(item.content))
envelope                = {"format": "lfhe-task-envelope/1", "module_code", "task",
                           "inputs":  [{object_type, object_id, content_sha256, content}…],
                           "context": [{object_type, object_id, content_sha256, content}…]}
                          (inputs and context sorted by (object_type, object_id))
envelope_sha256         = sha256(RFC8785(envelope))
set hash                = sha256(format + for each item sorted by (object_type, object_id), C order:
                                 "\n" + object_type + " " + object_id + " " + content_sha256)
input_snapshot_sha256   = set hash with format "lfhe-input-set/1"
context_snapshot_sha256 = set hash with format "lfhe-context-set/1"
```

The set hashes are order-independent and reject duplicates. Moving the same
object from input to context changes both set hashes (role is part of the
identity). Task parameters change only `envelope_sha256`.

## Verification

`lfhe_shared.envelopes.verify_envelope(envelope, run)` rebuilds every hash from
the referenced objects' contents. The database recomputes the two set hashes
on insert (`lfhe.object_set_sha256`) and refuses manifests that are malformed
or contain duplicates; the runner aborts (and closes the run as
`TRACE_INTEGRITY_ERROR`) if its own set hashes disagree with the database.

Phase 1 stores manifests and hashes, not the envelope body; Phase 2 decides
where envelope bodies are retained (object store) for full replay.
