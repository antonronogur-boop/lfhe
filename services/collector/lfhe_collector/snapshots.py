"""Database snapshot sink (P1-09).

Turns a fetched item into an immutable original-language article snapshot via
``lfhe.record_snapshot`` (the only worker write path).

Retention (source.retention_mode, decided by a human at source approval):
  FULL              raw bytes → write-once object store; CANONICAL_CLEAN_TEXT stored
  PERMITTED_EXCERPT no raw bytes kept; PERMITTED_EXCERPT text (≤ excerpt_max_chars)
  METADATA_ONLY     no raw bytes, no text; hashes + metadata only
Raw SHA-256 is always recorded.

Identity (CG1-02, docs/snapshot-identity.md):
  * content hash (content_identity_sha256) = clean-text SHA-256 when text was
    extracted, otherwise raw SHA-256;
  * snapshot identity (source_state_sha256) = canonical hash of the source
    state built by ``source_state()``: content hash + final URL + media type +
    title + language + every source-stated timestamp (with field/basis) +
    discovery identifiers + retention mode. A change to any of these is a new
    snapshot version, even when the clean text is identical; cosmetic markup
    and volatile response metadata are not.
Raw bytes are written to the object store only after a read-only pre-check
shows the state is new, so routine duplicates create no unreferenced objects
(rare concurrent races are covered by scripts/object_store_reconcile.py).

Time model (normalisation of 2026-10-08; G-03):
  publication_datetime   only as stated by the source (page metadata preferred,
                         feed/API timestamp otherwise), with the field it came from
  public availability    = stated publication time, basis SOURCE_PUBLISHED_TIMESTAMP
                         / RSS_TIMESTAMP; confidence HIGH only when page and feed agree
                         within 1 h, else MODERATE
                         no stated time → NULL, UNKNOWN, DATE_UNCERTAIN
                         stated time after retrieval → NULL, LOW_CONFIDENCE_TIMESTAMP,
                         DATE_UNCERTAIN (flagged, never "corrected")
  "updated"/lastmod times → source_updated_datetime only, never publication
  system_retrieval_datetime = when LFHÉ fetched the bytes
  Event time is not a snapshot attribute.
"""
from __future__ import annotations

import unicodedata
from datetime import timedelta

from psycopg.types.json import Jsonb

from lfhe_shared.canonical_json import canonical_sha256
from lfhe_shared.hashing import sha256_hex, text_sha256
from lfhe_shared.storage import ObjectStore

from .adapters import DiscoveredItem
from .extract import PREPROCESSOR_NAME, PREPROCESSOR_VERSION, extract
from .http import FetchResult

AGREEMENT_WINDOW = timedelta(hours=1)
DEFAULT_EXCERPT_MAX_CHARS = 500
KEPT_RESPONSE_HEADERS = ("content-type", "content-length", "content-language", "last-modified",
                         "etag", "date", "cache-control")


def _iso(dt):
    return dt.isoformat() if dt else None


def excerpt(text: str, max_chars: int) -> str:
    cut = text[:max_chars]
    while cut and unicodedata.normalize("NFC", cut) != cut:
        cut = cut[:-1]
    return cut


def _text_payload(kind: str, text: str, language: str | None) -> dict:
    return {"representation_type": kind, "preprocessor_name": PREPROCESSOR_NAME,
            "preprocessor_version": PREPROCESSOR_VERSION, "language": language,
            "text_content": text, "text_sha256": text_sha256(text), "char_length": len(text)}


def timestamp_fields(item: DiscoveredItem, page_published, page_field, retrieved_at) -> tuple[dict, dict]:
    stated = []
    if page_published:
        stated.append({"value": _iso(page_published), "field": page_field, "basis": "SOURCE_PUBLISHED_TIMESTAMP"})
    if item.published_at:
        stated.append({"value": _iso(item.published_at), "field": item.published_field,
                       "basis": item.published_basis})
    flags: dict = {"stated_publication_timestamps": stated} if stated else {}

    if page_published:
        publication, field, basis = page_published, page_field, "SOURCE_PUBLISHED_TIMESTAMP"
    elif item.published_at:
        publication, field, basis = item.published_at, item.published_field, item.published_basis
    else:
        return ({"publication_datetime": None, "publication_datetime_field": None,
                 "public_availability_datetime": None, "public_availability_basis": "UNKNOWN",
                 "public_availability_confidence": "UNKNOWN", "date_status": "DATE_UNCERTAIN"}, flags)

    if publication > retrieved_at:
        flags["publication_after_retrieval"] = True
        return ({"publication_datetime": _iso(publication), "publication_datetime_field": field,
                 "public_availability_datetime": None, "public_availability_basis": "LOW_CONFIDENCE_TIMESTAMP",
                 "public_availability_confidence": "LOW", "date_status": "DATE_UNCERTAIN"}, flags)

    confidence = "MODERATE"
    if page_published and item.published_at:
        if abs(page_published - item.published_at) <= AGREEMENT_WINDOW:
            confidence = "HIGH"
        else:
            flags["publication_timestamp_conflict"] = True
    return ({"publication_datetime": _iso(publication), "publication_datetime_field": field,
             "public_availability_datetime": _iso(publication), "public_availability_basis": basis,
             "public_availability_confidence": confidence, "date_status": "OK"}, flags)


SNAPSHOT_STATE_FORMAT = "lfhe-snapshot-state/1"


def source_state(*, final_url: str, media_type: str, content_sha256: str, content_basis: str,
                 title: str | None, language: str | None, language_method: str,
                 stated_publication: list[dict], source_updated: str | None, source_updated_field: str | None,
                 discovery: dict, retention_mode: str) -> dict:
    """The provenance-relevant state of one fetched document (identity A).
    Only strings / nulls / lists / objects → stable under jsonb round-trip."""
    return {
        "format": SNAPSHOT_STATE_FORMAT,
        "final_url": final_url,
        "media_type": media_type,
        "content": {"sha256": content_sha256, "basis": content_basis},
        "title_original": title,
        "language": language,
        "language_method": language_method,
        "stated_publication": stated_publication,
        "source_updated": {"value": source_updated, "field": source_updated_field} if source_updated else None,
        "discovery": discovery,
        "retention_mode": retention_mode,
    }


DISCOVERY_IDENTITY_KEYS = ("guid", "title", "author")


class DatabaseSnapshotSink:
    def __init__(self, conn, store: ObjectStore):
        self.conn = conn
        self.objects = store
        self.last_result: dict | None = None

    def store(self, source: dict, item: DiscoveredItem, canonical_url: str,
              fetched: FetchResult, run_id: str) -> str:
        return self.record(source, item, canonical_url, fetched, run_id)

    def record(self, source, item, canonical_url, fetched, run_id) -> str:
        retention = source["retention_mode"]
        ex = extract(fetched.content, fetched.media_type, fetched.charset,
                     language_hint=item.language_hint, source_language=source.get("primary_language"))
        raw_hash = sha256_hex(fetched.content)
        content_hash = text_sha256(ex.clean_text) if ex.clean_text else raw_hash

        text = None
        if ex.clean_text and retention == "FULL":
            text = _text_payload("CANONICAL_CLEAN_TEXT", ex.clean_text, ex.language)
        elif ex.clean_text and retention == "PERMITTED_EXCERPT":
            limit = int(source["collection_config"].get("excerpt_max_chars", DEFAULT_EXCERPT_MAX_CHARS))
            text = _text_payload("PERMITTED_EXCERPT", excerpt(ex.clean_text, limit), ex.language)

        times, time_flags = timestamp_fields(item, ex.published_at, ex.published_field, fetched.retrieved_at)
        updated, updated_field = ex.modified_at, ex.modified_field
        if updated is None and item.updated_at is not None:
            updated = item.updated_at
            updated_field = item.metadata.get("sitemap_lastmod_basis") and "sitemap:lastmod" or "feed:updated"
        title = ex.title or item.title
        discovery = {**item.metadata, **({"title": item.title} if item.title else {})}

        state = source_state(
            final_url=fetched.final_url, media_type=fetched.media_type, content_sha256=content_hash,
            content_basis="clean_text" if ex.clean_text else "raw", title=title, language=ex.language,
            language_method=ex.language_method,
            stated_publication=time_flags.get("stated_publication_timestamps", []),
            source_updated=_iso(updated), source_updated_field=updated_field,
            discovery={k: str(discovery[k]) for k in DISCOVERY_IDENTITY_KEYS if discovery.get(k)},
            retention_mode=retention)
        state_hash = canonical_sha256(state)

        if self.conn.execute("SELECT lfhe.snapshot_state_is_current(%s, %s, %s) AS cur",
                             (str(source["id"]), canonical_url, state_hash)).fetchone()["cur"]:
            self.last_result = {"outcome": "DUPLICATE", "precheck": True}
            return "DUPLICATE"  # nothing written: no object, no row

        raw_key = self.objects.put_if_absent(fetched.content) if retention == "FULL" else None
        headers = {k: v for k, v in fetched.headers.items() if k.lower() in KEPT_RESPONSE_HEADERS}
        payload = {
            "source_id": str(source["id"]), "collection_run_id": run_id,
            "canonical_url": canonical_url, "requested_url": fetched.requested_url,
            "final_url": fetched.final_url, "redirect_chain": list(fetched.redirects),
            "http_status": fetched.status_code, "content_type": fetched.content_type or "",
            "response_headers": headers, "raw_content_sha256": raw_hash,
            "raw_size_bytes": len(fetched.content), "raw_storage_key": raw_key,
            "retention_mode_applied": retention, "content_identity_sha256": content_hash,
            "title_original": title, "language": ex.language,
            "language_method": ex.language_method,
            **times,
            "source_updated_datetime": _iso(updated), "source_updated_datetime_field": updated_field,
            "system_retrieval_datetime": _iso(fetched.retrieved_at),
            "metadata": {"discovery": discovery, "extraction": ex.notes,
                         "content_identity_basis": "clean_text_sha256" if ex.clean_text else "raw_sha256",
                         **time_flags},
            "source_state": state, "source_state_sha256": state_hash,
            "text": text,
        }
        result = self.conn.execute("SELECT lfhe.record_snapshot(%s::jsonb) AS r", (Jsonb(payload),)).fetchone()["r"]
        self.last_result = result
        return result["outcome"]
