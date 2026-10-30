#!/usr/bin/env python3
"""Read-only verification of a RELEASED report (PO helper; changes nothing).

Usage:  python scripts/verify_release.py <report-code> <storage-root>
The postgres URL is taken from the hidden prompt (LFHE_DEV_DB_URL is also honoured).
Checks: PDF bytes in DB hash to the recorded SHA-256; the stored PDF file on disk has the same
SHA-256; manifest_hash = jcs_sha256(manifest_json); release row matches; audit chain; pilot_cycles = 0.
"""
import getpass
import hashlib
import os
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "services" / "shared"))
import psycopg  # noqa: E402

from lfhe_shared.audit import verify_chain  # noqa: E402

REF, HOST = "ylkubhuxvcsshfkbvski", "aws-0-eu-north-1.pooler.supabase.com"


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    code, root = argv[1], Path(argv[2])
    url = os.environ.get("LFHE_DEV_DB_URL") or \
        f"postgresql://postgres.{REF}:{quote(getpass.getpass('Supabase postgres password (hidden): '), safe='')}@{HOST}:5432/postgres"
    bad = []

    def check(name, ok, detail=""):
        print(("  OK    " if ok else "  FAIL  ") + name + (f"  [{detail}]" if detail else ""))
        if not ok:
            bad.append(name)

    with psycopg.connect(url) as c:
        r = c.execute(
            """SELECT rel.state, rel.report_version_id, rel.manifest_hash, rel.pdf_sha256, m.manifest_json,
                      lfhe.jcs_sha256(m.manifest_json) AS recomputed, a.storage_key, a.byte_size,
                      encode(sha256(a.pdf_bytes), 'hex') AS db_pdf_sha, rel.released_at
                 FROM lfhe.reports rep
                 JOIN lfhe.report_releases rel ON rel.report_id = rep.id
                 JOIN lfhe.release_manifests m ON m.id = rel.release_manifest_id
                 JOIN lfhe.release_pdf_artifacts a ON a.id = rel.pdf_artifact_id
                WHERE rep.code = %s""", (code,)).fetchone()
        if r is None:
            print("No RELEASED row for", code)
            return 1
        r = dict(zip(["state", "rvid", "mhash", "pdf", "mjson", "recomputed", "key", "size", "dbsha", "at"], r))
        print(f"Report {code}: {r['state']} at {r['at']}\n  manifest_hash {r['mhash']}\n  pdf_sha256    {r['pdf']}")
        check("manifest_hash = jcs_sha256(manifest_json)", r["mhash"] == r["recomputed"])
        check("PDF bytes stored in DB hash to the recorded SHA-256", r["dbsha"] == r["pdf"])
        f = root / r["key"]
        if f.exists():
            data = f.read_bytes()
            check("PDF file on disk hashes to the recorded SHA-256", hashlib.sha256(data).hexdigest() == r["pdf"],
                  f"{len(data)} bytes, {f}")
            check("PDF file size matches", len(data) == r["size"])
        else:
            check("PDF file on disk", False, f"missing: {f}")
        n = c.execute("SELECT count(*) FROM lfhe.pilot_cycles").fetchone()[0]
        check("pilot_cycles = 0", n == 0, f"count={n}")
        res = verify_chain(c)
        check("audit chain verifies", res.ok, str(res))
    print("\nRESULT:", "ALL CHECKS PASSED" if not bad else "FAILED: " + ", ".join(bad))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
