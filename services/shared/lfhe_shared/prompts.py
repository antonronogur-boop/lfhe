"""Prompt artifacts: Git bundle loading, hashing, registration, lock check.

See docs/prompt-versioning.md. A bundle is a directory

    packages/prompts/<MODULE>/<semver>/
        manifest.json        {"format": "lfhe-prompt-manifest/1", "module_code",
                              "semver", "module_version", "test_fixture"?, "description"?}
        system.md
        task.md
        output_schema.json   JSON Schema (draft 2020-12) for the structured output

Bundle hash 'lfhe-prompt-bundle/1' (identical to lfhe.prompt_bundle_sha256):
    sha256( "lfhe-prompt-bundle/1\\n<module>\\n<semver>"
            + "\\n<name> <sha256(file)>" for files sorted by name (bytewise) )
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

BUNDLE_FORMAT = "lfhe-prompt-bundle/1"
MANIFEST_FORMAT = "lfhe-prompt-manifest/1"
LOCK_FORMAT = "lfhe-prompt-lock/1"
REQUIRED_FILES = ("manifest.json", "system.md", "task.md", "output_schema.json")
_FILE_NAME = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
_MODULE = re.compile(r"^[A-Z][A-Z0-9_]{1,39}$")
_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class PromptBundleError(ValueError):
    pass


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def bundle_sha256(module_code: str, semver: str, files: dict[str, str]) -> str:
    parts = [BUNDLE_FORMAT, module_code, semver]
    parts += [f"{name} {_sha(files[name])}" for name in sorted(files, key=lambda n: n.encode("utf-8"))]
    return _sha("\n".join(parts))


@dataclass(frozen=True)
class PromptBundle:
    module_code: str
    semver: str
    module_version: str
    is_test_fixture: bool
    files: dict[str, str] = field(repr=False)
    git_path: str

    @property
    def content_hash(self) -> str:
        return bundle_sha256(self.module_code, self.semver, self.files)

    @property
    def output_schema(self) -> dict:
        return json.loads(self.files["output_schema.json"])


def load_bundle(directory: Path | str, *, git_path: str | None = None,
                repo_root: Path | str | None = None) -> PromptBundle:
    directory = Path(directory)
    if not directory.is_dir():
        raise PromptBundleError(f"{directory} is not a directory")
    files: dict[str, str] = {}
    for entry in sorted(directory.iterdir()):
        if entry.is_symlink() or not entry.is_file():
            raise PromptBundleError(f"{entry.name}: only regular files are allowed in a bundle")
        if not _FILE_NAME.match(entry.name):
            raise PromptBundleError(f"{entry.name}: invalid bundle file name")
        try:
            text = entry.read_bytes().decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PromptBundleError(f"{entry.name}: not UTF-8") from exc
        if unicodedata.normalize("NFC", text) != text:
            raise PromptBundleError(f"{entry.name}: not NFC-normalised")
        files[entry.name] = text
    missing = [f for f in REQUIRED_FILES if f not in files]
    if missing:
        raise PromptBundleError(f"missing required files: {missing}")
    try:
        manifest = json.loads(files["manifest.json"])
        schema = json.loads(files["output_schema.json"])
    except ValueError as exc:
        raise PromptBundleError(f"invalid JSON: {exc}") from exc
    if manifest.get("format") != MANIFEST_FORMAT:
        raise PromptBundleError(f"manifest format must be {MANIFEST_FORMAT}")
    module, semver = manifest.get("module_code"), manifest.get("semver")
    if not (isinstance(module, str) and _MODULE.match(module)):
        raise PromptBundleError("manifest module_code invalid")
    if not (isinstance(semver, str) and _SEMVER.match(semver)):
        raise PromptBundleError("manifest semver invalid")
    if (directory.parent.name, directory.name) != (module, semver):
        raise PromptBundleError(f"bundle must live in <...>/{module}/{semver}/ (found {directory})")
    if not isinstance(manifest.get("module_version"), str) or not manifest["module_version"]:
        raise PromptBundleError("manifest module_version required")
    fixture = manifest.get("test_fixture", False)
    if not isinstance(fixture, bool):
        raise PromptBundleError("manifest test_fixture must be boolean")
    if not isinstance(schema, dict):
        raise PromptBundleError("output_schema.json must be a JSON object")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise PromptBundleError(f"output_schema.json is not a valid JSON Schema: {exc.message}") from exc
    if git_path is None:
        root = Path(repo_root) if repo_root else _repo_root(directory)
        git_path = directory.resolve().relative_to(root.resolve()).as_posix()
    return PromptBundle(module, semver, manifest["module_version"], fixture, files, git_path)


def _repo_root(path: Path) -> Path:
    out = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise PromptBundleError(f"{path} is not inside a Git working tree")
    return Path(out.stdout.strip())


def git_state(directory: Path | str) -> tuple[str | None, bool]:
    """(HEAD commit, bundle directory clean?) — (None, False) outside Git."""
    directory = Path(directory)
    head = subprocess.run(["git", "-C", str(directory), "rev-parse", "HEAD"], capture_output=True, text=True)
    if head.returncode != 0:
        return None, False
    status = subprocess.run(["git", "-C", str(directory), "status", "--porcelain", "--", "."],
                            capture_output=True, text=True)
    return head.stdout.strip(), status.returncode == 0 and status.stdout.strip() == ""


def register(conn, bundle: PromptBundle, *, git_commit: str | None, git_tree_clean: bool) -> str:
    """Register via lfhe.register_prompt_version (connection must be a registrar)."""
    from psycopg.types.json import Jsonb
    payload = {"module_code": bundle.module_code, "semver": bundle.semver,
               "module_version": bundle.module_version, "is_test_fixture": bundle.is_test_fixture,
               "files": bundle.files, "git_path": bundle.git_path, "git_commit": git_commit,
               "git_tree_clean": git_tree_clean, "expected_content_hash": bundle.content_hash}
    row = conn.execute("SELECT lfhe.register_prompt_version(%s::jsonb) AS id", (Jsonb(payload),)).fetchone()
    return str(row["id"] if isinstance(row, dict) else row[0])


def verify_registered(conn, repo_root: Path | str, modules=None) -> list[str]:
    """Compare every registered prompt version (optionally only *modules*) with its Git artifact."""
    problems = []
    rows = conn.execute("SELECT module_code, semver, content_hash, git_path, files FROM lfhe.prompt_versions "
                        "WHERE %s::text[] IS NULL OR module_code = ANY(%s::text[]) ORDER BY module_code, semver",
                        (list(modules) if modules else None,) * 2).fetchall()
    for row in rows:
        label = f"{row['module_code']} {row['semver']}"
        if bundle_sha256(row["module_code"], row["semver"], row["files"]) != row["content_hash"]:
            problems.append(f"{label}: database content does not match its content_hash")
        path = Path(repo_root) / row["git_path"]
        if not path.is_dir():
            problems.append(f"{label}: Git artifact missing at {row['git_path']}")
            continue
        try:
            bundle = load_bundle(path, git_path=row["git_path"])
        except PromptBundleError as exc:
            problems.append(f"{label}: Git artifact invalid: {exc}")
            continue
        if bundle.content_hash != row["content_hash"]:
            problems.append(f"{label}: Git artifact differs from registered content")
    return problems


# -- Lock file: CI guard that released bundles are never edited in place -------
def discover_bundles(root: Path | str) -> dict[str, PromptBundle]:
    root = Path(root)
    found = {}
    for manifest in sorted(root.glob("*/*/manifest.json")):
        bundle = load_bundle(manifest.parent, git_path=manifest.parent.relative_to(root).as_posix())
        found[f"{bundle.module_code}/{bundle.semver}"] = bundle
    return found


def build_lock(root: Path | str) -> dict:
    return {"format": LOCK_FORMAT,
            "bundles": {k: b.content_hash for k, b in sorted(discover_bundles(root).items())}}


def check_lock(root: Path | str, lock: dict) -> list[str]:
    problems = []
    if lock.get("format") != LOCK_FORMAT:
        return [f"lock format must be {LOCK_FORMAT}"]
    locked = lock.get("bundles", {})
    current = {k: b.content_hash for k, b in discover_bundles(root).items()}
    for key, digest in current.items():
        if key not in locked:
            problems.append(f"{key}: bundle not in lock file (run scripts/prompt_registry.py lock)")
        elif locked[key] != digest:
            problems.append(f"{key}: content changed after locking — create a new semver instead")
    for key in locked:
        if key not in current:
            problems.append(f"{key}: locked bundle removed from Git (released artifacts must be preserved)")
    return problems
