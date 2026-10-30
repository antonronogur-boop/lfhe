import { type Session, can } from "@/lib/auth";
import {
  CONTENT_DECISIONS, type Eligibility, type Finding, RELEASE_RETURN_DECISIONS, SECURITY_DECISIONS, checklistRows, groupFindings,
  needsAcknowledgement, workflowLabel,
} from "@/lib/release";
import { createClient } from "@/lib/supabase/server";

import {
  acknowledgeWarning, decideContent, decideRelease, decideSecurity, releaseReport, requestQa, requestReleasePdf,
} from "../release-actions";

/*
 * Phase 6 workspace panels (server components). Everything shown is read from the database under
 * RLS; every button posts to a server action that calls a HUMAN_ONLY function. Showing or hiding a
 * button never grants authority — the database decides.
 */
const sevColor: Record<string, string> = { CRITICAL: "#a00", MAJOR: "#b45309", WARNING: "#a16207", INFO: "#555" };

interface Version { report_version_id: string; version_no: number; report_version_hash: string; is_latest: boolean }
interface Workflow {
  workflow_state: string; qa_result_id: string | null; qa_status: string | null; deterministic_qa_run_id: string | null;
  semantic_qa_run_id: string | null; warnings_total: number | null; warnings_acknowledged: number; content_approval_id: string | null;
  content_decision: string | null; security_review_id: string | null; security_status: string | null; release_decision: string | null;
  report_release_id: string | null; released_at: string | null; released_by: string | null; manifest_hash: string | null; pdf_sha256: string | null;
}
interface QaRun { id: string; kind: string; status: string; invalid_reasons: string[]; model_run_id: string | null; engine_version: string | null;
  diagnostic_only: boolean; created_at: string }
interface QaResult { id: string; result_no: number; status: string; fail_reasons: string[]; deterministic_qa_run_id: string; semantic_qa_run_id: string;
  changed_by_rerun: boolean; created_at: string }

function Hidden({ reportId, v }: { reportId: string; v: Version }) {
  return (
    <>
      <input type="hidden" name="report_id" value={reportId} />
      <input type="hidden" name="version_id" value={v.report_version_id} />
      <input type="hidden" name="version_hash" value={v.report_version_hash} />
    </>
  );
}

async function loadWorkflow(versionId: string) {
  const supabase = await createClient();
  const { data } = await supabase.from("report_version_workflow").select("*").eq("report_version_id", versionId).single();
  return (data ?? null) as Workflow | null;
}

export async function QaPanel({ reportId, v, session }: { reportId: string; v: Version; session: Session }) {
  const supabase = await createClient();
  const wf = await loadWorkflow(v.report_version_id);
  const [{ data: rs }, { data: runs }] = await Promise.all([
    supabase.from("qa_results").select("*").eq("report_version_id", v.report_version_id).order("result_no", { ascending: false }),
    supabase.from("qa_runs").select("id,kind,status,invalid_reasons,model_run_id,engine_version,diagnostic_only,created_at")
      .eq("report_version_id", v.report_version_id).order("created_at", { ascending: false }),
  ]);
  const results = (rs ?? []) as QaResult[];
  const current = results[0] ?? null;
  const runById = new Map(((runs ?? []) as QaRun[]).map((r) => [r.id, r]));
  let findings: Finding[] = [];
  let acked = new Set<string>();
  if (current) {
    const [{ data: f }, { data: a }] = await Promise.all([
      supabase.from("qa_check_results").select("*").in("qa_run_id", [current.deterministic_qa_run_id, current.semantic_qa_run_id])
        .order("finding_no"),
      supabase.from("warning_acknowledgements").select("qa_check_result_id").eq("qa_result_id", current.id),
    ]);
    findings = (f ?? []) as Finding[];
    acked = new Set(((a ?? []) as { qa_check_result_id: string }[]).map((x) => x.qa_check_result_id));
  }
  const g = groupFindings(findings);
  const reviewer = can(session, "REPORT_CONTENT_APPROVE");
  const acker = can(session, "QA_WARNING_ACKNOWLEDGE");
  const requester = can(session, "REPORT_EDIT") || reviewer;
  const d = current ? runById.get(current.deterministic_qa_run_id) : undefined;
  const s = current ? runById.get(current.semantic_qa_run_id) : undefined;
  return (
    <section>
      <h2>QA — version {v.version_no}</h2>
      <p className="muted">report_version_id <code>{v.report_version_id}</code> · report_version_hash <code>{v.report_version_hash}</code></p>
      <p>Workflow state: <strong>{workflowLabel(wf?.workflow_state)}</strong>
        {!v.is_latest && <strong style={{ color: "#a00" }}> · not the latest version — QA and approvals do not apply</strong>}</p>
      {requester && v.is_latest && (
        <form action={requestQa} className="card">
          <Hidden reportId={reportId} v={v} />
          <strong>Request M10 QA (M10-D deterministic → M10-S semantic) for this exact version</strong>{" "}
          <input name="reason" placeholder="reason" required minLength={5} /> <button type="submit">Request QA</button>
        </form>
      )}
      {!current && <p>No QA result yet for this version.</p>}
      {current && (
        <>
          <div className="card" style={{ borderLeft: `4px solid ${current.status === "PASS" ? "#2a7" : current.status === "FAIL" ? "#c33" : "#c90"}` }}>
            <div>Combined QA (computed by the database): <strong>{current.status}</strong> · result #{current.result_no}
              {current.changed_by_rerun && " · changed by rerun"}</div>
            <div className="muted">M10-D {d?.status ?? "?"} ({d?.engine_version}) · M10-S {s?.status ?? "?"} (model run {s?.model_run_id ?? "—"})
              {s?.diagnostic_only && " · semantic run diagnostic only (deterministic CRITICAL)"}</div>
            {s && s.invalid_reasons?.length > 0 && <div style={{ color: "#a00" }}>M10-S invalid: {s.invalid_reasons.join(", ")}</div>}
            {current.fail_reasons.length > 0 && <div style={{ color: "#a00" }}>Fail reasons: {current.fail_reasons.join(", ")}</div>}
            <div className="muted">{g.blocking} release-blocking · {g.warnings} warning(s) requiring acknowledgement ({wf?.warnings_acknowledged ?? 0} acknowledged)
              · passed checks: {g.passedChecks.join(", ")}</div>
          </div>
          {g.groups.map((grp) => (
            <div key={grp.severity}>
              <h3 style={{ color: sevColor[grp.severity] }}>{grp.severity}</h3>
              {grp.findings.map((f) => (
                <div key={f.id} className="card" style={{ borderLeft: `4px solid ${sevColor[f.severity]}` }}>
                  <div><strong>{f.layer === "D" ? "M10-D" : "M10-S"} {f.check_id}</strong> · {f.status} · {f.finding_code}
                    {f.status === "FAIL" ? <strong style={{ color: "#a00" }}> · blocks release</strong> : null}
                    {needsAcknowledgement(f) && (acked.has(f.id) ? " · acknowledged" : <strong style={{ color: "#a16207" }}> · needs acknowledgement</strong>)}</div>
                  <div>{f.details}</div>
                  <div className="muted">affected statement {f.affected_statement_id ?? "—"} · object {f.affected_object_id ?? "—"} ·
                    recommended (advisory) {f.recommended_action}</div>
                  {f.evidence_refs.length > 0 && (
                    <details><summary className="muted">evidence / provenance ({f.evidence_refs.length})</summary>
                      <ul>{f.evidence_refs.map((r) => <li key={`${r.object_type}:${r.object_id}`}><code>{r.object_type}</code> {r.object_id}</li>)}</ul>
                    </details>
                  )}
                  {acker && v.is_latest && current.status === "PASS_WITH_WARNINGS" && needsAcknowledgement(f) && !acked.has(f.id) && (
                    <form action={acknowledgeWarning} style={{ marginTop: 6 }}>
                      <Hidden reportId={reportId} v={v} />
                      <input type="hidden" name="qa_result_id" value={current.id} />
                      <input type="hidden" name="finding_id" value={f.id} />
                      <input name="rationale" placeholder="acknowledgement rationale" required minLength={10} style={{ width: 360 }} />{" "}
                      <button type="submit">Acknowledge this warning</button>
                    </form>
                  )}
                </div>
              ))}
            </div>
          ))}
          {reviewer && v.is_latest && !wf?.content_decision && (
            <form action={decideContent} className="card" style={{ background: "#f6f8fa" }}>
              <Hidden reportId={reportId} v={v} />
              <input type="hidden" name="qa_result_id" value={current.id} />
              <strong>Content decision on QA result #{current.result_no} ({current.status}) for hash {v.report_version_hash.slice(0, 16)}…</strong>{" "}
              <select name="decision">{CONTENT_DECISIONS.map((x) => <option key={x}>{x}</option>)}</select>{" "}
              <input name="rationale" placeholder="rationale" required minLength={10} style={{ width: 320 }} />{" "}
              <button type="submit">Record content decision</button>
            </form>
          )}
          {wf?.content_decision && <p>Content decision: <strong>{wf.content_decision}</strong> ({wf.content_approval_id})</p>}
          <details><summary>QA history ({results.length} result(s), runs preserved)</summary>
            <ul>{results.map((r) => <li key={r.id}>#{r.result_no} {r.status} · D {r.deterministic_qa_run_id} · S {r.semantic_qa_run_id} · {r.created_at}</li>)}</ul>
          </details>
        </>
      )}
    </section>
  );
}

export async function ReleasePanel({ reportId, v, session }: { reportId: string; v: Version; session: Session }) {
  const supabase = await createClient();
  const wf = await loadWorkflow(v.report_version_id);
  const { data: pdfs } = await supabase.from("release_pdf_artifacts")
    .select("id,pdf_sha256,byte_size,template_version,template_hash,renderer_version,renderer_hash,storage_key,created_at")
    .eq("report_version_id", v.report_version_id).order("created_at", { ascending: false });
  const artifacts = (pdfs ?? []) as { id: string; pdf_sha256: string; byte_size: number; template_version: string; template_hash: string;
    renderer_version: string; renderer_hash: string; storage_key: string; created_at: string }[];
  const chosen = artifacts[0];
  const { data: el } = await supabase.rpc("release_eligibility", { p_version: v.report_version_id, p_hash: v.report_version_hash,
                                                                   p_pdf: chosen?.id ?? null });
  const elig = (el ?? null) as Eligibility | null;
  const { data: rel } = await supabase.from("report_releases").select("*").eq("report_version_id", v.report_version_id).maybeSingle();
  const { data: man } = rel ? await supabase.from("release_manifests").select("manifest_json,manifest_hash").eq("id", rel.release_manifest_id).single()
    : { data: null };
  const secrev = can(session, "SECURITY_REVIEW");
  const authority = can(session, "RELEASE_DECIDE");
  return (
    <section>
      <h2>Security review &amp; release — version {v.version_no}</h2>
      <p className="muted">report_version_id <code>{v.report_version_id}</code> · hash <code>{v.report_version_hash}</code> · state{" "}
        <strong>{workflowLabel(wf?.workflow_state)}</strong></p>
      {rel && (
        <div className="card" style={{ borderLeft: "4px solid #1f4e79", background: "#f3f7fb" }}>
          <h3>RELEASED</h3>
          <div>released at {rel.released_at} by {rel.released_by}</div>
          <div>manifest hash <code>{rel.manifest_hash}</code></div>
          <div>PDF SHA-256 <code>{rel.pdf_sha256}</code> · <a href={`/reports/${reportId}/pdf/${rel.pdf_artifact_id}`}>download released PDF</a></div>
          <details><summary>release manifest (immutable)</summary><pre style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(man?.manifest_json, null, 2)}</pre></details>
          <p className="muted">A correction creates a new version that goes through QA, approval, security review and release again.</p>
        </div>
      )}
      <div className="card">
        <strong>Security / handling review</strong>: {wf?.security_status ?? "not opened (needs content approval)"}
        {secrev && v.is_latest && wf?.security_status === "PENDING" && wf.security_review_id && (
          <form action={decideSecurity} style={{ marginTop: 6 }}>
            <Hidden reportId={reportId} v={v} />
            <input type="hidden" name="security_review_id" value={wf.security_review_id} />
            <p className="muted">Content approval {wf.content_approval_id} · QA {wf.qa_status}. Review the preview of this exact version before deciding.</p>
            <select name="status">{SECURITY_DECISIONS.map((x) => <option key={x}>{x}</option>)}</select>{" "}
            <input name="rationale" placeholder="handling rationale" required minLength={10} style={{ width: 320 }} />{" "}
            <button type="submit">Record security decision</button>
          </form>
        )}
      </div>
      <div className="card">
        <strong>Release PDF artifacts</strong>
        {artifacts.length === 0 && <p className="muted">No PDF yet (rendered by the worker after security approval).</p>}
        <ul>{artifacts.map((p) => (
          <li key={p.id}><code>{p.pdf_sha256}</code> · {p.byte_size} bytes · {p.template_version} ({p.template_hash.slice(0, 12)}…) ·
            {" "}{p.renderer_version} ({p.renderer_hash.slice(0, 12)}…) · <a href={`/reports/${reportId}/pdf/${p.id}`}>download</a></li>))}</ul>
        {authority && v.is_latest && wf?.security_status === "APPROVED" && !rel && (
          <form action={requestReleasePdf}>
            <Hidden reportId={reportId} v={v} />
            <input name="reason" placeholder="reason for a new render" required minLength={5} /> <button type="submit">Request release PDF</button>
          </form>
        )}
      </div>
      {!rel && (
        <div className="card">
          <strong>Deterministic release eligibility (evaluated by the database)</strong>: {elig?.eligible ? "ELIGIBLE" : "NOT ELIGIBLE"}
          <ul>{checklistRows(elig).map((c) => (
            <li key={c.code} style={{ color: c.ok ? "#070" : "#a00" }}>{c.ok ? "✓" : "✗"} {c.label}</li>))}</ul>
          {authority && v.is_latest && elig?.eligible && chosen && (
            <form action={releaseReport} className="card" style={{ borderColor: "#1f4e79" }}>
              <Hidden reportId={reportId} v={v} />
              <input type="hidden" name="pdf_artifact_id" value={chosen.id} />
              <p>Release version {v.version_no} with PDF <code>{chosen.pdf_sha256.slice(0, 16)}…</code>. The database re-checks every condition
                and writes the decision, manifest and RELEASED state in one transaction.</p>
              <input name="rationale" placeholder="release rationale" required minLength={10} style={{ width: 320 }} />{" "}
              <label>type RELEASE to confirm <input name="confirm" required pattern="RELEASE" style={{ width: 90 }} /></label>{" "}
              <button type="submit">APPROVE_FOR_RELEASE</button>
            </form>
          )}
          {authority && v.is_latest && wf?.security_status === "APPROVED" && !wf.release_decision && (
            <form action={decideRelease}>
              <Hidden reportId={reportId} v={v} />
              <select name="decision">{RELEASE_RETURN_DECISIONS.map((x) => <option key={x}>{x}</option>)}</select>{" "}
              <input name="rationale" placeholder="rationale" required minLength={10} style={{ width: 320 }} />{" "}
              <button type="submit">Record release decision</button>
            </form>
          )}
          {wf?.release_decision && <p>Release decision: <strong>{wf.release_decision}</strong> — the report was not changed; a revision is a new version.</p>}
        </div>
      )}
    </section>
  );
}
