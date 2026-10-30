import { requestJob, requestPendingExtractions } from "@/app/jobs/actions";
import { Submit } from "@/components/client";
import { JobStatusLine, requestsFor } from "@/components/jobs";
import { Badge, Card, Chips, Empty, Flash, Locked, PageHeader, Tabs, When } from "@/components/ui";
import { can, requireSession } from "@/lib/auth";
import { CLAIM_STATUSES, CLAIM_TYPES } from "@/lib/claims";
import { type ClaimRow, type ClaimStateRow, eventsForClaims, snapshotInfo } from "@/lib/data";
import { createClient } from "@/lib/supabase/server";
import { analysisContexts } from "@/lib/workspace";

export const dynamic = "force-dynamic";

type Search = { error?: string; ok?: string; tab?: string; status?: string; type?: string; q?: string };

export default async function ClaimsPage({ searchParams }: { searchParams: Promise<Search> }) {
  const sp = await searchParams;
  const tab = sp.tab ?? "review";
  const session = await requireSession();
  if (!can(session, "CLAIM_READ")) {
    return <><PageHeader title="Claims" /><Locked>Your role does not include CLAIM_READ.</Locked></>;
  }
  const supabase = await createClient();
  const tabs = [
    { key: "review", label: "Needs review", href: "/claims?tab=review" },
    { key: "all", label: "All claims", href: "/claims?tab=all" },
    { key: "intake", label: "Article intake (M02)", href: "/claims?tab=intake" },
  ];
  return (
    <>
      <PageHeader title="Claims" crumbs={[{ href: "/", label: "Dashboard" }, { label: "Claims" }]}
        lede="AI-extracted claims, each grounded in an exact original-language evidence span that the database verified. The AI recommends; review, status and event building are your decisions." />
      <Flash ok={sp.ok} error={sp.error} okText={sp.ok} />
      <Tabs items={tabs} current={tab} />
      {tab === "intake" ? <Intake session={session} /> : <ClaimList sp={sp} tab={tab} session={session} supabase={supabase} />}
    </>
  );
}

async function ClaimList({ sp, tab, session, supabase }: { sp: Search; tab: string; session: Awaited<ReturnType<typeof requireSession>>;
  supabase: Awaited<ReturnType<typeof createClient>> }) {
  let ids: string[] | null = null;
  if (tab === "review" || sp.status) {
    let q = supabase.from("claim_state").select("claim_id").limit(300);
    if (tab === "review") q = q.eq("review_state", "PENDING");
    if (sp.status) q = q.eq("claim_status", sp.status);
    const { data } = await q;
    ids = ((data ?? []) as { claim_id: string }[]).map((r) => r.claim_id);
  }
  let query = supabase.from("claims").select("*").order("created_at", { ascending: false }).limit(150);
  if (ids) query = query.in("id", ids.length ? ids : ["00000000-0000-0000-0000-000000000000"]);
  if (sp.type) query = query.eq("claim_type", sp.type);
  if (sp.q) query = query.ilike("claim_text_normalised", `%${sp.q.replace(/[%_]/g, "")}%`);
  const { data, error } = await query;
  const claims = (data ?? []) as ClaimRow[];
  const cids = claims.map((c) => c.id);
  const [{ data: st }, snaps, events, contexts] = await Promise.all([
    supabase.from("claim_state").select("*").in("claim_id", cids.length ? cids : ["00000000-0000-0000-0000-000000000000"]),
    snapshotInfo(supabase, claims.map((c) => c.article_snapshot_id)),
    eventsForClaims(supabase, cids),
    analysisContexts(supabase),
  ]);
  const state = new Map(((st ?? []) as ClaimStateRow[]).map((s) => [s.claim_id, s]));
  const builder = can(session, "EVENT_ACTION");
  const lineage = can(session, "CLAIM_REVIEW");
  const base = `/claims?tab=${tab}`;
  return (
    <>
      <form method="get" className="form-row card subtle" style={{ padding: 12 }} role="search">
        <input type="hidden" name="tab" value={tab} />
        <div className="field"><label htmlFor="q">Search normalised text</label><input id="q" name="q" type="search" defaultValue={sp.q} /></div>
        <div className="field"><label htmlFor="status">Status</label>
          <select id="status" name="status" defaultValue={sp.status ?? ""}><option value="">any</option>
            {CLAIM_STATUSES.map((s) => <option key={s}>{s}</option>)}</select></div>
        <div className="field"><label htmlFor="type">Claim type</label>
          <select id="type" name="type" defaultValue={sp.type ?? ""}><option value="">any</option>
            {CLAIM_TYPES.map((s) => <option key={s}>{s}</option>)}</select></div>
        <button type="submit">Apply filters</button>{(sp.q || sp.status || sp.type) && <a className="btn ghost" href={base}>Clear</a>}
      </form>
      {error && <Flash error={`Could not load claims: ${error.message}`} />}
      {claims.length === 0 ? (
        <Empty title={tab === "review" ? "No claims are waiting for review" : "No claims match"}>
          Claims appear after M02 extraction of collected articles — see <a href="/claims?tab=intake">Article intake</a>.
        </Empty>
      ) : (
        <form action={requestJob}>
          <input type="hidden" name="return_to" value={base} />
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th aria-label="select" /><th>Claim</th><th>Source · availability</th><th>Type</th><th>Status</th><th>Review</th><th>Event</th></tr></thead>
              <tbody>
                {claims.map((c) => {
                  const s = state.get(c.id);
                  const snap = snaps.get(c.article_snapshot_id);
                  const evs = events.get(c.id) ?? [];
                  return (
                    <tr key={c.id}>
                      <td><input type="checkbox" name="claim_ids" value={c.id} aria-label={`select claim ${c.claim_local_id}`} /></td>
                      <td style={{ maxWidth: 460 }}>
                        <a className="title-cell" href={`/claims/${c.id}`}>{s?.effective_claim_text_normalised ?? c.claim_text_normalised}</a>
                        <div className="muted" lang={c.language_original} style={{ fontSize: 12.5 }}>“{c.span_exact_text}” · {c.language_original}
                          {(s?.effective_attribution ?? c.attribution) && <> · attributed to {s?.effective_attribution ?? c.attribution}</>}</div>
                        {c.review_flags.length > 0 && <div className="row" style={{ marginTop: 4 }}>{c.review_flags.map((f) => <Badge key={f} tone="warn">{f}</Badge>)}</div>}
                      </td>
                      <td style={{ fontSize: 12.5 }}>{snap?.source_name ?? "—"}<div className="muted">available <When at={snap?.public_availability_datetime} /></div></td>
                      <td><Badge tone="outline">{s?.effective_claim_type ?? c.claim_type}</Badge><div className="muted" style={{ fontSize: 12 }}>{c.source_statement_status}</div></td>
                      <td><Badge value={s?.claim_status} />{s?.high_impact && <div><Badge tone="danger">HIGH IMPACT</Badge></div>}</td>
                      <td><Badge value={s?.review_state} /></td>
                      <td style={{ fontSize: 12.5 }}>{evs.length === 0 ? <span className="muted">none</span> : evs.map((e) => (
                        <div key={e.event_id}><a href={`/events/${e.event_id}`}>{e.title}</a> <Badge value={e.role} /></div>))}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <Card title="Process the selected claims" tone="subtle" className="flat">
            {builder || lineage ? (
              <div className="form">
                <div className="form-row">
                  <div className="field">
                    <label htmlFor="ctx">Analysis context (mode · information cutoff)</label>
                    <select id="ctx" name="ctx" required defaultValue={contexts[0]?.key}>
                      {contexts.map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}
                    </select>
                  </div>
                  <div className="field"><label htmlFor="reason">Reason (audited)</label>
                    <input id="reason" name="reason" required minLength={5} defaultValue="analyst groups related claims for the pilot cycle" /></div>
                </div>
                <div className="row">
                  {builder ? <Submit kind="primary" name="job_type" value="BUILD_EVENTS">Build events (M05)</Submit>
                    : <Locked>Event building needs EVENT_ACTION.</Locked>}
                  {lineage && <Submit name="job_type" value="ANALYSE_LINEAGE">Analyse lineage (M04)</Submit>}
                  <a className="btn" href="/events/new">Create an event manually…</a>
                </div>
                <p className="muted" style={{ margin: 0, fontSize: 12 }}>Only claims publicly available by the chosen cutoff are accepted (REPLAY: stated
                  availability ≤ cutoff). M05 proposes candidate events and M04 proposes lineage; nothing becomes final without your decision.</p>
              </div>
            ) : <Locked>Requesting M04 / M05 needs CLAIM_REVIEW / EVENT_ACTION (analyst).</Locked>}
          </Card>
        </form>
      )}
    </>
  );
}

async function Intake({ session }: { session: Awaited<ReturnType<typeof requireSession>> }) {
  const supabase = await createClient();
  const { data: reps } = await supabase.from("text_representations").select("id,snapshot_id,language,is_original_language,char_length,created_at")
    .eq("is_original_language", true).order("created_at", { ascending: false }).limit(100);
  const rows = (reps ?? []) as { id: string; snapshot_id: string; language: string | null; char_length: number; created_at: string }[];
  const [snaps, { data: ext }, requests] = await Promise.all([
    snapshotInfo(supabase, rows.map((r) => r.snapshot_id)),
    supabase.from("claim_extraction_results").select("text_representation_id,outcome,claims_persisted,created_at")
      .in("text_representation_id", rows.length ? rows.map((r) => r.id) : ["00000000-0000-0000-0000-000000000000"]),
    requestsFor(rows.map((r) => r.id), ["EXTRACT_CLAIMS"]),
  ]);
  const extracted = new Map<string, { outcome: string; claims_persisted: number }[]>();
  for (const e of (ext ?? []) as { text_representation_id: string; outcome: string; claims_persisted: number }[]) {
    extracted.set(e.text_representation_id, [...(extracted.get(e.text_representation_id) ?? []), e]);
  }
  const reviewer = can(session, "CLAIM_REVIEW");
  return (
    <>
      <Card title="Collected article texts" actions={reviewer ? (
        <form action={requestPendingExtractions} className="row">
          <input name="reason" required minLength={5} defaultValue="analyst starts claim extraction for collected articles" aria-label="reason" style={{ minWidth: 300 }} />
          <Submit kind="primary">Extract all pending (M02)</Submit>
        </form>) : undefined}>
        <p className="muted">Original-language texts of collected snapshots. M02 extracts claims; each is verified against the exact text span before
          it is stored. Metadata-only snapshots cannot ground claims.</p>
        {rows.length === 0 ? <Empty title="No collected article text yet" /> : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Article</th><th>Source</th><th>Public availability</th><th>Retrieved</th><th>Extraction</th><th /></tr></thead>
              <tbody>
                {rows.map((r) => {
                  const s = snaps.get(r.snapshot_id);
                  const e = extracted.get(r.id) ?? [];
                  const req = requests.filter((x) => x.object_id === r.id);
                  return (
                    <tr key={r.id}>
                      <td style={{ maxWidth: 380 }}><span className="title-cell">{s?.title_original ?? "(untitled)"}</span>
                        <div className="muted wrap-anywhere" style={{ fontSize: 12 }}>{s?.final_url} · {r.language} · {r.char_length} chars</div></td>
                      <td>{s?.source_name}</td>
                      <td><When at={s?.public_availability_datetime} /><div className="muted" style={{ fontSize: 12 }}>{s?.public_availability_basis}</div></td>
                      <td><When at={s?.system_retrieval_datetime} /></td>
                      <td>{e.length === 0 && req.length === 0 && <Badge tone="neutral">not extracted</Badge>}
                        {e.map((x, i) => <div key={i}><Badge value={x.outcome === "CLAIMS_PERSISTED" ? "SUCCESS" : x.outcome}>{x.outcome.replaceAll("_", " ")}</Badge> {x.claims_persisted} claim(s)</div>)}
                        <JobStatusLine rows={req} /></td>
                      <td>{reviewer && s?.retention_mode_applied !== "METADATA_ONLY" ? (
                        <form action={requestJob}>
                          <input type="hidden" name="job_type" value="EXTRACT_CLAIMS" />
                          <input type="hidden" name="return_to" value="/claims?tab=intake" />
                          <input type="hidden" name="text_representation_id" value={r.id} />
                          <input type="hidden" name="reason" value="analyst requests claim extraction for this article" />
                          <Submit small>Extract (M02)</Submit>
                        </form>) : <span className="muted" style={{ fontSize: 12 }}>{s?.retention_mode_applied === "METADATA_ONLY" ? "metadata only" : ""}</span>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
