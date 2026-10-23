import { can, requireSession } from "@/lib/auth";
import {
  BASELINE_BASES, COMPARATOR_METHODS, DISPOSITIONS, FINDING_CLASSES, STAGES, type TimingRow, UX_AREAS, UX_SEVERITIES, currentDisposition,
  formatDuration, missingLabel, timingByStage,
} from "@/lib/pilot";
import { createClient } from "@/lib/supabase/server";

import {
  bindChainRuns, bindReport, closeCycle, disposeUxFinding, recordComparator, recordUxFinding, recordWorkload, startTimer, stopTimer,
} from "../actions";

export const dynamic = "force-dynamic";

const box = { border: "1px solid #ddd", borderRadius: 4, padding: 10, marginBottom: 12 } as const;
const muted = { color: "#666" } as const;

interface Cycle {
  id: string; code: string; pilot_mode: string; information_cutoff: string; data_boundary: string; input_scope: string;
  analyst_user_id: string; provider_setup: string; report_id: string | null; status: string; terminal_state: string | null;
  stop_reason: string | null; started_at: string; closed_at: string | null;
}
interface Segment { id: string; user_id: string; stage: string; started_at: string; ended_at: string | null }
interface Ux { id: string; finding_no: number; area: string; severity: string; finding_class: string; title: string; description: string; route: string | null; observed_at: string }
interface RunMetric {
  model_run_id: string; module_code: string; provider: string; model: string; status: string; error_code: string | null;
  latency_ms: number | null; input_tokens: number | null; output_tokens: number | null; is_repair_run: boolean;
  model_cost: string | null; cost_currency: string | null; prompt_semver: string;
}

export default async function PilotCycle({
  params, searchParams,
}: { params: Promise<{ id: string }>; searchParams: Promise<{ error?: string; ok?: string }> }) {
  const { id } = await params;
  const { error, ok } = await searchParams;
  const session = await requireSession();
  if (!can(session, "PILOT_READ")) return <p>You do not have permission to view the Phase 7 pilot.</p>;
  const participant = can(session, "PILOT_PARTICIPATE");
  const manager = can(session, "PILOT_MANAGE");
  const supabase = await createClient();
  const { data: cycleData } = await supabase.from("pilot_cycles").select("*").eq("id", id).single();
  if (!cycleData) return <p>Unknown pilot cycle.</p>;
  const c = cycleData as Cycle;
  const open = c.status === "OPEN";
  const [timing, segs, missing, ux, disp, comparator, workload, runs, reports] = await Promise.all([
    supabase.from("pilot_cycle_timing").select("*").eq("cycle_id", id),
    supabase.from("pilot_timing_segments").select("*").eq("cycle_id", id).order("started_at", { ascending: false }).limit(20),
    supabase.rpc("pilot_cycle_missing_metrics", { p_cycle: id }),
    supabase.from("pilot_ux_findings").select("*").eq("cycle_id", id).order("finding_no"),
    supabase.from("pilot_ux_finding_dispositions").select("*"),
    supabase.from("pilot_comparators").select("*").eq("cycle_id", id).maybeSingle(),
    supabase.from("pilot_workload_ratings").select("*").eq("cycle_id", id),
    supabase.from("pilot_model_run_metrics").select("*").eq("cycle_id", id).order("started_at"),
    c.report_id ? Promise.resolve({ data: [] }) :
      supabase.from("reports").select("id,code,report_mode,information_cutoff").eq("report_mode", c.pilot_mode).eq("information_cutoff", c.information_cutoff),
  ]);
  const t = timingByStage((timing.data ?? []) as TimingRow[], c.analyst_user_id);
  const mine = ((segs.data ?? []) as Segment[]).find((s) => s.user_id === session.userId && !s.ended_at);
  const missingCodes = (missing.data ?? []) as string[];
  const findings = (ux.data ?? []) as Ux[];
  const history = (disp.data ?? []) as { finding_id: string; disposition: string; seq: number }[];
  const myWorkload = ((workload.data ?? []) as { user_id: string }[]).some((w) => w.user_id === session.userId);
  const runRows = (runs.data ?? []) as RunMetric[];
  return (
    <main>
      <p><a href="/pilot">← pilot cycles</a></p>
      <h1>{c.code} <span style={muted}>· {c.pilot_mode} · {c.status}{c.terminal_state ? ` (${c.terminal_state})` : ""}</span></h1>
      {ok && <p role="status" style={{ color: "#060" }}>Done: {ok}</p>}
      {error && <p role="alert" style={{ color: "#a00" }}>Error: {error}</p>}
      <section style={box}>
        <div>Information cutoff: <strong>{c.information_cutoff}</strong> · boundary {c.data_boundary}</div>
        <div>Input scope: {c.input_scope}</div>
        <div>Provider setup: {c.provider_setup}</div>
        <div>Analyst: <code>{c.analyst_user_id}</code> · started {c.started_at}{c.closed_at ? ` · closed ${c.closed_at}` : ""}</div>
        <div>Report: {c.report_id ? <a href={`/reports/${c.report_id}`}>open the bound report</a> : "not bound"}</div>
        {c.stop_reason && <div>Stop reason: {c.stop_reason}</div>}
      </section>

      <section style={box}>
        <h2>Measurement completeness</h2>
        {missingCodes.length === 0 ? <p style={{ color: "#060" }}>Nothing missing — the cycle can be closed as COMPLETED.</p> : (
          <ul>{missingCodes.map((m) => <li key={m}>{missingLabel(m)}</li>)}</ul>
        )}
        <p style={muted}>Missing measurements are never filled in; a cycle with gaps can only be STOPPED with a reason.</p>
      </section>

      <section style={box}>
        <h2>Analyst active time</h2>
        <p>Total (cycle analyst, closed segments): <strong>{formatDuration(t.total)}</strong>{t.open ? " · a timer is running" : ""}</p>
        <table><tbody>{t.stages.map(([stage, s]) => <tr key={stage}><td>{stage}</td><td>{formatDuration(s)}</td></tr>)}</tbody></table>
        {open && participant && (
          <div style={{ display: "flex", gap: 12, marginTop: 8 }}>
            <form action={startTimer}>
              <input type="hidden" name="cycle_id" value={id} />
              <select name="stage" defaultValue={mine?.stage ?? "REPORT_EDIT"}>{STAGES.map((s) => <option key={s}>{s}</option>)}</select>{" "}
              <button type="submit">{mine ? "Switch stage" : "Start timer"}</button>
            </form>
            {mine && (
              <form action={stopTimer}>
                <input type="hidden" name="cycle_id" value={id} />
                <button type="submit">Stop timer ({mine.stage}, since {mine.started_at})</button>
              </form>
            )}
          </div>
        )}
        <p style={muted}>Start the timer when you begin active work on this cycle and stop it when you pause; the database clock is used.</p>
      </section>

      <section style={box}>
        <h2>Comparator</h2>
        {comparator.data ? (
          <p>{(comparator.data as { method: string }).method} · baseline{" "}
            {(comparator.data as { baseline_analyst_seconds: number | null }).baseline_analyst_seconds
              ? formatDuration((comparator.data as { baseline_analyst_seconds: number }).baseline_analyst_seconds) : "—"} ·{" "}
            {(comparator.data as { baseline_basis: string | null }).baseline_basis ?? "no baseline"} · comparable scope:{" "}
            {(comparator.data as { comparable_scope: boolean }).comparable_scope ? "yes" : "no"} — {(comparator.data as { reference: string }).reference}</p>
        ) : <p>Not recorded. Without a comparator, no productivity claim is possible.</p>}
        {open && manager && !comparator.data && (
          <form action={recordComparator} style={{ display: "grid", gap: 4, maxWidth: 620 }}>
            <input type="hidden" name="cycle_id" value={id} />
            <label>Method <select name="method">{COMPARATOR_METHODS.map((m) => <option key={m}>{m}</option>)}</select></label>
            <label>Baseline analyst time (whole minutes) <input name="baseline_minutes" inputMode="numeric" /></label>
            <label>Baseline basis <select name="baseline_basis" defaultValue=""><option value="">—</option>{BASELINE_BASES.map((m) => <option key={m}>{m}</option>)}</select></label>
            <label>Comparable workload scope <select name="comparable_scope"><option>yes</option><option>no</option></select></label>
            <label>Reference (where the baseline comes from) <input name="reference" required minLength={5} /></label>
            <button type="submit">Record comparator (immutable)</button>
          </form>
        )}
      </section>

      {open && manager && !c.report_id && (
        <section style={box}>
          <h2>Bind report</h2>
          <p style={muted}>Only reports with the same mode and exactly the same information cutoff can be bound.</p>
          <form action={bindReport}>
            <input type="hidden" name="cycle_id" value={id} />
            <select name="report_id">{((reports.data ?? []) as { id: string; code: string }[]).map((r) => <option key={r.id} value={r.id}>{r.code}</option>)}</select>{" "}
            <button type="submit">Bind</button>
          </form>
        </section>
      )}

      <section style={box}>
        <h2>Model runs (exact provider metrics)</h2>
        {open && manager && c.report_id && (
          <form action={bindChainRuns}><input type="hidden" name="cycle_id" value={id} /><button type="submit">Bind the report chain&apos;s model runs</button></form>
        )}
        <table style={{ borderCollapse: "collapse", width: "100%", marginTop: 8 }}>
          <thead><tr><th align="left">Module</th><th align="left">Provider / model</th><th align="left">Prompt</th><th align="left">Status</th><th align="right">Latency</th><th align="right">Tokens in/out</th><th align="right">Cost</th></tr></thead>
          <tbody>
            {runRows.map((r) => (
              <tr key={r.model_run_id} style={{ borderTop: "1px solid #eee" }}>
                <td>{r.module_code}{r.is_repair_run ? " (repair)" : ""}</td><td>{r.provider} / {r.model}</td><td>{r.prompt_semver}</td>
                <td>{r.status}{r.error_code ? ` · ${r.error_code}` : ""}</td>
                <td align="right">{r.latency_ms ?? "—"} ms</td><td align="right">{r.input_tokens ?? "?"} / {r.output_tokens ?? "?"}</td>
                <td align="right">{r.model_cost ? `${r.model_cost} ${r.cost_currency}` : "unknown"}</td>
              </tr>
            ))}
            {runRows.length === 0 && <tr><td colSpan={7}>No model runs bound.</td></tr>}
          </tbody>
        </table>
      </section>

      <section style={box}>
        <h2>UX findings</h2>
        <ul>
          {findings.map((f) => {
            const d = currentDisposition(history, f.id);
            return (
              <li key={f.id} style={{ marginBottom: 6 }}>
                <strong>#{f.finding_no} {f.severity}</strong> · {f.area} · {f.finding_class} — {f.title} <span style={muted}>({d})</span>
                <div style={muted}>{f.description}{f.route ? ` · ${f.route}` : ""}</div>
                {manager && (
                  <form action={disposeUxFinding} style={{ display: "flex", gap: 4 }}>
                    <input type="hidden" name="cycle_id" value={id} /><input type="hidden" name="finding_id" value={f.id} />
                    <select name="disposition">{DISPOSITIONS.map((x) => <option key={x}>{x}</option>)}</select>
                    <input name="note" placeholder="note" required minLength={5} /><button type="submit">Record disposition</button>
                  </form>
                )}
              </li>
            );
          })}
          {findings.length === 0 && <li>None recorded.</li>}
        </ul>
        {participant && (
          <form action={recordUxFinding} style={{ display: "grid", gap: 4, maxWidth: 620 }}>
            <input type="hidden" name="cycle_id" value={id} />
            <label>Area <select name="area">{UX_AREAS.map((x) => <option key={x}>{x}</option>)}</select></label>
            <label>Severity <select name="severity">{UX_SEVERITIES.map((x) => <option key={x}>{x}</option>)}</select></label>
            <label>Class <select name="finding_class">{FINDING_CLASSES.map((x) => <option key={x}>{x}</option>)}</select></label>
            <label>Title <input name="title" required minLength={5} maxLength={200} /></label>
            <label>What happened <textarea name="description" required minLength={10} rows={3} /></label>
            <label>Route (optional) <input name="route" placeholder="/reports/[id]" /></label>
            <button type="submit">Record UX finding</button>
          </form>
        )}
        <p style={muted}>Only BLOCKING findings stop the affected pilot path; MINOR and ENHANCEMENT findings are not implemented in Phase 7.</p>
      </section>

      <section style={box}>
        <h2>Workload (raw NASA-TLX, 0–100)</h2>
        {myWorkload ? <p>Your rating is recorded.</p> : open && participant ? (
          <form action={recordWorkload} style={{ display: "grid", gap: 4, maxWidth: 420 }}>
            <input type="hidden" name="cycle_id" value={id} />
            {["mental", "physical", "temporal", "performance", "effort", "frustration"].map((d) => (
              <label key={d}>{d} <input name={d} type="number" min={0} max={100} required /></label>
            ))}
            <label>Note <input name="note" /></label>
            <button type="submit">Record workload</button>
          </form>
        ) : <p>Not recorded.</p>}
      </section>

      {open && manager && (
        <section style={box}>
          <h2>Close the cycle</h2>
          <form action={closeCycle} style={{ display: "grid", gap: 4, maxWidth: 620 }}>
            <input type="hidden" name="cycle_id" value={id} />
            <label>Outcome <select name="outcome"><option>COMPLETED</option><option>STOPPED</option></select></label>
            <label>Note / stop reason <input name="note" required minLength={10} /></label>
            <button type="submit">Close (irreversible)</button>
          </form>
          <p style={muted}>COMPLETED is refused while any measurement is missing. STOPPED keeps all evidence collected so far.</p>
        </section>
      )}
    </main>
  );
}
