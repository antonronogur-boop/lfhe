"""P1-10 unit tests: canonical JSON (RFC 8785), prompt bundles, lock file."""
import json
import shutil

import pytest

from conftest import REPO_ROOT
from lfhe_shared.canonical_json import CanonicalJsonError, canonical_dumps, canonical_sha256
from lfhe_shared.prompts import PromptBundleError, build_lock, check_lock, load_bundle

FIXTURE = REPO_ROOT / "tests/fixtures/prompts/T00_ECHO/1.0.0"


@pytest.mark.parametrize("value,expected", [
    ({"b": 1, "a": [True, None, "x"]}, '{"a":[true,null,"x"],"b":1}'),
    ({"€": 1, "\U0001F600": 2, "z": 0}, '{"z":0,"€":1,"\U0001F600":2}'),   # UTF-16 order
    ("é\n\u0001\"\\", '"é\\n\\u0001\\"\\\\"'),
    ([1e21, 1e-7, 0.000001, 100.0, -0.5, 1.5e300], "[1e+21,1e-7,0.000001,100,-0.5,1.5e+300]"),
])
def test_canonical_json_vectors(value, expected):
    assert canonical_dumps(value) == expected


def test_canonical_json_rejects_unrepresentable_values():
    for bad in (float("nan"), 2 ** 60, {1: "x"}, {"a": object()}):
        with pytest.raises(CanonicalJsonError):
            canonical_dumps(bad)
    assert canonical_sha256({"a": 1, "b": 2}) == canonical_sha256({"b": 2, "a": 1})


def test_committed_fixture_bundle_loads():
    b = load_bundle(FIXTURE, repo_root=REPO_ROOT)
    assert (b.module_code, b.semver, b.is_test_fixture) == ("T00_ECHO", "1.0.0", True)
    assert b.output_schema["required"] == ["echo"] and len(b.content_hash) == 64


def _copy(tmp_path, module="T00_ECHO", semver="1.0.0"):
    d = tmp_path / module / semver
    shutil.copytree(FIXTURE, d)
    return d


@pytest.mark.parametrize("mutate,match", [
    (lambda d: (d / "task.md").unlink(), "missing required"),
    (lambda d: (d / "notes").mkdir(), "regular files"),
    (lambda d: (d / "Bad Name.md").write_text("x"), "invalid bundle file name"),
    (lambda d: (d / "output_schema.json").write_text('{"type": 5}'), "not a valid JSON Schema"),
    (lambda d: (d / "system.md").write_text("é"), "NFC"),
    (lambda d: (d / "manifest.json").write_text(json.dumps({"format": "lfhe-prompt-manifest/1", "module_code": "T00_ECHO",
                                                           "semver": "2.0.0", "module_version": "x"})), "must live in"),
])
def test_invalid_bundles_are_rejected(tmp_path, mutate, match):
    d = _copy(tmp_path)
    mutate(d)
    with pytest.raises(PromptBundleError, match=match):
        load_bundle(d, git_path="x")


def test_lock_detects_edit_removal_and_unlocked_bundle(tmp_path):
    root = tmp_path / "prompts"
    d = _copy(root)
    lock = build_lock(root)
    assert check_lock(root, lock) == []
    (d / "system.md").write_text("edited in place", encoding="utf-8")
    assert any("content changed" in p for p in check_lock(root, lock))
    shutil.rmtree(d)
    assert any("removed" in p for p in check_lock(root, lock))
    _copy(root, semver="1.0.0")
    shutil.copytree(REPO_ROOT / "tests/fixtures/prompts/T00_ECHO/1.0.1", root / "T00_ECHO" / "1.0.1")
    assert any("not in lock" in p for p in check_lock(root, lock))


def test_repository_prompt_lock_is_current():
    root = REPO_ROOT / "packages" / "prompts"
    assert check_lock(root, json.loads((root / "prompt-lock.json").read_text())) == []
