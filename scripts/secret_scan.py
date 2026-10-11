#!/usr/bin/env python3
"""Lightweight secret scanner for the LFHÉ repository.

Runs in the test suite and in CI (CI additionally runs gitleaks). It is a
backstop, not a replacement for proper secret management: secrets must never
be written into source, prompts, fixtures or documentation in the first place.

Usage:
    python scripts/secret_scan.py            # scan git-tracked + untracked, non-ignored files
    python scripts/secret_scan.py <dir>      # scan every file under <dir>

Exit code 0 = clean, 1 = findings.
"""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PATTERNS: dict[str, re.Pattern[str]] = {
    "private_key_block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
    "aws_access_key_id": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "supabase_secret_key": re.compile(r"\bsb_secret_[A-Za-z0-9_\-]{20,}"),
    "anthropic_api_key": re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}"),
    "openai_api_key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{32,}"),
    "github_token": re.compile(r"\b(?:ghp|gho|ghs|ghu|github_pat)_[A-Za-z0-9_]{30,}"),
    # A signed JWT (e.g. a Supabase service_role key): three base64url parts.
    "jwt_token": re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{20,}"),
    # postgres URL with an inline password that is not an obvious placeholder
    "db_url_with_password": re.compile(
        r"postgres(?:ql)?://[^:\s/]+:(?!CHANGE_ME|password@|postgres@|\$\{|<)[^@\s]{6,}@"
    ),
}

FORBIDDEN_FILE_NAMES = re.compile(r"(^|/)\.env(\.(?!example$)[^/]+)?$")
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".ico", ".woff", ".woff2", ".lock"}
SKIP_DIRS = {".git", "node_modules", ".next", "__pycache__", ".pytest_cache", ".local"}
# Files allowed to contain pattern *definitions* (this scanner and its test).
SELF_ALLOWLIST = {"scripts/secret_scan.py", "tests/security/test_secret_scan.py"}


@dataclass(frozen=True)
class Finding:
    path: str
    rule: str
    line: int


def _repo_files(root: Path) -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    return [root / p for p in out]


def _all_files(root: Path) -> list[Path]:
    files = []
    for p in root.rglob("*"):
        if p.is_file() and not any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            files.append(p)
    return files


def scan(root: Path, use_git: bool = True) -> list[Finding]:
    root = root.resolve()
    files = _repo_files(root) if use_git else _all_files(root)
    findings: list[Finding] = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        if rel in SELF_ALLOWLIST or not path.is_file():
            continue
        if FORBIDDEN_FILE_NAMES.search(rel):
            findings.append(Finding(rel, "forbidden_env_file", 0))
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for rule, pattern in PATTERNS.items():
                if pattern.search(line):
                    findings.append(Finding(rel, rule, lineno))
    return findings


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        findings = scan(Path(argv[1]), use_git=False)
    else:
        findings = scan(Path(__file__).resolve().parent.parent, use_git=True)
    for f in findings:
        # Never print the matched value itself.
        print(f"SECRET-SCAN: {f.rule} in {f.path}:{f.line}")
    if findings:
        print(f"SECRET-SCAN: {len(findings)} finding(s)")
        return 1
    print("SECRET-SCAN: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
