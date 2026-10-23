"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { type Permission, requirePermission, requireSession } from "@/lib/auth";
import { formObject } from "@/lib/claims";
import {
  AcknowledgeSchema, ContentDecisionSchema, PdfRequestSchema, ReleaseDecisionSchema, ReleaseSchema, RequestQaSchema, SecurityDecisionSchema,
} from "@/lib/release";
import { createClient } from "@/lib/supabase/server";

/*
 * Phase 6 server actions. The permission check here only gives a readable failure; PostgreSQL
 * re-checks the human identity, the role, the exact version / hash, the current QA result, the
 * ordering (QA → acknowledgement → content → security → release) and writes the audit entry.
 * No action here can create RELEASED except lfhe.release_report, which re-evaluates eligibility.
 */
function back(reportId: string, view: string, query: string): never {
  revalidatePath(`/reports/${reportId}`);
  redirect(`/reports/${reportId}?view=${view}&${query}`);
}

function fail(reportId: string, view: string, message: string): never {
  back(reportId, view, `error=${encodeURIComponent(message.slice(0, 400))}`);
}

async function rpc(reportId: string, view: string, fn: string, args: Record<string, unknown>) {
  const supabase = await createClient();
  const { error } = await supabase.rpc(fn, args);
  if (error) fail(reportId, view, error.message);
}

export async function requestQa(form: FormData) {
  const session = await requireSession();
  const raw = formObject(form);
  const f = RequestQaSchema.safeParse(raw);
  if (!f.success) fail(String(raw.report_id ?? ""), "qa", f.error.issues[0]?.message ?? "invalid request");
  if (!session.permissions.has("REPORT_EDIT") && !session.permissions.has("REPORT_CONTENT_APPROVE"))
    fail(f.data.report_id, "qa", "permission REPORT_EDIT or REPORT_CONTENT_APPROVE required");
  await rpc(f.data.report_id, "qa", "request_report_qa", { p_version: f.data.version_id, p_hash: f.data.version_hash, p_reason: f.data.reason });
  back(f.data.report_id, "qa", "ok=qa-requested");
}

async function guarded<T extends { report_id: string }>(perm: Permission, view: string, form: FormData,
                                                        schema: { safeParse: (x: unknown) => { success: true; data: T } | { success: false; error: { issues: { message: string }[] } } }) {
  await requirePermission(perm);
  const raw = formObject(form);
  const f = schema.safeParse(raw);
  if (!f.success) fail(String(raw.report_id ?? ""), view, f.error.issues[0]?.message ?? "invalid input");
  return f.data;
}

export async function acknowledgeWarning(form: FormData) {
  const f = await guarded("QA_WARNING_ACKNOWLEDGE", "qa", form, AcknowledgeSchema);
  await rpc(f.report_id, "qa", "acknowledge_qa_warning", { p_version: f.version_id, p_hash: f.version_hash, p_qa_result: f.qa_result_id,
                                                            p_finding: f.finding_id, p_rationale: f.rationale });
  back(f.report_id, "qa", "ok=warning-acknowledged");
}

export async function decideContent(form: FormData) {
  const f = await guarded("REPORT_CONTENT_APPROVE", "qa", form, ContentDecisionSchema);
  await rpc(f.report_id, "qa", "decide_report_content", { p_version: f.version_id, p_hash: f.version_hash, p_qa_result: f.qa_result_id,
                                                           p_decision: f.decision, p_rationale: f.rationale });
  back(f.report_id, "qa", `ok=content-${f.decision.toLowerCase()}`);
}

export async function decideSecurity(form: FormData) {
  const f = await guarded("SECURITY_REVIEW", "release", form, SecurityDecisionSchema);
  await rpc(f.report_id, "release", "decide_security_review", { p_version: f.version_id, p_hash: f.version_hash,
                                                                 p_review: f.security_review_id, p_status: f.status, p_rationale: f.rationale });
  back(f.report_id, "release", `ok=security-${f.status.toLowerCase()}`);
}

export async function requestReleasePdf(form: FormData) {
  const f = await guarded("RELEASE_DECIDE", "release", form, PdfRequestSchema);
  await rpc(f.report_id, "release", "request_release_pdf", { p_version: f.version_id, p_hash: f.version_hash, p_reason: f.reason });
  back(f.report_id, "release", "ok=pdf-requested");
}

export async function decideRelease(form: FormData) {
  const f = await guarded("RELEASE_DECIDE", "release", form, ReleaseDecisionSchema);
  await rpc(f.report_id, "release", "decide_release", { p_version: f.version_id, p_hash: f.version_hash, p_decision: f.decision,
                                                         p_rationale: f.rationale });
  back(f.report_id, "release", `ok=${f.decision.toLowerCase()}`);
}

export async function releaseReport(form: FormData) {
  const f = await guarded("RELEASE_DECIDE", "release", form, ReleaseSchema);
  await rpc(f.report_id, "release", "release_report", { p_version: f.version_id, p_hash: f.version_hash, p_pdf_artifact: f.pdf_artifact_id,
                                                         p_rationale: f.rationale });
  back(f.report_id, "release", "ok=released");
}
