#!/usr/bin/env python3
"""Prompt artifact operations (see docs/prompt-versioning.md).

    prompt_registry.py lock                      rewrite packages/prompts/prompt-lock.json
    prompt_registry.py check-lock                CI: locked bundles unchanged and present
    prompt_registry.py register <bundle_dir>...  register bundles in the database
    prompt_registry.py verify                    compare every registered version with Git

register/verify read the connection string from LFHE_REGISTRAR_DATABASE_URL
(a login role that is a member of lfhe_registrar; never put it on the command
line). Registration does NOT activate: activation is a human action
(lfhe.activate_prompt_version, permission PROMPT_ACTIVATE).
"""
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "services" / "shared"))

from lfhe_shared.prompts import (PromptBundleError, build_lock, check_lock, git_state,  # noqa: E402
                                 load_bundle, register, verify_registered)

PROMPTS = REPO / "packages" / "prompts"
LOCK = PROMPTS / "prompt-lock.json"


def _connect():
    import psycopg
    from psycopg.rows import dict_row
    url = os.environ.get("LFHE_REGISTRAR_DATABASE_URL")
    if not url:
        raise SystemExit("LFHE_REGISTRAR_DATABASE_URL is not set")
    return psycopg.connect(url, autocommit=True, row_factory=dict_row)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "lock":
        LOCK.write_text(json.dumps(build_lock(PROMPTS), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {LOCK.relative_to(REPO)}")
        return 0
    if cmd == "check-lock":
        problems = check_lock(PROMPTS, json.loads(LOCK.read_text(encoding="utf-8")))
        for p in problems:
            print("PROMPT-LOCK:", p)
        print("PROMPT-LOCK: ok" if not problems else f"PROMPT-LOCK: {len(problems)} problem(s)")
        return 1 if problems else 0
    if cmd == "register" and len(argv) > 2:
        with _connect() as conn:
            for d in argv[2:]:
                try:
                    bundle = load_bundle(Path(d), repo_root=REPO)
                except PromptBundleError as exc:
                    print(f"{d}: {exc}")
                    return 1
                commit, clean = git_state(Path(d))
                pid = register(conn, bundle, git_commit=commit, git_tree_clean=clean)
                print(f"{bundle.module_code} {bundle.semver} {bundle.content_hash} → {pid}"
                      f"{'' if clean else '  (WARNING: uncommitted changes — not activatable in PROD)'}")
        return 0
    if cmd == "verify":
        with _connect() as conn:
            problems = verify_registered(conn, REPO)
        for p in problems:
            print("PROMPT-VERIFY:", p)
        print("PROMPT-VERIFY: ok" if not problems else f"PROMPT-VERIFY: {len(problems)} problem(s)")
        return 1 if problems else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
