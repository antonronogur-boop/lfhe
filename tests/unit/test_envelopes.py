"""CG1-05 — deterministic envelope / input-set / context-set hashes."""
import hashlib

import pytest

from lfhe_shared.canonical_json import canonical_sha256
from lfhe_shared.envelopes import EnvelopeError, EnvelopeItem, TaskEnvelope, set_sha256, verify_envelope

A = EnvelopeItem("text_representation", "aaaa-1", {"text": "Első bizonyíték", "lang": "hu"})
B = EnvelopeItem("text_representation", "bbbb-2", {"text": "Друге джерело", "lang": "uk"})
C = EnvelopeItem("reference_context", "ctx-1", {"note": "context"})


def test_known_vector_for_set_hash():
    entries = [{"object_type": "t", "object_id": "1", "content_sha256": "0" * 64}]
    expected = hashlib.sha256(("lfhe-input-set/1\nt 1 " + "0" * 64).encode()).hexdigest()
    assert set_sha256("lfhe-input-set/1", entries) == expected
    assert set_sha256("lfhe-input-set/1", []) == hashlib.sha256(b"lfhe-input-set/1").hexdigest()


def test_hashes_are_order_independent_and_deterministic():
    e1 = TaskEnvelope("T_X", {"k": 1}, [A, B], [C])
    e2 = TaskEnvelope("T_X", {"k": 1}, [B, A], [C])
    assert e1.as_dict() == e2.as_dict()
    assert (e1.envelope_sha256, e1.input_snapshot_sha256, e1.context_snapshot_sha256) == \
        (e2.envelope_sha256, e2.input_snapshot_sha256, e2.context_snapshot_sha256)


def test_input_and_context_hashes_are_separate():
    base = TaskEnvelope("T_X", {}, [A], [C])
    other_ctx = TaskEnvelope("T_X", {}, [A], [EnvelopeItem("reference_context", "ctx-1", {"note": "changed"})])
    other_input = TaskEnvelope("T_X", {}, [EnvelopeItem("text_representation", "aaaa-1", {"text": "x"})], [C])
    moved = TaskEnvelope("T_X", {}, [A, C], [])  # same objects, different role
    assert base.input_snapshot_sha256 == other_ctx.input_snapshot_sha256
    assert base.context_snapshot_sha256 != other_ctx.context_snapshot_sha256
    assert base.input_snapshot_sha256 != other_input.input_snapshot_sha256
    assert base.context_snapshot_sha256 == other_input.context_snapshot_sha256
    assert moved.input_snapshot_sha256 != base.input_snapshot_sha256
    assert len({base.envelope_sha256, other_ctx.envelope_sha256, other_input.envelope_sha256,
                moved.envelope_sha256}) == 4
    assert base.input_manifest == [{"object_type": "text_representation", "object_id": "aaaa-1",
                                    "content_sha256": canonical_sha256(A.content)}]


def test_task_parameters_change_only_the_envelope_hash():
    a, b = TaskEnvelope("T_X", {"k": 1}, [A], [C]), TaskEnvelope("T_X", {"k": 2}, [A], [C])
    assert a.envelope_sha256 != b.envelope_sha256
    assert (a.input_snapshot_sha256, a.context_snapshot_sha256) == (b.input_snapshot_sha256, b.context_snapshot_sha256)


def test_verify_envelope_detects_tampering():
    e = TaskEnvelope("T_X", {}, [A, B], [C])
    run = {"envelope_sha256": e.envelope_sha256, "input_snapshot_sha256": e.input_snapshot_sha256,
           "context_snapshot_sha256": e.context_snapshot_sha256}
    assert verify_envelope(e.as_dict(), run) == []
    tampered = e.as_dict()
    tampered["inputs"][0]["content"]["text"] = "altered"
    problems = verify_envelope(tampered, run)
    assert "envelope_sha256 mismatch" in problems and any("content hash mismatch" in p for p in problems)


def test_invalid_references_and_duplicates_rejected():
    with pytest.raises(EnvelopeError):
        EnvelopeItem("Bad Type", "x", {})
    with pytest.raises(EnvelopeError):
        EnvelopeItem("text_representation", "has space", {})
    with pytest.raises(EnvelopeError, match="duplicate"):
        TaskEnvelope("T_X", {}, [A, A], []).input_manifest
