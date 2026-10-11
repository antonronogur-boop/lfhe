"""Deterministic URL canonicalisation (DS §9, §32).

Used for article identity: the same canonical URL within one source is the
same ARTICLE; content changes become new snapshot versions of it.
"""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PREFIXES = ("utm_",)
TRACKING_KEYS = {"fbclid", "gclid", "dclid", "mc_cid", "mc_eid", "yclid", "_hsenc", "_hsmi", "ref_src"}


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower().rstrip(".")
    port = parts.port
    netloc = host if port is None or (scheme, port) in (("http", 80), ("https", 443)) else f"{host}:{port}"
    path = parts.path or "/"
    query = urlencode(sorted(
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith(TRACKING_PREFIXES) and k.lower() not in TRACKING_KEYS
    ))
    return urlunsplit((scheme, netloc, path, query, ""))
