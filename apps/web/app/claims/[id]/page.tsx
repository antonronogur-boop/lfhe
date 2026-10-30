import { Submit } from "@/components/client";
import { Badge, Card, Flash, KV, Locked, PageHeader, Short, When } from "@/components/ui";
import { can, requireSession } from "@/lib/auth";
import { CLAIM_STATUSES, CLAIM_TYPES, HIGH_IMPACT_REASONS, REVIEW_DECISIONS, spanContext } from "@/lib/claims";
import { type ClaimRow, type ClaimStateRow, eventsForClaims, snapshotInfo } from "@/lib/data";
import { createClient } from "@/lib/supabase/server";

import { decideRevalidation, markHighImpact, reviewClaim, setClaimStatus } from "../actions";

export const dynamic = "force-dynamic";

export default async function ClaimDetail({ params, searchParams }: {
  params: Promise<{ id: string }>; searchParams: Promise<{ ok?: string; error?: string }>;
}) {
  const { id } = await params;
  const { ok, error } = await searchParams;
  const session = await requireSession();
  if (!can(session, "CLAIM_READ")) return <Locked>Your role does not include CLAIM_READ.</Locked>;
  const supabase = await createClient();
  const { data: c } = await supabase.from("claims").select("*").eq("id", id).maybeSingle();
  if (!c) return <><PageHeader title="Claim not found" crumbs={[{ href: "/claims", label: "Claims" }, { label: id }]} /></>;
  const claim = c as ClaimRow;
  const [{ data: st }, snaps, events, { data: text }, { data: reviews }, { data: statuses }, { data: reval }, { data: ext }, { data: cls }, { data: run }] =
    await Promise.all([
      supabase.from("claim_state").select("*").eq("claim_id", id).maybeSingle(),
      snapshotInfo(supabase, [claim.article_snapshot_id]),
      eventsForClaims(supabase, [id]),
      supabase.from("text_representations").select("text_content,language").eq("id", claim.text_representation_id).maybeSingle(),
      supabase.from("claim_reviews").select("*").eq("claim_id", id).order("seq", { ascending: false }),
      supabase.from("claim_status_history").select("*").eq("claim_id", id).order("seq", { ascending: false }),
      supabase.from("claim_revalidations").select("id,created_at").eq("claim_id", id),
      supabase.from("claim_extraction_results").select("outcome,created_at,model_run_id").eq("model_run_id", claim.created_by_model_run_id).maybeSingle(),
      supabase.from("taxonomy_assignments").select("taxonomy_id,assignment_confidence").eq("target_object_id", id),
      supabase.from("model_runs").select("module_code,prompt_semver,provider,model,status,completed_at").eq("id", claim.created_by_model_run_id).maybeSingle(),
    ]);
  const s = st as ClaimStateRow | null;
  const snap = snaps.get(claim.article_snapshot_id);
  const ctx = text?.text_content ? spanContext(text.text_content as string, claim.span_start, claim.span_end, 260) : null;
  const evs = events.get(id) ?? [];
  const reviewer = can(session, "CLAIM_REVIEW");
  const back = `/claims/${id}`;
  return (
    <>
      <PageHeader title={s?.effective_claim_text_normalised ?? claim.claim_text_normalised}
        crumbs={[{ href: "/", label: "Dashboard" }, { href: "/claims", label: "Claims" }, { label: claim.claim_local_id }]}
        badges={<><Badge value={s?.claim_status} /><Badge value={s?.review_state} />{s?.high_impact && <Badge tone="danger">HIGH IMPACT</Badge>}</>} />
      <Flash ok={ok} error={error} />
      <div className="split">
        <div>
          <Card title="Original-language evidence" tone="accent">
            {ctx ? (
              <div className="evidence quote" lang={claim.language_original}>
                <span className="muted">…{ctx.before}</span><mark>{ctx.span}</mark><span className="muted">{ctx.after}…</span>
              </div>
            ) : <div className="evidence" lang={claim.language_original}><mark>{claim.span_exact_text}</mark></div>}
            <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>Exact span [{claim.span_start}, {claim.span_end}) in code points of text
              representation <Short id={claim.text_representation_id} />; verified by the database against the stored text.</p>
            <KV rows={[
              ["Claim (original)", <span key="o" lang={claim.language_original}>{claim.claim_text_original}</span>],
              ["Claim (normalised)", s?.effective_claim_text_normalised ?? claim.claim_text_normalised],
              ["Attribution", s?.effective_attribution ?? claim.attribution ?? <span className="muted">none stated</span>],
              ["Claim type", <Badge key="t" tone="outline">{s?.effective_claim_type ?? claim.claim_type}</Badge>],
              ["Source statement status", claim.source_statement_status],
              ["Evidence", `${claim.evidence_type} · ${claim.evidence_directness}`],
              ["Event date (as stated)", claim.event_date ?? "—"],
              ["Review flags", claim.review_flags.length ? claim.review_flags.map((f) => <Badge key={f} tone="warn">{f}</Badge>) : "none"],
            ]} />
          </Card>
          <Card title="Source and provenance">
            <KV rows={[
              ["Source", snap?.source_name],
              ["Article", <span key="a">{snap?.title_original ?? "(untitled)"} <div className="muted wrap-anywhere" style={{ fontSize: 12 }}>{snap?.final_url}</div></span>],
              ["Publication (stated)", <When key="p" at={snap?.publication_datetime} />],
              ["Public availability", <span key="pa"><When at={snap?.public_availability_datetime} /> <span className="muted">({snap?.public_availability_basis})</span></span>],
              ["Retrieved by LFHÉ", <When key="r" at={snap?.system_retrieval_datetime} />],
              ["Extraction", <span key="e">{ext?.outcome ?? "—"} · model run <Short id={claim.created_by_model_run_id} />
                {run && <span className="muted"> · {run.module_code} {run.prompt_semver} · {run.provider}/{run.model}</span>}</span>],
              ["Classification", (cls ?? []).length ? (cls as { taxonomy_id: string; assignment_confidence: string }[]).map((x, i) =>
                <Badge key={i} tone="info">{x.taxonomy_id} · {x.assignment_confidence}</Badge>) : <span className="muted">none</span>],
            ]} />
          </Card>
          <Card title="Events using this claim">
            {evs.length === 0 ? <p className="muted">Not part of any event yet. Select it on the <a href="/claims?tab=all">claims list</a> to
              request M05 event building, or <a href={`/events/new?claim=${id}`}>create an event manually</a>.</p> : (
              <ul className="timeline">{evs.map((e) => <li key={e.event_id}><a href={`/events/${e.event_id}`}>{e.title}</a> · v{e.version_no}{" "}
                <Badge value={e.role} /> <Badge value={e.state} /></li>)}</ul>)}
          </Card>
          <Card title="Review and status history (audit)">
            <ul className="timeline">
              {((reviews ?? []) as { id: string; decision: string; reason: string; created_at: string; modified_claim_text_normalised: string | null }[]).map((r) => (
                <li key={r.id}><Badge value={r.decision} /> <When at={r.created_at} /> — {r.reason}
                  {r.modified_claim_text_normalised && <div className="muted">modified text: {r.modified_claim_text_normalised}</div>}</li>))}
              {((statuses ?? []) as { id: string; old_status: string | null; new_status: string; basis: string; actor_type: string; reason: string; created_at: string }[]).map((h) => (
                <li key={h.id}>status {h.old_status ?? "∅"} → <Badge value={h.new_status} /> <span className="muted">{h.basis} · {h.actor_type}</span>{" "}
                  <When at={h.created_at} /> — {h.reason}</li>))}
              {(reviews ?? []).length + (statuses ?? []).length === 0 && <li className="muted">No human decision yet.</li>}
            </ul>
          </Card>
        </div>
        <div>
          <Card title="Your review decision" tone="warn">
            {!reviewer ? <Locked>Claim review needs CLAIM_REVIEW (analyst). You can read everything on this page.</Locked> : (
              <form action={reviewClaim} className="form">
                <input type="hidden" name="return_to" value={back} />
                <input type="hidden" name="claim_id" value={claim.id} />
                <input type="hidden" name="claim_hash" value={claim.claim_hash} />
                <input type="hidden" name="expected_previous_review_id" value={s?.latest_review_id ?? ""} />
                <div className="field"><label htmlFor="decision">Decision</label>
                  <select id="decision" name="decision">{REVIEW_DECISIONS.map((d) => <option key={d}>{d}</option>)}</select>
                  <span className="help">APPROVE keeps the extraction; REJECT and REQUEST_REPROCESSING exclude the claim from M04/M05 inputs.</span></div>
                <div className="field"><label htmlFor="reason">Reason (audited)</label><input id="reason" name="reason" required minLength={5} /></div>
                <details className="panel"><summary>Modifications (only for MODIFY_AND_APPROVE)</summary><div className="panel-body form">
                  <div className="field"><label>Normalised text</label><textarea name="claim_text_normalised" rows={2} /></div>
                  <div className="field"><label>Claim type</label><select name="claim_type" defaultValue=""><option value="" />
                    {CLAIM_TYPES.map((t) => <option key={t}>{t}</option>)}</select></div>
                  <div className="field"><label>Attribution</label><input name="attribution" /></div>
                  <p className="muted" style={{ margin: 0, fontSize: 12 }}>The evidence span can never be changed.</p>
                </div></details>
                <Submit kind="primary">Record decision</Submit>
              </form>
            )}
          </Card>
          <Card title="Claim status">
            <p className="muted" style={{ fontSize: 12.5 }}>Current: <Badge value={s?.claim_status} /> ({s?.status_basis})</p>
            {reviewer ? (
              <form action={setClaimStatus} className="form">
                <input type="hidden" name="return_to" value={back} />
                <input type="hidden" name="claim_id" value={claim.id} />
                <input type="hidden" name="expected_current_status" value={s?.claim_status ?? "UNVERIFIED"} />
                <div className="field"><label htmlFor="new_status">New status</label>
                  <select id="new_status" name="new_status">{CLAIM_STATUSES.map((x) => <option key={x}>{x}</option>)}</select></div>
                <div className="field"><label htmlFor="sreason">Basis (audited)</label><input id="sreason" name="reason" required minLength={5} /></div>
                <Submit>Set status</Submit>
              </form>
            ) : <Locked>Status changes need CLAIM_REVIEW.</Locked>}
          </Card>
          <Card title="High impact">
            {reviewer ? (
              <form action={markHighImpact} className="form">
                <input type="hidden" name="return_to" value={back} />
                <input type="hidden" name="claim_id" value={claim.id} />
                <input type="hidden" name="high_impact" value={String(!s?.high_impact)} />
                {!s?.high_impact && <div className="field"><label>Reasons</label>
                  <select name="reasons" multiple size={4}>{HIGH_IMPACT_REASONS.map((r) => <option key={r}>{r}</option>)}</select></div>}
                <div className="field"><label htmlFor="hreason">Reason (audited)</label><input id="hreason" name="reason" required minLength={5} /></div>
                <Submit>{s?.high_impact ? "Remove high impact" : "Mark high impact"}</Submit>
              </form>
            ) : <Locked>Needs CLAIM_REVIEW.</Locked>}
            {s?.revalidation_pending && reviewer && ((reval ?? []) as { id: string }[]).map((r) => (
              <form key={r.id} action={decideRevalidation} className="form" style={{ marginTop: 10 }}>
                <input type="hidden" name="return_to" value={back} />
                <input type="hidden" name="revalidation_id" value={r.id} />
                <p style={{ color: "var(--warn)", margin: 0 }}>High-impact revalidation of the automatically assigned status is required.</p>
                <select name="approve" aria-label="revalidation"><option value="true">Confirm status</option><option value="false">Reject (revert)</option></select>
                <input name="reason" required minLength={5} aria-label="reason" />
                <Submit>Decide</Submit>
              </form>
            ))}
          </Card>
        </div>
      </div>
    </>
  );
}
