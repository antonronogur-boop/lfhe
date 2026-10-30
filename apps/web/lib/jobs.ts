import { z } from "zod";

/**
 * CR7-03 — human requests for existing pipeline jobs (lfhe.request_workflow_job, HUMAN_ONLY). The browser only
 * names the step and the exact object; the database builds the payload, checks the permission, cutoff
 * eligibility, the M06 / manual-promotion rule and idempotency, and audits the request. Nothing is executed here.
 */
export const REQUESTABLE_JOBS = ["EXTRACT_CLAIMS", "ANALYSE_LINEAGE", "BUILD_EVENTS", "ASSESS_RELEVANCE", "ASSESS_EVENT",
  "CHALLENGE_ASSESSMENT"] as const;
export type RequestableJob = (typeof REQUESTABLE_JOBS)[number];

export const JOB_LABELS: Record<string, { module: string; label: string }> = {
  COLLECT_SOURCE: { module: "collector", label: "Collect source" },
  EXTRACT_CLAIMS: { module: "M02", label: "Claim extraction" },
  CLASSIFY_CLAIMS: { module: "M03", label: "Claim classification" },
  ANALYSE_LINEAGE: { module: "M04", label: "Lineage analysis" },
  BUILD_EVENTS: { module: "M05", label: "Event building" },
  ASSESS_RELEVANCE: { module: "M06", label: "Relevance (HU / NATO)" },
  ASSESS_EVENT: { module: "M07", label: "Intelligence assessment" },
  CHALLENGE_ASSESSMENT: { module: "M08", label: "Structured challenge" },
  EDIT_REPORT: { module: "M09", label: "Executive editing (draft)" },
  RENDER_REPORT: { module: "render", label: "Preview render" },
  RUN_REPORT_QA: { module: "M10", label: "QA (M10-D + M10-S)" },
  RENDER_RELEASE_PDF: { module: "PDF", label: "Release PDF" },
};

export const DISPLAY_STATUS: Record<string, string> = {
  PENDING: "QUEUED", RUNNING: "RUNNING", SUCCESS: "SUCCEEDED", HUMAN_REVIEW: "NEEDS_HUMAN_REVIEW", FAILED: "FAILED", SKIPPED: "SKIPPED",
};

export function displayStatus(raw: string | null | undefined): string {
  return DISPLAY_STATUS[raw ?? ""] ?? (raw ?? "—");
}

const uuid = z.string().uuid();
const reason = z.string().trim().min(5, "a reason of at least 5 characters is required");

export const JobRequestSchema = z.object({
  job_type: z.enum(REQUESTABLE_JOBS),
  return_to: z.string().regex(/^\/[A-Za-z0-9/_?=&%.-]*$/, "invalid return path"),
  reason,
  ctx: z.string().optional(),
  text_representation_id: uuid.optional(),
  claim_ids: z.array(uuid).max(100).optional(),
  event_version_id: uuid.optional(),
  event_version_hash: z.string().regex(/^[0-9a-f]{64}$/).optional(),
  assessment_version_id: uuid.optional(),
  assessment_version_hash: z.string().regex(/^[0-9a-f]{64}$/).optional(),
  baseline_code: z.string().trim().max(120).optional(),
}).superRefine((f, ctx) => {
  const need = (cond: boolean, msg: string) => { if (!cond) ctx.addIssue({ code: "custom", message: msg }); };
  if (f.job_type === "EXTRACT_CLAIMS") need(!!f.text_representation_id, "choose an article text");
  if (f.job_type === "ANALYSE_LINEAGE" || f.job_type === "BUILD_EVENTS") {
    need((f.claim_ids?.length ?? 0) > 0, "select at least one claim");
    need(!!f.ctx, "choose the analysis context (mode and cutoff)");
  }
  if (f.job_type === "ASSESS_RELEVANCE" || f.job_type === "ASSESS_EVENT") {
    need(!!f.event_version_id && !!f.event_version_hash, "the exact event version is required");
    need(!!f.ctx, "choose the analysis context (mode and cutoff)");
  }
  if (f.job_type === "CHALLENGE_ASSESSMENT") need(!!f.assessment_version_id && !!f.assessment_version_hash, "the exact assessment version is required");
});
export type JobRequest = z.infer<typeof JobRequestSchema>;

/** Parameters for lfhe.request_workflow_job (mode / cutoff resolved on the server from the chosen context). */
export function jobParams(f: JobRequest, mc: { report_mode: string; information_cutoff: string } | null): Record<string, unknown> {
  switch (f.job_type) {
    case "EXTRACT_CLAIMS": return { text_representation_id: f.text_representation_id };
    case "ANALYSE_LINEAGE":
    case "BUILD_EVENTS": return { claim_ids: f.claim_ids, ...mc };
    case "ASSESS_RELEVANCE":
    case "ASSESS_EVENT": return { event_version_id: f.event_version_id, event_version_hash: f.event_version_hash, ...mc,
      ...(f.baseline_code ? { baseline_code: f.baseline_code } : {}) };
    case "CHALLENGE_ASSESSMENT": return { assessment_version_id: f.assessment_version_id, assessment_version_hash: f.assessment_version_hash };
  }
}

export function jobFormObject(form: FormData): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of form.entries()) {
    if (typeof v !== "string") continue;
    if (k === "claim_ids") out.claim_ids = [...((out.claim_ids as string[]) ?? []), v];
    else if (v !== "") out[k] = v;
  }
  return out;
}

/** Human-readable explanation of the request outcome. */
export function outcomeText(outcome: string): string {
  return ({
    ENQUEUED: "queued for the worker",
    ALREADY_ACTIVE: "already queued or running — no second job was created",
    ALREADY_COMPLETED: "already completed for this exact input — no re-run",
    REQUEUED_AFTER_FAILURE: "re-queued after a permanent failure (new job)",
    REQUEUED_AFTER_REJECTION: "re-queued after the previous model output was rejected (new run, audited)",
  } as Record<string, string>)[outcome] ?? outcome;
}

/** Plain-language explanation of a closed ingestion rejection code such as "ATTRIBUTION_MISSING:AS1" (CR7-04). */
export function explainRejection(reason: string): string {
  const [code, ref] = reason.split(":");
  const where = ref ? ` (statement ${ref})` : "";
  const text = ({
    ATTRIBUTION_MISSING: "the source of a claim that is not corroborated was not named inside the statement",
    ATTRIBUTION_CONTRADICTS_WORKFLOW_STATE: "the model marked the statement as needing / not needing a source attribution against the workflow rule",
    CONFIDENCE_RATIONALE_REQUIRED: "the confidence recommendation had no sufficient rationale",
    FINAL_CONFIDENCE_IS_HUMAN_ONLY: "the model tried to set the final confidence, which only a human may do",
    CONTRADICTION_OMITTED: "a contradicting claim was not kept visible",
    PROVENANCE_CLASS_MISMATCH: "a statement cited evidence that does not match its provenance class",
    SCHEMA_VALIDATION_FAILED: "the output did not match the required format",
  } as Record<string, string>)[code];
  return `${text ?? code}${where}`;
}
