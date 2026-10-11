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


# -- CG1-08 / CG1-08A: credentials hidden in URL values ----------------------
_SCHEME_SLASHES = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://([^/?#]*)")
_SPECIAL_SCHEME = re.compile(r"^(https?|wss?|ftp|file):", re.IGNORECASE)
_SPECIAL_AUTHORITY = re.compile(r"^[A-Za-z]+:/*([^/?#]*)")


def url_inspection_form(value: str) -> str:
    """Mirror of lfhe.url_inspection_form: remove tab/LF/CR everywhere, trim
    leading/trailing U+0001–U+0020, read '\\' as '/' (how URL parsers read it)."""
    v = re.sub(r"[\t\n\r]", "", value)
    v = re.sub(r"^[\x01-\x20]+|[\x01-\x20]+$", "", v)
    return v.replace("\\", "/")


def url_credential_problems(url: str) -> list[str]:
    """Mirror of lfhe.url_credential_problems (CG1-08A): userinfo in the
    authority of an absolute or protocol-relative URL, or a query/fragment
    parameter with a credential-like decoded NAME in ANY string. Values are
    never returned."""
    if not isinstance(url, str):
        return []
    v = url_inspection_form(url)
    authority = None
    if m := _SCHEME_SLASHES.match(v):
        authority = m.group(1)
    elif _SPECIAL_SCHEME.match(v):
        authority = _SPECIAL_AUTHORITY.match(v).group(1)
    elif v.startswith("//"):
        authority = re.match(r"^//([^/?#]*)", v).group(1)
    out: list[str] = []
    if authority is not None and ("@" in authority or "%40" in authority.lower()):
        out.append("USERINFO")
    if "?" in v or "#" in v:
        query = re.search(r"\?([^#]*)", v)
        fragment = re.search(r"#(.*)$", v)
        params = (query.group(1) if query else "") + "&" + (fragment.group(1) if fragment else "")
        for part in params.split("&"):
            if not part:
                continue
            name = unquote_plus(part.split("=", 1)[0])
            if name and is_credential_key(name):
                out.append(f"CREDENTIAL_PARAMETER:{name.lower()}")
    return out


_CANONICAL_HTTP = re.compile(r"^https?://[a-z0-9._~%:\[\]-]+([/?#].*)?\Z", re.IGNORECASE | re.DOTALL)
_SOURCE_URL_FIELDS = {"RSS_ATOM": "feed_url", "STRUCTURED_FEED": "sitemap_url", "OFFICIAL_API": "endpoint"}


def is_canonical_http_url(value) -> bool:
    return (isinstance(value, str) and bool(_CANONICAL_HTTP.match(value))
            and not re.search(r"[\x01-\x20\x7f\\]", value))


def _url_field_problems(value, path: str) -> list[str]:
    if value is None:
        return [f"{path} (MISSING)"]
    if not isinstance(value, str):
        return [f"{path} (NOT_A_STRING)"]
    out = [] if is_canonical_http_url(value) else [f"{path} (NOT_CANONICAL_ABSOLUTE_HTTP_URL)"]
    return out + [f"{path} ({p})" for p in url_credential_problems(value)]


def source_config_problems(method: str, config) -> list[str]:
    """Mirror of lfhe.source_config_problems (CG1-08A)."""
    if not isinstance(config, dict):
        return ["$ (NOT_AN_OBJECT)"]
    if method in _SOURCE_URL_FIELDS:
        field = _SOURCE_URL_FIELDS[method]
        return _url_field_problems(config.get(field), f"$.{field}")
    if method == "HTTP_FETCH":
        urls = config.get("urls")
        if urls is None:
            return ["$.urls (MISSING)"]
        if not isinstance(urls, list) or not urls:
            return ["$.urls (NOT_A_NON_EMPTY_ARRAY)"]
        out: list[str] = []
        for i, u in enumerate(urls):
            out += _url_field_problems(u, f"$.urls[{i}]")
        return out
    return []


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
