"""Reassemble the pilot result JSONs of a pilot-real-provider run from its notice annotations (see
emit_result_annotations.py). Usage: python scripts/fetch_pilot_result.py <run_id> <out_dir>. Needs the gh CLI."""
from __future__ import annotations

import base64
import collections
import gzip
import json
import pathlib
import subprocess
import sys

REPO = "antonronogur-boop/lfhe"


def gh(path: str):
    return json.loads(subprocess.check_output(["gh", "api", "--paginate", path]))


def main(run_id: str, out: str) -> int:
    parts = collections.defaultdict(dict)
    for job in gh(f"repos/{REPO}/actions/runs/{run_id}/jobs")["jobs"]:
        for a in gh(f"repos/{REPO}/check-runs/{job['id']}/annotations"):
            t = a.get("title") or ""
            if t.startswith("p7r|"):
                _, name, i, n = t.split("|")
                parts[name][int(i)] = (int(n), a["message"])
    outdir = pathlib.Path(out)
    outdir.mkdir(parents=True, exist_ok=True)
    for name, chunks in parts.items():
        n = next(iter(chunks.values()))[0]
        assert sorted(chunks) == list(range(n)), f"{name}: incomplete ({sorted(chunks)} of {n})"
        data = gzip.decompress(base64.b64decode("".join(chunks[i][1] for i in range(n))))
        json.loads(data)
        (outdir / name).write_bytes(data)
        print(outdir / name)
    return 0 if parts else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
