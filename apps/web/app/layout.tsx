import "./globals.css";

import type { ReactNode } from "react";

import { signOut } from "@/app/login/actions";
import { NavLink } from "@/components/client";
import { can, getSession } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";
import { queueCounts } from "@/lib/workspace";

export const metadata = { title: "LFHÉ — analyst workspace" };
export const dynamic = "force-dynamic";

export default async function RootLayout({ children }: { children: ReactNode }) {
  const session = await getSession().catch(() => null);
  if (!session) {
    return (
      <html lang="en">
        <body><div className="unauth">{children}</div></body>
      </html>
    );
  }
  const supabase = await createClient();
  const q = await queueCounts(supabase, session);
  const reviewerQueue = can(session, "QA_WARNING_ACKNOWLEDGE") || can(session, "REPORT_CONTENT_APPROVE");
  return (
    <html lang="en">
      <body>
        <div className="shell">
          <aside className="sidebar" aria-label="Main navigation">
            <div className="brand">LFHÉ</div>
            <div className="brand-sub">AI-assisted, human-governed air-domain OSINT · Phase 7 pilot</div>
            <NavLink href="/">Dashboard</NavLink>
            <div className="nav-group">Analysis</div>
            {can(session, "SOURCE_READ") && <NavLink href="/sources">Sources</NavLink>}
            {can(session, "CLAIM_READ") && <NavLink href="/claims" count={q.claimsToReview}>Claims</NavLink>}
            {can(session, "CLAIM_READ") && <NavLink href="/events" count={q.eventsCandidate}>Events</NavLink>}
            {can(session, "CLAIM_READ") && <NavLink href="/assessments" count={q.assessmentsInReview}>Assessments</NavLink>}
            {can(session, "CLAIM_READ") && <NavLink href="/reports">Reports</NavLink>}
            {(reviewerQueue || can(session, "SECURITY_REVIEW") || can(session, "RELEASE_DECIDE")) && <div className="nav-group">Decisions</div>}
            {reviewerQueue && <NavLink href="/queue/review" count={q.qaToAcknowledge + q.contentToApprove}>QA &amp; content approval</NavLink>}
            {can(session, "SECURITY_REVIEW") && <NavLink href="/queue/security" count={q.securityPending}>Security review</NavLink>}
            {can(session, "RELEASE_DECIDE") && <NavLink href="/queue/release" count={q.releaseReady}>Release decisions</NavLink>}
            <div className="nav-group">Operations</div>
            {can(session, "SYSTEM_READ") && <NavLink href="/jobs" count={q.failedJobs} alert={q.failedJobs > 0}>Pipeline jobs</NavLink>}
            {can(session, "PILOT_READ") && <NavLink href="/pilot" count={q.blockingUx} alert={q.blockingUx > 0}>Pilot</NavLink>}
            <div className="sidebar-foot">
              <div className="who">{session.email ?? session.userId}</div>
              <div className="row" style={{ marginTop: 6 }}>
                {session.roles.map((r) => <span key={r} className="badge role">{r.replaceAll("_", " ")}</span>)}
              </div>
              <form action={signOut}><button type="submit">Sign out</button></form>
            </div>
          </aside>
          <div className="main">
            <div className="topbar">
              <div className="boundary">
                <span className="badge warn">DEV / localhost only</span>
                <span className="badge info">Public OSINT · synthetic · authorised replay</span>
                <span className="muted">AI recommends — every decision is a human, audited database action.</span>
              </div>
              <div className="boundary">
                {q.activeJobs > 0 && <a className="badge info" href="/jobs">{q.activeJobs} job(s) running / queued</a>}
                {q.failedJobs > 0 && <a className="badge danger" href="/jobs?status=FAILED">{q.failedJobs} failed job(s)</a>}
              </div>
            </div>
            <div className="content">{children}</div>
          </div>
        </div>
      </body>
    </html>
  );
}
