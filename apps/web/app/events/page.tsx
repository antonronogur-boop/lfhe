import { Badge, Chips, Empty, Flash, Locked, PageHeader, When } from "@/components/ui";
import { can, requireSession } from "@/lib/auth";
import { EVENT_STATES } from "@/lib/events";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

interface Head {
  event_id: string; origin: string; head_version_id: string; head_version_no: number; head_content_hash: string; title: string;
  event_type: string; state: string; structural_status: string | null; successor_event_id: string | null;
  head_review_decision: string | null; head_pending_review: boolean; is_current: boolean;
}
interface Rel { event_id: string; priority_score: number | null; automatic_assessment_recommended: boolean | null;
  hu_nato_relevance_established: boolean | null; manually_promoted_or_requested: boolean; scored_event_version_id: string | null }

export default async function EventsPage({ searchParams }: { searchParams: Promise<{ state?: string; ok?: string; error?: string; all?: string }> }) {
  const sp = await searchParams;
  const session = await requireSession();
  if (!can(session, "CLAIM_READ")) return <><PageHeader title="Events" /><Locked>Your role does not include CLAIM_READ.</Locked></>;
  const supabase = await createClient();
  let q = supabase.from("event_heads").select("*").order("event_id").limit(300);
  if (sp.state) q = q.eq("state", sp.state);
  if (!sp.all) q = q.eq("is_current", true);
  const { data, error } = await q;
  const heads = (data ?? []) as Head[];
  const ids = heads.map((h) => h.event_id);
  const none = ["00000000-0000-0000-0000-000000000000"];
  const [{ data: rel }, { data: claims }, { data: av }, { data: created }] = await Promise.all([
    supabase.from("event_relevance_queue").select("event_id,priority_score,automatic_assessment_recommended,hu_nato_relevance_established,manually_promoted_or_requested,scored_event_version_id")
      .in("event_id", ids.length ? ids : none),
    supabase.from("event_claims").select("event_version_id,role").in("event_version_id", heads.length ? heads.map((h) => h.head_version_id) : none),
    supabase.from("assessment_versions").select("id,event_version_id").in("event_version_id", heads.length ? heads.map((h) => h.head_version_id) : none),
    supabase.from("events").select("id,created_at").in("id", ids.length ? ids : none),
  ]);
  const relBy = new Map(((rel ?? []) as Rel[]).map((r) => [r.event_id, r]));
  const claimCount = new Map<string, { n: number; contra: number }>();
  for (const c of (claims ?? []) as { event_version_id: string; role: string }[]) {
    const x = claimCount.get(c.event_version_id) ?? { n: 0, contra: 0 };
    claimCount.set(c.event_version_id, { n: x.n + 1, contra: x.contra + (c.role === "CONTRADICTS" ? 1 : 0) });
  }
  const avIds = ((av ?? []) as { id: string; event_version_id: string }[]);
  const { data: avs } = await supabase.from("assessment_version_states").select("assessment_version_id,state").in("assessment_version_id",
    avIds.length ? avIds.map((a) => a.id) : none);
  const avState = new Map(((avs ?? []) as { assessment_version_id: string; state: string }[]).map((a) => [a.assessment_version_id, a.state]));
  const assessmentBy = new Map<string, string[]>();
  for (const a of avIds) assessmentBy.set(a.event_version_id, [...(assessmentBy.get(a.event_version_id) ?? []), avState.get(a.id) ?? "DRAFT"]);
  const createdAt = new Map(((created ?? []) as { id: string; created_at: string }[]).map((e) => [e.id, e.created_at]));
  heads.sort((a, b) => (createdAt.get(b.event_id) ?? "").localeCompare(createdAt.get(a.event_id) ?? ""));

  const chips = [{ key: "", label: "All current", href: "/events" },
    ...EVENT_STATES.map((s) => ({ key: s, label: s.charAt(0) + s.slice(1).toLowerCase(), href: `/events?state=${s}` }))];
  return (
    <>
      <PageHeader title="Events" crumbs={[{ href: "/", label: "Dashboard" }, { label: "Events" }]}
        lede="Developments built from claims — by M05 proposal or by you. Every structural change, review, state change and relevance decision is a human, audited action; every version is kept."
        actions={can(session, "EVENT_ACTION") ? <a className="btn primary" href="/events/new">New event from claims</a> : undefined} />
      <Flash ok={sp.ok} error={sp.error} />
      <Chips items={chips} current={sp.state ?? ""} />
      {error && <Flash error={`Could not load events: ${error.message}`} />}
      {heads.length === 0 ? (
        <Empty title="No events yet">Select claims on the <a href="/claims?tab=all">claims list</a> and request M05 event building, or create one
          manually.</Empty>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Event</th><th>State</th><th>Claims</th><th>Head review</th><th>Relevance (M06)</th><th>Assessment</th><th>Created</th></tr></thead>
            <tbody>
              {heads.map((h) => {
                const r = relBy.get(h.event_id);
                const cc = claimCount.get(h.head_version_id) ?? { n: 0, contra: 0 };
                const as = assessmentBy.get(h.head_version_id) ?? [];
                return (
                  <tr key={h.event_id}>
                    <td style={{ maxWidth: 380 }}><a className="title-cell" href={`/events/${h.event_id}`}>{h.title}</a>
                      <div className="muted" style={{ fontSize: 12 }}>{h.event_type} · v{h.head_version_no} · {h.origin === "AI" ? "proposed by M05" : "human"}
                        {h.structural_status && <> · {h.structural_status}</>}</div></td>
                    <td><Badge value={h.state} />{cc.contra > 0 && <div><Badge tone="danger">contested evidence</Badge></div>}</td>
                    <td className="num">{cc.n}{cc.contra > 0 && <span className="muted"> ({cc.contra} contra)</span>}</td>
                    <td>{h.head_review_decision ? <Badge value={h.head_review_decision} /> : <Badge tone="warn">pending</Badge>}</td>
                    <td>{r?.priority_score != null ? <><b>{Number(r.priority_score).toFixed(2)}</b>{" "}
                      {r.automatic_assessment_recommended ? <Badge tone="ok">assess</Badge> : <Badge tone="neutral">monitor</Badge>}</>
                      : <span className="muted">not scored</span>}
                      {r?.manually_promoted_or_requested && <div><Badge tone="violet">manual request</Badge></div>}</td>
                    <td>{as.length === 0 ? <span className="muted">none</span> : as.map((s, i) => <Badge key={i} value={s} />)}</td>
                    <td style={{ fontSize: 12.5 }}><When at={createdAt.get(h.event_id)} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>{sp.all ? <a href="/events">Hide merged / superseded events</a>
        : <a href="/events?all=1">Show merged / superseded events too</a>}</p>
    </>
  );
}
