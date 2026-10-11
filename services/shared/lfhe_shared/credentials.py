"""Credential-key rule 'lfhe-credential-keys/1' (CG1-03).

Exact mirror of lfhe.is_credential_key / lfhe.credential_key_paths (the
database is authoritative; this copy gives early, readable errors and is
cross-checked against the database by tests)."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote_plus

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


# -- CG1-08: credentials hidden in URL values ----------------------------------
_ABSOLUTE_URL = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")


def url_credential_problems(url: str) -> list[str]:
    """Mirror of lfhe.url_credential_problems: userinfo in the authority, or a
    query/fragment parameter whose decoded NAME is credential-like. Values are
    never returned."""
    if not isinstance(url, str) or not _ABSOLUTE_URL.match(url):
        return []
    out: list[str] = []
    authority = re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://([^/?#]*)", url).group(1)
    if "@" in authority or "%40" in authority.lower():
        out.append("USERINFO")
    query = re.search(r"\?([^#]*)", url)
    fragment = re.search(r"#(.*)$", url)
    params = (query.group(1) if query else "") + "&" + (fragment.group(1) if fragment else "")
    for part in params.split("&"):
        if not part:
            continue
        name = unquote_plus(part.split("=", 1)[0])
        if name and is_credential_key(name):
            out.append(f"CREDENTIAL_PARAMETER:{name.lower()}")
    return out


def credential_url_paths(value: Any, path: str = "$") -> list[str]:
    out: list[str] = []
    if isinstance(value, str):
        out.extend(f"{path} ({p})" for p in url_credential_problems(value))
    elif isinstance(value, dict):
        for key in sorted(value, key=lambda k: k.encode("utf-8")):
            out.extend(credential_url_paths(value[key], f"{path}.{key}"))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            out.extend(credential_url_paths(v, f"{path}[{i}]"))
    return out
