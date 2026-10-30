import { can, requireSession } from "@/lib/auth";
import {
  type CanonicalReport, EDITORIAL_TRANSFORMS, SECTION_TITLES, SELECTABLE_SECTIONS, SELECTION_DECISIONS, confidenceLabel, diffVersions,
} from "@/lib/reports";
import { createClient } from "@/lib/supabase/server";
import { AutopilotCard, type AutopilotRow } from "@/components/autopilot";
import { Badge, Flash, PageHeader, Tabs, When } from "@/components/ui";

import {
  decideCandidate, decideRemovals, editStatement, freezeSelection, moveStatement, refreshCandidates, removeStatement,
} from "../actions";
import { QaPanel, ReleasePanel } from "./release-panels";

export const dynamic = "force-dynamic";

interface Candidate {
  candidate_id: string; candidate_type: string; object_id: string; object_hash: string; recommended_section: string;
  recommended_rank: number | null; latest_decision_id: string | null; latest_decision: string | null;
  selected_section: string | null; selected_priority: number | null;
}
interface VersionState {
  report_version_id: string; version_no: number; report_version_hash: string; origin: string; length_status: string;
  length_review_required: boolean; length_review_pending: boolean; removal_proposals: number; is_latest: boolean; created_at: string;
}
interface AStatement {
  id: string; assessment_version_id: string; statement_local_id: string; statement_type: string; epistemic_category: string;
  statement_text: string; attribution_required: boolean; attribution_text: string | null; likelihood_term: string | null;
}
interface Proposal { id: string; proposal_no: number; target_item_local_id: string | null; target_statement_local_id: string | null; reason: string }

const confStyle: Record<string, object> = {
  "conf-high": { borderLeft: "4px solid #1f4e79" }, "conf-moderate": { borderLeft: "4px solid #5b6f84" },
  "conf-low": { borderLeft: "4px dashed #8a6d3b" }, "conf-none": { borderLeft: "4px dotted #bbb" },
};

export default async function ReportWorkspace({
  params, searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ view?: string; version?: string; a?: string; b?: string; error?: string; ok?: string }>;
}) {
  const { id } = await params;
  const { view = "pool", version, a, b, error, ok } = await searchParams;
  const session = await requireSession();
  if (!can(session, "CLAIM_READ")) return <p>You do not have permission to view reports.</p>;
  const editor = can(session, "REPORT_EDIT");
  const supabase = await createClient();

  const { data: report } = await supabase.from("reports").select("*").eq("id", id).single();
  if (!report) return <p>Unknown report.</p>;
  const { data: apData } = await supabase.from("report_autopilot").select("report_id,enabled,reason,changed_at");
  const [{ data: candData }, { data: versionData }] = await Promise.all([
    supabase.from("report_candidate_state").select("*").eq("report_id", id).order("created_at"),
    supabase.from("report_version_states").select("*").eq("report_id", id).order("version_no", { ascending: false }),
  ]);
  const cands = (candData ?? []) as Candidate[];
  const versions = (versionData ?? []) as VersionState[];
  const assessmentIds = cands.filter((c) => c.candidate_type === "ASSESSMENT_VERSION").map((c) => c.object_id);
  const { data: avStates } = await supabase.from("assessment_version_states")
    .select("assessment_version_id,final_analytic_confidence,state,event_version_id").in("assessment_version_id", assessmentIds);
  const avState = new Map(((avStates ?? []) as { assessment_version_id: string; final_analytic_confidence: string | null; state: string; event_version_id: string }[])
    .map((r) => [r.assessment_version_id, r]));

  const current = versions.find((v) => v.report_version_id === version) ?? versions[0];
  let canonical: CanonicalReport | null = null;
  let proposals: Proposal[] = [];
  let render: { content: string; template_version: string; renderer_version: string; content_sha256: string } | null = null;
  const sources = new Map<string, AStatement>();
  const claimsBySource = new Map<string, { claim_id: string; text: string; role: string }[]>();
  if (current) {
    const [{ data: v }, { data: p }, { data: r }] = await Promise.all([
      supabase.from("report_versions").select("canonical_json").eq("id", current.report_version_id).single(),
      supabase.from("report_removal_proposals").select("*").eq("report_version_id", current.report_version_id).order("proposal_no"),
      supabase.from("report_renders").select("content,template_version,renderer_version,content_sha256")
        .eq("report_version_id", current.report_version_id).limit(1),
    ]);
    canonical = (v?.canonical_json ?? null) as CanonicalReport | null;
    proposals = (p ?? []) as Proposal[];
    render = (r ?? [])[0] ?? null;
    const ids = [...new Set(canonical?.sections.flatMap((s) => s.items.flatMap((i) => i.statements.flatMap((st) => st.sources))) ?? [])];
    if (ids.length) {
      const [{ data: st }, { data: ev }] = await Promise.all([
        supabase.from("assessment_statements").select("*").in("id", ids),
        supabase.from("assessment_statement_evidence").select("statement_id,object_type,object_id,role").in("statement_id", ids),
      ]);
      for (const s of (st ?? []) as AStatement[]) sources.set(s.id, s);
      const evid = (ev ?? []) as { statement_id: string; object_type: string; object_id: string; role: string }[];
      const claimIds = evid.filter((e) => e.object_type === "claim").map((e) => e.object_id);
      const { data: cl } = claimIds.length
        ? await supabase.from("claims").select("id,claim_text_normalised").in("id", claimIds) : { data: [] };
      const ctext = new Map(((cl ?? []) as { id: string; claim_text_normalised: string }[]).map((c) => [c.id, c.claim_text_normalised]));
      for (const e of evid.filter((x) => x.object_type === "claim")) {
        claimsBySource.set(e.statement_id, [...(claimsBySource.get(e.statement_id) ?? []),
          { claim_id: e.object_id, text: ctext.get(e.object_id) ?? "(not visible)", role: e.role }]);
      }
    }
  }
  const link = (v: string, extra = "") => `/reports/${id}?view=${v}${current ? `&version=${current.report_version_id}` : ""}${extra}`;
  const hidden = (vs: VersionState) => (
    <>
      <input type="hidden" name="report_id" value={id} />
      <input type="hidden" name="version_id" value={vs.report_version_id} />
      <input type="hidden" name="version_hash" value={vs.report_version_hash} />
    </>
  );

  return (
    <main>
      <PageHeader title={report.title} crumbs={[{ href: "/", label: "Dashboard" }, { href: "/reports", label: "Reports" }, { label: report.code }]}
        badges={<><Badge value={report.report_mode} />{current && <Badge tone="outline">v{current.version_no}</Badge>}</>}
        lede={<>{report.code} · cycle {report.cycle_label} · information cutoff <When at={report.information_cutoff} /> · built only from approved
          Phase 4 material you select; M09 suggests wording, every inclusion and removal is your decision.</>} />
      <Tabs current={view} items={[["pool", "Candidate pool"], ["draft", "Draft"], ["versions", "Versions"], ["preview", "Preview"],
        ["qa", "QA"], ["release", "Approvals & release"]].map(([k, l]) => ({ key: k, label: l, href: link(k) }))} />
      <Flash ok={ok} error={error} />
      {view === "pool" && <AutopilotCard reports={[{ id, code: report.code, report_mode: report.report_mode, information_cutoff: report.information_cutoff }]}
        state={(apData ?? []) as AutopilotRow[]} allowed={can(session, "EVENT_ACTION")} fixedReport={id} />}

      {view === "pool" && (
        <section>
          <h2>Candidate pool</h2>
          <p className="muted">Only approved, as-of current Phase 4 material for this report&apos;s mode and cutoff appears here. Nothing is
            ever removed from the pool; inclusion is your decision.</p>
          {editor && (
            <form action={refreshCandidates} style={{ marginBottom: 8 }}>
              <input type="hidden" name="report_id" value={id} />
              <button type="submit">Refresh eligible candidates</button>
            </form>
          )}
          {cands.map((c) => {
            const st = avState.get(c.object_id);
            const conf = confidenceLabel(st?.final_analytic_confidence);
            return (
              <div key={c.candidate_id} className="card" style={confStyle[conf.cls]}>
                <div><strong>{c.candidate_type}</strong> {c.object_id} <span className="muted">hash {c.object_hash.slice(0, 12)}…</span></div>
                <div className="muted">
                  recommended {c.recommended_section}{c.recommended_rank !== null && <> · M06 priority {c.recommended_rank}</>}
                  {st && <> · {conf.label} · assessment state {st.state} · event version {st.event_version_id}</>}
                </div>
                <div>Decision: <strong>{c.latest_decision ?? "none"}</strong>
                  {c.selected_section && <> → {c.selected_section} (priority {c.selected_priority})</>}</div>
                {editor && (
                  <form action={decideCandidate} style={{ marginTop: 6 }}>
                    <input type="hidden" name="report_id" value={id} />
                    <input type="hidden" name="candidate_id" value={c.candidate_id} />
                    <input type="hidden" name="object_hash" value={c.object_hash} />
                    <input type="hidden" name="expected_previous_decision_id" value={c.latest_decision_id ?? ""} />
                    <select name="decision">{SELECTION_DECISIONS.map((d) => <option key={d}>{d}</option>)}</select>{" "}
                    <select name="section" defaultValue={c.selected_section ?? c.recommended_section}>
                      <option value="" />{(SELECTABLE_SECTIONS[c.candidate_type] ?? []).map((s) => <option key={s}>{s}</option>)}
                    </select>{" "}
                    <input name="priority" type="number" min={1} max={999} defaultValue={c.selected_priority ?? 1} style={{ width: 60 }} />{" "}
                    <input name="reason" placeholder="reason" required minLength={5} />{" "}
                    <button type="submit">Record</button>
                  </form>
                )}
              </div>
            );
          })}
          {cands.length === 0 && <p>No eligible approved material yet.</p>}
          {editor && cands.some((c) => c.latest_decision === "INCLUDE") && (
            <form action={freezeSelection} className="card" style={{ background: "#f6f8fa" }}>
              <input type="hidden" name="report_id" value={id} />
              <strong>Freeze the included selection and request the M09 draft</strong>{" "}
              <input name="reason" placeholder="reason" required minLength={5} /> <button type="submit">Request M09 draft</button>
            </form>
          )}
        </section>
      )}

      {view === "draft" && (!current || !canonical) && <p>No draft yet. Select candidates and request the M09 draft.</p>}
      {view === "draft" && current && canonical && (
        <section>
          <h2>Draft version {current.version_no} <span className="muted">({current.origin}, {current.report_version_hash.slice(0, 16)}…)</span></h2>
          <p className="muted">State DRAFT_VERSION · length {current.length_status}
            {current.length_review_pending && <strong style={{ color: "#a50" }}> · REPORT_LENGTH_REVIEW_REQUIRED — your decision is pending</strong>}
            {!current.is_latest && <strong style={{ color: "#a00" }}> · not the latest version (read-only)</strong>}</p>
          {current.length_review_pending && editor && current.is_latest && (
            <form action={decideRemovals} className="card" style={{ borderColor: "#a50" }}>
              {hidden(current)}
              <input type="hidden" name="proposal_ids" value={proposals.map((p) => p.id).join(",")} />
              <strong>M09 removal proposals (substantive removal is your decision)</strong>
              {proposals.length === 0 && <p>No proposals: confirm to keep the current length.</p>}
              {proposals.map((p) => (
                <div key={p.id}>
                  #{p.proposal_no} remove {p.target_item_local_id ? `item ${p.target_item_local_id}` : `statement ${p.target_statement_local_id}`}
                  {" "}— <em>{p.reason}</em>{" "}
                  <label><input type="radio" name={`decision_${p.id}`} value="ACCEPT" required /> accept</label>{" "}
                  <label><input type="radio" name={`decision_${p.id}`} value="REJECT" /> keep</label>
                </div>
              ))}
              <input name="reason" placeholder="reason" required minLength={5} /> <button type="submit">Record removal decisions</button>
            </form>
          )}
          {canonical.sections.map((sec) => {
            const cov = canonical!.coverage.find((c) => c.section === sec.section);
            return (
              <div key={sec.section} style={{ marginBottom: 10 }}>
                <h3 style={{ marginBottom: 4 }}>{SECTION_TITLES[sec.section]}
                  {cov && (cov.target_min !== null || cov.target_max !== null) && (
                    <small className="muted"> ({cov.count} of target {cov.target_min ?? "–"}–{cov.target_max ?? "–"}
                      {cov.below_target && " · below target: no filler is generated"}{cov.above_target && " · above target"})</small>)}
                </h3>
                {sec.items.length === 0 && <p className="muted"><em>No approved material was selected for this section.</em></p>}
                {sec.items.map((it) => {
                  const conf = confidenceLabel(it.final_analytic_confidence);
                  return (
                    <article key={it.item_local_id} className="card" style={confStyle[conf.cls]}>
                      <div className="muted">{it.item_local_id} · {conf.label} · pinned{" "}
                        {Object.entries(it.pins).filter(([, v]) => v).map(([k, v]) => `${k} ${v!.id.slice(0, 8)}…`).join(", ")}</div>
                      {it.statements.map((st, n) => (
                        <div key={st.report_statement_local_id} style={{ margin: "6px 0" }}>
                          <div style={st.statement_role === "CAVEAT" ? { color: "#555" } : undefined}>
                            {st.statement_role === "CAVEAT" && <strong>Caveat: </strong>}{st.text}
                            {st.likelihood_term && <span className="muted"> [likelihood: {st.likelihood_term}]</span>}
                            {st.contested && <strong style={{ color: "#9a3412" }}> [contested]</strong>}
                          </div>
                          <details>
                            <summary className="muted">{st.report_statement_local_id} · {st.statement_role} · {st.editorial_transform} · provenance</summary>
                            <ul>
                              {st.sources.map((sid) => {
                                const s = sources.get(sid);
                                return (
                                  <li key={sid}>
                                    {s ? <>{s.statement_local_id} {s.statement_type} ({s.epistemic_category}): “{s.statement_text}”
                                      {s.attribution_required && <span className="muted"> · attribution required: “{s.attribution_text}”</span>}
                                      {s.likelihood_term && <span className="muted"> · likelihood {s.likelihood_term}</span>}
                                      <span className="muted"> · assessment version {s.assessment_version_id}</span></> : sid}
                                    <ul>{(claimsBySource.get(sid) ?? []).map((c) => (
                                      <li key={c.claim_id} className="muted">{c.role} claim {c.claim_id}: {c.text}</li>))}</ul>
                                  </li>
                                );
                              })}
                            </ul>
                            {editor && current.is_latest && (
                              <>
                                <form action={editStatement} style={{ display: "grid", gap: 4, maxWidth: 760 }}>
                                  {hidden(current)}
                                  <input type="hidden" name="statement_local_id" value={st.report_statement_local_id} />
                                  <textarea name="text" defaultValue={st.text} rows={2} required />
                                  <select name="editorial_transform" defaultValue="PARAPHRASE">
                                    {EDITORIAL_TRANSFORMS.map((t) => <option key={t}>{t}</option>)}</select>
                                  <input name="reason" placeholder="reason for the edit" required minLength={5} />
                                  <button type="submit">Save as new version (sources kept)</button>
                                </form>
                                <form action={moveStatement} style={{ display: "inline" }}>
                                  {hidden(current)}
                                  <input type="hidden" name="statement_local_id" value={st.report_statement_local_id} />
                                  <input type="hidden" name="reason" value="analyst reorders statements" />
                                  {n > 0 && <button name="direction" value="up">↑</button>}
                                  {n < it.statements.length - 1 && <button name="direction" value="down">↓</button>}
                                </form>{" "}
                                <form action={removeStatement} style={{ display: "inline" }}>
                                  {hidden(current)}
                                  <input type="hidden" name="statement_local_id" value={st.report_statement_local_id} />
                                  <input name="reason" placeholder="why remove (human decision)" required minLength={5} />
                                  <button type="submit">Remove (new version)</button>
                                </form>
                              </>
                            )}
                          </details>
                        </div>
                      ))}
                    </article>
                  );
                })}
              </div>
            );
          })}
          {canonical.human_removals.length > 0 && <p className="muted">Removed by human decision: {canonical.human_removals.join(", ")}</p>}
        </section>
      )}

      {view === "versions" && (
        <section>
          <h2>Versions</h2>
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead><tr><th align="left">#</th><th align="left">origin</th><th align="left">hash</th><th align="left">length</th><th /></tr></thead>
            <tbody>{versions.map((v) => (
              <tr key={v.report_version_id} style={{ borderTop: "1px solid #ddd" }}>
                <td>{v.version_no}</td><td>{v.origin}</td><td><code>{v.report_version_hash.slice(0, 20)}…</code></td>
                <td>{v.length_status}{v.length_review_pending && " · review pending"}</td>
                <td><a href={`/reports/${id}?view=draft&version=${v.report_version_id}`}>open</a></td>
              </tr>))}</tbody>
          </table>
          {versions.length > 1 && (
            <form method="get" style={{ marginTop: 8 }}>
              <input type="hidden" name="view" value="versions" />
              Compare <select name="a" defaultValue={a ?? versions[1].report_version_id}>{versions.map((v) => <option key={v.report_version_id} value={v.report_version_id}>v{v.version_no}</option>)}</select>
              {" "}with <select name="b" defaultValue={b ?? versions[0].report_version_id}>{versions.map((v) => <option key={v.report_version_id} value={v.report_version_id}>v{v.version_no}</option>)}</select>
              {" "}<button type="submit">Compare</button>
            </form>
          )}
          {a && b && <VersionCompare a={a} b={b} />}
        </section>
      )}

      {view === "qa" && (current ? <QaPanel reportId={id} v={current} session={session} /> : <p>No version yet.</p>)}
      {view === "release" && (current ? <ReleasePanel reportId={id} v={current} session={session} /> : <p>No version yet.</p>)}

      {view === "preview" && (
        <section>
          <h2>Deterministic preview</h2>
          {!render && <p>No preview rendered yet for this version (the worker renders every new version).</p>}
          {render && (
            <>
              <p className="muted">PREVIEW of version {current?.version_no} · {render.template_version} · {render.renderer_version} · sha256 {render.content_sha256.slice(0, 16)}…
                — not QA-approved, not security-reviewed, not released.</p>
              <iframe title="report preview" sandbox="" srcDoc={render.content} style={{ width: "100%", height: 1100, border: "1px solid #ccc" }} />
            </>
          )}
        </section>
      )}
    </main>
  );
}

async function VersionCompare({ a, b }: { a: string; b: string }) {
  const supabase = await createClient();
  const { data } = await supabase.from("report_versions").select("id,version_no,canonical_json,report_version_hash").in("id", [a, b]);
  const rows = (data ?? []) as { id: string; version_no: number; canonical_json: CanonicalReport; report_version_hash: string }[];
  const A = rows.find((r) => r.id === a);
  const B = rows.find((r) => r.id === b);
  if (!A || !B) return <p>Unknown version.</p>;
  const diff = diffVersions(A.canonical_json, B.canonical_json).filter((d) => d.kind !== "unchanged");
  return (
    <div style={{ marginTop: 10 }}>
      <p className="muted">v{A.version_no} ({A.report_version_hash.slice(0, 12)}…) → v{B.version_no} ({B.report_version_hash.slice(0, 12)}…)</p>
      {diff.length === 0 && <p>No statement-level difference.</p>}
      {diff.map((d) => (
        <div key={d.key} className="card" style={{ borderLeft: `4px solid ${d.kind === "added" ? "#2a7" : d.kind === "removed" ? "#c33" : "#c90"}` }}>
          <strong>{d.kind}</strong> <code>{d.key}</code>{d.sourcesChanged && d.kind === "changed" && " · sources changed"}
          {d.before !== undefined && <div style={{ color: "#a00" }}>− {d.before}</div>}
          {d.after !== undefined && <div style={{ color: "#070" }}>+ {d.after}</div>}
        </div>
      ))}
    </div>
  );
}
