import { JobRequestForm, JobStatusLine, requestsFor } from "@/components/jobs";
import { Submit } from "@/components/client";
import { Badge, Card, Flash, KV, Locked, PageHeader, Short, Steps, When } from "@/components/ui";
import { can, requireSession } from "@/lib/auth";
import { CLAIM_TYPES } from "@/lib/claims";
import { snapshotInfo } from "@/lib/data";
import { DATE_CONFIDENCE, EVENT_REVIEW_DECISIONS, EVENT_ROLES, SETTABLE_STATES } from "@/lib/events";
import { createClient } from "@/lib/supabase/server";
import { analysisContexts } from "@/lib/workspace";

import { decideRelevance, promoteEvent, reviewEventVersion, setEventState, updateEvent } from "../actions";

export const dynamic = "force-dynamic";

interface Version { id: string; version_no: number; title: string; description: string; event_type: string; event_date_start: string | null;
  event_date_end: string | null; event_date_confidence: string; locations: string[]; origin: string; content_hash: string; created_at: string;
  created_by_model_run_id: string | null }
interface Relevance { id: string; event_version_id: string; priority_score: number; military_significance: number; novelty_change: number;
  hu_nato_relevance_score: number; strategic_relevance: number; time_sensitivity: number; applicable_pir_ids: string[];
  recommendation: string | null; automatic_assessment_recommended: boolean; hu_nato_relevance_established: boolean;
  hu_nato_dimensions: string[]; hu_nato_relevance_rationale: string | null; executive_relevance: string | null; reasoning_summary: string;
  relevance_uncertainty: string | null; created_at: string; model_run_id: string }

export default async function EventDetail({ params, searchParams }: {
  params: Promise<{ id: string }>; searchParams: Promise<{ ok?: string; error?: string }>;
}) {
  const { id } = await params;
  const { ok, error } = await searchParams;
  const session = await requireSession();
  if (!can(session, "CLAIM_READ")) return <Locked>Your role does not include CLAIM_READ.</Locked>;
  const supabase = await createClient();
  const { data: headRow } = await supabase.from("event_heads").select("*").eq("event_id", id).maybeSingle();
  if (!headRow) return <PageHeader title="Event not found" crumbs={[{ href: "/events", label: "Events" }, { label: id }]} />;
  const head = headRow as { head_version_id: string; head_content_hash: string; state: string; origin: string; structural_status: string | null;
    successor_event_id: string | null; head_review_decision: string | null; is_current: boolean };
  const [{ data: vers }, { data: ec }, { data: states }, { data: reviews }, { data: rels }, { data: decisions }, { data: proposals }, contexts] =
    await Promise.all([
      supabase.from("event_versions").select("*").eq("event_id", id).order("version_no", { ascending: false }),
      supabase.from("event_claims").select("claim_id,role").eq("event_version_id", head.head_version_id),
      supabase.from("event_state_history").select("*").eq("event_id", id).order("seq", { ascending: false }),
      supabase.from("event_version_reviews").select("*").eq("event_version_id", head.head_version_id).order("seq", { ascending: false }),
      supabase.from("relevance_results").select("*").eq("event_id", id).order("created_at", { ascending: false }),
      supabase.from("relevance_decisions").select("*").eq("event_id", id).order("seq", { ascending: false }),
      supabase.from("event_proposals").select("id,proposal_type,reason,proposal_confidence,model_run_id,created_at").eq("materialised_event_id", id),
      analysisContexts(supabase),
    ]);
  const versions = (vers ?? []) as Version[];
  const v = versions.find((x) => x.id === head.head_version_id) ?? versions[0];
  const roles = (ec ?? []) as { claim_id: string; role: string }[];
  const claimIds = roles.map((r) => r.claim_id);
  const none = ["00000000-0000-0000-0000-000000000000"];
  const [{ data: cl }, { data: cst }, { data: av }] = await Promise.all([
    supabase.from("claims").select("id,claim_text_normalised,span_exact_text,attribution,article_snapshot_id,language_original").in("id", claimIds.length ? claimIds : none),
    supabase.from("claim_state").select("claim_id,claim_status,review_state").in("claim_id", claimIds.length ? claimIds : none),
    supabase.from("assessment_versions").select("id,assessment_id,version_no,event_version_id,report_mode,information_cutoff,origin,created_at")
      .in("event_version_id", versions.length ? versions.map((x) => x.id) : none).order("created_at", { ascending: false }),
  ]);
  const claims = new Map(((cl ?? []) as { id: string; claim_text_normalised: string; span_exact_text: string; attribution: string | null;
    article_snapshot_id: string; language_original: string }[]).map((c) => [c.id, c]));
  const cstate = new Map(((cst ?? []) as { claim_id: string; claim_status: string; review_state: string }[]).map((c) => [c.claim_id, c]));
  const snaps = await snapshotInfo(supabase, [...claims.values()].map((c) => c.article_snapshot_id));
  const assessments = (av ?? []) as { id: string; version_no: number; event_version_id: string; report_mode: string; information_cutoff: string;
    origin: string; created_at: string }[];
  const { data: avst } = await supabase.from("assessment_version_states").select("assessment_version_id,state,final_analytic_confidence")
    .in("assessment_version_id", assessments.length ? assessments.map((a) => a.id) : none);
  const avState = new Map(((avst ?? []) as { assessment_version_id: string; state: string; final_analytic_confidence: string | null }[])
    .map((a) => [a.assessment_version_id, a]));
  const relevance = (rels ?? []) as Relevance[];
  const latestRel = relevance.find((r) => r.event_version_id === head.head_version_id) ?? null;
  const relDecisions = (decisions ?? []) as { id: string; action: string; relevance_result_id: string | null; event_version_id: string;
    override: Record<string, unknown> | null; reason: string; created_at: string }[];
  const manual = relDecisions.some((d) => d.event_version_id === head.head_version_id && ["PROMOTE", "REQUEST_ASSESSMENT"].includes(d.action));
  const jobs = await requestsFor([head.head_version_id, ...assessments.map((a) => a.id)]);
  const contra = roles.filter((r) => r.role === "CONTRADICTS").length;
  const eventActor = can(session, "EVENT_ACTION");
  const reviewer = can(session, "ASSESSMENT_REVIEW");
  const reviewed = ((reviews ?? []) as { decision: string }[])[0]?.decision === "APPROVE";
  const approved = [...avState.values()].some((a) => a.state === "APPROVED");
  const headAssess = assessments.filter((a) => a.event_version_id === head.head_version_id);
  const back = `/events/${id}`;
  const canAssess = !!latestRel?.automatic_assessment_recommended || manual;

  return (
    <>
      <PageHeader title={v?.title ?? "Event"} crumbs={[{ href: "/", label: "Dashboard" }, { href: "/events", label: "Events" }, { label: v?.title ?? id }]}
        badges={<><Badge value={head.state} />{contra > 0 && <Badge tone="danger">contested evidence ({contra})</Badge>}
          {head.structural_status && <Badge tone="neutral">{head.structural_status}</Badge>}</>}
        lede={<>Version {v?.version_no} · {v?.event_type} · {head.origin === "AI" ? "proposed by M05, decided by humans" : "created by a human"} · hash{" "}
          <Short id={head.head_content_hash} n={12} /></>} />
      <Flash ok={ok} error={error} />
      <Steps steps={[
        { label: "Claims", detail: <div>{roles.length} linked</div>, state: roles.length ? "done" : "current" },
        { label: "Event reviewed", detail: <div>{reviewed ? "approved" : "pending"}</div>, state: reviewed ? "done" : "current" },
        { label: "Relevance (M06)", detail: <div>{latestRel ? `score ${Number(latestRel.priority_score).toFixed(2)}` : manual ? "manual request" : "not scored"}</div>,
          state: latestRel || manual ? "done" : reviewed ? "current" : "todo" },
        { label: "Assessment (M07/M08)", detail: <div>{headAssess.length ? `${headAssess.length} version(s)` : "not requested"}</div>,
          state: headAssess.length ? "done" : canAssess ? "current" : "todo" },
        { label: "Human approval", detail: <div>{approved ? "approved" : "pending"}</div>, state: approved ? "done" : headAssess.length ? "current" : "todo" },
      ]} />
      <div className="split">
        <div>
          <Card title="Current version" tone="accent">
            <p style={{ fontSize: 14.5 }}>{v?.description}</p>
            <KV rows={[
              ["Type", v?.event_type],
              ["Event date", v?.event_date_start ? `${v.event_date_start}${v.event_date_end ? ` – ${v.event_date_end}` : ""} (${v.event_date_confidence})` : "unknown"],
              ["Locations", v?.locations?.length ? v.locations.join(", ") : "—"],
              ["Version", <span key="v">v{v?.version_no} · {v?.origin} · <When at={v?.created_at} /></span>],
              ["M05 run", v?.created_by_model_run_id ? <Short key="r" id={v.created_by_model_run_id} /> : "—"],
            ]} />
          </Card>
          <Card title={`Claims in this version (${roles.length})`}>
            {contra > 0 && <p style={{ color: "var(--danger)", fontSize: 13 }}>This event contains contradicting evidence. The contradiction must stay
              visible in every assessment and report built on it.</p>}
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Role</th><th>Claim and evidence</th><th>Source · availability</th><th>Status</th></tr></thead>
                <tbody>{roles.map((r) => {
                  const c = claims.get(r.claim_id);
                  const s = c ? snaps.get(c.article_snapshot_id) : undefined;
                  const cs = cstate.get(r.claim_id);
                  return (
                    <tr key={r.claim_id}>
                      <td><Badge value={r.role} /></td>
                      <td style={{ maxWidth: 420 }}><a href={`/claims/${r.claim_id}`}>{c?.claim_text_normalised ?? r.claim_id}</a>
                        {c && <div className="muted" lang={c.language_original} style={{ fontSize: 12.5 }}>“{c.span_exact_text}”
                          {c.attribution && <> · {c.attribution}</>}</div>}</td>
                      <td style={{ fontSize: 12.5 }}>{s?.source_name}<div className="muted"><When at={s?.public_availability_datetime} /></div></td>
                      <td><Badge value={cs?.claim_status} /> <Badge value={cs?.review_state} /></td>
                    </tr>);
                })}</tbody>
              </table>
            </div>
          </Card>
          <Card title="Relevance (M06) — Hungarian / NATO">
            {!latestRel ? <p className="muted">No M06 result for the current version yet.</p> : (
              <>
                <div className="grid cols-3" style={{ marginBottom: 10 }}>
                  <div className="stat"><div className="label">Priority score</div><div className="value">{Number(latestRel.priority_score).toFixed(2)}</div>
                    <div className="hint">recommendation only (no hidden threshold)</div></div>
                  <div className="stat"><div className="label">Assessment</div><div className="value" style={{ fontSize: 18 }}>
                    {latestRel.automatic_assessment_recommended ? "recommended" : "not recommended"}</div></div>
                  <div className="stat"><div className="label">HU / NATO relevance</div><div className="value" style={{ fontSize: 18 }}>
                    {latestRel.hu_nato_relevance_established ? "established" : "not established"}</div></div>
                </div>
                <KV rows={[
                  ["Factors", `military ${latestRel.military_significance} · novelty ${latestRel.novelty_change} · HU/NATO ${latestRel.hu_nato_relevance_score} · strategic ${latestRel.strategic_relevance} · time ${latestRel.time_sensitivity}`],
                  ["PIRs", latestRel.applicable_pir_ids.join(", ") || "—"],
                  ["Dimensions", latestRel.hu_nato_dimensions.join(", ") || "—"],
                  ["Why it matters", latestRel.hu_nato_relevance_rationale ?? "—"],
                  ["Executive relevance", latestRel.executive_relevance ?? "—"],
                  ["Reasoning", latestRel.reasoning_summary],
                  ["Uncertainty", latestRel.relevance_uncertainty ?? "—"],
                  ["Run", <span key="r"><Short id={latestRel.model_run_id} /> · <When at={latestRel.created_at} /></span>],
                ]} />
                {reviewer ? (
                  <form action={decideRelevance} className="form" style={{ marginTop: 12 }}>
                    <input type="hidden" name="event_id" value={id} />
                    <input type="hidden" name="result_id" value={latestRel.id} />
                    <div className="form-row">
                      <div className="field"><label>Decision</label><select name="action"><option>VALIDATE</option><option>OVERRIDE</option></select></div>
                      <div className="field"><label>Override: priority 0–5</label><input name="priority_score" type="number" min={0} max={5} step={0.01} /></div>
                      <div className="field"><label>Override: recommend assessment</label>
                        <select name="automatic_assessment_recommended" defaultValue=""><option value="">unchanged</option><option value="true">yes</option><option value="false">no</option></select></div>
                    </div>
                    <div className="form-row"><div className="field"><label>Reason (audited)</label><input name="reason" required minLength={5} /></div>
                      <Submit>Record relevance decision</Submit></div>
                  </form>
                ) : <Locked>Relevance decisions need ASSESSMENT_REVIEW.</Locked>}
              </>
            )}
            {relDecisions.length > 0 && (
              <ul className="timeline" style={{ marginTop: 12 }}>{relDecisions.map((d) => (
                <li key={d.id}><Badge tone="violet">{d.action}</Badge> <When at={d.created_at} /> — {d.reason}
                  {d.override && <span className="muted"> · override {JSON.stringify(d.override)}</span>}</li>))}</ul>
            )}
          </Card>
          <Card title="Assessments of this event">
            {assessments.length === 0 ? <p className="muted">No assessment yet.</p> : (
              <div className="table-wrap"><table className="table">
                <thead><tr><th>Assessment version</th><th>Event version</th><th>Context</th><th>State</th><th>Final confidence</th></tr></thead>
                <tbody>{assessments.map((a) => {
                  const st = avState.get(a.id);
                  return (<tr key={a.id}><td><a href={`/assessments/${a.id}`}>v{a.version_no} · {a.origin}</a></td>
                    <td>{a.event_version_id === head.head_version_id ? "current" : <Short id={a.event_version_id} />}</td>
                    <td><Badge value={a.report_mode} /> <span className="muted" style={{ fontSize: 12 }}><When at={a.information_cutoff} /></span></td>
                    <td><Badge value={st?.state} /></td><td>{st?.final_analytic_confidence ? <Badge value={st.final_analytic_confidence} /> : "—"}</td></tr>);
                })}</tbody></table></div>
            )}
          </Card>
          <Card title="History">
            <ul className="timeline">
              {((states ?? []) as { id: string; old_state: string | null; new_state: string; actor_type: string; reason: string; created_at: string }[]).map((s) => (
                <li key={s.id}>state {s.old_state ?? "∅"} → <Badge value={s.new_state} /> <span className="muted">{s.actor_type}</span> <When at={s.created_at} /> — {s.reason}</li>))}
              {((reviews ?? []) as { id: string; decision: string; reason: string; created_at: string }[]).map((r) => (
                <li key={r.id}>head version review <Badge value={r.decision} /> <When at={r.created_at} /> — {r.reason}</li>))}
              {versions.map((x) => <li key={x.id}>version {x.version_no} ({x.origin}) <When at={x.created_at} /> · <Short id={x.content_hash} n={12} /></li>)}
              {((proposals ?? []) as { id: string; proposal_type: string; reason: string; proposal_confidence: string | null; created_at: string }[]).map((p) => (
                <li key={p.id}>M05 proposal {p.proposal_type} ({p.proposal_confidence ?? "—"}) <When at={p.created_at} /> — {p.reason}</li>))}
            </ul>
          </Card>
        </div>
        <div>
          <Card title="Next steps" tone="warn">
            <JobStatusLine rows={jobs} />
            <h3 style={{ marginTop: 10 }}>1 · Review the event version</h3>
            {eventActor ? (
              <form action={reviewEventVersion} className="form">
                <input type="hidden" name="event_id" value={id} />
                <input type="hidden" name="version_id" value={head.head_version_id} />
                <input type="hidden" name="version_hash" value={head.head_content_hash} />
                <div className="form-row">
                  <div className="field"><label>Decision</label><select name="decision">{EVENT_REVIEW_DECISIONS.map((d) => <option key={d}>{d}</option>)}</select></div>
                  <div className="field"><label>Reason (audited)</label><input name="reason" required minLength={5} defaultValue="" /></div>
                </div>
                <Submit kind="primary">Record event review</Submit>
              </form>
            ) : <Locked>Event decisions need EVENT_ACTION (analyst).</Locked>}
            <h3 style={{ marginTop: 14 }}>2 · State</h3>
            {eventActor && head.state !== "REJECTED" ? (
              <form action={setEventState} className="form">
                <input type="hidden" name="event_id" value={id} />
                <input type="hidden" name="expected_state" value={head.state} />
                <div className="form-row">
                  <div className="field"><label>New state</label>
                    <select name="new_state" defaultValue={head.state === "CANDIDATE" ? "ACTIVE" : head.state}>
                      {[...SETTABLE_STATES, "REJECTED"].filter((s) => s !== head.state).map((s) => <option key={s}>{s}</option>)}</select></div>
                  <div className="field"><label>Reason (audited)</label><input name="reason" required minLength={5} /></div>
                </div>
                <Submit>Change state</Submit>
              </form>
            ) : <Locked>{head.state === "REJECTED" ? "A rejected event keeps its history and is not reopened." : "Needs EVENT_ACTION."}</Locked>}
            <h3 style={{ marginTop: 14 }}>3 · Relevance (M06)</h3>
            <JobRequestForm jobType="ASSESS_RELEVANCE" returnTo={back} contexts={contexts} allowed={reviewer}
              lockedReason="Requesting M06 needs ASSESSMENT_REVIEW." cta="Request relevance (M06)"
              hidden={{ event_version_id: head.head_version_id, event_version_hash: head.head_content_hash }}
              defaultReason="analyst requests HU / NATO relevance scoring" />
            <h3 style={{ marginTop: 14 }}>4 · Assessment (M07 → M08)</h3>
            {!canAssess && reviewer && (
              <form action={promoteEvent} className="form" style={{ marginBottom: 10 }}>
                <p className="muted" style={{ margin: 0, fontSize: 12.5 }}>No M06 recommendation for this version. You may request an assessment
                  regardless of the score — recorded as an audited manual request.</p>
                <input type="hidden" name="event_id" value={id} />
                <input type="hidden" name="version_id" value={head.head_version_id} />
                <input type="hidden" name="version_hash" value={head.head_content_hash} />
                <input type="hidden" name="action" value="REQUEST_ASSESSMENT" />
                <div className="form-row"><div className="field"><label>Reason (audited)</label><input name="reason" required minLength={5} /></div>
                  <Submit>Record manual assessment request</Submit></div>
              </form>
            )}
            <JobRequestForm jobType="ASSESS_EVENT" returnTo={back} contexts={contexts} allowed={reviewer && canAssess}
              lockedReason={reviewer ? "First obtain an M06 recommendation or record an audited manual assessment request." : "Requesting M07 needs ASSESSMENT_REVIEW."}
              cta="Request assessment (M07)" hidden={{ event_version_id: head.head_version_id, event_version_hash: head.head_content_hash }}
              defaultReason="analyst requests an intelligence assessment"
              note="M07 drafts statements; M08 challenges them automatically; approval and final confidence remain yours." />
          </Card>
          {eventActor && v && (
            <Card title="Edit (creates a new version)">
              <details className="panel"><summary>Edit title, description, dates or claim roles</summary><div className="panel-body">
                <form action={updateEvent} className="form">
                  <input type="hidden" name="event_id" value={id} />
                  <input type="hidden" name="expected_head" value={head.head_version_id} />
                  <div className="field"><label>Title</label><input name="title" defaultValue={v.title} required minLength={3} /></div>
                  <div className="field"><label>Description</label><textarea name="description" defaultValue={v.description} required /></div>
                  <div className="form-row">
                    <div className="field"><label>Type</label><select name="event_type" defaultValue={v.event_type}>{CLAIM_TYPES.map((t) => <option key={t}>{t}</option>)}</select></div>
                    <div className="field"><label>Date start</label><input name="event_date_start" defaultValue={v.event_date_start ?? ""} placeholder="YYYY-MM-DD" /></div>
                    <div className="field"><label>Date end</label><input name="event_date_end" defaultValue={v.event_date_end ?? ""} /></div>
                    <div className="field"><label>Date confidence</label><select name="event_date_confidence" defaultValue={v.event_date_confidence}>
                      {DATE_CONFIDENCE.map((d) => <option key={d}>{d}</option>)}</select></div>
                  </div>
                  <div className="field"><label>Locations (comma separated)</label><input name="locations" defaultValue={v.locations.join(", ")} /></div>
                  <fieldset><legend>Claims (untick to remove — removal is recorded)</legend>
                    {roles.map((r) => (
                      <div key={r.claim_id} className="row" style={{ marginBottom: 4 }}>
                        <input type="checkbox" name="claim_ids" value={r.claim_id} defaultChecked aria-label="keep claim" />
                        <select name={`role_${r.claim_id}`} defaultValue={r.role} aria-label="role">{EVENT_ROLES.map((x) => <option key={x}>{x}</option>)}</select>
                        <span style={{ fontSize: 12.5 }}>{claims.get(r.claim_id)?.claim_text_normalised}</span>
                      </div>))}
                  </fieldset>
                  <div className="field"><label>Reason (audited)</label><input name="reason" required minLength={5} /></div>
                  <Submit>Save as new version</Submit>
                </form>
              </div></details>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
