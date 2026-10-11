"""Exact original-language evidence-span resolution (foundation for F10).

Offsets are Unicode code points into an immutable, NFC-normalised
text_representation (offset_unit = UNICODE_CODE_POINT). Python ``str``
indexing is code-point based, so ``text[start:end]`` is exact.

Phase 1 provides only the resolution primitives; evidence spans, claims and
their tables are Phase 2.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass


class SpanError(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedSpan:
    start: int
    end: int
    text: str


def resolve_span(text: str, start: int, end: int, exact_text: str) -> ResolvedSpan:
    """Verify that ``text[start:end] == exact_text`` (no normalisation, no
    fuzzy matching, no translation)."""
    if not (0 <= start < end <= len(text)):
        raise SpanError(f"offsets [{start}, {end}) outside text of length {len(text)}")
    if unicodedata.normalize("NFC", exact_text) != exact_text:
        raise SpanError("exact_text is not NFC-normalised")
    found = text[start:end]
    if found != exact_text:
        raise SpanError("text at offsets does not equal exact_text")
    return ResolvedSpan(start, end, found)


def locate_unique(text: str, exact_text: str) -> ResolvedSpan:
    """Find *exact_text* in *text*; it must occur exactly once."""
    if not exact_text:
        raise SpanError("empty exact_text")
    first = text.find(exact_text)
    if first < 0:
        raise SpanError("exact_text not found in original-language text")
    if text.find(exact_text, first + 1) >= 0:
        raise SpanError("exact_text is ambiguous (occurs more than once); offsets required")
    return ResolvedSpan(first, first + len(exact_text), exact_text)
