"""Task envelopes and their verifiable hashes (CG1-05).

    envelope = {
      "format": "lfhe-task-envelope/1",
      "module_code": ...,
      "task": {...},                                   # task parameters
      "inputs":  [{"object_type", "object_id", "content_sha256", "content"}, ...],
      "context": [{"object_type", "object_id", "content_sha256", "content"}, ...],
    }

* item.content_sha256   = canonical_sha256(item.content)   (RFC 8785)
* envelope_sha256       = canonical_sha256(envelope)        — exact bytes-level identity
* input_snapshot_sha256 = set_sha256("lfhe-input-set/1", manifest(inputs))
* context_snapshot_sha256 = set_sha256("lfhe-context-set/1", manifest(context))
  (identical to lfhe.object_set_sha256 in the database)

Inputs and context are sorted by (object_type, object_id) inside the envelope,
so the envelope hash does not depend on caller ordering.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from .canonical_json import canonical_sha256

ENVELOPE_FORMAT = "lfhe-task-envelope/1"
INPUT_SET_FORMAT = "lfhe-input-set/1"
CONTEXT_SET_FORMAT = "lfhe-context-set/1"
_TYPE = re.compile(r"^[a-z][a-z0-9_]{1,62}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")


class EnvelopeError(ValueError):
    pass


@dataclass(frozen=True)
class EnvelopeItem:
    object_type: str
    object_id: str
    content: Any

    def __post_init__(self):
        if not _TYPE.match(self.object_type) or not _ID.match(self.object_id):
            raise EnvelopeError(f"invalid object reference {self.object_type}:{self.object_id}")

    @property
    def content_sha256(self) -> str:
        return canonical_sha256(self.content)

    def manifest_entry(self) -> dict:
        return {"object_type": self.object_type, "object_id": self.object_id, "content_sha256": self.content_sha256}


def _sorted(items: list[EnvelopeItem]) -> list[EnvelopeItem]:
    keys = [(i.object_type, i.object_id) for i in items]
    if len(set(keys)) != len(keys):
        raise EnvelopeError("duplicate object in envelope set")
    return sorted(items, key=lambda i: (i.object_type.encode(), i.object_id.encode()))


def manifest(items: list[EnvelopeItem]) -> list[dict]:
    return [i.manifest_entry() for i in _sorted(items)]


def set_sha256(fmt: str, manifest_entries: list[dict]) -> str:
    lines = [fmt] + [f"{m['object_type']} {m['object_id']} {m['content_sha256']}"
                     for m in sorted(manifest_entries, key=lambda m: (m["object_type"].encode(), m["object_id"].encode()))]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TaskEnvelope:
    module_code: str
    task: dict
    inputs: list[EnvelopeItem]
    context: list[EnvelopeItem]

    def as_dict(self) -> dict:
        return {
            "format": ENVELOPE_FORMAT,
            "module_code": self.module_code,
            "task": self.task,
            "inputs": [{**i.manifest_entry(), "content": i.content} for i in _sorted(self.inputs)],
            "context": [{**i.manifest_entry(), "content": i.content} for i in _sorted(self.context)],
        }

    @property
    def envelope_sha256(self) -> str:
        return canonical_sha256(self.as_dict())

    @property
    def input_manifest(self) -> list[dict]:
        return manifest(self.inputs)

    @property
    def context_manifest(self) -> list[dict]:
        return manifest(self.context)

    @property
    def input_snapshot_sha256(self) -> str:
        return set_sha256(INPUT_SET_FORMAT, self.input_manifest)

    @property
    def context_snapshot_sha256(self) -> str:
        return set_sha256(CONTEXT_SET_FORMAT, self.context_manifest)


def verify_envelope(envelope: dict, run: dict) -> list[str]:
    """Independently check a stored model_run against an envelope rebuilt from
    the referenced objects' contents."""
    problems = []
    if canonical_sha256(envelope) != run["envelope_sha256"]:
        problems.append("envelope_sha256 mismatch")
    for key, fmt, col in (("inputs", INPUT_SET_FORMAT, "input"), ("context", CONTEXT_SET_FORMAT, "context")):
        entries = []
        for item in envelope[key]:
            if canonical_sha256(item["content"]) != item["content_sha256"]:
                problems.append(f"{key}: content hash mismatch for {item['object_type']}:{item['object_id']}")
            entries.append({k: item[k] for k in ("object_type", "object_id", "content_sha256")})
        if set_sha256(fmt, entries) != run[f"{col}_snapshot_sha256"]:
            problems.append(f"{col}_snapshot_sha256 mismatch")
    return problems
