import { can, requireSession } from "@/lib/auth";
import {
  BASELINE_BASES, COMPARATOR_METHODS, DISPOSITIONS, FINDING_CLASSES, STAGES, type TimingRow, UX_AREAS, UX_SEVERITIES, currentDisposition,
  formatDuration, missingLabel, timingByStage,
} from "@/lib/pilot";
import { createClient } from "@/lib/supabase/server";
import { Badge, Card, Flash, KV, Locked, PageHeader, Stat, When } from "@/components/ui";
import { Submit } from "@/components/client";
import { capacityStatement, runSummary, timeByGroup, timeCost, type TimingAll } from "@/lib/pilot";

import {
  bindChainRuns, bindReport, closeCycle, disposeUxFinding, recordComparator, recordUxFinding, recordWorkload, startTimer, stopTimer,
} from "../actions";

export const dynamic = "force-dynamic";


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
  if (!can(session, "PILOT_READ")) return <Locked>Viewing the pilot needs PILOT_READ.</Locked>;
  const participant = can(session, "PILOT_PARTICIPATE");
  const manager = can(session, "PILOT_MANAGE");
  const supabase = await createClient();
  const { data: cycleData } = await supabase.from("pilot_cycles").select("*").eq("id", id).single();
  if (!cycleData) return <PageHeader title="Unknown pilot cycle" crumbs={[{ href: "/pilot", label: "Pilot" }, { label: id }]} />;
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
  const groups = timeByGroup((timing.data ?? []) as TimingAll[]);
  const allSeconds = Object.values(groups).reduce((a, b) => a + b, 0);
  const [{ data: costRows }, wfRes] = await Promise.all([
    supabase.from("pilot_cost_assumptions").select("code,currency,loaded_hourly_cost").order("created_at", { ascending: false }).limit(1),
    c.report_id ? supabase.from("report_version_workflow").select("report_version_id,version_no,workflow_state,qa_status,deterministic_qa_run_id,semantic_qa_run_id,manifest_hash,pdf_sha256,released_at")
      .eq("report_id", c.report_id).eq("is_latest", true).maybeSingle() : Promise.resolve({ data: null }),
  ]);
  const cost = ((costRows ?? []) as { code: string; currency: string; loaded_hourly_cost: string }[])[0] ?? null;
  const wf = wfRes.data as { version_no: number; workflow_state: string; qa_status: string | null; deterministic_qa_run_id: string | null;
    semantic_qa_run_id: string | null; manifest_hash: string | null; pdf_sha256: string | null; released_at: string | null } | null;
  const { data: qaRows } = wf?.deterministic_qa_run_id ? await supabase.from("qa_check_results").select("qa_run_id,status")
    .in("qa_run_id", [wf.deterministic_qa_run_id, wf.semantic_qa_run_id].filter(Boolean) as string[]).neq("status", "PASS") : { data: [] };
  const qaCount = (run: string | null | undefined) => ((qaRows ?? []) as { qa_run_id: string }[]).filter((r) => r.qa_run_id === run).length;
  const mine = ((segs.data ?? []) as Segment[]).find((s) => s.user_id === session.userId && !s.ended_at);
  const missingCodes = (missing.data ?? []) as string[];
  const findings = (ux.data ?? []) as Ux[];
  const history = (disp.data ?? []) as { finding_id: string; disposition: string; seq: number }[];
  const myWorkload = ((workload.data ?? []) as { user_id: string }[]).some((w) => w.user_id === session.userId);
  const runRows = (runs.data ?? []) as RunMetric[];
  const ai = runSummary(runRows);
  const comp = comparator.data as { method: string } | null;
  return (
    <main>
      <PageHeader title={c.code} crumbs={[{ href: "/", label: "Dashboard" }, { href: "/pilot", label: "Pilot" }, { label: c.code }]}
        badges={<><Badge value={c.pilot_mode} /><Badge value={c.status} />{c.terminal_state && <Badge value={c.terminal_state} />}
          {open && (missingCodes.length === 0 ? <Badge tone="ok">ready to complete</Badge> : <Badge tone="warn">{missingCodes.length} measurement gap(s)</Badge>)}</>}
        lede={<>Measurement only — pilot records never change analytical, QA, approval, security or release state. Cutoff <When at={c.information_cutoff} />.</>} />
      <Flash ok={ok} error={error} />
      <div className="grid cols-4" style={{ marginBottom: 16 }}>
        <Stat label="Analyst time" value={formatDuration(groups.analyst)} hint={`cycle analyst: ${formatDuration(t.total)}${t.open ? " · timer running" : ""}`} />
        <Stat label="Reviewer time" value={formatDuration(groups.reviewer)} hint="warnings + content approval" />
        <Stat label="Security time" value={formatDuration(groups.security)} />
        <Stat label="Release time" value={formatDuration(groups.release)} hint="release + provenance inspection" />
        <Stat label="AI executions" value={ai.runs} hint={`${ai.failed} not succeeded · ${ai.repairs} repair(s)`} />
        <Stat label="Tokens in / out" value={`${ai.tokensIn.toLocaleString("en")} / ${ai.tokensOut.toLocaleString("en")}`} />
        <Stat label="Model cost" value={ai.cost ? `${ai.cost.value.toFixed(4)} ${ai.cost.currency}` : "unknown"}
          hint={ai.unpriced ? `${ai.unpriced} run(s) without a matching price` : "explicit provider price"} />
        <Stat label="QA (D / S findings)" value={wf?.qa_status ? `${qaCount(wf.deterministic_qa_run_id)} / ${qaCount(wf.semantic_qa_run_id)}` : "—"}
          hint={wf?.qa_status ? `latest version v${wf.version_no}: ${wf.qa_status.replaceAll("_", " ")}` : "no QA yet"} />
      </div>
      <div className="grid cols-2">
        <Card title="Cycle facts">
          <KV rows={[
            ["Information cutoff", <When key="c" at={c.information_cutoff} />], ["Data boundary", c.data_boundary], ["Input scope", c.input_scope],
            ["Provider setup", c.provider_setup], ["Models used", ai.models.join(", ") || "—"],
            ["Analyst", <code key="a">{c.analyst_user_id}</code>], ["Started", <When key="s" at={c.started_at} />], ["Closed", <When key="cl" at={c.closed_at} />],
            ["Report", c.report_id ? <a key="r" href={`/reports/${c.report_id}`}>open the bound report</a> : "not bound"],
            ["Workflow state", wf ? <Badge key="w" value={wf.workflow_state} /> : "—"],
            ["Provenance", wf?.manifest_hash ? <span key="m">manifest <code>{wf.manifest_hash.slice(0, 16)}…</code> · PDF <code>{wf.pdf_sha256?.slice(0, 16)}…</code></span> : "not released"],
            ...(c.stop_reason ? [["Stop reason", c.stop_reason] as [string, string]] : []),
          ]} />
        </Card>
        <Card title="Economics (explicit inputs only)" tone={comp && comp.method !== "NONE" ? undefined : "warn"}>
          <p style={{ fontWeight: 600 }}>{capacityStatement(comp?.method)}</p>
          <KV rows={[
            ["Cost assumption", cost ? `${cost.code} · ${cost.loaded_hourly_cost} ${cost.currency}/h` : "none recorded"],
            ["Recorded human time", formatDuration(allSeconds)],
            ["Human time at loaded cost", cost ? `${timeCost(allSeconds, Number(cost.loaded_hourly_cost))?.toLocaleString("en")} ${cost.currency} (time cost — not a saving)` : "—"],
            ["Model cost", ai.cost ? `${ai.cost.value.toFixed(4)} ${ai.cost.currency}` : "unknown (never assumed zero)"],
          ]} />
          <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>Capacity value is never shown as a cash saving; cash effects need documented evidence.</p>
        </Card>
      </div>

      <section className="card">
        <h2>Measurement completeness</h2>
        {missingCodes.length === 0 ? <p style={{ color: "#060" }}>Nothing missing — the cycle can be closed as COMPLETED.</p> : (
          <ul>{missingCodes.map((m) => <li key={m}>{missingLabel(m)}</li>)}</ul>
        )}
        <p className="muted">Missing measurements are never filled in; a cycle with gaps can only be STOPPED with a reason.</p>
      </section>

      <section className="card">
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
        <p className="muted">Start the timer when you begin active work on this cycle and stop it when you pause; the database clock is used.</p>
      </section>

      <section className="card">
        <h2>Comparator</h2>
        {comparator.data ? (
          <p>{(comparator.data as { method: string }).method} · baseline{" "}
            {(comparator.data as { baseline_analyst_seconds: number | null }).baseline_analyst_seconds
              ? formatDuration((comparator.data as { baseline_analyst_seconds: number }).baseline_analyst_seconds) : "—"} ·{" "}
            {(comparator.data as { baseline_basis: string | null }).baseline_basis ?? "no baseline"} · comparable scope:{" "}
            {(comparator.data as { comparable_scope: boolean }).comparable_scope ? "yes" : "no"} — {(comparator.data as { reference: string }).reference}</p>
        ) : <p>Not recorded. Without a comparator, no productivity claim is possible.</p>}
        {open && manager && !comparator.data && (
          <form action={recordComparator} className="form" style={{ maxWidth: 620 }}>
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
        <section className="card">
          <h2>Bind report</h2>
          <p className="muted">Only reports with the same mode and exactly the same information cutoff can be bound.</p>
          <form action={bindReport}>
            <input type="hidden" name="cycle_id" value={id} />
            <select name="report_id">{((reports.data ?? []) as { id: string; code: string }[]).map((r) => <option key={r.id} value={r.id}>{r.code}</option>)}</select>{" "}
            <button type="submit">Bind</button>
          </form>
        </section>
      )}

      <section className="card">
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

      <section className="card">
        <h2>UX findings</h2>
        <ul>
          {findings.map((f) => {
            const d = currentDisposition(history, f.id);
            return (
              <li key={f.id} style={{ marginBottom: 6 }}>
                <strong>#{f.finding_no} {f.severity}</strong> · {f.area} · {f.finding_class} — {f.title} <span className="muted">({d})</span>
                <div className="muted">{f.description}{f.route ? ` · ${f.route}` : ""}</div>
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
          <form action={recordUxFinding} className="form" style={{ maxWidth: 620 }}>
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
        <p className="muted">Only BLOCKING findings stop the affected pilot path; MINOR and ENHANCEMENT findings are not implemented in Phase 7.</p>
      </section>

      <section className="card">
        <h2>Workload (raw NASA-TLX, 0–100)</h2>
        {myWorkload ? <p>Your rating is recorded.</p> : open && participant ? (
          <form action={recordWorkload} className="form" style={{ maxWidth: 420 }}>
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
        <section className="card">
          <h2>Close the cycle</h2>
          <form action={closeCycle} className="form" style={{ maxWidth: 620 }}>
            <input type="hidden" name="cycle_id" value={id} />
            <label>Outcome <select name="outcome"><option>COMPLETED</option><option>STOPPED</option></select></label>
            <label>Note / stop reason <input name="note" required minLength={10} /></label>
            <button type="submit">Close (irreversible)</button>
          </form>
          <p className="muted">COMPLETED is refused while any measurement is missing. STOPPED keeps all evidence collected so far.</p>
        </section>
      )}
    </main>
  );
}
