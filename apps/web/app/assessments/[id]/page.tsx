import { JobRequestForm, JobStatusLine, requestsFor } from "@/components/jobs";
import { Submit } from "@/components/client";
import { Badge, Card, Confirm, EpistemicBadge, Flash, KV, Locked, PageHeader, Short, Steps, When } from "@/components/ui";
import { ASSESSMENT_DECISIONS, CONFIDENCE, FLAG_DISPOSITIONS } from "@/lib/assessments";
import { can, requireSession } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";

import { disposeFlag, modifyAndApprove, reviewAssessment } from "../actions";

export const dynamic = "force-dynamic";

interface Statement { id: string; statement_local_id: string; statement_type: string; epistemic_category: string; statement_text: string;
  provenance_class: string; evidence_required: boolean; attribution_required: boolean; attribution_text: string | null;
  source_epistemic_status: unknown; likelihood_term: string | null; likelihood_rationale: string | null }
interface Flag { id: string; flag_no: number; flag_type: string; severity: string; affected_statement_id: string | null; affected_field: string | null;
  explanation: string; evidence_claim_ids: string[]; recommended_action: string }

export default async function AssessmentDetail({ params, searchParams }: {
  params: Promise<{ id: string }>; searchParams: Promise<{ ok?: string; error?: string }>;
}) {
  const { id } = await params;
  const { ok, error } = await searchParams;
  const session = await requireSession();
  if (!can(session, "CLAIM_READ")) return <Locked>Your role does not include CLAIM_READ.</Locked>;
  const supabase = await createClient();
  const { data: avRow } = await supabase.from("assessment_versions").select("*").eq("id", id).maybeSingle();
  if (!avRow) return <PageHeader title="Assessment not found" crumbs={[{ href: "/assessments", label: "Assessments" }, { label: id }]} />;
  const av = avRow as { id: string; assessment_id: string; version_no: number; event_version_id: string; event_version_hash: string; report_mode: string;
    information_cutoff: string; origin: string; created_by_model_run_id: string | null; ai_recommended_confidence: string | null;
    ai_confidence_rationale: string | null; content: { derived_summary?: { text: string } | null; indicators_to_watch?: { indicator_local_id: string;
      indicator_text: string; observable_condition: string }[] }; content_hash: string; created_at: string; baseline_status: string | null };
  const none = ["00000000-0000-0000-0000-000000000000"];
  const [{ data: stRow }, { data: stmts }, { data: chal }, { data: hist }, { data: appr }, { data: ev }, { data: later }, { data: run }] = await Promise.all([
    supabase.from("assessment_version_states").select("*").eq("assessment_version_id", id).maybeSingle(),
    supabase.from("assessment_statements").select("*").eq("assessment_version_id", id).order("statement_local_id"),
    supabase.from("challenge_runs").select("*").eq("assessment_version_id", id).order("created_at", { ascending: false }),
    supabase.from("assessment_state_history").select("*").eq("assessment_version_id", id).order("seq", { ascending: false }),
    supabase.from("analytical_approvals").select("*").eq("assessment_version_id", id).order("seq", { ascending: false }),
    supabase.from("event_versions").select("id,event_id,title,version_no").eq("id", av.event_version_id).maybeSingle(),
    supabase.from("assessment_versions").select("id,version_no").eq("assessment_id", av.assessment_id).gt("version_no", av.version_no),
    av.created_by_model_run_id ? supabase.from("model_runs").select("module_code,prompt_semver,provider,model,status,usage,started_at,completed_at")
      .eq("id", av.created_by_model_run_id).maybeSingle() : Promise.resolve({ data: null }),
  ]);
  const state = stRow as { state: string; final_analytic_confidence: string | null; final_confidence_rationale: string | null; approved_at: string | null } | null;
  const statements = (stmts ?? []) as Statement[];
  const sIds = statements.map((s) => s.id);
  const runs = (chal ?? []) as { id: string; model_run_id: string; challenge_result: string; strongest_counterargument: string;
    confidence_challenge: string | null; recommended_overall_action: string; created_at: string }[];
  const [{ data: evid }, { data: prem }, { data: flagRows }] = await Promise.all([
    supabase.from("assessment_statement_evidence").select("statement_id,object_type,object_id,role").in("statement_id", sIds.length ? sIds : none),
    supabase.from("assessment_statement_premises").select("statement_id,premise_statement_id").in("statement_id", sIds.length ? sIds : none),
    supabase.from("challenge_flags").select("*").in("challenge_run_id", runs.length ? runs.map((r) => r.id) : none).order("flag_no"),
  ]);
  const flags = (flagRows ?? []) as Flag[];
  const { data: disp } = await supabase.from("challenge_flag_dispositions").select("*").in("flag_id", flags.length ? flags.map((f) => f.id) : none)
    .order("created_at", { ascending: false });
  const dispBy = new Map<string, { disposition: string; reason: string; created_at: string }[]>();
  for (const d of (disp ?? []) as { flag_id: string; disposition: string; reason: string; created_at: string }[]) {
    dispBy.set(d.flag_id, [...(dispBy.get(d.flag_id) ?? []), d]);
  }
  const evidence = (evid ?? []) as { statement_id: string; object_type: string; object_id: string; role: string }[];
  const claimIds = [...new Set(evidence.filter((e) => e.object_type === "claim").map((e) => e.object_id))];
  const { data: cl } = await supabase.from("claims").select("id,claim_text_normalised,attribution").in("id", claimIds.length ? claimIds : none);
  const claim = new Map(((cl ?? []) as { id: string; claim_text_normalised: string; attribution: string | null }[]).map((c) => [c.id, c]));
  const localOf = new Map(statements.map((s) => [s.id, s.statement_local_id]));
  const premises = new Map<string, string[]>();
  for (const p of (prem ?? []) as { statement_id: string; premise_statement_id: string }[]) {
    premises.set(p.statement_id, [...(premises.get(p.statement_id) ?? []), localOf.get(p.premise_statement_id) ?? p.premise_statement_id]);
  }
  const jobs = await requestsFor([id, av.event_version_id], ["CHALLENGE_ASSESSMENT", "ASSESS_EVENT"]);
  const reviewer = can(session, "ASSESSMENT_REVIEW");
  const confSetter = can(session, "FINAL_CONFIDENCE_SET");
  const reviewable = state && ["IN_REVIEW", "ESCALATED"].includes(state.state) && (later ?? []).length === 0;
  const challenged = runs.length > 0;
  const event = ev as { event_id: string; title: string; version_no: number } | null;
  const groups = (["FACT", "ASSUMPTION", "ASSESSMENT"] as const).map((g) => ({ g, items: statements.filter((s) => s.epistemic_category === g) }));
  return (
    <>
      <PageHeader title={event?.title ?? "Assessment"}
        crumbs={[{ href: "/", label: "Dashboard" }, { href: "/assessments", label: "Assessments" }, { label: `v${av.version_no}` }]}
        badges={<><Badge value={state?.state} /><Badge value={av.report_mode} /></>}
        lede={<>Assessment version {av.version_no} ({av.origin}) of event{" "}
          {event && <a href={`/events/${event.event_id}`}>v{event.version_no}</a>} · information cutoff <When at={av.information_cutoff} /> · hash{" "}
          <Short id={av.content_hash} n={12} /></>} />
      <Flash ok={ok} error={error} />
      {(later ?? []).length > 0 && <div className="alert warn"><div>A later version of this assessment exists — this one is read-only.{" "}
        {(later as { id: string; version_no: number }[]).map((l) => <a key={l.id} href={`/assessments/${l.id}`}>open v{l.version_no}</a>)}</div></div>}
      <Steps steps={[
        { label: "M07 draft", detail: <div>{av.origin === "AI" ? "model draft" : "human version"}</div>, state: "done" },
        { label: "M08 challenge", detail: <div>{challenged ? runs[0].challenge_result.replaceAll("_", " ") : "pending"}</div>, state: challenged ? "done" : "current" },
        { label: "Human review", detail: <div>{state?.state ?? "—"}</div>, state: state?.state === "APPROVED" ? "done" : challenged ? "current" : "todo" },
        { label: "Approved for reports", detail: <div>{state?.final_analytic_confidence ? `final ${state.final_analytic_confidence}` : "not yet"}</div>,
          state: state?.state === "APPROVED" ? "done" : "todo" },
      ]} />
      <div className="split">
        <div>
          {groups.map(({ g, items }) => items.length > 0 && (
            <Card key={g} title={<span className="row">{g === "FACT" ? "Facts (reported, attributed)" : g === "ASSUMPTION" ? "Assumptions" : "Assessments (analytic judgement)"}{" "}
              <EpistemicBadge category={g} /></span>} tone={g === "ASSESSMENT" ? "accent" : undefined}>
              {items.map((s) => {
                const ev2 = evidence.filter((e) => e.statement_id === s.id);
                return (
                  <article key={s.id} style={{ borderTop: "1px solid var(--border)", paddingTop: 10, marginTop: 10 }}>
                    <div className="row" style={{ marginBottom: 4 }}>
                      <b>{s.statement_local_id}</b><Badge tone="outline">{s.statement_type}</Badge><EpistemicBadge category={s.epistemic_category} />
                      <Badge tone="neutral">{s.provenance_class}</Badge>
                      {s.likelihood_term && <Badge tone="violet" title="likelihood = how probable">likelihood: {s.likelihood_term.replaceAll("_", " ")}</Badge>}
                    </div>
                    <p className="quote" style={{ margin: "4px 0" }}>{s.statement_text}</p>
                    <div className="muted" style={{ fontSize: 12.5 }}>
                      {s.attribution_required && <div>attribution required: “{s.attribution_text}”</div>}
                      {s.likelihood_rationale && <div>likelihood rationale: {s.likelihood_rationale}</div>}
                      {premises.get(s.id) && <div>premises: {premises.get(s.id)!.join(", ")}</div>}
                      {sourceStatus(s.source_epistemic_status)}
                    </div>
                    {ev2.length > 0 && <ul style={{ margin: "6px 0 0", paddingLeft: 18, fontSize: 12.5 }}>{ev2.map((e, i) => (
                      <li key={i}><Badge value={e.role} />{" "}{e.object_type === "claim" ? <a href={`/claims/${e.object_id}`}>{claim.get(e.object_id)?.claim_text_normalised ?? e.object_id}</a>
                        : <>{e.object_type} <Short id={e.object_id} /></>}</li>))}</ul>}
                  </article>);
              })}
            </Card>
          ))}
          {(av.content.derived_summary?.text || (av.content.indicators_to_watch ?? []).length > 0) && (
            <Card title="Derived summary and indicators">
              {av.content.derived_summary?.text && <p>{av.content.derived_summary.text}</p>}
              <ul>{(av.content.indicators_to_watch ?? []).map((i) => <li key={i.indicator_local_id}><b>{i.indicator_local_id}</b> {i.indicator_text}
                <span className="muted"> — observable: {i.observable_condition}</span></li>)}</ul>
            </Card>
          )}
          <Card title="M08 structured challenge" tone={flags.some((f) => ["CRITICAL", "MAJOR"].includes(f.severity)) ? "danger" : undefined}>
            {runs.length === 0 ? <p className="muted">The M08 challenge has not run yet — human review is possible only after it.</p> : runs.slice(0, 1).map((r) => (
              <div key={r.id}>
                <KV rows={[["Result", <Badge key="r" tone="violet">{r.challenge_result.replaceAll("_", " ")}</Badge>],
                  ["Strongest counter-argument", r.strongest_counterargument], ["Confidence challenge", r.confidence_challenge ?? "—"],
                  ["Recommended", r.recommended_overall_action], ["Run", <span key="m"><Short id={r.model_run_id} /> · <When at={r.created_at} /></span>]]} />
                {flags.map((f) => {
                  const d = dispBy.get(f.id) ?? [];
                  return (
                    <div key={f.id} className="card flat" style={{ marginTop: 10, marginBottom: 0 }}>
                      <div className="row"><b>Flag {f.flag_no}</b><Badge value={f.severity} /><Badge tone="outline">{f.flag_type}</Badge>
                        {f.affected_statement_id && <span className="muted">on {localOf.get(f.affected_statement_id) ?? "statement"}</span>}
                        {d[0] ? <Badge value={d[0].disposition === "ACCEPTED" ? "APPROVED" : d[0].disposition}>{d[0].disposition}</Badge> : <Badge tone="warn">undisposed</Badge>}</div>
                      <p style={{ margin: "6px 0" }}>{f.explanation}</p>
                      <div className="muted" style={{ fontSize: 12.5 }}>recommended: {f.recommended_action}</div>
                      {d.map((x, i) => <div key={i} className="muted" style={{ fontSize: 12.5 }}>disposition {x.disposition} · <When at={x.created_at} /> — {x.reason}</div>)}
                      {reviewer && (
                        <form action={disposeFlag} className="form-row" style={{ marginTop: 8 }}>
                          <input type="hidden" name="version_id" value={id} />
                          <input type="hidden" name="flag_id" value={f.id} />
                          <div className="field"><label>Disposition</label><select name="disposition">{FLAG_DISPOSITIONS.map((x) => <option key={x}>{x}</option>)}</select></div>
                          <div className="field"><label>Reason (audited)</label><input name="reason" required minLength={5} /></div>
                          <Submit small>Record</Submit>
                        </form>
                      )}
                    </div>);
                })}
              </div>
            ))}
            {!challenged && <JobRequestForm jobType="CHALLENGE_ASSESSMENT" returnTo={`/assessments/${id}`} allowed={reviewer}
              lockedReason="Needs ASSESSMENT_REVIEW." cta="Request M08 challenge" hidden={{ assessment_version_id: id, assessment_version_hash: av.content_hash }}
              defaultReason="analyst requests the structured challenge"
              note="The worker normally runs M08 automatically after M07; this re-request is idempotent (no second challenge of one version)." />}
          </Card>
          <Card title="History (audit)">
            <ul className="timeline">
              {((hist ?? []) as { id: string; old_state: string | null; new_state: string; actor_type: string; reason: string; created_at: string }[]).map((h) => (
                <li key={h.id}>{h.old_state ?? "∅"} → <Badge value={h.new_state} /> <span className="muted">{h.actor_type}</span> <When at={h.created_at} /> — {h.reason}</li>))}
              {((appr ?? []) as { id: string; decision: string; final_analytic_confidence: string | null; reason: string; created_at: string }[]).map((a) => (
                <li key={a.id}>human decision <Badge value={a.decision} />{a.final_analytic_confidence && <> final confidence <Badge value={a.final_analytic_confidence} /></>}{" "}
                  <When at={a.created_at} /> — {a.reason}</li>))}
            </ul>
          </Card>
        </div>
        <div>
          <Card title="Confidence and likelihood">
            <KV rows={[
              ["AI recommended confidence (M07)", av.ai_recommended_confidence ? <Badge tone="outline">{av.ai_recommended_confidence}</Badge> : "—"],
              ["AI rationale", av.ai_confidence_rationale ?? "—"],
              ["Final analytic confidence (human)", state?.final_analytic_confidence ? <Badge value={state.final_analytic_confidence} /> : <span className="muted">not set — only an approval sets it</span>],
              ["Human rationale", state?.final_confidence_rationale ?? "—"],
              ["Likelihood terms", statements.filter((s) => s.likelihood_term).map((s) => `${s.statement_local_id}: ${s.likelihood_term}`).join(" · ") || "—"],
              ["M07 run", run ? <span key="r">{(run as { module_code: string }).module_code} {(run as { prompt_semver: string }).prompt_semver} · {(run as { provider: string }).provider}/{(run as { model: string }).model}</span> : "—"],
            ]} />
            <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>Likelihood says how probable a judgement is; analytic confidence says how well-founded the
              assessment is. They are recorded and shown separately.</p>
          </Card>
          <Card title="Human analytical review" tone="warn">
            <JobStatusLine rows={jobs} />
            {!reviewer ? <Locked>Review needs ASSESSMENT_REVIEW (analyst, reviewer).</Locked>
              : !reviewable ? <Locked>{state?.state === "APPROVED" ? "Approved — this version is now eligible as a report candidate (as of its cutoff)."
                : !challenged ? "The M08 challenge must run before a human review." : `State ${state?.state}: no review decision is open for this version.`}</Locked> : (
              <form action={reviewAssessment} className="form">
                <input type="hidden" name="version_id" value={id} />
                <input type="hidden" name="version_hash" value={av.content_hash} />
                <div className="field"><label htmlFor="decision">Decision</label>
                  <select id="decision" name="decision">{ASSESSMENT_DECISIONS.map((d) => <option key={d}>{d}</option>)}</select>
                  <span className="help">REQUEST_REPROCESSING returns the draft; ESCALATE keeps it open for a senior decision.</span></div>
                {confSetter ? (
                  <>
                    <div className="field"><label htmlFor="final_confidence">Final analytic confidence (APPROVE only)</label>
                      <select id="final_confidence" name="final_confidence" defaultValue=""><option value="">—</option>{CONFIDENCE.map((c) => <option key={c}>{c}</option>)}</select></div>
                    <div className="field"><label htmlFor="confidence_rationale">Confidence rationale (≥ 20 characters, APPROVE only)</label>
                      <textarea id="confidence_rationale" name="confidence_rationale" rows={2} /></div>
                  </>
                ) : <Locked>Your role cannot set the final analytic confidence (FINAL_CONFIDENCE_SET), so it cannot approve.</Locked>}
                <div className="field"><label htmlFor="reason">Reason (audited)</label><input id="reason" name="reason" required minLength={5} /></div>
                <Confirm>I reviewed the statements, their evidence and the M08 flags of this exact version.</Confirm>
                <Submit kind="primary">Record review decision</Submit>
              </form>
            )}
          </Card>
          {reviewer && confSetter && reviewable && (
            <Card title="Modify and approve (new immutable version)">
              <details className="panel"><summary>Edit statement wording</summary><div className="panel-body">
                <form action={modifyAndApprove} className="form">
                  <input type="hidden" name="version_id" value={id} />
                  <input type="hidden" name="version_hash" value={av.content_hash} />
                  {statements.map((s) => <div key={s.id} className="field"><label>{s.statement_local_id} · {s.statement_type}</label>
                    <textarea name={`text_${s.statement_local_id}`} defaultValue={s.statement_text} rows={2} /></div>)}
                  <p className="muted" style={{ margin: 0, fontSize: 12 }}>Types, evidence, premises and likelihood are kept; the database re-validates
                    provenance and records the original as SUPERSEDED.</p>
                  <div className="field"><label>Final analytic confidence</label><select name="final_confidence" required>{CONFIDENCE.map((c) => <option key={c}>{c}</option>)}</select></div>
                  <div className="field"><label>Confidence rationale (≥ 20 characters)</label><textarea name="confidence_rationale" required minLength={20} rows={2} /></div>
                  <div className="field"><label>Reason (audited)</label><input name="reason" required minLength={5} /></div>
                  <Confirm>I take responsibility for the modified wording.</Confirm>
                  <Submit>Modify and approve</Submit>
                </form>
              </div></details>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}

/** Per-claim epistemic status recorded with the statement (status, source statement status, corroboration). */
function sourceStatus(v: unknown) {
  const rows = (Array.isArray(v) ? v : v ? [v] : []) as { claim_id?: string; claim_status?: string; source_statement_status?: string;
    corroborated_for_attribution?: boolean; high_impact?: boolean }[];
  if (rows.length === 0) return null;
  return <div>source status: {rows.map((r, i) => <span key={i} style={{ marginRight: 8 }}>{r.claim_status ?? "?"}
    {r.source_statement_status ? ` · ${r.source_statement_status}` : ""}{r.corroborated_for_attribution ? " · corroborated" : ""}
    {r.high_impact ? " · high impact" : ""}</span>)}</div>;
}
