import { decideEvents } from "@/app/inbox/actions";
import { AutopilotCard, type AutopilotRow, type ReportOption } from "@/components/autopilot";
import { Submit } from "@/components/client";
import { Badge, Card, Empty, Flash, Locked, PageHeader, Stat, When } from "@/components/ui";
import { can, requireSession } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";
import { queueCounts } from "@/lib/workspace";

export const dynamic = "force-dynamic";

interface Head { event_id: string; title: string; state: string; head_version_id: string; head_content_hash: string; origin?: string }

export default async function Inbox({ searchParams }: { searchParams: Promise<{ ok?: string; error?: string }> }) {
  const { ok, error } = await searchParams;
  const session = await requireSession();
  const crumbs = [{ href: "/", label: "Dashboard" }, { label: "Inbox" }];
  if (!can(session, "CLAIM_READ")) return <><PageHeader title="Inbox" crumbs={crumbs} /><Locked>The inbox needs read access.</Locked></>;
  const supabase = await createClient();
  const q = await queueCounts(supabase, session);
  const none = ["00000000-0000-0000-0000-000000000000"];
  const [{ data: heads }, { data: reports }, { data: ap }, { data: inReview }] = await Promise.all([
    supabase.from("event_heads").select("event_id,title,state,head_version_id,head_content_hash,origin").eq("state", "CANDIDATE").eq("is_current", true)
      .order("title").limit(100),
    supabase.from("reports").select("id,code,report_mode,information_cutoff").order("created_at", { ascending: false }).limit(20),
    supabase.from("report_autopilot").select("report_id,enabled,reason,changed_at"),
    supabase.from("assessment_version_states").select("assessment_version_id,state,event_version_id").in("state", ["IN_REVIEW", "ESCALATED"]).limit(30),
  ]);
  const events = (heads ?? []) as Head[];
  const verIds = events.map((e) => e.head_version_id);
  const [{ data: rel }, { data: ass }] = await Promise.all([
    supabase.from("relevance_results").select("event_version_id,priority_score,automatic_assessment_recommended").in("event_version_id", verIds.length ? verIds : none),
    supabase.from("assessment_versions").select("id,event_version_id").in("event_version_id", verIds.length ? verIds : none),
  ]);
  const score = new Map(((rel ?? []) as { event_version_id: string; priority_score: number; automatic_assessment_recommended: boolean }[]).map((r) => [r.event_version_id, r]));
  const assessed = new Set(((ass ?? []) as { event_version_id: string }[]).map((a) => a.event_version_id));
  const reviewIds = ((inReview ?? []) as { event_version_id: string }[]).map((a) => a.event_version_id);
  const { data: titles } = await supabase.from("event_versions").select("id,title").in("id", reviewIds.length ? reviewIds : none);
  const titleOf = new Map(((titles ?? []) as { id: string; title: string }[]).map((t) => [t.id, t.title]));
  const actor = can(session, "EVENT_ACTION");
  const todo = events.length + reviewIds.length + q.qaToAcknowledge + q.contentToApprove + q.securityPending + q.releaseReady + q.failedJobs;

  return (
    <>
      <PageHeader title="Inbox" crumbs={crumbs}
        lede={<>Everything that needs <b>your</b> decision, in one place. {todo === 0 ? "Nothing is waiting." : `${todo} item(s) waiting.`} The system does the
          grouping, scoring, drafting and challenging; you confirm, approve and release.</>} />
      <Flash ok={ok} error={error} />
      <div className="grid cols-4" style={{ marginBottom: 16 }}>
        <Stat label="New events to confirm" value={events.length} tone={events.length ? "warn" : undefined} />
        <Stat label="Assessments to review" value={q.assessmentsInReview} href="/assessments?view=review" tone={q.assessmentsInReview ? "warn" : undefined} />
        <Stat label="Report gates waiting" value={q.qaToAcknowledge + q.contentToApprove + q.securityPending + q.releaseReady}
          hint="QA · content · security · release" href="/queue/review" />
        <Stat label="Pipeline problems" value={q.failedJobs} href="/jobs" tone={q.failedJobs ? "alert" : "ok"} />
      </div>
      <AutopilotCard reports={(reports ?? []) as ReportOption[]} state={(ap ?? []) as AutopilotRow[]} allowed={actor} />
      <Card title="1 · New events to confirm" actions={<a href="/events?state=CANDIDATE">Open the event list</a>}>
        {events.length === 0 ? <Empty title="No new event" /> : !actor ? <Locked>Confirming events needs EVENT_ACTION (analyst).</Locked> : (
          <form action={decideEvents} className="form">
            <div className="table-wrap"><table className="table">
              <thead><tr><th /><th>Event</th><th>Relevance</th><th>Assessment</th></tr></thead>
              <tbody>{events.map((e) => {
                const r = score.get(e.head_version_id);
                return (
                  <tr key={e.event_id}>
                    <td><input type="checkbox" name="item" aria-label={`select ${e.title}`} defaultChecked
                      value={`${e.event_id}|${e.head_version_id}|${e.head_content_hash}`} /></td>
                    <td><a href={`/events/${e.event_id}`}>{e.title}</a></td>
                    <td>{r ? <><Badge tone={r.automatic_assessment_recommended ? "ok" : "neutral"}>{Number(r.priority_score).toFixed(2)}</Badge>{" "}
                      {r.automatic_assessment_recommended ? "assessment recommended" : "not recommended"}</> : <span className="muted">pending</span>}</td>
                    <td>{assessed.has(e.head_version_id) ? <Badge value="DRAFTED" tone="info" /> : <span className="muted">not yet</span>}</td>
                  </tr>);
              })}</tbody>
            </table></div>
            <div className="form-row">
              <div className="field"><label htmlFor="in-reason">Reason (audited, one per click)</label>
                <input id="in-reason" name="reason" required minLength={5} defaultValue="reviewed in the inbox" /></div>
              <Submit name="decision" value="CONFIRM" kind="primary">Confirm selected (approve → ACTIVE)</Submit>
              <Submit name="decision" value="REJECT" kind="danger">Reject selected</Submit>
            </div>
            <p className="muted" style={{ margin: 0, fontSize: 12 }}>Each event is approved and activated by its own audited decision under your name. Open an event to read
              its claims first; untick what you want to look at separately.</p>
          </form>
        )}
      </Card>
      <Card title="2 · Assessments awaiting your review" actions={<a href="/assessments?view=review">Open</a>}>
        {reviewIds.length === 0 ? <Empty title="No assessment waits for review" /> : (
          <ul className="timeline">{((inReview ?? []) as { assessment_version_id: string; state: string; event_version_id: string }[]).map((a) => (
            <li key={a.assessment_version_id}><a href={`/assessments/${a.assessment_version_id}`}>{titleOf.get(a.event_version_id) ?? "assessment"}</a>{" "}
              <Badge value={a.state} /></li>))}</ul>)}
        <p className="muted" style={{ marginBottom: 0 }}>You dispose the challenge flags and set the final confidence here. That decision stays yours.</p>
      </Card>
      <Card title="3 · Report gates">
        <ul className="timeline">
          {can(session, "QA_WARNING_ACKNOWLEDGE") || can(session, "REPORT_CONTENT_APPROVE") ? <li><a href="/queue/review">QA &amp; content approval</a> <Badge tone="info">{q.qaToAcknowledge + q.contentToApprove}</Badge></li> : null}
          {can(session, "SECURITY_REVIEW") ? <li><a href="/queue/security">Security review</a> <Badge tone="info">{q.securityPending}</Badge></li> : null}
          {can(session, "RELEASE_DECIDE") ? <li><a href="/queue/release">Release decisions</a> <Badge tone="info">{q.releaseReady}</Badge></li> : null}
        </ul>
        <p className="muted" style={{ marginBottom: 0 }}>Each gate belongs to a different role, so no one can release their own work.</p>
      </Card>
      <p className="muted" style={{ fontSize: 12 }}>Updated <When at={new Date().toISOString()} />.</p>
    </>
  );
}
