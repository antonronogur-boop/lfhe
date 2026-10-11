"""P1-09 unit tests: write-once object store, span primitives, deterministic extraction."""
import os
import unicodedata

import pytest

from lfhe_collector.extract import extract, normalise_lines
from lfhe_collector.snapshots import excerpt
from lfhe_shared.hashing import sha256_hex, text_sha256
from lfhe_shared.spans import SpanError, locate_unique, resolve_span
from lfhe_shared.storage import LocalObjectStore, ObjectIntegrityError, content_key


def test_object_store_is_write_once_and_tamper_evident(tmp_path):
    store = LocalObjectStore(tmp_path)
    key = store.put_if_absent(b"original bytes")
    assert key == content_key(sha256_hex(b"original bytes"))
    assert store.put_if_absent(b"original bytes") == key  # idempotent
    assert store.get(key) == b"original bytes"
    path = tmp_path / key
    os.chmod(path, 0o644)
    path.write_bytes(b"tampered")
    with pytest.raises(ObjectIntegrityError):
        store.get(key)
    with pytest.raises(ObjectIntegrityError):
        store.put_if_absent(b"original bytes")  # existing object verified, not silently trusted
    with pytest.raises(ValueError):
        store.get("../../etc/passwd")


def test_text_hash_requires_nfc():
    with pytest.raises(ValueError):
        text_sha256(unicodedata.normalize("NFD", "Éves"))
    assert text_sha256("Éves") == sha256_hex("Éves".encode())


def test_span_primitives():
    text = "Képviselők szerint a gyakorlat jövő hónapban lesz. A gyakorlat rövid."
    s = locate_unique(text, "jövő hónapban")
    assert text[s.start:s.end] == "jövő hónapban"
    assert resolve_span(text, s.start, s.end, "jövő hónapban").start == s.start
    with pytest.raises(SpanError):
        resolve_span(text, s.start, s.end + 1, "jövő hónapban")
    with pytest.raises(SpanError):
        resolve_span(text, -1, 3, "Kép")
    with pytest.raises(SpanError, match="ambiguous"):
        locate_unique(text, "gyakorlat")
    with pytest.raises(SpanError, match="not found"):
        locate_unique(text, "next month")


def test_extraction_is_deterministic_and_normalised():
    html = ("<html lang='hu-HU'><head><title> Cím </title>"
            "<meta property='article:published_time' content='2026-10-05T10:00:00'></head>"
            "<body><nav>menü</nav><main><p>Első  sor</p><p></p><p>Masodik   sor</p></main></body></html>").encode()
    a = extract(html, "text/html", "utf-8")
    b = extract(html, "text/html", "utf-8")
    assert a == b
    assert a.clean_text == "Első sor\nMasodik sor" and a.title == "Cím"
    assert (a.language, a.language_method) == ("hu", "html_lang")
    assert a.published_at is None, "timestamp without zone is not used"


def test_extraction_records_decode_problems_and_non_text_types():
    bad = extract(b"<html><body><p>caf\xe9 au lait is served daily at the synthetic canteen.</p></body></html>",
                  "text/html", "utf-8")
    assert bad.notes["decode_replacements"] is True and "�" in bad.clean_text
    js = extract(b'{"a": 1}', "application/json", "utf-8", source_language="en")
    assert js.clean_text is None and js.language_method == "source_primary_language"


def test_excerpt_never_splits_a_combining_sequence():
    text = unicodedata.normalize("NFC", "ab" + "é" * 3)  # NFC composes é
    assert excerpt(text, 3) == text[:3]
    assert normalise_lines(" x \n\n  y  ") == "x\ny"


def test_concurrent_writers_never_observe_a_partial_object(tmp_path):
    """Regression (found in Phase 2): a second writer must not read a half-written object."""
    import threading
    store = LocalObjectStore(tmp_path)
    data = os.urandom(4 * 1024 * 1024)
    barrier, errors, keys = threading.Barrier(8), [], []

    def write():
        try:
            barrier.wait()
            keys.append(store.put_if_absent(data))
        except Exception as exc:  # surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=write) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and len(set(keys)) == 1
    assert store.get(keys[0]) == data and list(store.iter_keys()) == keys[:1]
