"""Credential-key rule 'lfhe-credential-keys/1' (CG1-03).

Exact mirror of lfhe.is_credential_key / lfhe.credential_key_paths (the
database is authoritative; this copy gives early, readable errors and is
cross-checked against the database by tests)."""
from __future__ import annotations

import re
from typing import Any

FORBIDDEN_SEGMENTS = frozenset({
    "headers", "header", "auth", "authorization", "authentication", "cookies", "cookie",
    "password", "passwords", "passwd", "token", "secret", "secrets", "apikey",
    "credential", "credentials", "bearer",
})
FORBIDDEN_LAST_SEGMENTS = frozenset({"key", "keys"})


def normalise_key(key: str) -> str:
    k = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key).lower()
    return re.sub(r"[^a-z0-9]+", "_", k).strip("_")


def is_credential_key(key: str) -> bool:
    segments = normalise_key(key).split("_")
    return bool(FORBIDDEN_SEGMENTS.intersection(segments)) or segments[-1] in FORBIDDEN_LAST_SEGMENTS


def credential_key_paths(value: Any, path: str = "$") -> list[str]:
    out: list[str] = []
    if isinstance(value, dict):
        for key in sorted(value, key=lambda k: k.encode("utf-8")):
            if is_credential_key(key):
                out.append(f"{path}.{key}")
            out.extend(credential_key_paths(value[key], f"{path}.{key}"))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            out.extend(credential_key_paths(v, f"{path}[{i}]"))
    return out
