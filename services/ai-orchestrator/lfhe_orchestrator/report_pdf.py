"""Phase 6 release PDF artifact (Addendum §19, DC6-04; CG0 C.9).

canonical report JSON → deterministic HTML (report_render, variant RELEASE) → approved template →
headless Chromium print-to-PDF → write-once content-addressed object storage (prefix release-pdf) →
lfhe.record_release_pdf (bytes + SHA-256 + version / hash / template / renderer binding).

* The authoritative released PDF is the exact stored bytes and their SHA-256. Byte-for-byte
  reproducibility of Chromium output is NOT claimed (DC6-04): every distinct byte artifact gets its own
  identity, and only the artifact selected by the release transaction becomes the released one.
* The HTML is self-contained (inline CSS, no scripts, no remote resources); Chromium runs offline in a
  throw-away profile with networking-related features disabled. No credential, path or user data enters
  the PDF (Chromium writes title / producer metadata only).
* renderer identity = {renderer_version, html renderer version + source SHA-256, this module's source
  SHA-256, Chromium version, template version}; renderer_hash = SHA-256(JCS(identity)), recomputed by
  the database.
"""
from __future__ import annotations

import base64
import glob
import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from psycopg.types.json import Jsonb

from lfhe_shared.canonical_json import canonical_sha256
from lfhe_shared.storage import ObjectStore

from . import report_render
from .report_render import RENDERER_VERSION, TEMPLATE_VERSION, render_report_html, template_sha256

PDF_RENDERER_VERSION = "lfhe-release-pdf-renderer/1.0.0"
STORAGE_PREFIX = "release-pdf"
_CANDIDATES = ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable")


class PdfRenderError(RuntimeError):
    pass


def chromium_path() -> str:
    explicit = os.environ.get("LFHE_CHROMIUM_PATH")
    if explicit:
        return explicit
    for name in _CANDIDATES:
        found = shutil.which(name)
        if found:
            return found
    for pattern in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome", "/opt/pw-browsers/chromium/chrome-linux/chrome"):
        hits = sorted(glob.glob(pattern))
        if hits:
            return hits[-1]
    raise PdfRenderError("headless Chromium not found (set LFHE_CHROMIUM_PATH)")


def chromium_version(path: str) -> str:
    out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise PdfRenderError("cannot determine Chromium version")
    return out.stdout.strip()


def _source_sha(module) -> str:
    return hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()


def renderer_identity(path: str | None = None) -> dict:
    import sys
    return {"renderer_version": PDF_RENDERER_VERSION, "html_renderer_version": RENDERER_VERSION,
            "html_renderer_source_sha256": _source_sha(report_render),
            "pdf_renderer_source_sha256": _source_sha(sys.modules[__name__]),
            "chromium_version": chromium_version(path or chromium_path()), "template_version": TEMPLATE_VERSION,
            "template_sha256": template_sha256()}


def html_to_pdf(html: str, *, path: str | None = None, timeout: int = 120) -> bytes:
    exe = path or chromium_path()
    with tempfile.TemporaryDirectory(prefix="lfhe-pdf-") as tmp:
        src, out = Path(tmp) / "report.html", Path(tmp) / "report.pdf"
        src.write_text(html, encoding="utf-8")
        args = [exe, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                "--disable-extensions", "--disable-background-networking", "--disable-sync", "--disable-component-update",
                "--disable-features=Translate,MediaRouter,OptimizationHints", "--mute-audio",
                f"--user-data-dir={Path(tmp) / 'profile'}", "--no-pdf-header-footer", f"--print-to-pdf={out}",
                src.as_uri()]
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            args.insert(1, "--no-sandbox")          # root containers only; the HTML is our own escaped output
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        if not out.exists() or out.stat().st_size == 0:
            raise PdfRenderError(f"Chromium produced no PDF (exit {proc.returncode})")
        data = out.read_bytes()
    if not data.startswith(b"%PDF-"):
        raise PdfRenderError("Chromium output is not a PDF")
    return data


def render_release_pdf(conn, report_version_id: str, report_version_hash: str, *, store: ObjectStore, worker_id: str,
                       chromium: str | None = None) -> dict:
    v = conn.execute("SELECT canonical_json, report_version_hash FROM lfhe.report_versions WHERE id = %s",
                     (str(report_version_id),)).fetchone()
    if v is None or v["report_version_hash"] != report_version_hash:
        raise ValueError("VERSION_HASH_MISMATCH")
    preview = conn.execute(
        """SELECT id, content, template_sha256 FROM lfhe.report_renders WHERE report_version_id = %s AND report_version_hash = %s
           AND template_version = %s AND renderer_version = %s""",
        (str(report_version_id), report_version_hash, TEMPLATE_VERSION, RENDERER_VERSION)).fetchone()
    if preview is None:
        report_render.render_and_record(conn, str(report_version_id), report_version_hash, worker_id=worker_id)
        preview = conn.execute(
            """SELECT id, content, template_sha256 FROM lfhe.report_renders WHERE report_version_id = %s
               AND template_version = %s AND renderer_version = %s""",
            (str(report_version_id), TEMPLATE_VERSION, RENDERER_VERSION)).fetchone()
    # the release HTML is the same deterministic rendering of the same canonical JSON
    if render_report_html(v["canonical_json"], str(report_version_id), report_version_hash) != preview["content"]:
        raise ValueError("PREVIEW_RENDER_MISMATCH")
    html = render_report_html(v["canonical_json"], str(report_version_id), report_version_hash, variant="RELEASE")
    exe = chromium or chromium_path()
    identity = renderer_identity(exe)
    pdf = html_to_pdf(html, path=exe)
    key = store.put_if_absent(pdf, prefix=STORAGE_PREFIX)
    if store.get(key) != pdf:
        raise ValueError("STORED_PDF_MISMATCH")
    out = conn.execute("SELECT lfhe.record_release_pdf(%s::jsonb) AS r", (Jsonb({
        "report_version_id": str(report_version_id), "report_version_hash": report_version_hash,
        "preview_render_id": str(preview["id"]), "source_html": html, "template_version": TEMPLATE_VERSION,
        "template_hash": preview["template_sha256"], "renderer_version": PDF_RENDERER_VERSION,
        "renderer_identity": identity, "storage_key": key, "pdf_base64": base64.b64encode(pdf).decode("ascii"),
        "worker_id": worker_id}),)).fetchone()["r"]
    return {**out, "storage_key": key, "renderer_hash": canonical_sha256(identity), "byte_size": len(pdf)}
