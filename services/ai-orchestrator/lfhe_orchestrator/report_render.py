"""Deterministic report preview rendering (Phase 5 Addendum §20; CG0 C.9; K-09).

The HTML is a pure function of (report_version_id, report_version_hash, canonical_json,
template, renderer). No clock, locale, randomness or database state enters the bytes. The
preview is never QA-approved, security-approved or released; the authoritative report is the
canonical JSON of the bound version.
"""
from __future__ import annotations

import hashlib
from html import escape
from pathlib import Path

TEMPLATE_VERSION = "LFHE-EXECUTIVE-REPORT/1.0.0"
RENDERER_VERSION = "lfhe-report-renderer/1.0.0"
_TEMPLATE_DIR = Path(__file__).resolve().parents[3] / "packages" / "report-templates" / "LFHE-EXECUTIVE-REPORT" / "1.0.0"
SECTION_TITLES = {
    "KEY_JUDGMENT": "Key Judgments", "SIGNIFICANT_DEVELOPMENT": "Significant Developments",
    "INDICATOR_WARNING": "Indicators &amp; Warning", "TREND_WATCH": "Trend Watch", "WHAT_TO_WATCH": "What to Watch",
    "CAVEAT": "Caveats",
}


def template_css() -> str:
    return (_TEMPLATE_DIR / "template.css").read_text(encoding="utf-8")


def template_sha256() -> str:
    return hashlib.sha256(template_css().encode("utf-8")).hexdigest()


def _target(cov: dict) -> str:
    lo, hi = cov.get("target_min"), cov.get("target_max")
    if lo is None and hi is None:
        return ""
    rng = f"{lo}–{hi}" if lo is not None and lo != hi else f"{hi}" if lo is None else f"{lo}"
    note = " · below target" if cov.get("below_target") else " · above target — length review" if cov.get("above_target") else ""
    return f' <span class="target">({cov["count"]} of {rng}{escape(note)})</span>'


def render_report_html(canonical: dict, report_version_id: str, report_version_hash: str) -> str:
    rep = canonical["report"]
    cov = {c["section"]: c for c in canonical.get("coverage") or []}
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
             f'<title>{escape(rep["code"])} v{canonical["version_no"]} — DRAFT PREVIEW</title>',
             f'<style>{template_css()}</style></head><body>',
             '<div class="banner">Draft preview — not QA-approved, not security-reviewed, not released</div>',
             f'<header class="report"><h1>{escape(rep["title"])}</h1><div class="meta">{escape(rep["code"])} · '
             f'{escape(rep["cycle_label"])} · {escape(rep["report_mode"])} · information cutoff {escape(rep["information_cutoff"])}'
             f' · version {canonical["version_no"]} · length {escape(canonical["length_status"])}</div></header>']
    prov = []
    for sec in canonical["sections"]:
        name = sec["section"]
        parts.append(f'<section class="sec-{name}" data-section="{name}"><h2>{SECTION_TITLES[name]}{_target(cov.get(name, {}))}</h2>')
        if not sec["items"]:
            parts.append('<p class="gap">No approved material was selected for this section.</p>')
        for item in sec["items"]:
            conf = item.get("final_analytic_confidence") or "NONE"
            parts.append(f'<article class="item conf-{conf}" data-item="{escape(item["item_local_id"])}">')
            if item.get("final_analytic_confidence"):
                parts.append(f'<div class="conf">{conf.lower()} confidence (analyst-approved)</div>')
            for st in item["statements"]:
                ref = f'{item["item_local_id"]}/{st["report_statement_local_id"]}'
                lk = f' <span class="lk">[likelihood: {escape(st["likelihood_term"].replace("_", " ").lower())}]</span>' \
                    if st.get("likelihood_term") else ""
                cont = ' <span class="contested">contested</span>' if st.get("contested") else ""
                parts.append(f'<p class="st role-{st["statement_role"]}" data-statement="{escape(ref)}">{escape(st["text"])}'
                             f'{lk}{cont}<sup class="src">{len(prov) + 1}</sup></p>')
                prov.append((ref, st["statement_role"], st["editorial_transform"], st["sources"]))
            parts.append('</article>')
        parts.append('</section>')
    parts.append('<section class="provenance"><h2>Statement provenance (approved assessment statements)</h2><table>'
                 '<tr><th>#</th><th>report statement</th><th>role</th><th>transform</th><th>source assessment statement ids</th></tr>')
    for n, (ref, role, tr, srcs) in enumerate(prov, 1):
        parts.append(f'<tr><td>{n}</td><td>{escape(ref)}</td><td>{role}</td><td>{tr}</td><td>{escape(" ".join(srcs))}</td></tr>')
    removed = canonical.get("human_removals") or []
    parts.append('</table>' + (f'<p>Removed by human decision: {escape(" ".join(removed))}</p>' if removed else '') + '</section>')
    parts.append(f'<footer class="version">report_version_id {escape(report_version_id)} · report_version_hash '
                 f'{escape(report_version_hash)} · selection_set {escape(canonical["selection_set"]["hash"])} · template '
                 f'{TEMPLATE_VERSION} ({template_sha256()[:16]}) · renderer {RENDERER_VERSION}</footer></body></html>')
    return "".join(parts)


def render_and_record(conn, report_version_id: str, report_version_hash: str, *, worker_id: str) -> dict:
    v = conn.execute("SELECT canonical_json, report_version_hash FROM lfhe.report_versions WHERE id = %s",
                     (str(report_version_id),)).fetchone()
    if v is None or v["report_version_hash"] != report_version_hash:
        raise ValueError("VERSION_HASH_MISMATCH")
    html = render_report_html(v["canonical_json"], str(report_version_id), report_version_hash)
    from psycopg.types.json import Jsonb
    return conn.execute("SELECT lfhe.record_report_render(%s::jsonb) r", (Jsonb({
        "report_version_id": str(report_version_id), "report_version_hash": report_version_hash,
        "template_version": TEMPLATE_VERSION, "template_sha256": template_sha256(), "renderer_version": RENDERER_VERSION,
        "content": html, "worker_id": worker_id}),)).fetchone()["r"]
