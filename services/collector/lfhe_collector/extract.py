"""Deterministic extraction from a fetched original-language document.

Preprocessor ``lfhe-clean-text`` 1.0.0 — any change to the algorithm below
MUST bump PREPROCESSOR_VERSION, because evidence-span offsets (Phase 2) point
into the text it produces and stored text representations are immutable.

Algorithm (v1.0.0):
  1. Decode bytes: HTTP charset → <meta charset> → UTF-8. Undecodable bytes
     are replaced (U+FFFD) and the replacement is recorded, never hidden.
  2. HTML (text/html, application/xhtml+xml): parse with the stdlib-backed
     ``html.parser``; drop script, style, noscript, template, nav, footer,
     header, aside, form, iframe, svg; take the first <article>, else <main>,
     else <body>, else the document.
     text/plain: the decoded text as-is.  Other types: no clean text.
  3. Split into lines, collapse internal whitespace runs to one space, strip,
     drop empty lines, join with "\\n".
  4. Unicode NFC.
Text is never translated, summarised or "cleaned" of content: hidden or
instruction-like text inside the article body is preserved verbatim as data.

Timestamps are taken only where the document states them with a time zone;
nothing is inferred.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone

from bs4 import BeautifulSoup

PREPROCESSOR_NAME = "lfhe-clean-text"
PREPROCESSOR_VERSION = "1.0.0"
DETECTOR_MIN_CHARS = 40

_DROP_TAGS = ("script", "style", "noscript", "template", "nav", "footer", "header",
              "aside", "form", "iframe", "svg")
_WS = re.compile(r"[ \t  -​  　\f\v\r]+")
_META_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?([A-Za-z0-9_\-:.]+)""", re.I)
_LANG = re.compile(r"^[a-z]{2,3}$")

_PUBLISHED_META = (
    ("property", "article:published_time"),
    ("name", "article:published_time"),
    ("itemprop", "datePublished"),
    ("name", "dc.date.issued"),
    ("name", "dc.date"),
    ("name", "date"),
)
_MODIFIED_META = (
    ("property", "article:modified_time"),
    ("itemprop", "dateModified"),
    ("name", "dc.date.modified"),
)


@dataclass
class Extraction:
    clean_text: str | None
    title: str | None
    language: str | None
    language_method: str
    published_at: datetime | None = None
    published_field: str | None = None
    modified_at: datetime | None = None
    modified_field: str | None = None
    notes: dict = field(default_factory=dict)


def _parse_ts(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None  # no zone stated → ambiguous → not used
    return dt.astimezone(timezone.utc)


def _decode(content: bytes, http_charset: str | None, notes: dict) -> str:
    charset = http_charset
    if not charset:
        m = _META_CHARSET.search(content[:4096])
        charset = m.group(1).decode("ascii", "ignore") if m else None
    charset = charset or "utf-8"
    try:
        text = content.decode(charset)
    except (LookupError, UnicodeDecodeError):
        text = content.decode(charset if _codec_exists(charset) else "utf-8", errors="replace")
        notes["decode_replacements"] = True
    notes["charset"] = charset.lower()
    return text


def _codec_exists(name: str) -> bool:
    import codecs
    try:
        codecs.lookup(name)
        return True
    except LookupError:
        return False


def normalise_lines(text: str) -> str:
    lines = (_WS.sub(" ", line).strip() for line in text.split("\n"))
    return unicodedata.normalize("NFC", "\n".join(line for line in lines if line))


def _norm_lang(value: str | None) -> str | None:
    if not value:
        return None
    primary = value.strip().replace("_", "-").split("-")[0].lower()
    return primary if _LANG.match(primary) else None


def _jsonld_objects(soup):
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or "")
        except (ValueError, TypeError):
            continue
        stack = [data]
        while stack:
            obj = stack.pop(0)
            if isinstance(obj, list):
                stack.extend(obj)
            elif isinstance(obj, dict):
                yield obj
                if "@graph" in obj:
                    stack.append(obj["@graph"])


def _stated_time(soup, meta_keys, jsonld_key):
    for attr, key in meta_keys:
        for tag in soup.find_all(["meta", "time"], attrs={attr: re.compile(f"^{re.escape(key)}$", re.I)}):
            dt = _parse_ts(tag.get("content") or tag.get("datetime"))
            if dt:
                return dt, f"html:{attr}={key}"
    for obj in _jsonld_objects(soup):
        dt = _parse_ts(obj.get(jsonld_key))
        if dt:
            return dt, f"jsonld:{jsonld_key}"
    return None, None


def _detect(text: str) -> str | None:
    if len(text) < DETECTOR_MIN_CHARS:
        return None
    import py3langid
    lang, _ = py3langid.classify(text)
    return _norm_lang(lang)


def extract(content: bytes, media_type: str | None, http_charset: str | None, *,
            language_hint: str | None = None, source_language: str | None = None) -> Extraction:
    notes: dict = {}
    media_type = (media_type or "").lower()
    title = clean = html_lang = None
    published = modified = (None, None)

    if media_type in ("text/html", "application/xhtml+xml"):
        soup = BeautifulSoup(_decode(content, http_charset, notes), "html.parser")
        html_tag = soup.find("html")
        html_lang = _norm_lang(html_tag.get("lang") if html_tag else None)
        if soup.title and soup.title.string:
            title = normalise_lines(soup.title.get_text(" ")) or None
        if not title:
            og = soup.find("meta", attrs={"property": "og:title"})
            title = normalise_lines(og.get("content", "")) if og else None
        published = _stated_time(soup, _PUBLISHED_META, "datePublished")
        modified = _stated_time(soup, _MODIFIED_META, "dateModified")
        for tag in soup.find_all(_DROP_TAGS):
            tag.decompose()
        root = soup.find("article") or soup.find("main") or soup.find("body") or soup
        notes["content_root"] = root.name if root is not soup else "document"
        clean = normalise_lines(root.get_text("\n"))
    elif media_type == "text/plain":
        clean = normalise_lines(_decode(content, http_charset, notes))
    else:
        notes["no_clean_text_reason"] = f"media type {media_type or 'unknown'} not text-extractable"

    clean = clean or None
    if html_lang:
        language, method = html_lang, "html_lang"
    elif _norm_lang(language_hint):
        language, method = _norm_lang(language_hint), "feed_language"
    elif clean and (detected := _detect(clean)):
        language, method = detected, "detector"
    elif _norm_lang(source_language):
        language, method = _norm_lang(source_language), "source_primary_language"
    else:
        language, method = None, "none"

    return Extraction(clean, title, language, method, published[0], published[1],
                      modified[0], modified[1], notes)
