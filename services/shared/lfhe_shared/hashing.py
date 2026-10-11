"""Content hashing used across LFHÉ (raw bytes and canonical text)."""
from __future__ import annotations

import hashlib
import unicodedata


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def text_sha256(text: str) -> str:
    """SHA-256 of the UTF-8 encoding of *text* (must already be NFC).

    Matches the database CHECK on lfhe.text_representations.text_sha256."""
    if unicodedata.normalize("NFC", text) != text:
        raise ValueError("text must be NFC-normalised before hashing")
    return sha256_hex(text.encode("utf-8"))
