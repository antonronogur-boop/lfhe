import { Submit } from "@/components/client";
import { Badge, Card, Empty, Flash, Locked, PageHeader, When } from "@/components/ui";
import { can, requireSession } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";

import { createReport } from "./actions";

export const dynamic = "force-dynamic";

interface ReportRow { id: string; code: string; title: string; cycle_label: string; report_mode: string; information_cutoff: string; created_at: string }

export default async function ReportsPage({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  const { error } = await searchParams;
  const session = await requireSession();
  if (!can(session, "CLAIM_READ")) return <><PageHeader title="Reports" /><Locked>Your role does not include CLAIM_READ.</Locked></>;
  const editor = can(session, "REPORT_EDIT");
  const supabase = await createClient();
  const { data, error: loadError } = await supabase.from("reports").select("*").order("created_at", { ascending: false }).limit(50);
  const reports = (data ?? []) as ReportRow[];
  const { data: wf } = await supabase.from("report_version_workflow").select("report_id,version_no,workflow_state,qa_status").eq("is_latest", true)
    .in("report_id", reports.length ? reports.map((r) => r.id) : ["00000000-0000-0000-0000-000000000000"]);
  const state = new Map(((wf ?? []) as { report_id: string; version_no: number; workflow_state: string; qa_status: string | null }[]).map((w) => [w.report_id, w]));
  const { data: pool } = await supabase.from("report_candidate_state").select("report_id,latest_decision")
    .in("report_id", reports.length ? reports.map((r) => r.id) : ["00000000-0000-0000-0000-000000000000"]);
  const poolBy = new Map<string, { n: number; inc: number }>();
  for (const c of (pool ?? []) as { report_id: string; latest_decision: string | null }[]) {
    const x = poolBy.get(c.report_id) ?? { n: 0, inc: 0 };
    poolBy.set(c.report_id, { n: x.n + 1, inc: x.inc + (c.latest_decision === "INCLUDE" ? 1 : 0) });
  }
  return (
    <>
      <PageHeader title="Reports" crumbs={[{ href: "/", label: "Dashboard" }, { label: "Reports" }]}
        lede="Draft reports are built only from approved Phase 4 material that you select. M09 edits wording; you decide inclusion, section placement and every substantive removal. Drafts are previews — not QA-approved, not security-reviewed, not released." />
      <Flash error={error} />
      {loadError && <Flash error={`Could not load reports: ${loadError.message}`} />}
      {reports.length === 0 ? <Empty title="No reports yet">Create a report cycle below; its mode and information cutoff fix which approved material is eligible.</Empty> : (
        <div className="table-wrap" style={{ marginBottom: 16 }}><table className="table">
          <thead><tr><th>Report</th><th>Cycle</th><th>Mode · information cutoff</th><th>Candidate pool</th><th>Latest version</th></tr></thead>
          <tbody>{reports.map((r) => {
            const w = state.get(r.id);
            const p = poolBy.get(r.id);
            return (
              <tr key={r.id}>
                <td><a className="title-cell" href={`/reports/${r.id}`}>{r.code}</a><div className="muted">{r.title}</div></td>
                <td>{r.cycle_label}</td>
                <td><Badge value={r.report_mode} /> <When at={r.information_cutoff} /></td>
                <td>{p ? `${p.n} eligible · ${p.inc} included` : <span className="muted">empty — refresh after approvals</span>}</td>
                <td>{w ? <><Badge tone="outline">v{w.version_no}</Badge> <Badge value={w.workflow_state} /></> : <span className="muted">no draft</span>}</td>
              </tr>);
          })}</tbody>
        </table></div>
      )}
      <Card title="New report cycle">
        {!editor ? <Locked>Creating reports needs REPORT_EDIT (analyst).</Locked> : (
          <form action={createReport} className="form">
            <div className="form-grid">
              <div className="field"><label htmlFor="code">Code</label><input id="code" name="code" placeholder="RPT-P7-REPLAY-01" required pattern="RPT-[A-Z0-9][A-Z0-9_\-]{1,60}" /></div>
              <div className="field"><label htmlFor="cycle_label">Cycle label</label><input id="cycle_label" name="cycle_label" placeholder="P7-REPLAY-01" required /></div>
              <div className="field"><label htmlFor="report_mode">Mode</label><select id="report_mode" name="report_mode"><option>LIVE</option><option>REPLAY</option></select></div>
              <div className="field"><label htmlFor="information_cutoff">Information cutoff (local time of this server)</label>
                <input id="information_cutoff" name="information_cutoff" type="datetime-local" required /></div>
            </div>
            <div className="field"><label htmlFor="title">Title</label><input id="title" name="title" required minLength={3} /></div>
            <div className="field"><label htmlFor="reason">Reason (audited)</label><input id="reason" name="reason" required minLength={5} /></div>
            <p className="muted" style={{ margin: 0, fontSize: 12.5 }}>REPLAY: only material with stated public availability ≤ cutoff is eligible. LIVE: retrieved ≤ cutoff.
              A pilot cycle bound to this report must use exactly the same mode and cutoff.</p>
            <div><Submit kind="primary">Create report and load eligible candidates</Submit></div>
          </form>
        )}
      </Card>
    </>
  );
}
