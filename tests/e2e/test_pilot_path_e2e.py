"""CR7-03 browser E2E — the whole human-in-command path in a real browser, with several roles.

login → M02 request → claim review → M05 request → event review / state → M06 request + relevance decision → M07 request
(M08 chained) → challenge disposition → human approval with final confidence → report candidate pool → selection → M09 draft
→ QA (M10-D + M10-S) → warning acknowledgement (REVIEWER) → content approval (REVIEWER) → security review
(SECURITY_REVIEWER) → release PDF + release (RELEASE_AUTHORITY) → released PDF / manifest / hash; plus the pilot measurement
path (cycle, bind, comparator NONE, timer, chain runs, workload, COMPLETED) on the throw-away database.

Every human action is performed through the UI. SQL is used only to WAIT for the worker and to ASSERT outcomes (read-only).
The model is the SYNTHETIC_TEST_ONLY scripted stand-in (tests/e2e/synthetic_provider.py); nothing here touches DEV.
Skips unless PostgreSQL, PostgREST, Node dependencies and Playwright are available."""
from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = [pytest.mark.e2e]

try:
    from playwright.sync_api import Page, expect, sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

from stack import CUTOFF, Stack, postgrest_binary  # noqa: E402

CUTOFF_LOCAL = "2026-03-01T00:00"          # the Next server runs in UTC in the E2E stack


def _skip_reason() -> str | None:
    if sync_playwright is None:
        return "playwright not installed"
    if postgrest_binary() is None:
        return "PostgREST binary not available (LFHE_E2E_POSTGREST)"
    if not (ROOT / "apps" / "web" / "node_modules" / ".bin" / "next").exists():
        return "apps/web dependencies not installed (npm ci)"
    if shutil.which("npm") is None:
        return "npm not available"
    return None


class Attached:
    """Attach to a stack started with `python tests/e2e/stack.py` (LFHE_E2E_ATTACH=<its JSON output>)."""

    def __init__(self, path: str):
        import psycopg
        from psycopg.rows import dict_row
        info = json.loads(Path(path).read_text())
        self.web_url, self.users = info["web"], {k: dict(v) for k, v in info["users"].items()}
        self._db = info["db"]
        self._psycopg, self._row = psycopg, dict_row
        for u in self.users.values():
            u["id"] = str(self.sql("SELECT id FROM auth.users WHERE email=%s", u["email"])[0]["id"])

    def sql(self, query, *args):
        with self._psycopg.connect(self._db, autocommit=True, row_factory=self._row) as c:
            return c.execute(query, args).fetchall()

    def down(self):
        pass


@pytest.fixture(scope="module")
def stack():
    reason = _skip_reason()
    if reason:
        pytest.skip(reason)
    if os.environ.get("LFHE_E2E_ATTACH"):
        st = Attached(os.environ["LFHE_E2E_ATTACH"])
    else:
        st = Stack().up()
    try:
        yield st
    finally:
        st.down()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def wait_for(stack, query, predicate=lambda rows: bool(rows), timeout=90, *args):
    deadline = time.monotonic() + timeout
    rows = []
    while time.monotonic() < deadline:
        rows = stack.sql(query, *args)
        if predicate(rows):
            return rows
        time.sleep(0.5)
    diag = ""
    base = getattr(stack, "base", None)
    if base is not None:
        for name in ("worker.log", "web.log", "postgrest.log"):
            f = Path(base) / name
            if f.exists():
                diag += f"\n--- {name} (tail) ---\n" + "\n".join(f.read_text(errors="replace").splitlines()[-25:])
        diag += "\nprocesses alive: " + str([p.poll() is None for p in getattr(stack, "procs", [])])
    raise AssertionError(f"timed out waiting for: {query} -> {rows}{diag}")


def login(browser, stack, who: str) -> Page:
    ctx = browser.new_context(viewport={"width": 1400, "height": 1000}, accept_downloads=True)
    page = ctx.new_page()
    u = stack.users[who]
    page.goto(f"{stack.web_url}/login")
    page.get_by_label("E-mail").fill(u["email"])
    page.get_by_label("Password").fill(u["password"])
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url(f"{stack.web_url}/")
    expect(page.get_by_role("heading", name="Dashboard")).to_be_visible()
    return page


def ok(page: Page):
    errors = page.locator(".alert.error")
    assert errors.count() == 0, errors.first.inner_text()
    expect(page.locator(".alert.success").first).to_be_visible(timeout=30000)
    page.goto(_strip_feedback(page.url))            # reopen without the feedback, so the next action's result is unambiguous
    page.wait_for_load_state("networkidle")


def _strip_feedback(url: str) -> str:
    base, _, query = url.partition("?")
    keep = [p for p in query.split("&") if p and not p.startswith(("ok=", "error="))]
    return base + ("?" + "&".join(keep) if keep else "")


def press(page: Page, scope, name, **kw):
    """Submit through a button and wait for the server action's redirect (…ok= / …error=), so the feedback checked
    afterwards is the result of THIS action (old feedback is cleared by reopening the page without it)."""
    assert "ok=" not in page.url and "error=" not in page.url, page.url
    scope.get_by_role("button", name=name, **kw).click()
    page.wait_for_url(lambda u: "ok=" in u or "error=" in u, timeout=60000)
    page.wait_for_load_state("networkidle")


def go(page: Page, stack, path: str):
    page.goto(f"{stack.web_url}{path}")
    page.wait_for_load_state("networkidle")


def test_full_human_in_command_path(stack, browser):
    analyst = login(browser, stack, "analyst")

    # --- report first, then the pilot cycle with exactly the same mode and cutoff (runbook order) ------------------
    go(analyst, stack, "/reports")
    analyst.locator("#code").fill("RPT-E2E-REPLAY-01")
    analyst.locator("#cycle_label").fill("E2E-REPLAY-01")
    analyst.locator("#report_mode").select_option("REPLAY")
    analyst.locator("#information_cutoff").fill(CUTOFF_LOCAL)
    analyst.locator("#title").fill("E2E synthetic replay report")
    analyst.locator("#reason").fill("E2E: open the synthetic replay cycle")
    analyst.get_by_role("button", name="Create report and load eligible candidates").click()
    analyst.wait_for_url(re.compile(r"/reports/[0-9a-f-]{36}\?"))
    report_id = re.search(r"/reports/([0-9a-f-]{36})", analyst.url).group(1)
    assert stack.sql("SELECT report_mode::text m, information_cutoff c FROM lfhe.reports WHERE id=%s", report_id)[0]["m"] == "REPLAY"

    go(analyst, stack, "/pilot")
    analyst.locator("#code").fill("P7C-E2E-REPLAY-01")
    analyst.locator("#pilot_mode").select_option("REPLAY")
    analyst.locator("#cutoff").fill(CUTOFF_LOCAL)
    analyst.locator("#boundary").select_option("SYNTHETIC")
    analyst.locator("#scope").fill("E2E synthetic corpus (SYNTHETIC_TEST_ONLY), two statements")
    analyst.locator("#provider").fill("synthetic scripted model (E2E only)")
    analyst.get_by_role("button", name="Create pilot cycle").click()
    analyst.wait_for_url(re.compile(r"/pilot/[0-9a-f-]{36}\?"))
    cycle_url = analyst.url.split("?")[0]
    ok(analyst)
    analyst.locator("select[name=report_id]").select_option(report_id)
    press(analyst, analyst, "Bind", exact=True)
    ok(analyst)
    analyst.locator("select[name=method]").select_option("NONE")
    analyst.locator("select[name=comparable_scope]").select_option("no")
    analyst.locator("input[name=reference]").fill("No timed or documented manual baseline exists; E2E validates instrumentation")
    press(analyst, analyst, re.compile("Record comparator"))
    ok(analyst)
    expect(analyst.get_by_text("observational only / productivity claim not available").first).to_be_visible()
    analyst.locator("select[name=stage]").select_option("CLAIM_REVIEW")
    press(analyst, analyst, "Start timer")
    ok(analyst)

    # --- M02 request from the intake view ------------------------------------------------------------------------
    go(analyst, stack, "/claims?tab=intake")
    press(analyst, analyst, "Extract all pending (M02)")
    ok(analyst)
    claims = wait_for(stack, "SELECT c.id FROM lfhe.claims c JOIN lfhe.processing_jobs j ON j.job_type='CLASSIFY_CLAIMS' "
                             "AND j.status IN ('SUCCESS','HUMAN_REVIEW') GROUP BY c.id", lambda r: len(r) >= 2)
    claim_ids = [str(r["id"]) for r in claims]

    # --- human claim review --------------------------------------------------------------------------------------
    for cid in claim_ids:
        go(analyst, stack, f"/claims/{cid}")
        expect(analyst.locator(".evidence mark")).to_be_visible()                 # original-language evidence span
        analyst.locator("#decision").select_option("APPROVE")
        analyst.locator("#reason").fill("E2E: span matches the source text")
        press(analyst, analyst, "Record decision")
        ok(analyst)
    assert {r["review_state"] for r in stack.sql("SELECT review_state FROM lfhe.claim_state")} == {"VALIDATED"}

    # --- M05 request for the selected claims, in the report's REPLAY context ------------------------------------
    go(analyst, stack, "/claims?tab=all")
    for box in analyst.locator("input[name=claim_ids]").all():
        box.check()
    analyst.locator("#ctx").select_option(report_id)
    press(analyst, analyst, "Build events (M05)")
    ok(analyst)
    ev = wait_for(stack, "SELECT event_id, head_version_id FROM lfhe.event_heads WHERE is_current")
    event_id = str(ev[0]["event_id"])
    assert stack.sql("SELECT state::text s FROM lfhe.event_heads WHERE event_id=%s", event_id)[0]["s"] == "CANDIDATE"

    # --- event: human review + state, M06 request + validation, M07 request -----------------------------------------
    go(analyst, stack, f"/events/{event_id}")
    expect(analyst.get_by_text("contested evidence").first).to_be_visible()    # CONTRADICTS claim is visible
    review = analyst.locator("form", has=analyst.get_by_role("button", name="Record event review"))
    review.locator("select[name=decision]").select_option("APPROVE")
    review.locator("input[name=reason]").fill("E2E: event correctly groups the statement and its denial")
    press(analyst, review, "Record event review")
    ok(analyst)
    state = analyst.locator("form", has=analyst.get_by_role("button", name="Change state"))
    state.locator("select[name=new_state]").select_option("ACTIVE")
    state.locator("input[name=reason]").fill("E2E: promote the candidate event")
    press(analyst, state, "Change state")
    ok(analyst)
    m06 = analyst.locator("form", has=analyst.get_by_role("button", name="Request relevance (M06)"))
    m06.locator("select[name=ctx]").select_option(report_id)
    press(analyst, m06, "Request relevance (M06)")
    ok(analyst)
    wait_for(stack, "SELECT 1 FROM lfhe.relevance_results WHERE event_id=%s", bool, 90, event_id)
    go(analyst, stack, f"/events/{event_id}")
    rel = analyst.locator("form", has=analyst.get_by_role("button", name="Record relevance decision"))
    rel.locator("select[name=action]").select_option("VALIDATE")
    rel.locator("input[name=reason]").fill("E2E: relevance rationale is evidence-based")
    press(analyst, rel, "Record relevance decision")
    ok(analyst)
    m07 = analyst.locator("form", has=analyst.get_by_role("button", name="Request assessment (M07)"))
    m07.locator("select[name=ctx]").select_option(report_id)
    press(analyst, m07, "Request assessment (M07)")
    ok(analyst)
    av = wait_for(stack, "SELECT s.assessment_version_id id FROM lfhe.assessment_version_states s JOIN lfhe.assessment_versions v "
                         "ON v.id = s.assessment_version_id JOIN lfhe.event_versions e ON e.id = v.event_version_id "
                         "WHERE e.event_id=%s AND s.state='IN_REVIEW'", bool, 120, event_id)
    av_id = str(av[0]["id"])

    # --- human analytical review --------------------------------------------------------------------------------
    go(analyst, stack, f"/assessments/{av_id}")
    for cat in ("FACT", "ASSESSMENT"):
        expect(analyst.locator(f".badge.epi-{cat}").first).to_be_visible()
    expect(analyst.get_by_text("Final analytic confidence (human)")).to_be_visible()
    flags = analyst.locator("form", has=analyst.locator("select[name=disposition]"))
    for i in range(flags.count()):
        form = flags.nth(i)
        form.locator("select[name=disposition]").select_option("ACKNOWLEDGED")
        form.locator("input[name=reason]").fill("E2E: flag considered; confidence kept LOW")
        press(analyst, form, "Record", exact=True)
        ok(analyst)
    analyst.locator("#decision").select_option("APPROVE")
    analyst.locator("#final_confidence").select_option("LOW")
    analyst.locator("#confidence_rationale").fill("Single official source contradicted by an official denial.")
    analyst.locator("#reason").fill("E2E: approve with LOW confidence")
    analyst.get_by_label(re.compile("I reviewed the statements")).check()
    press(analyst, analyst, "Record review decision")
    ok(analyst)
    assert stack.sql("SELECT state::text s, final_analytic_confidence::text c FROM lfhe.assessment_version_states "
                     "WHERE assessment_version_id=%s", av_id)[0] == {"s": "APPROVED", "c": "LOW"}

    # --- report: candidate → selection → M09 draft → QA ----------------------------------------------------------
    go(analyst, stack, f"/reports/{report_id}?view=pool")
    press(analyst, analyst, "Refresh eligible candidates")
    ok(analyst)
    cand = analyst.locator("form", has=analyst.get_by_role("button", name="Record", exact=True)).first
    cand.locator("select[name=decision]").select_option("INCLUDE")
    cand.locator("select[name=section]").select_option("KEY_JUDGMENT")
    cand.locator("input[name=reason]").fill("E2E: key judgement for the cycle")
    press(analyst, cand, "Record", exact=True)
    ok(analyst)
    freeze = analyst.locator("form", has=analyst.get_by_role("button", name="Request M09 draft"))
    freeze.locator("input[name=reason]").fill("E2E: freeze the selection")
    press(analyst, freeze, "Request M09 draft")
    ok(analyst)
    wait_for(stack, "SELECT 1 FROM lfhe.report_versions v JOIN lfhe.report_renders r ON r.report_version_id=v.id WHERE v.report_id=%s",
             bool, 120, report_id)
    go(analyst, stack, f"/reports/{report_id}?view=qa")
    qa = analyst.locator("form", has=analyst.get_by_role("button", name="Request QA"))
    qa.locator("input[name=reason]").fill("E2E: request QA for this exact version")
    press(analyst, qa, "Request QA")
    ok(analyst)
    wait_for(stack, "SELECT 1 FROM lfhe.report_version_workflow WHERE report_id=%s AND is_latest AND workflow_state='QA_PASSED_WITH_WARNINGS'",
             bool, 120, report_id)
    analyst.close()

    # --- REVIEWER: warning acknowledgement + content approval ----------------------------------------------------
    reviewer = login(browser, stack, "reviewer")
    go(reviewer, stack, "/queue/review")
    reviewer.get_by_role("link", name="Open").first.click()
    reviewer.wait_for_load_state("networkidle")
    warnings = reviewer.locator("form", has=reviewer.get_by_role("button", name="Acknowledge this warning"))
    assert warnings.count() >= 1
    while warnings.count() > 0:
        form = warnings.first
        form.locator("input[name=rationale]").fill("E2E: warning reviewed against the evidence; caveat stays visible")
        press(reviewer, form, "Acknowledge this warning")
        ok(reviewer)
    content = reviewer.locator("form", has=reviewer.get_by_role("button", name="Record content decision"))
    content.locator("select[name=decision]").select_option("APPROVE")
    content.locator("input[name=rationale]").fill("E2E: content approved for this exact version")
    press(reviewer, content, "Record content decision")
    ok(reviewer)
    reviewer.close()

    # --- SECURITY_REVIEWER ---------------------------------------------------------------------------------------
    sec = login(browser, stack, "security")
    go(sec, stack, "/queue/security")
    sec.get_by_role("link", name="Open").first.click()
    sec.wait_for_load_state("networkidle")
    form = sec.locator("form", has=sec.get_by_role("button", name="Record security decision"))
    form.locator("select[name=status]").select_option("APPROVED")
    form.locator("input[name=rationale]").fill("E2E: OSINT-only synthetic content, releasable")
    press(sec, form, "Record security decision")
    ok(sec)
    sec.close()

    # --- RELEASE_AUTHORITY ---------------------------------------------------------------------------------------
    ra = login(browser, stack, "release")
    go(ra, stack, "/queue/release")
    ra.get_by_role("link", name="Open").first.click()
    ra.wait_for_load_state("networkidle")
    release_url = ra.url
    pdf = ra.locator("form", has=ra.get_by_role("button", name="Request release PDF"))
    pdf.locator("input[name=reason]").fill("E2E: render the release PDF")
    press(ra, pdf, "Request release PDF")
    ok(ra)
    wait_for(stack, "SELECT 1 FROM lfhe.release_pdf_artifacts a JOIN lfhe.report_versions v ON v.id=a.report_version_id WHERE v.report_id=%s",
             bool, 180, report_id)
    ra.goto(release_url.split("&ok=")[0])
    rel_form = ra.locator("form", has=ra.get_by_role("button", name="APPROVE_FOR_RELEASE"))
    rel_form.locator("input[name=rationale]").fill("E2E: all release conditions verified")
    rel_form.locator("input[name=confirm]").fill("RELEASE")
    press(ra, rel_form, "APPROVE_FOR_RELEASE")
    ok(ra)
    expect(ra.get_by_role("heading", name="RELEASED")).to_be_visible()
    rel = stack.sql("SELECT r.manifest_hash, r.pdf_sha256, r.pdf_artifact_id FROM lfhe.report_releases r WHERE r.report_id=%s", report_id)[0]
    expect(ra.get_by_text(rel["manifest_hash"])).to_be_visible()
    resp = ra.request.get(f"{stack.web_url}/reports/{report_id}/pdf/{rel['pdf_artifact_id']}")
    assert resp.status == 200 and resp.body()[:4] == b"%PDF"
    ra.close()

    # --- pilot measurement completes (throw-away DB only) --------------------------------------------------------
    analyst = login(browser, stack, "analyst")
    analyst.goto(cycle_url)
    press(analyst, analyst, re.compile("Stop timer"))
    ok(analyst)
    press(analyst, analyst, re.compile("Bind the report chain"))
    ok(analyst)
    for d in ("mental", "physical", "temporal", "performance", "effort", "frustration"):
        analyst.locator(f"input[name={d}]").fill("40")
    press(analyst, analyst, "Record workload")
    ok(analyst)
    expect(analyst.get_by_text("Nothing missing")).to_be_visible()
    close = analyst.locator("form", has=analyst.get_by_role("button", name=re.compile("Close")))
    close.locator("select[name=outcome]").select_option("COMPLETED")
    close.locator("input[name=note]").fill("E2E: complete synthetic cycle (validation only)")
    press(analyst, close, re.compile("Close"))
    ok(analyst)
    assert stack.sql("SELECT status, terminal_state FROM lfhe.pilot_cycles WHERE code='P7C-E2E-REPLAY-01'")[0] == \
        {"status": "COMPLETED", "terminal_state": "RELEASED"}
    analyst.close()

    # --- audit / provenance / human attribution ------------------------------------------------------------------
    users = {k: v["id"] for k, v in stack.users.items()}
    reqs = stack.sql("SELECT job_type, requested_by::text u FROM lfhe.workflow_job_requests ORDER BY seq")
    assert {r["job_type"] for r in reqs} >= {"EXTRACT_CLAIMS", "BUILD_EVENTS", "ASSESS_RELEVANCE", "ASSESS_EVENT"}
    assert {r["u"] for r in reqs} == {users["analyst"]}
    assert stack.sql("SELECT count(*) n FROM lfhe.audit_log WHERE event_type='WORKFLOW_JOB_REQUESTED'")[0]["n"] == len(reqs)
    who = {r["k"]: r["u"] for r in stack.sql(
        "SELECT 'approval' k, reviewer_user_id::text u FROM lfhe.analytical_approvals UNION ALL "
        "SELECT 'content', reviewer_user_id::text FROM lfhe.content_approvals UNION ALL "
        "SELECT 'security', reviewer_user_id::text FROM lfhe.security_reviews WHERE status <> 'PENDING' UNION ALL "
        "SELECT 'release', released_by::text FROM lfhe.report_releases")}
    assert who == {"approval": users["analyst"], "content": users["reviewer"], "security": users["security"], "release": users["release"]}


def test_role_boundaries_in_the_ui(stack, browser):
    """VIEWER stays read-only; ADMIN gets no analytical authority; locked actions explain why."""
    claim = stack.sql("SELECT id FROM lfhe.claims LIMIT 1")
    event = stack.sql("SELECT event_id FROM lfhe.event_heads LIMIT 1")
    if not claim or not event:
        pytest.skip("needs the data of the full-path test")
    viewer = login(browser, stack, "viewer")
    go(viewer, stack, f"/claims/{claim[0]['id']}")
    expect(viewer.get_by_text("Claim review needs CLAIM_REVIEW")).to_be_visible()
    expect(viewer.get_by_role("button", name="Record decision")).to_have_count(0)
    go(viewer, stack, f"/events/{event[0]['event_id']}")
    expect(viewer.get_by_role("button", name="Request assessment (M07)")).to_have_count(0)
    go(viewer, stack, "/jobs")
    expect(viewer.get_by_text("Job status needs SYSTEM_READ")).to_be_visible()
    viewer.close()
    admin = login(browser, stack, "admin")
    go(admin, stack, f"/events/{event[0]['event_id']}")
    expect(admin.get_by_text("Event decisions need EVENT_ACTION").first).to_be_visible()
    expect(admin.get_by_role("button", name="Request relevance (M06)")).to_have_count(0)
    go(admin, stack, "/queue/release")
    expect(admin.get_by_text("your role cannot take these decisions")).to_be_visible()
    admin.close()
