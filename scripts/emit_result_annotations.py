"""Phase 7 pilot: publish the (already secret-scanned) result JSONs as GitHub Actions notice annotations, so they can
be read back through the REST API (check-run annotations) without downloading the artifact zip.
Encoding: gzip + base64, split into chunks; title = "p7r|<file>|<i>|<n>". Contents are the same files as the artifact."""
from __future__ import annotations

import base64
import gzip
import pathlib
import sys

CHUNK = 4000          # GitHub truncates annotation messages at 4096 characters
MAX_NOTICES = 10      # GitHub keeps at most 10 notices per step (~40 KB of gzip+base64)


def main(directory: str) -> int:
    chunks = []
    for p in sorted(pathlib.Path(directory).glob("p7-*.json")):
        blob = base64.b64encode(gzip.compress(p.read_bytes(), 9)).decode()
        parts = [blob[i:i + CHUNK] for i in range(0, len(blob), CHUNK)] or [""]
        chunks += [(p.name, i, len(parts), part) for i, part in enumerate(parts)]
    if len(chunks) > MAX_NOTICES:
        print(f"::warning::results too large for annotations ({len(chunks)} chunks); use the artifact")
        return 0
    for name, i, n, part in chunks:
        print(f"::notice title=p7r|{name}|{i}|{n}::{part}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "p7-results"))
