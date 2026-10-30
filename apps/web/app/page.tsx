import { Badge, Card, Empty, PageHeader, Stat, When } from "@/components/ui";
import { can, requireSession } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";
import { openBlockingFindings, queueCounts } from "@/lib/workspace";

export const dynamic = "force-dynamic";

const TARGET = { total: 6, replay: 2, live: 2 };

export default async function Dashboard() {
  const session = await requireSession();
  const supabase = await createClient();
  const q = await queueCounts(supabase, session);
  const analyst = can(session, "CLAIM_REVIEW") || can(session, "EVENT_ACTION");
  const reviewer = can(session, "REPORT_CONTENT_APPROVE") || can(session, "QA_WARNING_ACKNOWLEDGE");
  const lead = can(session, "PILOT_MANAGE");
  const reads = can(session, "CLAIM_READ");
  const none = ["00000000-0000-0000-0000-000000000000"];

  const [{ data: candEvents }, { data: inReview }, { data: reports }, { data: cycles }, { data: timer }, { data: failed }, blocking] = await Promise.all([
    reads ? supabase.from("event_heads").select("event_id,title,state").eq("state", "CANDIDATE").eq("is_current", true).limit(6) : Promise.resolve({ data: [] }),
    reads ? supabase.from("assessment_version_states").select("assessment_version_id,state,event_version_id").in("state", ["IN_REVIEW", "ESCALATED"]).limit(6)
      : Promise.resolve({ data: [] }),
    reads ? supabase.from("reports").select("id,code,title,report_mode,information_cutoff,created_at").order("created_at", { ascending: false }).limit(5)
      : Promise.resolve({ data: [] }),
    can(session, "PILOT_READ") ? supabase.from("pilot_cycles").select("id,code,pilot_mode,status,report_id,started_at").order("started_at", { ascending: false })
      : Promise.resolve({ data: [] }),
    can(session, "PILOT_PARTICIPATE") ? supabase.from("pilot_timing_segments").select("cycle_id,stage,started_at").eq("user_id", session.userId).is("ended_at", null)
      : Promise.resolve({ data: [] }),
    can(session, "SYSTEM_READ") ? supabase.from("processing_jobs").select("id,job_type,object_id,last_error,completed_at").eq("status", "FAILED")
      .order("completed_at", { ascending: false }).limit(5) : Promise.resolve({ data: [] }),
    can(session, "PILOT_READ") ? openBlockingFindings(supabase) : Promise.resolve([]),
  ]);
  const evIds = ((inReview ?? []) as { event_version_id: string }[]).map((a) => a.event_version_id);
  const { data: evTitles } = await supabase.from("event_versions").select("id,title").in("id", evIds.length ? evIds : none);
  const titleOf = new Map(((evTitles ?? []) as { id: string; title: string }[]).map((e) => [e.id, e.title]));
  const reportList = (reports ?? []) as { id: string; code: string; title: string; report_mode: string; information_cutoff: string }[];
  const { data: wf } = await supabase.from("report_version_workflow").select("report_id,version_no,workflow_state").eq("is_latest", true)
    .in("report_id", reportList.length ? reportList.map((r) => r.id) : none);
  const stateOf = new Map(((wf ?? []) as { report_id: string; version_no: number; workflow_state: string }[]).map((w) => [w.report_id, w]));
  const cycleList = (cycles ?? []) as { id: string; code: string; pilot_mode: string; status: string; report_id: string | null; started_at: string }[];
  const completed = cycleList.filter((c) => c.status === "COMPLETED");
  const replay = completed.filter((c) => c.pilot_mode === "REPLAY").length;
  const live = completed.filter((c) => c.pilot_mode === "LIVE").length;
  const open = cycleList.filter((c) => c.status === "OPEN");
  const missing = lead ? await Promise.all(open.map(async (c) => {
    const { data } = await supabase.rpc("pilot_cycle_missing_metrics", { p_cycle: c.id });
    return { cycle: c, missing: (data ?? []) as string[] };
  })) : [];
  const active = ((timer ?? []) as { cycle_id: string; stage: string; started_at: string }[])[0];

  return (
    <>
      <PageHeader title="Dashboard" lede={<>Signed in as <b>{session.email}</b> · {session.roles.map((r) => <span key={r} className="badge role" style={{ marginRight: 4 }}>{r.replaceAll("_", " ")}</span>)}
        · live database state; every number links to its work queue.</>} />
      {active && <div className="alert info"><div><b>Timer running</b> — stage {active.stage.replaceAll("_", " ")} since <When at={active.started_at} />.{" "}
        <a href={`/pilot/${active.cycle_id}`}>Open the pilot cycle</a> to switch stage or stop.</div></div>}
      {blocking.length > 0 && <div className="alert error"><div><b>{blocking.length} unresolved BLOCKING UX finding(s)</b> — the affected pilot path is stopped until resolved:{" "}
        {blocking.slice(0, 3).map((f) => f.title).join(" · ")} <a href="/pilot?tab=ux">Review</a></div></div>}
      <div className="grid cols-4" style={{ marginBottom: 16 }}>
        {reads && <Stat label="Claims to review" value={q.claimsToReview} href="/claims?tab=review" tone={q.claimsToReview ? "warn" : undefined} />}
        {reads && <Stat label="Candidate events" value={q.eventsCandidate} href="/events?state=CANDIDATE" tone={q.eventsCandidate ? "warn" : undefined} />}
        {reads && <Stat label="Assessments awaiting review" value={q.assessmentsInReview} href="/assessments?view=review" tone={q.assessmentsInReview ? "warn" : undefined} />}
        {can(session, "SYSTEM_READ") && <Stat label="Pipeline jobs" value={q.failedJobs} hint={`${q.activeJobs} queued / running`} href="/jobs"
          tone={q.failedJobs ? "alert" : "ok"} />}
        {reviewer && <Stat label="QA warnings to acknowledge" value={q.qaToAcknowledge} href="/queue/review" tone={q.qaToAcknowledge ? "warn" : undefined} />}
        {reviewer && <Stat label="Content approvals pending" value={q.contentToApprove} href="/queue/review" tone={q.contentToApprove ? "warn" : undefined} />}
        {can(session, "SECURITY_REVIEW") && <Stat label="Security reviews pending" value={q.securityPending} href="/queue/security" tone={q.securityPending ? "warn" : undefined} />}
        {can(session, "RELEASE_DECIDE") && <Stat label="Ready for release decision" value={q.releaseReady} href="/queue/release" tone={q.releaseReady ? "warn" : undefined} />}
        {can(session, "PILOT_READ") && <Stat label="Pilot cycles completed" value={`${completed.length} / ${TARGET.total}`}
          hint={`REPLAY ${replay}/${TARGET.replay}+ · LIVE ${live}/${TARGET.live}+ · ${open.length} open`} href="/pilot" />}
      </div>
      <div className="grid cols-2">
        {analyst && (
          <Card title="Events awaiting a decision" actions={<a href="/events?state=CANDIDATE">All</a>}>
            {(candEvents ?? []).length === 0 ? <p className="muted">No candidate event.</p> : (
              <ul className="timeline">{((candEvents ?? []) as { event_id: string; title: string; state: string }[]).map((e) => (
                <li key={e.event_id}><a href={`/events/${e.event_id}`}>{e.title}</a> <Badge value={e.state} /></li>))}</ul>)}
          </Card>
        )}
        {(analyst || reviewer) && (
          <Card title="Assessments awaiting human review" actions={<a href="/assessments?view=review">All</a>}>
            {(inReview ?? []).length === 0 ? <p className="muted">Nothing waiting.</p> : (
              <ul className="timeline">{((inReview ?? []) as { assessment_version_id: string; state: string; event_version_id: string }[]).map((a) => (
                <li key={a.assessment_version_id}><a href={`/assessments/${a.assessment_version_id}`}>{titleOf.get(a.event_version_id) ?? "assessment"}</a> <Badge value={a.state} /></li>))}</ul>)}
          </Card>
        )}
        {reads && (
          <Card title="Reports" actions={<a href="/reports">All reports</a>}>
            {reportList.length === 0 ? <Empty title="No report yet" /> : (
              <ul className="timeline">{reportList.map((r) => {
                const w = stateOf.get(r.id);
                return <li key={r.id}><a href={`/reports/${r.id}`}>{r.code}</a> — {r.title} <Badge value={r.report_mode} />{" "}
                  {w ? <Badge value={w.workflow_state}>{`v${w.version_no} · ${w.workflow_state.replaceAll("_", " ")}`}</Badge> : <Badge tone="neutral">no draft yet</Badge>}</li>;
              })}</ul>)}
          </Card>
        )}
        {can(session, "PILOT_READ") && (
          <Card title="Pilot measurement" actions={<a href="/pilot">Pilot workspace</a>}>
            <div className="progress" aria-label="cycles completed"><span style={{ width: `${Math.min(100, (completed.length / TARGET.total) * 100)}%` }} /></div>
            <p className="muted" style={{ fontSize: 12.5, marginTop: 6 }}>{completed.length} of {TARGET.total} complete cycles (≥ {TARGET.replay} REPLAY, ≥ {TARGET.live} LIVE).
              Capability verdict: OPERATIONAL VALUE NOT YET VALIDATED.</p>
            {open.length === 0 ? <p className="muted">No open cycle.</p> : (
              <ul className="timeline">{open.map((c) => {
                const m = missing.find((x) => x.cycle.id === c.id)?.missing;
                return <li key={c.id}><a href={`/pilot/${c.id}`}>{c.code}</a> <Badge value={c.pilot_mode} /> <Badge value={c.status} />
                  {m && (m.length === 0 ? <Badge tone="ok">measurement complete</Badge> : <span className="muted"> · missing: {m.join(", ").replaceAll("_", " ").toLowerCase()}</span>)}</li>;
              })}</ul>)}
          </Card>
        )}
        {can(session, "SYSTEM_READ") && (failed ?? []).length > 0 && (
          <Card title="Failed pipeline jobs" tone="danger" actions={<a href="/jobs?status=FAILED">All</a>}>
            <ul className="timeline">{((failed ?? []) as { id: string; job_type: string; last_error: string | null; completed_at: string | null }[]).map((j) => (
              <li key={j.id}><b>{j.job_type}</b> <When at={j.completed_at} /> — <span style={{ color: "var(--danger)" }}>{(j.last_error ?? "").slice(0, 160)}</span></li>))}</ul>
          </Card>
        )}
      </div>
    </>
  );
}
