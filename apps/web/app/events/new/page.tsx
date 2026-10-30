import { Submit } from "@/components/client";
import { Badge, Card, Empty, Flash, Locked, PageHeader, When } from "@/components/ui";
import { can, requireSession } from "@/lib/auth";
import { CLAIM_TYPES } from "@/lib/claims";
import { snapshotInfo } from "@/lib/data";
import { DATE_CONFIDENCE, EVENT_ROLES } from "@/lib/events";
import { createClient } from "@/lib/supabase/server";

import { createEvent } from "../actions";

export const dynamic = "force-dynamic";

export default async function NewEvent({ searchParams }: { searchParams: Promise<{ claim?: string; error?: string }> }) {
  const sp = await searchParams;
  const session = await requireSession();
  const crumbs = [{ href: "/", label: "Dashboard" }, { href: "/events", label: "Events" }, { label: "New event" }];
  if (!can(session, "EVENT_ACTION")) {
    return <><PageHeader title="New event" crumbs={crumbs} /><Locked>Creating events needs EVENT_ACTION (analyst).</Locked></>;
  }
  const supabase = await createClient();
  const { data: st } = await supabase.from("claim_state").select("claim_id,review_state,claim_status")
    .not("review_state", "in", "(REJECTED,REPROCESSING_REQUESTED)").limit(200);
  const states = new Map(((st ?? []) as { claim_id: string; review_state: string; claim_status: string }[]).map((s) => [s.claim_id, s]));
  const ids = [...states.keys()];
  const { data } = await supabase.from("claims").select("id,claim_text_normalised,span_exact_text,claim_type,article_snapshot_id,created_at")
    .in("id", ids.length ? ids : ["00000000-0000-0000-0000-000000000000"]).order("created_at", { ascending: false }).limit(150);
  const claims = (data ?? []) as { id: string; claim_text_normalised: string; span_exact_text: string; claim_type: string; article_snapshot_id: string }[];
  const snaps = await snapshotInfo(supabase, claims.map((c) => c.article_snapshot_id));
  return (
    <>
      <PageHeader title="New event from claims" crumbs={crumbs}
        lede="A human-created event (audited CREATE action). Choose the claims and their role — a CONTRADICTS claim keeps the dispute visible in everything built on the event." />
      <Flash error={sp.error} />
      {claims.length === 0 ? <Empty title="No reviewable claims">Claims rejected or sent for reprocessing are not offered.</Empty> : (
        <form action={createEvent} className="form">
          <Card title="Claims">
            <div className="table-wrap"><table className="table">
              <thead><tr><th>Use</th><th>Role</th><th>Claim</th><th>Source · availability</th><th>Review</th></tr></thead>
              <tbody>{claims.map((c) => {
                const s = snaps.get(c.article_snapshot_id);
                return (
                  <tr key={c.id}>
                    <td><input type="checkbox" name="claim_ids" value={c.id} defaultChecked={sp.claim === c.id} aria-label="use claim" /></td>
                    <td><select name={`role_${c.id}`} defaultValue="SUPPORTS" aria-label="role">{EVENT_ROLES.map((r) => <option key={r}>{r}</option>)}</select></td>
                    <td style={{ maxWidth: 420 }}>{c.claim_text_normalised}<div className="muted" style={{ fontSize: 12.5 }}>“{c.span_exact_text}” · {c.claim_type}</div></td>
                    <td style={{ fontSize: 12.5 }}>{s?.source_name}<div className="muted"><When at={s?.public_availability_datetime} /></div></td>
                    <td><Badge value={states.get(c.id)?.review_state} /></td>
                  </tr>);
              })}</tbody>
            </table></div>
          </Card>
          <Card title="Event">
            <div className="form">
              <div className="field"><label htmlFor="title">Title</label><input id="title" name="title" required minLength={3} maxLength={300} /></div>
              <div className="field"><label htmlFor="description">Description</label><textarea id="description" name="description" required /></div>
              <div className="form-grid">
                <div className="field"><label>Type</label><select name="event_type" defaultValue="DEPLOYMENT">{CLAIM_TYPES.map((t) => <option key={t}>{t}</option>)}</select></div>
                <div className="field"><label>Date start</label><input name="event_date_start" placeholder="YYYY-MM-DD" /></div>
                <div className="field"><label>Date end</label><input name="event_date_end" placeholder="YYYY-MM-DD" /></div>
                <div className="field"><label>Date confidence</label><select name="event_date_confidence" defaultValue="UNKNOWN">{DATE_CONFIDENCE.map((d) => <option key={d}>{d}</option>)}</select></div>
              </div>
              <div className="field"><label>Locations (comma separated)</label><input name="locations" /></div>
              <div className="field"><label>Reason (audited)</label><input name="reason" required minLength={5} /></div>
              <div><Submit kind="primary">Create event</Submit></div>
            </div>
          </Card>
        </form>
      )}
    </>
  );
}
