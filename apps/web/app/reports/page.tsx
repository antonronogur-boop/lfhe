import { can, requireSession } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";

import { createReport } from "./actions";

export const dynamic = "force-dynamic";

interface ReportRow { id: string; code: string; title: string; cycle_label: string; report_mode: string; information_cutoff: string; created_at: string }

export default async function ReportsPage({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  const { error } = await searchParams;
  const session = await requireSession();
  if (!can(session, "CLAIM_READ")) return <p>You do not have permission to view reports.</p>;
  const editor = can(session, "REPORT_EDIT");
  const supabase = await createClient();
  const { data, error: loadError } = await supabase.from("reports").select("*").order("created_at", { ascending: false }).limit(50);
  const reports = (data ?? []) as ReportRow[];
  return (
    <main>
      <h1>Reports — analyst workspace</h1>
      <p style={{ color: "#555" }}>
        Draft reports are built only from approved Phase 4 material that you select. M09 edits wording; you decide inclusion,
        section placement and every substantive removal. Drafts are previews — not QA-approved, not security-reviewed, not released.
      </p>
      {error && <p role="alert" style={{ color: "#a00" }}>Error: {error}</p>}
      {loadError && <p role="alert" style={{ color: "#a00" }}>Could not load reports: {loadError.message}</p>}
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead><tr><th align="left">Code</th><th align="left">Title</th><th align="left">Cycle</th><th align="left">Mode / cutoff</th></tr></thead>
        <tbody>
          {reports.map((r) => (
            <tr key={r.id} style={{ borderTop: "1px solid #ddd" }}>
              <td><a href={`/reports/${r.id}`}>{r.code}</a></td><td>{r.title}</td><td>{r.cycle_label}</td>
              <td>{r.report_mode} · {r.information_cutoff}</td>
            </tr>
          ))}
          {reports.length === 0 && <tr><td colSpan={4}>No reports yet.</td></tr>}
        </tbody>
      </table>
      {editor && (
        <details style={{ marginTop: 16 }}>
          <summary>New report cycle</summary>
          <form action={createReport} style={{ display: "grid", gap: 4, maxWidth: 560 }}>
            <label>Code <input name="code" placeholder="RPT-2026-W43" required /></label>
            <label>Title <input name="title" required minLength={3} /></label>
            <label>Cycle label <input name="cycle_label" placeholder="2026-W43" required /></label>
            <label>Mode <select name="report_mode"><option>LIVE</option><option>REPLAY</option></select></label>
            <label>Information cutoff <input name="information_cutoff" type="datetime-local" required /></label>
            <label>Reason <input name="reason" required minLength={5} /></label>
            <button type="submit">Create report and load eligible candidates</button>
          </form>
        </details>
      )}
    </main>
  );
}
