#!/usr/bin/env python3
"""K-05 real-source collection validation (run by the Product Owner, DEV only).

The cloud development environment cannot reach the source domains, so this
script runs on the PO's machine against the DEV Supabase project, with the
REAL Phase 1 collector, job queue, robots handling and snapshot rules.

Rules implemented (PO K-05 instruction):
* Feed / sitemap URLs are never guessed or constructed. Each source has a
  PO-confirmed official DISCOVERY PAGE; the endpoint is read from that page
  (<link rel="alternate">, feed links, robots.txt "Sitemap:" lines, sitemap
  index entries) and verified by fetching it. Zero or several matching
  endpoints → SOURCE_CONFIGURATION_UNRESOLVED (no workaround, no substitute).
* robots.txt is respected (blocked → BLOCKED_BY_ROBOTS); access control is
  never bypassed (401/403 → ACCESS_DENIED).
* All sources use retention PERMITTED_EXCERPT; at most `max_items` items each.
* Two passes per source, each as a COLLECT_SOURCE job processed by the real
  job handler (F3); then provenance completeness (F4) and duplicate control
  on the second pass (F5) are evaluated from the database.
* At the end every K-05 source is DEACTIVATED (re-activation is a separate,
  audited human decision).

Usage (PowerShell, from the repo root, venv active):
    copy scripts\\k05_sources.template.json k05_sources.json   # then edit + confirm
    $env:LFHE_K05_DB_URL = "<DEV session pooler URI>"           # never paste it in chat
    $env:LFHE_SMOKE_SUPABASE_URL / LFHE_SMOKE_ANON_KEY / LFHE_SMOKE_ADMIN_EMAIL / LFHE_SMOKE_ADMIN_PASSWORD
    $env:LFHE_K05_USER_AGENT = "LFHE-OSINT-Collector/0.1 (+contact: <your contact>)"
    python scripts\\k05_validate_sources.py k05_sources.json

Outputs k05-report.json and k05-report.md in the current directory (they contain
no credentials) and prints the JSON. Exit code 0 only if every source PASSes.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

REPO = Path(__file__).resolve().parent.parent
for sub in ("services/shared", "services/collector"):
    sys.path.insert(0, str(REPO / sub))

FEED_TYPES = ("application/rss+xml", "application/atom+xml", "application/feed+json", "application/xml", "text/xml")


# ---------------------------------------------------------------------------
# Discovery (no guessing: every candidate comes from the official page itself)
# ---------------------------------------------------------------------------
class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[dict] = []
        self._a: dict | None = None

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "link" and "alternate" in a.get("rel", "").lower() and a.get("href"):
            self.links.append({"href": a["href"], "type": a.get("type", "").lower(), "text": a.get("title", ""),
                               "kind": "link-alternate"})
        elif tag == "a" and a.get("href"):
            self._a = {"href": a["href"], "type": a.get("type", "").lower(), "text": a.get("title", ""), "kind": "anchor"}

    def handle_data(self, data):
        if self._a is not None:
            self._a["text"] += " " + data.strip()

    def handle_endtag(self, tag):
        if tag == "a" and self._a is not None:
            self.links.append(self._a)
            self._a = None


def _same_site(url: str, domain: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return host == domain or host.endswith("." + domain)


def _matches(hint: str | None, *texts: str) -> bool:
    return not hint or any(hint.lower() in (t or "").lower() for t in texts)


def _is_feed(fetched) -> bool:
    import feedparser
    parsed = feedparser.parse(fetched.content, response_headers={"content-type": fetched.content_type})
    return bool(parsed.get("version")) and len(parsed.entries) > 0


def resolve_feed(http, page: str, domain: str, hint: str | None) -> tuple[str | None, dict]:
    first = http.get(page)
    if _is_feed(first):
        return first.final_url, {"method": "DISCOVERY_PAGE_IS_FEED", "candidates": [first.final_url]}
    parser = _LinkParser()
    parser.feed(first.content.decode(first.charset or "utf-8", errors="replace"))
    candidates = []
    for link in parser.links:
        href = urljoin(first.final_url, link["href"])
        looks_like_feed = (link["type"] in FEED_TYPES or any(k in href.lower() for k in ("rss", "atom", "feed"))
                           or href.lower().endswith(".xml"))
        if looks_like_feed and _same_site(href, domain) and _matches(hint, link["text"], href):
            candidates.append(href)
    candidates = list(dict.fromkeys(candidates))[:15]
    verified = []
    for c in candidates:
        try:
            if _is_feed(http.get(c)):
                verified.append(c)
        except Exception:  # noqa: BLE001 — an unverifiable candidate is simply not a candidate
            continue
    detail = {"method": "LINKED_FROM_DISCOVERY_PAGE", "candidates": candidates, "verified": verified}
    return (verified[0] if len(verified) == 1 else None), detail


def resolve_sitemap(http, page: str, domain: str, hint: str | None) -> tuple[str | None, dict]:
    import defusedxml.ElementTree as SafeET
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    first = http.get(page)
    if urlsplit(page).path.endswith("robots.txt"):
        listed = [line.split(":", 1)[1].strip() for line in first.content.decode("utf-8", "replace").splitlines()
                  if line.lower().startswith("sitemap:")]
    else:
        listed = [first.final_url]
    listed = [u for u in listed if _same_site(u, domain)]
    urlsets, examined = [], []
    queue = list(listed)
    while queue and len(examined) < 25:
        u = queue.pop(0)
        examined.append(u)
        try:
            root = SafeET.fromstring(http.get(u).content)
        except Exception:  # noqa: BLE001
            continue
        tag = root.tag.split("}")[-1]
        if tag == "sitemapindex":
            children = [e.findtext("sm:loc", default="", namespaces=ns).strip() for e in root.findall("sm:sitemap", ns)]
            queue.extend(c for c in children if c and _same_site(c, domain) and _matches(hint, c))
        elif tag == "urlset" and root.findall("sm:url", ns) and _matches(hint, u):
            urlsets.append(u)
    detail = {"method": "ROBOTS_OR_SITEMAP_INDEX", "listed": listed, "examined": examined, "urlsets": urlsets}
    return (urlsets[0] if len(urlsets) == 1 else None), detail


# ---------------------------------------------------------------------------
# Supabase REST (human ADMIN session; HUMAN_ONLY functions)
# ---------------------------------------------------------------------------
class Rest:
    def __init__(self, base: str, anon: str):
        import httpx
        self.base, self.anon = base.rstrip("/"), anon
        self.http = httpx.Client(timeout=30)

    def sign_in(self, email: str, password: str) -> str:
        r = self.http.post(f"{self.base}/auth/v1/token?grant_type=password", headers={"apikey": self.anon},
                           json={"email": email, "password": password})
        r.raise_for_status()
        return r.json()["access_token"]

    def rpc(self, fn: str, args: dict, token: str):
        r = self.http.post(f"{self.base}/rest/v1/rpc/{fn}", json=args, headers={
            "apikey": self.anon, "Authorization": f"Bearer {token}", "Accept-Profile": "lfhe", "Content-Profile": "lfhe"})
        if r.status_code >= 400:
            raise RuntimeError(f"{fn}: HTTP {r.status_code} {r.text[:300]}")
        return r.json() if r.text else None


# ---------------------------------------------------------------------------
def evaluate(db, source_id: str, runs: list[dict], expected_language: str | None) -> dict:
    snaps = db.execute(
        """SELECT s.*, t.id AS rep_id, t.language AS rep_language, t.is_original_language, t.representation_type
           FROM lfhe.article_snapshots s JOIN lfhe.articles a ON a.id = s.article_id
           LEFT JOIN lfhe.text_representations t ON t.snapshot_id = s.id
           WHERE a.source_id = %s""", (source_id,)).fetchall()
    required = ("requested_url", "final_url", "http_status", "content_type", "raw_content_sha256",
                "system_retrieval_datetime", "source_state_sha256", "public_availability_basis",
                "retention_mode_applied", "content_identity_sha256")
    f4_problems = []
    for s in snaps:
        missing = [k for k in required if s[k] is None]
        if missing:
            f4_problems.append(f"{s['id']}: missing {missing}")
        if s["retention_mode_applied"] != "PERMITTED_EXCERPT":
            f4_problems.append(f"{s['id']}: retention {s['retention_mode_applied']}")
        if s["rep_id"] is None:
            f4_problems.append(f"{s['id']}: no original-language text excerpt")
        elif not s["is_original_language"]:
            f4_problems.append(f"{s['id']}: text not original language")
        if s.get("final_url_in_source_domain") is False:
            f4_problems.append(f"{s['id']}: final URL outside the source domain")
    dup = db.execute(
        """SELECT count(*) AS n FROM (SELECT s.article_id, s.source_state_sha256 FROM lfhe.article_snapshots s
           JOIN lfhe.articles a ON a.id = s.article_id WHERE a.source_id = %s
           GROUP BY 1, 2 HAVING count(*) > 1) d""", (source_id,)).fetchone()["n"]
    languages = sorted({s["rep_language"] or "unknown" for s in snaps})
    p1, p2 = (runs + [None, None])[:2]
    f3 = bool(p1 and p1["status"] in ("SUCCESS", "PARTIAL") and p1["counts"].get("new", 0) >= 1 and p1["job_id"])
    # F5: a re-run creates no uncontrolled duplicate — no second snapshot with an identical
    # source state for any article, and already-known items come back as DUPLICATE (unchanged)
    # or REVISED (a controlled new version). Genuinely new items published between the passes
    # are reported in f5_note, not hidden.
    f5 = bool(p2 and p2["status"] in ("SUCCESS", "PARTIAL") and dup == 0
              and p2["counts"].get("duplicate", 0) + p2["counts"].get("revised", 0) >= 1)
    return {
        "F3_job_collection": "PASS" if f3 else "FAIL",
        "F4_provenance_complete": "PASS" if snaps and not f4_problems else "FAIL",
        "F5_second_pass_no_uncontrolled_duplicates": "PASS" if f5 else "FAIL",
        "language_as_expected": (expected_language is None or languages == [expected_language]),
        "snapshots": len(snaps), "text_languages": languages, "duplicate_state_groups": dup,
        "f4_problems": f4_problems[:20],
        "f5_note": None if not p2 else (
            f"pass 2: new={p2['counts'].get('new', 0)} revised={p2['counts'].get('revised', 0)} "
            f"duplicate={p2['counts'].get('duplicate', 0)} (new items published between passes are reported, "
            "not hidden)"),
    }


def run_pass(db, queue, handler, source_id: str, label: str) -> dict:
    job = queue.enqueue("COLLECT_SOURCE", "source", source_id, f"k05:{source_id}:{label}", max_attempts=1)
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        status = db.execute("SELECT status FROM lfhe.processing_jobs WHERE id=%s", (job,)).fetchone()["status"]
        if status not in ("PENDING", "RUNNING"):
            break
        queue.run_once({"COLLECT_SOURCE": handler}, limit=1)
    run = db.execute("SELECT id, status, error_code, error_message, job_id, items_discovered AS discovered, "
                     "items_new AS new, items_revised AS revised, items_duplicate AS duplicate, "
                     "items_skipped AS skipped, items_failed AS failed FROM lfhe.collection_runs "
                     "WHERE job_id=%s ORDER BY started_at DESC LIMIT 1", (job,)).fetchone()
    j = db.execute("SELECT status, last_error FROM lfhe.processing_jobs WHERE id=%s", (job,)).fetchone()
    return {"label": label, "job_id": job, "job_status": j["status"], "job_error": (j["last_error"] or "")[:300],
            **({"run_id": str(run["id"]), "status": run["status"],
                "counts": {k: run[k] for k in ("discovered", "new", "revised", "duplicate", "skipped", "failed")},
                "error_code": run["error_code"], "job_id_run": str(run["job_id"])} if run else
               {"status": "NO_RUN", "counts": {}})}


def main(argv: list[str]) -> int:
    import psycopg
    from psycopg.rows import dict_row

    from lfhe_collector.collector import make_collect_handler
    from lfhe_collector.http import AccessDenied, PoliteHttpClient, RobotsDisallowed
    from lfhe_collector.snapshots import DatabaseSnapshotSink
    from lfhe_shared.jobs import JobQueue
    from lfhe_shared.storage import LocalObjectStore

    if len(argv) != 2:
        print(__doc__)
        return 2
    config = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    env = {k: os.environ.get(k) for k in ("LFHE_K05_DB_URL", "LFHE_SMOKE_SUPABASE_URL", "LFHE_SMOKE_ANON_KEY",
                                          "LFHE_SMOKE_ADMIN_EMAIL", "LFHE_SMOKE_ADMIN_PASSWORD", "LFHE_K05_USER_AGENT")}
    missing = [k for k, v in env.items() if not v]
    if missing:
        raise SystemExit(f"missing environment variable(s): {missing}")
    if "set-me" in env["LFHE_K05_USER_AGENT"] or "contact" not in env["LFHE_K05_USER_AGENT"]:
        raise SystemExit("LFHE_K05_USER_AGENT must identify the collector and a real contact")

    db = psycopg.connect(env["LFHE_K05_DB_URL"], autocommit=True, row_factory=dict_row)
    if db.execute("SELECT environment FROM lfhe.deployment_environment").fetchone()["environment"] != "DEV":
        raise SystemExit("refusing to run: database is not DEV")
    rest = Rest(env["LFHE_SMOKE_SUPABASE_URL"], env["LFHE_SMOKE_ANON_KEY"])
    admin = rest.sign_in(env["LFHE_SMOKE_ADMIN_EMAIL"], env["LFHE_SMOKE_ADMIN_PASSWORD"])
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    store = LocalObjectStore(Path(config.get("object_store", ".local/k05-objects")))
    report = {"k05_run": stamp, "environment": "DEV", "git_commit": os.popen("git rev-parse HEAD").read().strip(),
              "sources": []}

    with PoliteHttpClient(env["LFHE_K05_USER_AGENT"], timeout=30, max_bytes=5 * 1024 * 1024,
                          min_interval=float(config.get("min_interval_seconds", 5)), respect_robots=True) as http:
        queue = JobQueue(db, "k05-validator")
        handler = make_collect_handler(db, http, DatabaseSnapshotSink(db, store), "k05-validator")
        for s in config["sources"]:
            entry = {"id": s["id"], "name": s["name"], "domain": s["domain"], "method": s["method"],
                     "discovery_page": s.get("discovery_page"), "expected_language": s.get("expected_language")}
            report["sources"].append(entry)
            if not s.get("po_confirmed") or not s.get("discovery_page"):
                entry.update(status="SOURCE_CONFIGURATION_UNRESOLVED",
                             reason="discovery page not confirmed by the Product Owner")
                continue
            try:
                if s["method"] == "RSS_ATOM":
                    endpoint, detail = resolve_feed(http, s["discovery_page"], s["domain"], s.get("hint"))
                    cfg_key = "feed_url"
                elif s["method"] == "STRUCTURED_FEED":
                    endpoint, detail = resolve_sitemap(http, s["discovery_page"], s["domain"], s.get("hint"))
                    cfg_key = "sitemap_url"
                elif s["method"] == "HTTP_FETCH":
                    http.get(s["discovery_page"])
                    endpoint, detail, cfg_key = s["discovery_page"], {"method": "DISCOVERY_PAGE_ITSELF"}, "urls"
                else:
                    raise ValueError(f"method {s['method']} not part of K-05")
            except RobotsDisallowed as exc:
                entry.update(status="BLOCKED_BY_ROBOTS", reason=str(exc)[:300])
                continue
            except AccessDenied as exc:
                entry.update(status="ACCESS_DENIED", reason=str(exc)[:300])
                continue
            except Exception as exc:  # noqa: BLE001 — reported, never worked around
                entry.update(status="SOURCE_UNAVAILABLE", reason=f"{type(exc).__name__}: {exc}"[:300])
                continue
            entry["resolution"] = detail
            if not endpoint:
                entry.update(status="SOURCE_CONFIGURATION_UNRESOLVED",
                             reason="no unique, verified endpoint on the discovery page")
                continue
            entry["resolved_endpoint"] = endpoint
            cfg = {cfg_key: [endpoint] if cfg_key == "urls" else endpoint,
                   "max_items": int(s.get("max_items", 5)), "excerpt_max_chars": int(s.get("excerpt_max_chars", 1500))}
            payload = {"name": f"{s['id']} {s['name']} ({stamp})", "canonical_domain": s["domain"],
                       "source_type": s["source_type"], "primary_language": s["primary_language"],
                       "collection_method": s["method"], "collection_config": cfg,
                       "collection_frequency": s.get("frequency", "1 hour"), "retention_mode": "PERMITTED_EXCERPT",
                       "official_status": s.get("official_status", "OFFICIAL"),
                       "terms_notes": "K-05 real-source validation (DEV); PERMITTED_EXCERPT only"}
            sid = None
            try:
                sid = rest.rpc("create_source", {"p": payload}, admin)
                entry["source_id"] = sid
                rest.rpc("set_collection_method_approval", {"p_id": sid, "p_approved": True,
                                                            "p_reason": "K-05: PO-approved source set"}, admin)
                rest.rpc("set_source_active", {"p_id": sid, "p_active": True, "p_reason": "K-05 validation run"}, admin)
                runs = [run_pass(db, queue, handler, sid, "pass1"), run_pass(db, queue, handler, sid, "pass2")]
                entry["passes"] = runs
                entry.update(evaluate(db, sid, runs, s.get("expected_language")))
                ok = (entry["F3_job_collection"] == entry["F4_provenance_complete"]
                      == entry["F5_second_pass_no_uncontrolled_duplicates"] == "PASS") and entry["language_as_expected"]
                entry["status"] = "PASS" if ok else "FAIL"
            except Exception as exc:  # noqa: BLE001
                entry.update(status="FAIL", reason=f"{type(exc).__name__}: {exc}"[:300])
            finally:
                if sid:
                    try:
                        rest.rpc("set_source_active", {"p_id": sid, "p_active": False,
                                                       "p_reason": "K-05 validation finished"}, admin)
                    except Exception:  # noqa: BLE001
                        entry["deactivation"] = "FAILED — deactivate manually"
    statuses = [e["status"] for e in report["sources"]]
    report["overall"] = "PASS" if statuses and all(x == "PASS" for x in statuses) else "NOT PASSED"
    report["summary"] = {x: statuses.count(x) for x in sorted(set(statuses))}
    Path("k05-report.json").write_text(json.dumps(report, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    lines = ["| ID | Source | Method | Endpoint | F3 | F4 | F5 | Lang | Status |", "|---|---|---|---|---|---|---|---|---|"]
    for e in report["sources"]:
        lines.append(f"| {e['id']} | {e['name']} | {e['method']} | {e.get('resolved_endpoint', '-')} | "
                     f"{e.get('F3_job_collection', '-')} | {e.get('F4_provenance_complete', '-')} | "
                     f"{e.get('F5_second_pass_no_uncontrolled_duplicates', '-')} | "
                     f"{','.join(e.get('text_languages', [])) or '-'} | {e['status']} |")
    Path("k05-report.md").write_text(f"# K-05 report {stamp}\n\nOverall: **{report['overall']}**\n\n"
                                     + "\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, default=str, ensure_ascii=False))
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
