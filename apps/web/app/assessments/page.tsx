import { Badge, Empty, Locked, PageHeader, Tabs, When } from "@/components/ui";
import { can, requireSession } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

const VIEWS: Record<string, { label: string; states: string[] | null }> = {
  review: { label: "Awaiting human review", states: ["IN_REVIEW", "ESCALATED"] },
  pipeline: { label: "Drafting / challenge", states: ["DRAFT", "CHALLENGED"] },
  approved: { label: "Approved", states: ["APPROVED"] },
  all: { label: "All versions", states: null },
};

export default async function AssessmentsPage({ searchParams }: { searchParams: Promise<{ view?: string }> }) {
  const { view = "review" } = await searchParams;
  const session = await requireSession();
  if (!can(session, "CLAIM_READ")) return <><PageHeader title="Assessments" /><Locked>Your role does not include CLAIM_READ.</Locked></>;
  const supabase = await createClient();
  const tabs = [...Object.entries(VIEWS).map(([k, v]) => ({ key: k, label: v.label, href: `/assessments?view=${k}` })),
    { key: "queue", label: "Events awaiting assessment", href: "/assessments?view=queue" }];
  const header = <PageHeader title="Assessments" crumbs={[{ href: "/", label: "Dashboard" }, { label: "Assessments" }]}
    lede="Statement-centric M07 assessments, challenged by M08, decided by a human. FACT, ASSUMPTION and ASSESSMENT stay separate; likelihood (how probable) and analytic confidence (how well-founded) are different fields — the final confidence is set only by a human approval." />;
  if (view === "queue") return <>{header}<Tabs items={tabs} current={view} /><Queue /></>;
  const none = ["00000000-0000-0000-0000-000000000000"];
  let q = supabase.from("assessment_version_states").select("*").order("assessment_version_id").limit(300);
  if (VIEWS[view]?.states) q = q.in("state", VIEWS[view].states!);
  const { data } = await q;
  const states = (data ?? []) as { assessment_version_id: string; version_no: number; origin: string; event_version_id: string;
    ai_recommended_confidence: string | null; state: string; final_analytic_confidence: string | null; approved_at: string | null }[];
  const ids = states.map((s) => s.assessment_version_id);
  const [{ data: av }, { data: st }, { data: ch }] = await Promise.all([
    supabase.from("assessment_versions").select("id,report_mode,information_cutoff,created_at,event_version_id").in("id", ids.length ? ids : none),
    supabase.from("assessment_statements").select("assessment_version_id,epistemic_category").in("assessment_version_id", ids.length ? ids : none),
    supabase.from("challenge_runs").select("id,assessment_version_id,challenge_result").in("assessment_version_id", ids.length ? ids : none),
  ]);
  const meta = new Map(((av ?? []) as { id: string; report_mode: string; information_cutoff: string; created_at: string; event_version_id: string }[])
    .map((a) => [a.id, a]));
  const evIds = [...new Set(states.map((s) => s.event_version_id))];
  const { data: evs } = await supabase.from("event_versions").select("id,event_id,title,version_no").in("id", evIds.length ? evIds : none);
  const ev = new Map(((evs ?? []) as { id: string; event_id: string; title: string; version_no: number }[]).map((e) => [e.id, e]));
  const cat = new Map<string, Record<string, number>>();
  for (const s of (st ?? []) as { assessment_version_id: string; epistemic_category: string }[]) {
    const x = cat.get(s.assessment_version_id) ?? {};
    x[s.epistemic_category] = (x[s.epistemic_category] ?? 0) + 1;
    cat.set(s.assessment_version_id, x);
  }
  const challenge = new Map(((ch ?? []) as { assessment_version_id: string; challenge_result: string }[]).map((c) => [c.assessment_version_id, c.challenge_result]));
  states.sort((a, b) => (meta.get(b.assessment_version_id)?.created_at ?? "").localeCompare(meta.get(a.assessment_version_id)?.created_at ?? ""));
  return (
    <>
      {header}
      <Tabs items={tabs} current={view} />
      {states.length === 0 ? <Empty title="Nothing here">{view === "review" ? "No assessment is waiting for a human decision." : "No assessment versions."}</Empty> : (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Event</th><th>Version</th><th>Context</th><th>Statements</th><th>M08</th><th>AI rec. confidence</th><th>State</th><th>Final confidence</th></tr></thead>
            <tbody>{states.map((s) => {
              const m = meta.get(s.assessment_version_id);
              const e = ev.get(s.event_version_id);
              const c = cat.get(s.assessment_version_id) ?? {};
              return (
                <tr key={s.assessment_version_id}>
                  <td style={{ maxWidth: 340 }}><a className="title-cell" href={`/assessments/${s.assessment_version_id}`}>{e?.title ?? "event"}</a>
                    <div className="muted" style={{ fontSize: 12 }}>event v{e?.version_no} · <When at={m?.created_at} /></div></td>
                  <td>v{s.version_no} · {s.origin}</td>
                  <td><Badge value={m?.report_mode} /><div className="muted" style={{ fontSize: 12 }}><When at={m?.information_cutoff} /></div></td>
                  <td>{(["FACT", "ASSUMPTION", "ASSESSMENT"] as const).map((k) => c[k] ? <span key={k} className={`badge epi-${k}`} style={{ marginRight: 4 }}>{k} {c[k]}</span> : null)}</td>
                  <td>{challenge.get(s.assessment_version_id) ? <Badge tone="violet">{challenge.get(s.assessment_version_id)!.replaceAll("_", " ")}</Badge> : <span className="muted">pending</span>}</td>
                  <td>{s.ai_recommended_confidence ? <Badge tone="outline">{s.ai_recommended_confidence}</Badge> : "—"}</td>
                  <td><Badge value={s.state} /></td>
                  <td>{s.final_analytic_confidence ? <Badge value={s.final_analytic_confidence} /> : <span className="muted">not set</span>}</td>
                </tr>);
            })}</tbody>
          </table>
        </div>
      )}
    </>
  );
}

async function Queue() {
  const supabase = await createClient();
  const { data } = await supabase.from("event_relevance_queue").select("*").eq("is_current", true);
  const rows = ((data ?? []) as { event_id: string; head_version_id: string; state: string; priority_score: number | null;
    automatic_assessment_recommended: boolean | null; manually_promoted_or_requested: boolean; scored_event_version_id: string | null }[])
    .filter((r) => r.state !== "REJECTED" && (r.automatic_assessment_recommended || r.manually_promoted_or_requested));
  const none = ["00000000-0000-0000-0000-000000000000"];
  const { data: av } = await supabase.from("assessment_versions").select("event_version_id").in("event_version_id",
    rows.length ? rows.map((r) => r.head_version_id) : none);
  const assessed = new Set(((av ?? []) as { event_version_id: string }[]).map((a) => a.event_version_id));
  const waiting = rows.filter((r) => !assessed.has(r.head_version_id));
  const { data: evs } = await supabase.from("event_versions").select("id,title").in("id", waiting.length ? waiting.map((w) => w.head_version_id) : none);
  const title = new Map(((evs ?? []) as { id: string; title: string }[]).map((e) => [e.id, e.title]));
  if (waiting.length === 0) return <Empty title="No event is waiting for an assessment">Events appear here when M06 recommends an assessment or a human records a manual request.</Empty>;
  return (
    <div className="table-wrap"><table className="table">
      <thead><tr><th>Event</th><th>State</th><th>M06 score</th><th>Why</th><th /></tr></thead>
      <tbody>{waiting.map((r) => (
        <tr key={r.event_id}><td><a className="title-cell" href={`/events/${r.event_id}`}>{title.get(r.head_version_id) ?? r.event_id}</a></td>
          <td><Badge value={r.state} /></td>
          <td>{r.priority_score != null ? Number(r.priority_score).toFixed(2) : "—"}</td>
          <td>{r.automatic_assessment_recommended ? <Badge tone="ok">M06 recommends</Badge> : null} {r.manually_promoted_or_requested ? <Badge tone="violet">manual request</Badge> : null}</td>
          <td><a className="btn small" href={`/events/${r.event_id}`}>Request M07 →</a></td></tr>))}</tbody>
    </table></div>
  );
}
