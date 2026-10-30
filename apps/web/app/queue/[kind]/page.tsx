import { Badge, Empty, Locked, PageHeader, When } from "@/components/ui";
import { can, requireSession } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

/* Decision queues for the Phase 6 human gates. They only list the latest report versions in the matching workflow
   state (report_version_workflow); every decision is taken in the report workspace through HUMAN_ONLY functions. */
const QUEUES: Record<string, { title: string; lede: string; states: string[]; view: string; perm: string[] }> = {
  review: { title: "QA and content approval", view: "qa", perm: ["QA_WARNING_ACKNOWLEDGE", "REPORT_CONTENT_APPROVE"],
    lede: "Reviewer queue: acknowledge QA warnings with a rationale, then approve, return or reject the exact version's content.",
    states: ["QA_PASSED_WITH_WARNINGS", "WARNING_ACKNOWLEDGED", "QA_PASSED"] },
  security: { title: "Security review", view: "release", perm: ["SECURITY_REVIEW"],
    lede: "Security reviewer queue: handling / releasability review of content-approved versions (OSINT-only boundary).",
    states: ["SECURITY_REVIEW_PENDING"] },
  release: { title: "Release decisions", view: "release", perm: ["RELEASE_DECIDE"],
    lede: "Release authority queue: security-approved versions. Release re-evaluates every condition; RETURN and REJECT never modify the report.",
    states: ["SECURITY_APPROVED"] },
};

export default async function Queue({ params }: { params: Promise<{ kind: string }> }) {
  const { kind } = await params;
  const cfg = QUEUES[kind];
  const session = await requireSession();
  if (!cfg) return <PageHeader title="Unknown queue" />;
  const crumbs = [{ href: "/", label: "Dashboard" }, { label: cfg.title }];
  if (!cfg.perm.some((p) => session.permissions.has(p))) {
    return <><PageHeader title={cfg.title} crumbs={crumbs} /><Locked>This queue belongs to {cfg.perm.join(" / ")}; your role cannot take these decisions.</Locked></>;
  }
  if (!can(session, "CLAIM_READ")) return <Locked>Needs CLAIM_READ.</Locked>;
  const supabase = await createClient();
  const { data } = await supabase.from("report_version_workflow").select("*").eq("is_latest", true).in("workflow_state", cfg.states);
  const rows = (data ?? []) as { report_version_id: string; report_id: string; version_no: number; workflow_state: string; qa_status: string | null;
    warnings_total: number | null; warnings_acknowledged: number }[];
  const { data: reps } = await supabase.from("reports").select("id,code,title,report_mode,information_cutoff")
    .in("id", rows.length ? rows.map((r) => r.report_id) : ["00000000-0000-0000-0000-000000000000"]);
  const rep = new Map(((reps ?? []) as { id: string; code: string; title: string; report_mode: string; information_cutoff: string }[]).map((r) => [r.id, r]));
  return (
    <>
      <PageHeader title={cfg.title} crumbs={crumbs} lede={cfg.lede} />
      {rows.length === 0 ? <Empty title="Nothing waiting for you" /> : (
        <div className="table-wrap"><table className="table">
          <thead><tr><th>Report</th><th>Version</th><th>Mode · cutoff</th><th>QA</th><th>Workflow state</th><th /></tr></thead>
          <tbody>{rows.map((r) => {
            const x = rep.get(r.report_id);
            return (
              <tr key={r.report_version_id}>
                <td><span className="title-cell">{x?.code}</span><div className="muted">{x?.title}</div></td>
                <td>v{r.version_no}</td>
                <td><Badge value={x?.report_mode} /> <span className="muted" style={{ fontSize: 12 }}><When at={x?.information_cutoff} /></span></td>
                <td><Badge value={r.qa_status} />{(r.warnings_total ?? 0) > 0 && <div className="muted" style={{ fontSize: 12 }}>{r.warnings_acknowledged}/{r.warnings_total} warnings acknowledged</div>}</td>
                <td><Badge value={r.workflow_state} /></td>
                <td><a className="btn small primary" href={`/reports/${r.report_id}?view=${cfg.view}&version=${r.report_version_id}`}>Open</a></td>
              </tr>);
          })}</tbody>
        </table></div>
      )}
    </>
  );
}
