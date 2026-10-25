"""The pilot result hand-over via annotations round-trips within GitHub's limits (4096 chars / message, 10 notices)."""
import base64
import gzip
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_roundtrip(tmp_path):
    src = ROOT / "docs" / "cg7-real-provider-run7-bm02-superseded-base.json"
    (tmp_path / "p7-bm-02-real-provider.json").write_bytes(src.read_bytes())
    out = subprocess.check_output([sys.executable, str(ROOT / "scripts" / "emit_result_annotations.py"), str(tmp_path)], text=True)
    lines = out.splitlines()
    assert 1 <= len(lines) <= 10
    parts = {}
    for ln in lines:
        m = re.fullmatch(r"::notice title=p7r\|([^|]+)\|(\d+)\|(\d+)::(.*)", ln)
        assert m and len(m.group(4)) <= 4096
        parts[int(m.group(2))] = m.group(4)
    data = gzip.decompress(base64.b64decode("".join(parts[i] for i in sorted(parts))))
    assert json.loads(data) == json.loads(src.read_bytes())
