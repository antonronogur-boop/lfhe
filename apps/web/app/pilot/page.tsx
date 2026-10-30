import { Submit } from "@/components/client";
import { Badge, Card, Empty, Flash, Locked, PageHeader, Stat, Tabs, When } from "@/components/ui";
import { can, requireSession } from "@/lib/auth";
import { DATA_BOUNDARIES, DISPOSITIONS, FINDING_CLASSES, PILOT_MODES, UX_AREAS, UX_SEVERITIES, currentDisposition } from "@/lib/pilot";
import { createClient } from "@/lib/supabase/server";

import { createCycle, disposeUxFinding, recordCostAssumption, recordProviderPrice, recordUxFinding } from "./actions";

export const dynamic = "force-dynamic";

interface CycleRow {
  id: string; code: string; pilot_mode: string; information_cutoff: string; status: string; terminal_state: string | null;
  report_id: string | null; analyst_user_id: string; started_at: string; closed_at: string | null; data_boundary: string;
}
interface PriceRow { id: string; provider: string; model: string; currency: string; input_cost_per_mtok: string; output_cost_per_mtok: string; effective_from: string; source: string }
interface CostRow { id: string; code: string; currency: string; loaded_hourly_cost: string; weekly_work_hours: string; working_weeks_per_year: string; basis: string }
interface Ux { id: string; finding_no: number; cycle_id: string | null; area: string; severity: string; finding_class: string; title: string; description: string;
  route: string | null; observed_at: string }

const TARGET = { total: 6, replay: 2, live: 2 };

export default async function PilotPage({ searchParams }: { searchParams: Promise<{ error?: string; ok?: string; tab?: string }> }) {
  const { error, ok, tab = "cycles" } = await searchParams;
  const session = await requireSession();
  if (!can(session, "PILOT_READ")) return <><PageHeader title="Pilot" /><Locked>Viewing the Phase 7 pilot needs PILOT_READ.</Locked></>;
  const manager = can(session, "PILOT_MANAGE");
  const participant = can(session, "PILOT_PARTICIPATE");
  const supabase = await createClient();
  const [{ data, error: loadError }, { data: costs }, { data: prices }, { data: uxData }, { data: disp }] = await Promise.all([
    supabase.from("pilot_cycles").select("*").order("started_at", { ascending: false }).limit(100),
    supabase.from("pilot_cost_assumptions").select("*").order("created_at", { ascending: false }),
    supabase.from("pilot_provider_prices").select("*").order("effective_from", { ascending: false }),
    supabase.from("pilot_ux_findings").select("*").order("finding_no", { ascending: false }),
    supabase.from("pilot_ux_finding_dispositions").select("*").order("seq"),
  ]);
  const cycles = (data ?? []) as CycleRow[];
  const done = cycles.filter((c) => c.status === "COMPLETED");
  const replay = done.filter((c) => c.pilot_mode === "REPLAY").length;
  const live = done.filter((c) => c.pilot_mode === "LIVE").length;
  const findings = (uxData ?? []) as Ux[];
  const history = (disp ?? []) as { finding_id: string; disposition: string; seq: number; note: string; decided_at: string }[];
  const openBlocking = findings.filter((f) => f.severity === "BLOCKING" && ["OPEN", "REOPENED", "BACKLOG"].includes(currentDisposition(history, f.id)));
  const code = (id: string | null) => cycles.find((c) => c.id === id)?.code;
  return (
    <>
      <PageHeader title="Pilot measurement" crumbs={[{ href: "/", label: "Dashboard" }, { label: "Pilot" }]}
        lede="Phase 7 controlled pilot. Pilot records are measurement only: they never change claims, events, assessments, reports, QA, approvals, security review or release. Timers use the database clock; nothing accepts a typed-in duration." />
      <Flash ok={ok} error={error} okText={ok?.replaceAll("-", " ")} />
      {loadError && <Flash error={`Could not load pilot cycles: ${loadError.message}`} />}
      <div className="grid cols-4" style={{ marginBottom: 16 }}>
        <Stat label="Complete cycles" value={`${done.length} / ${TARGET.total}`} hint="target six complete end-to-end cycles" />
        <Stat label="REPLAY" value={`${replay} / ${TARGET.replay}+`} tone={replay >= TARGET.replay ? "ok" : undefined} />
        <Stat label="LIVE / near-live" value={`${live} / ${TARGET.live}+`} tone={live >= TARGET.live ? "ok" : undefined} />
        <Stat label="Blocking UX findings" value={openBlocking.length} tone={openBlocking.length ? "alert" : "ok"} href="/pilot?tab=ux" />
      </div>
      <div className="progress" style={{ marginBottom: 16 }}><span style={{ width: `${Math.min(100, (done.length / TARGET.total) * 100)}%` }} /></div>
      <Tabs current={tab} items={[{ key: "cycles", label: "Cycles", href: "/pilot" }, { key: "ux", label: `UX findings (${findings.length})`, href: "/pilot?tab=ux" },
        { key: "economics", label: "Cost & price inputs", href: "/pilot?tab=economics" }]} />

      {tab === "cycles" && (
        <>
          {cycles.length === 0 ? <Empty title="No pilot cycle yet">Create the report first (mode + cutoff), then a cycle with exactly the same mode and cutoff.</Empty> : (
            <div className="table-wrap" style={{ marginBottom: 16 }}><table className="table">
              <thead><tr><th>Cycle</th><th>Mode · cutoff</th><th>Boundary</th><th>Status</th><th>Report</th><th>Started</th></tr></thead>
              <tbody>{cycles.map((c) => (
                <tr key={c.id}><td><a className="title-cell" href={`/pilot/${c.id}`}>{c.code}</a></td>
                  <td><Badge value={c.pilot_mode} /> <When at={c.information_cutoff} /></td><td>{c.data_boundary}</td>
                  <td><Badge value={c.status} />{c.terminal_state && <> <Badge value={c.terminal_state} /></>}</td>
                  <td>{c.report_id ? <a href={`/reports/${c.report_id}`}>bound report</a> : <span className="muted">not bound</span>}</td>
                  <td><When at={c.started_at} /></td></tr>))}</tbody>
            </table></div>
          )}
          <Card title="New pilot cycle">
            {!manager ? <Locked>Creating cycles needs PILOT_MANAGE (pilot lead).</Locked> : (
              <form action={createCycle} className="form">
                <div className="form-grid">
                  <div className="field"><label htmlFor="code">Code</label><input id="code" name="code" placeholder="P7C-REPLAY-01" required pattern="P7C-[A-Z0-9][A-Z0-9_\-]{1,40}" /></div>
                  <div className="field"><label htmlFor="pilot_mode">Mode</label><select id="pilot_mode" name="pilot_mode">{PILOT_MODES.map((m) => <option key={m}>{m}</option>)}</select></div>
                  <div className="field"><label htmlFor="cutoff">Information cutoff (must equal the report&apos;s)</label><input id="cutoff" name="information_cutoff" type="datetime-local" required /></div>
                  <div className="field"><label htmlFor="boundary">Data boundary</label><select id="boundary" name="data_boundary">{DATA_BOUNDARIES.map((m) => <option key={m}>{m}</option>)}</select></div>
                </div>
                <div className="field"><label htmlFor="scope">Input scope</label><input id="scope" name="input_scope" required minLength={10} placeholder="sources / window / corpus" /></div>
                <div className="form-grid">
                  <div className="field"><label htmlFor="analyst">Analyst user id</label><input id="analyst" name="analyst_user_id" required defaultValue={session.userId} /></div>
                  <div className="field"><label htmlFor="provider">Provider setup</label><input id="provider" name="provider_setup" required placeholder="anthropic / claude-sonnet-5-5 / provider_fixed_sampling" /></div>
                </div>
                <p className="muted" style={{ margin: 0, fontSize: 12.5 }}>The cycle clock starts now (started_at). Create it when the timed work begins — never just to test.</p>
                <div><Submit kind="primary">Create pilot cycle</Submit></div>
              </form>
            )}
          </Card>
        </>
      )}

      {tab === "ux" && (
        <>
          {findings.length === 0 ? <Empty title="No UX finding recorded" /> : findings.map((f) => {
            const d = currentDisposition(history, f.id);
            const trail = history.filter((h) => h.finding_id === f.id);
            const openNow = ["OPEN", "REOPENED", "BACKLOG"].includes(d);
            return (
              <Card key={f.id} tone={f.severity === "BLOCKING" && openNow ? "danger" : undefined}
                title={<span className="row">#{f.finding_no} {f.title}</span>}
                actions={<><Badge value={f.severity} /><Badge tone="outline">{f.area}</Badge><Badge tone="neutral">{f.finding_class}</Badge>
                  <Badge value={d === "RESOLVED" ? "SUCCESS" : d === "OPEN" ? "PENDING" : d}>{d}</Badge></>}>
                <p>{f.description}</p>
                <p className="muted" style={{ fontSize: 12.5 }}>observed <When at={f.observed_at} />{f.route && <> · {f.route}</>}{f.cycle_id && <> · cycle {code(f.cycle_id)}</>}</p>
                {trail.length > 0 && <ul className="timeline">{trail.map((h) => <li key={h.seq}><Badge tone="neutral">{h.disposition}</Badge> <When at={h.decided_at} /> — {h.note}</li>)}</ul>}
                {manager && (
                  <form action={disposeUxFinding} className="form-row" style={{ marginTop: 8 }}>
                    <input type="hidden" name="cycle_id" value={f.cycle_id ?? ""} /><input type="hidden" name="finding_id" value={f.id} />
                    <div className="field"><label>Disposition (append-only)</label><select name="disposition">{DISPOSITIONS.map((x) => <option key={x}>{x}</option>)}</select></div>
                    <div className="field"><label>Note</label><input name="note" required minLength={5} /></div>
                    <Submit small>Record disposition</Submit>
                  </form>
                )}
              </Card>);
          })}
          <Card title="Record a UX finding">
            {!participant ? <Locked>Needs PILOT_PARTICIPATE.</Locked> : (
              <form action={recordUxFinding} className="form">
                <div className="form-grid">
                  <div className="field"><label>Cycle (optional)</label><select name="cycle_id" defaultValue=""><option value="">— not tied to a cycle —</option>
                    {cycles.filter((c) => c.status === "OPEN").map((c) => <option key={c.id} value={c.id}>{c.code}</option>)}</select></div>
                  <div className="field"><label>Area</label><select name="area">{UX_AREAS.map((x) => <option key={x}>{x}</option>)}</select></div>
                  <div className="field"><label>Severity</label><select name="severity">{UX_SEVERITIES.map((x) => <option key={x}>{x}</option>)}</select></div>
                  <div className="field"><label>Class</label><select name="finding_class">{FINDING_CLASSES.map((x) => <option key={x}>{x}</option>)}</select></div>
                </div>
                <div className="field"><label>Title</label><input name="title" required minLength={5} maxLength={200} /></div>
                <div className="field"><label>What happened</label><textarea name="description" required minLength={10} rows={3} /></div>
                <div className="field"><label>Route (optional)</label><input name="route" placeholder="/events/[id]" /></div>
                <div><Submit kind="primary">Record UX finding</Submit></div>
                <p className="muted" style={{ margin: 0, fontSize: 12 }}>Only BLOCKING findings stop the affected pilot path. Findings are append-only; a resolution is a new disposition.</p>
              </form>
            )}
          </Card>
        </>
      )}

      {tab === "economics" && (
        <div className="grid cols-2">
          <Card title="Cost assumptions (explicit analysis inputs)">
            <p className="muted">Capacity value = hours released × loaded hourly cost — never a cash saving; cash effects need documented evidence.</p>
            <ul className="timeline">{((costs ?? []) as CostRow[]).map((c) => (
              <li key={c.id}><b>{c.code}</b>: {c.loaded_hourly_cost} {c.currency}/h · {c.weekly_work_hours} h/week · {c.working_weeks_per_year} weeks/year — {c.basis}</li>))}
              {(costs ?? []).length === 0 && <li className="muted">None recorded — economic values cannot be computed.</li>}</ul>
            {manager && (
              <details className="panel"><summary>Record a cost assumption (immutable)</summary><div className="panel-body">
                <form action={recordCostAssumption} className="form">
                  <div className="form-grid">
                    <div className="field"><label>Code</label><input name="code" placeholder="COST-2026-A" required /></div>
                    <div className="field"><label>Currency</label><input name="currency" placeholder="EUR" required /></div>
                    <div className="field"><label>Loaded hourly cost</label><input name="loaded_hourly_cost" required /></div>
                    <div className="field"><label>Weekly work hours</label><input name="weekly_work_hours" required /></div>
                    <div className="field"><label>Working weeks per year</label><input name="working_weeks_per_year" required /></div>
                  </div>
                  <div className="field"><label>Basis / source</label><input name="basis" required minLength={10} /></div>
                  <div><Submit>Record</Submit></div>
                </form></div></details>
            )}
          </Card>
          <Card title="Provider prices (a run without a price has unknown cost)">
            <ul className="timeline">{((prices ?? []) as PriceRow[]).map((p) => (
              <li key={p.id}><b>{p.provider} / {p.model}</b>: {p.input_cost_per_mtok} in · {p.output_cost_per_mtok} out {p.currency} per million tokens from <When at={p.effective_from} /> — {p.source}</li>))}
              {(prices ?? []).length === 0 && <li className="muted">None recorded — model cost is unknown.</li>}</ul>
            {manager && (
              <details className="panel"><summary>Record a provider price (immutable)</summary><div className="panel-body">
                <form action={recordProviderPrice} className="form">
                  <div className="form-grid">
                    <div className="field"><label>Provider</label><select name="provider"><option>anthropic</option></select></div>
                    <div className="field"><label>Model identifier</label><input name="model" required /></div>
                    <div className="field"><label>Currency</label><input name="currency" placeholder="USD" required /></div>
                    <div className="field"><label>Input cost / M tokens</label><input name="input_cost_per_mtok" required /></div>
                    <div className="field"><label>Output cost / M tokens</label><input name="output_cost_per_mtok" required /></div>
                    <div className="field"><label>Effective from</label><input name="effective_from" type="datetime-local" required /></div>
                  </div>
                  <div className="field"><label>Source (price list / invoice)</label><input name="source" required minLength={5} /></div>
                  <div><Submit>Record</Submit></div>
                </form></div></details>
            )}
          </Card>
        </div>
      )}
    </>
  );
}
