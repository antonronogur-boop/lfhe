"""QA-D18 — deterministic original-language grounding (Python side).

The database (lfhe.claim_grounding_problems + the claims BEFORE INSERT
trigger) is authoritative. This module mirrors the text-level checks with the
SAME reason codes so the orchestrator can reject a candidate before ingestion
and explain why, and it resolves missing offsets deterministically:

* offsets supplied  → they must resolve exactly (text[start:end] == exact_text);
                      a wrong offset is a failure, never silently "corrected";
* offsets null      → exact_text must occur exactly once in the original text
                      (lfhe_shared.spans.locate_unique); otherwise failure.

No normalisation, fuzzy matching or translation is ever applied to evidence.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from .spans import SpanError, locate_unique

LOCATOR_TYPE = "TEXT_REPRESENTATION_CODE_POINTS"
NOT_GROUNDED = "CLAIM_NOT_GROUNDED_IN_ORIGINAL_SOURCE"


@dataclass(frozen=True)
class GroundingResult:
    problems: tuple[str, ...]
    span: dict | None              # resolved span incl. offsets + locator_type, when grounded
    offset_method: str | None      # MODEL_OFFSETS | UNIQUE_EXACT_MATCH

    @property
    def ok(self) -> bool:
        return not self.problems


def ground(original_text: str, original_language: str | None, span: dict | None,
           claim_text_original: str | None) -> GroundingResult:
    problems: list[str] = []
    if not isinstance(span, dict):
        return GroundingResult(("EXACT_TEXT_MISSING",), None, None)
    locator = span.get("locator_type", LOCATOR_TYPE)
    if locator != LOCATOR_TYPE:
        problems.append("LOCATOR_TYPE_UNSUPPORTED")
    if not original_language:
        problems.append("ORIGINAL_LANGUAGE_UNKNOWN")
    elif span.get("language") != original_language:
        problems.append("LANGUAGE_MISMATCH")
    exact = span.get("exact_text")
    if not isinstance(exact, str) or exact == "":
        return GroundingResult(tuple(problems + ["EXACT_TEXT_MISSING"]), None, None)
    if unicodedata.normalize("NFC", exact) != exact:
        problems.append("EXACT_TEXT_NOT_NFC")
    start, end = span.get("start"), span.get("end")
    method = None
    if start is None and end is None:
        try:
            located = locate_unique(original_text, exact)
        except SpanError as exc:
            problems.append("EXACT_TEXT_AMBIGUOUS" if "ambiguous" in str(exc) else "EXACT_TEXT_MISMATCH")
            return GroundingResult(tuple(problems), None, None)
        start, end, method = located.start, located.end, "UNIQUE_EXACT_MATCH"
    else:
        if not (isinstance(start, int) and isinstance(end, int)) or isinstance(start, bool) or isinstance(end, bool) \
                or start < 0 or end <= start or end > len(original_text):
            problems.append("OFFSETS_INVALID")
            return GroundingResult(tuple(problems), None, None)
        if original_text[start:end] != exact:
            problems.append("EXACT_TEXT_MISMATCH")
            return GroundingResult(tuple(problems), None, None)
        method = "MODEL_OFFSETS"
    if not claim_text_original or claim_text_original not in exact:
        problems.append("CLAIM_TEXT_ORIGINAL_NOT_IN_SPAN")
    if problems:
        return GroundingResult(tuple(problems), None, None)
    return GroundingResult((), {"exact_text": exact, "start": start, "end": end, "language": span.get("language"),
                                "locator_type": LOCATOR_TYPE}, method)
