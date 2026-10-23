import { can, requireSession } from "@/lib/auth";
import { DATA_BOUNDARIES, PILOT_MODES } from "@/lib/pilot";
import { createClient } from "@/lib/supabase/server";

import { createCycle, recordCostAssumption, recordProviderPrice } from "./actions";

export const dynamic = "force-dynamic";

interface CycleRow {
  id: string; code: string; pilot_mode: string; information_cutoff: string; status: string; terminal_state: string | null;
  report_id: string | null; analyst_user_id: string; started_at: string; closed_at: string | null; data_boundary: string;
}
interface PriceRow { id: string; provider: string; model: string; currency: string; input_cost_per_mtok: string; output_cost_per_mtok: string; effective_from: string; source: string }
interface CostRow { id: string; code: string; currency: string; loaded_hourly_cost: string; weekly_work_hours: string; working_weeks_per_year: string; basis: string }

export default async function PilotPage({ searchParams }: { searchParams: Promise<{ error?: string; ok?: string }> }) {
  const { error, ok } = await searchParams;
  const session = await requireSession();
  if (!can(session, "PILOT_READ")) return <p>You do not have permission to view the Phase 7 pilot.</p>;
  const manager = can(session, "PILOT_MANAGE");
  const supabase = await createClient();
  const [{ data, error: loadError }, { data: costs }, { data: prices }] = await Promise.all([
    supabase.from("pilot_cycles").select("*").order("started_at", { ascending: false }).limit(100),
    supabase.from("pilot_cost_assumptions").select("*").order("created_at", { ascending: false }),
    supabase.from("pilot_provider_prices").select("*").order("effective_from", { ascending: false }),
  ]);
  const cycles = (data ?? []) as CycleRow[];
  const done = cycles.filter((c) => c.status === "COMPLETED");
  return (
    <main>
      <h1>Phase 7 pilot — measurement workspace</h1>
      <p style={{ color: "#555" }}>
        Pilot records are measurement only: they never change claims, events, assessments, reports, QA, approvals, security review
        or release. Timers use the database clock; nothing here accepts a typed-in duration. Public OSINT, synthetic or authorised
        public replay material only.
      </p>
      {ok && <p role="status" style={{ color: "#060" }}>Done: {ok}</p>}
      {error && <p role="alert" style={{ color: "#a00" }}>Error: {error}</p>}
      {loadError && <p role="alert" style={{ color: "#a00" }}>Could not load pilot cycles: {loadError.message}</p>}
      <p>
        Completed cycles: <strong>{done.length}</strong> (REPLAY {done.filter((c) => c.pilot_mode === "REPLAY").length} · LIVE{" "}
        {done.filter((c) => c.pilot_mode === "LIVE").length}) — target 6, at least 2 REPLAY and 2 LIVE.
      </p>
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead><tr><th align="left">Cycle</th><th align="left">Mode / cutoff</th><th align="left">Boundary</th><th align="left">Status</th><th align="left">Report</th></tr></thead>
        <tbody>
          {cycles.map((c) => (
            <tr key={c.id} style={{ borderTop: "1px solid #ddd" }}>
              <td><a href={`/pilot/${c.id}`}>{c.code}</a></td>
              <td>{c.pilot_mode} · {c.information_cutoff}</td>
              <td>{c.data_boundary}</td>
              <td>{c.status}{c.terminal_state ? ` (${c.terminal_state})` : ""}</td>
              <td>{c.report_id ? <a href={`/reports/${c.report_id}`}>report</a> : "—"}</td>
            </tr>
          ))}
          {cycles.length === 0 && <tr><td colSpan={5}>No pilot cycles yet.</td></tr>}
        </tbody>
      </table>
      {manager && (
        <details style={{ marginTop: 16 }}>
          <summary>New pilot cycle</summary>
          <form action={createCycle} style={{ display: "grid", gap: 4, maxWidth: 620 }}>
            <label>Code <input name="code" placeholder="P7C-LIVE-01" required /></label>
            <label>Mode <select name="pilot_mode">{PILOT_MODES.map((m) => <option key={m}>{m}</option>)}</select></label>
            <label>Information cutoff (must equal the report&apos;s) <input name="information_cutoff" type="datetime-local" required /></label>
            <label>Data boundary <select name="data_boundary">{DATA_BOUNDARIES.map((m) => <option key={m}>{m}</option>)}</select></label>
            <label>Input scope <input name="input_scope" required minLength={10} placeholder="sources / window / corpus" /></label>
            <label>Analyst user id <input name="analyst_user_id" required defaultValue={session.userId} /></label>
            <label>Provider setup <input name="provider_setup" required placeholder="provider / model / configuration" /></label>
            <button type="submit">Create pilot cycle</button>
          </form>
        </details>
      )}
      <h2 style={{ marginTop: 24 }}>Cost assumptions (explicit analysis inputs)</h2>
      <p style={{ color: "#555" }}>Capacity value = hours released × loaded hourly cost. It is not a cash saving; cash effects need documented evidence.</p>
      <ul>
        {((costs ?? []) as CostRow[]).map((c) => (
          <li key={c.id}>{c.code}: {c.loaded_hourly_cost} {c.currency}/h · {c.weekly_work_hours} h/week · {c.working_weeks_per_year} weeks/year — {c.basis}</li>
        ))}
        {(costs ?? []).length === 0 && <li>None recorded — economic values cannot be computed.</li>}
      </ul>
      {manager && (
        <details>
          <summary>Record a cost assumption</summary>
          <form action={recordCostAssumption} style={{ display: "grid", gap: 4, maxWidth: 620 }}>
            <label>Code <input name="code" placeholder="COST-2026-A" required /></label>
            <label>Currency <input name="currency" placeholder="EUR" required /></label>
            <label>Loaded hourly cost <input name="loaded_hourly_cost" required /></label>
            <label>Weekly work hours <input name="weekly_work_hours" required /></label>
            <label>Working weeks per year <input name="working_weeks_per_year" required /></label>
            <label>Basis / source <input name="basis" required minLength={10} /></label>
            <button type="submit">Record (immutable)</button>
          </form>
        </details>
      )}
      <h2 style={{ marginTop: 24 }}>Provider prices (explicit; a run without a price has unknown cost)</h2>
      <ul>
        {((prices ?? []) as PriceRow[]).map((p) => (
          <li key={p.id}>{p.provider} / {p.model}: {p.input_cost_per_mtok} in · {p.output_cost_per_mtok} out {p.currency} per million tokens from {p.effective_from} — {p.source}</li>
        ))}
        {(prices ?? []).length === 0 && <li>None recorded — model cost is unknown.</li>}
      </ul>
      {manager && (
        <details>
          <summary>Record a provider price</summary>
          <form action={recordProviderPrice} style={{ display: "grid", gap: 4, maxWidth: 620 }}>
            <label>Provider <select name="provider"><option>anthropic</option></select></label>
            <label>Model identifier <input name="model" required /></label>
            <label>Currency <input name="currency" placeholder="USD" required /></label>
            <label>Input cost per million tokens <input name="input_cost_per_mtok" required /></label>
            <label>Output cost per million tokens <input name="output_cost_per_mtok" required /></label>
            <label>Effective from <input name="effective_from" type="datetime-local" required /></label>
            <label>Source (price list / invoice) <input name="source" required minLength={5} /></label>
            <button type="submit">Record (immutable)</button>
          </form>
        </details>
      )}
    </main>
  );
}
