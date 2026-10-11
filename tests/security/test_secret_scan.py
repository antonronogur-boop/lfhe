"""F8 — no application secret is committed to source control."""
from pathlib import Path

import secret_scan

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_repository_is_clean():
    findings = secret_scan.scan(REPO_ROOT, use_git=True)
    assert findings == [], f"secret-like content found: {findings}"


def test_scanner_detects_planted_dummy_secrets(tmp_path):
    # Dummy values constructed at runtime so this file itself holds no secret.
    fake_jwt = "eyJ" + "a" * 20 + ".eyJ" + "b" * 20 + "." + "c" * 30
    fake_aws = "AKIA" + "Z" * 16
    (tmp_path / "config.py").write_text(f"KEY = '{fake_jwt}'\nAWS = '{fake_aws}'\n")
    (tmp_path / ".env").write_text("LFHE_ENV=DEV\n")
    rules = {f.rule for f in secret_scan.scan(tmp_path, use_git=False)}
    assert {"jwt_token", "aws_access_key_id", "forbidden_env_file"} <= rules


def test_env_example_is_allowed_and_placeholder_db_url_passes(tmp_path):
    (tmp_path / ".env.example").write_text(
        "LFHE_DATABASE_URL=postgresql://user:CHANGE_ME@localhost:5432/db\n"
    )
    assert secret_scan.scan(tmp_path, use_git=False) == []


def test_env_files_are_gitignored():
    gitignore = (REPO_ROOT / ".gitignore").read_text()
    assert ".env" in gitignore and "!.env.example" in gitignore
