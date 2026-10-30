import { Badge, Chips, Empty, Locked, PageHeader, Short, When } from "@/components/ui";
import { can, requireSession } from "@/lib/auth";
import { JOB_LABELS, displayStatus } from "@/lib/jobs";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

interface Job { id: string; job_type: string; object_type: string; object_id: string; status: string; attempt_count: number; max_attempts: number;
  last_error: string | null; created_at: string; started_at: string | null; completed_at: string | null; next_attempt_at: string }

export default async function JobsPage({ searchParams }: { searchParams: Promise<{ status?: string; type?: string }> }) {
  const sp = await searchParams;
  const session = await requireSession();
  const crumbs = [{ href: "/", label: "Dashboard" }, { label: "Pipeline jobs" }];
  if (!can(session, "SYSTEM_READ")) return <><PageHeader title="Pipeline jobs" crumbs={crumbs} /><Locked>Job status needs SYSTEM_READ (analyst, admin).</Locked></>;
  const supabase = await createClient();
  let q = supabase.from("processing_jobs").select("*").order("created_at", { ascending: false }).limit(200);
  if (sp.status) q = q.eq("status", sp.status);
  if (sp.type) q = q.eq("job_type", sp.type);
  const { data } = await q;
  const jobs = (data ?? []) as Job[];
  const { data: reqs } = await supabase.from("workflow_job_requests").select("job_id,requested_by,reason,created_at")
    .in("job_id", jobs.length ? jobs.map((j) => j.id) : ["00000000-0000-0000-0000-000000000000"]);
  const humanReq = new Map(((reqs ?? []) as { job_id: string; reason: string; created_at: string }[]).map((r) => [r.job_id, r]));
  const chips = [{ key: "", label: "All", href: "/jobs" }, ...["PENDING", "RUNNING", "HUMAN_REVIEW", "SUCCESS", "FAILED"].map((s) => ({
    key: s, label: displayStatus(s).replaceAll("_", " ").toLowerCase(), href: `/jobs?status=${s}` }))];
  return (
    <>
      <PageHeader title="Pipeline jobs" crumbs={crumbs}
        lede="The worker queue (lease, back-off and max-attempt rules unchanged). Requests made by a human (CR7-03) are marked with their audited reason. NEEDS HUMAN REVIEW means the model step finished and a person decides next." />
      <Chips items={chips} current={sp.status ?? ""} />
      {jobs.length === 0 ? <Empty title="No jobs" /> : (
        <div className="table-wrap"><table className="table">
          <thead><tr><th>Step</th><th>Object</th><th>Status</th><th>Attempts</th><th>Requested</th><th>Finished</th><th>Detail</th></tr></thead>
          <tbody>{jobs.map((j) => {
            const h = humanReq.get(j.id);
            return (
              <tr key={j.id}>
                <td><b>{JOB_LABELS[j.job_type]?.module ?? ""}</b> {JOB_LABELS[j.job_type]?.label ?? j.job_type}</td>
                <td>{j.object_type} <Short id={j.object_id} /></td>
                <td><Badge value={displayStatus(j.status)} /></td>
                <td className="num">{j.attempt_count}/{j.max_attempts}</td>
                <td style={{ fontSize: 12.5 }}><When at={j.created_at} />{h ? <div><Badge tone="accent">human request</Badge> <span className="muted">{h.reason}</span></div>
                  : <div className="muted">worker / pipeline chain</div>}</td>
                <td style={{ fontSize: 12.5 }}><When at={j.completed_at} /></td>
                <td style={{ fontSize: 12.5, maxWidth: 360 }} className="wrap-anywhere">{j.status === "PENDING" && j.attempt_count > 0 && <div>retry after <When at={j.next_attempt_at} /></div>}
                  {j.last_error && <span style={{ color: j.status === "FAILED" ? "var(--danger)" : "var(--text-2)" }}>{j.last_error.slice(0, 300)}</span>}</td>
              </tr>);
          })}</tbody>
        </table></div>
      )}
    </>
  );
}
