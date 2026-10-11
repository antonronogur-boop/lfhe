# K-05 — real-source collection validation (Product Owner run, DEV only)

The cloud development environment cannot reach the approved source domains, so K-05 runs on the
PO's machine against DEV Supabase with the real collector (`scripts/k05_validate_sources.py`).

## Rules (PO K-05 instruction)
* Approved set K05-01 … K05-08 only; all PERMITTED_EXCERPT; no substitutes, no workarounds.
* Feed / sitemap URLs are never guessed: the script reads them from a **PO-confirmed official
  discovery page** and verifies them. Zero or several verified endpoints →
  `SOURCE_CONFIGURATION_UNRESOLVED`. robots.txt disallow → `BLOCKED_BY_ROBOTS`; 401/403 →
  `ACCESS_DENIED`; network / 5xx → `SOURCE_UNAVAILABLE`.
* Two passes per source, each a `COLLECT_SOURCE` job processed by the real job handler.
* Per source: F3 (job collection), F4 (provenance completeness incl. original-language excerpt),
  F5 (second pass creates no uncontrolled duplicate), language as expected, overall status.
* The K-05 sources are deactivated at the end (re-activation is a separate audited decision).

## Steps (PowerShell, repo root, venv active)
1. `git pull`, then apply migrations if not yet done (see `dev-supabase-smoke.md`).
2. `copy scripts\k05_sources.template.json k05_sources.json` (git-ignored). For each source open the
   official page in a browser, put its exact address into `discovery_page`, set `po_confirmed` to
   `true`; optionally set `hint` (e.g. `Top Stories`) when the page lists several feeds.
   For STRUCTURED_FEED use the site's `robots.txt` or official sitemap index as the discovery page.
3. Environment (values only in your shell; never paste them into the chat):
   ```powershell
   $env:LFHE_K05_DB_URL = "<DEV session pooler URI>"
   $env:LFHE_SMOKE_SUPABASE_URL = "https://ylkubhuxvcsshfkbvski.supabase.co"
   $env:LFHE_SMOKE_ANON_KEY = "<DEV anon key>"
   $env:LFHE_SMOKE_ADMIN_EMAIL = "<DEV admin email>"; $env:LFHE_SMOKE_ADMIN_PASSWORD = "<password>"
   $env:LFHE_K05_USER_AGENT = "LFHE-OSINT-Collector/0.1 (+contact: <your contact address>)"
   python scripts\k05_validate_sources.py k05_sources.json
   ```
4. Send `k05-report.json` (and/or `k05-report.md`) back. They contain no credentials.
   Runtime: roughly 5–15 minutes (5 s politeness interval per host, ≤5 items per source).
