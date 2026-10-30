"""CR7-06: the read-only scripts/verify_release.py passes on a genuine release and detects a damaged PDF file."""
import importlib.util
from pathlib import Path

import pytest
from p6_helpers import make_pdf, release, store, through_security
from test_p6_release import p6, people  # noqa: F401  (module fixtures)

pytestmark = pytest.mark.db
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_release.py"


def _load():
    spec = importlib.util.spec_from_file_location("verify_release", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_verify_release_script(pg, p6, people, tmp_path, monkeypatch, capsys):  # noqa: F811
    a, rev, sec, ra = people["ANALYST"], people["REVIEWER"], people["SECURITY_REVIEWER"], people["RELEASE_AUTHORITY"]
    objstore = store(tmp_path)
    d, q, c, s = through_security(pg, a, rev, sec, "RPT-CR706-1")
    pdf = make_pdf(pg, d.rv, objstore)
    release(pg, ra, d.rv, pdf["pdf_artifact_id"])
    monkeypatch.setenv("LFHE_DEV_DB_URL", pg.admin_url)
    mod = _load()
    root = tmp_path / "objects"
    assert mod.main(["verify_release.py", "RPT-CR706-1", str(root)]) == 0
    assert "ALL CHECKS PASSED" in capsys.readouterr().out
    f = root / pdf["storage_key"]
    f.chmod(0o644)
    f.write_bytes(f.read_bytes() + b"x")
    assert mod.main(["verify_release.py", "RPT-CR706-1", str(root)]) == 1
    assert "FAILED" in capsys.readouterr().out
