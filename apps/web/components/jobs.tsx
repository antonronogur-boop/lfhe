import type { ReactNode } from "react";

import { requestJob } from "@/app/jobs/actions";
import { Submit } from "@/components/client";
import { Badge, Locked, When } from "@/components/ui";
import { JOB_LABELS, type RequestableJob } from "@/lib/jobs";
import { createClient } from "@/lib/supabase/server";
import type { AnalysisContext } from "@/lib/workspace";

export interface RequestRow {
  request_id: string; job_type: string; object_type: string; object_id: string; outcome: string; report_mode: string | null;
  information_cutoff: string | null; requested_at: string; job_id: string; display_status: string; attempt_count: number;
  max_attempts: number; last_error: string | null; completed_at: string | null;
}

/** Latest human requests for the given objects with the live job status (CR7-03 status view). */
export async function requestsFor(objectIds: string[], jobTypes?: string[]): Promise<RequestRow[]> {
  if (objectIds.length === 0) return [];
  const supabase = await createClient();
  let q = supabase.from("workflow_job_request_status").select("*").in("object_id", objectIds).order("seq", { ascending: false }).limit(40);
  if (jobTypes) q = q.in("job_type", jobTypes);
  const { data } = await q;
  return (data ?? []) as RequestRow[];
}

export function JobStatusLine({ rows }: { rows: RequestRow[] }) {
  if (rows.length === 0) return null;
  const latest = new Map<string, RequestRow>();
  for (const r of rows) if (!latest.has(r.job_type)) latest.set(r.job_type, r);
  return (
    <div className="stack" style={{ gap: 4 }}>
      {[...latest.values()].map((r) => (
        <div key={r.request_id} className="row" style={{ fontSize: 12.5 }}>
          <Badge value={r.display_status} />
          <span><b>{JOB_LABELS[r.job_type]?.module}</b> {JOB_LABELS[r.job_type]?.label}</span>
          {r.report_mode && <span className="muted">{r.report_mode} · cutoff <When at={r.information_cutoff} /></span>}
          <span className="muted">requested <When at={r.requested_at} /> · attempt {r.attempt_count}/{r.max_attempts}</span>
          {r.display_status === "FAILED" && r.last_error && <span style={{ color: "var(--danger)" }}>{r.last_error}</span>}
        </div>
      ))}
    </div>
  );
}

/** A human request for one pipeline step. Hidden fields name the exact object; the database does the rest. */
export function JobRequestForm({ jobType, hidden, returnTo, contexts, allowed, lockedReason, cta, note, defaultReason, children }: {
  jobType: RequestableJob; hidden: Record<string, string | string[] | undefined>; returnTo: string; contexts?: AnalysisContext[];
  allowed: boolean; lockedReason: string; cta: string; note?: ReactNode; defaultReason?: string; children?: ReactNode;
}) {
  if (!allowed) return <Locked>{lockedReason}</Locked>;
  return (
    <form action={requestJob} className="form" aria-label={`${JOB_LABELS[jobType]?.module} request`}>
      <input type="hidden" name="job_type" value={jobType} />
      <input type="hidden" name="return_to" value={returnTo} />
      {Object.entries(hidden).flatMap(([k, v]) => (Array.isArray(v) ? v : v ? [v] : []).map((x, i) =>
        <input key={`${k}-${i}`} type="hidden" name={k} value={x} />))}
      {children}
      <div className="form-row">
        {contexts && (
          <div className="field">
            <label htmlFor={`ctx-${jobType}`}>Analysis context (mode · information cutoff)</label>
            <select id={`ctx-${jobType}`} name="ctx" required defaultValue={contexts[0]?.key}>
              {contexts.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
            </select>
          </div>
        )}
        <div className="field">
          <label htmlFor={`reason-${jobType}`}>Reason (audited)</label>
          <input id={`reason-${jobType}`} name="reason" required minLength={5} defaultValue={defaultReason} />
        </div>
        <Submit kind="primary" pendingText="Requesting…">{cta}</Submit>
      </div>
      {note && <p className="muted" style={{ margin: 0, fontSize: 12 }}>{note}</p>}
    </form>
  );
}
