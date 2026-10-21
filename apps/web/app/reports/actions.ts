"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { requirePermission } from "@/lib/auth";
import { formObject } from "@/lib/claims";
import {
  type CanonicalReport, CreateReportSchema, DecideCandidateSchema, EditStatementSchema, StatementRefSchema, VersionActionSchema,
  applyStatementEdit, applyStatementMove, applyStatementRemoval, contentFromCanonical, decideCandidateArgs, removalDecisions,
} from "@/lib/reports";
import { createClient } from "@/lib/supabase/server";

/*
 * Every action checks REPORT_EDIT server-side for a readable failure, then calls a HUMAN_ONLY
 * PostgreSQL function with the user's own session. The database re-checks identity and
 * permission, binds the action to the exact candidate / version hash, re-validates provenance,
 * creates a NEW immutable report version for any content change, and writes the audit entry.
 */
function back(reportId: string | undefined, query: string): never {
  revalidatePath("/reports");
  redirect(reportId ? `/reports/${reportId}?${query}` : `/reports?${query}`);
}

function fail(reportId: string | undefined, message: string): never {
  back(reportId, `error=${encodeURIComponent(message.slice(0, 400))}`);
}

export async function createReport(form: FormData) {
  await requirePermission("REPORT_EDIT");
  const parsed = CreateReportSchema.safeParse(formObject(form));
  if (!parsed.success) fail(undefined, parsed.error.issues[0]?.message ?? "invalid report");
  const { reason, ...p } = parsed.data;
  const supabase = await createClient();
  const { data, error } = await supabase.rpc("create_report", {
    p: { ...p, information_cutoff: new Date(p.information_cutoff).toISOString() }, p_reason: reason,
  });
  if (error) fail(undefined, error.message);
  const refreshed = await supabase.rpc("refresh_report_candidates", { p_report: data as string });
  if (refreshed.error) fail(data as string, refreshed.error.message);
  back(data as string, "ok=created");
}

export async function refreshCandidates(form: FormData) {
  await requirePermission("REPORT_EDIT");
  const reportId = String(form.get("report_id") ?? "");
  const supabase = await createClient();
  const { error } = await supabase.rpc("refresh_report_candidates", { p_report: reportId });
  if (error) fail(reportId, error.message);
  back(reportId, "ok=refreshed");
}

export async function decideCandidate(form: FormData) {
  await requirePermission("REPORT_EDIT");
  const raw = formObject(form);
  const parsed = DecideCandidateSchema.safeParse(raw);
  if (!parsed.success) fail(String(raw.report_id ?? ""), parsed.error.issues[0]?.message ?? "invalid decision");
  const supabase = await createClient();
  const { error } = await supabase.rpc("decide_report_candidate", decideCandidateArgs(parsed.data));
  if (error) fail(parsed.data.report_id, error.message);
  back(parsed.data.report_id, "ok=decision");
}

export async function freezeSelection(form: FormData) {
  await requirePermission("REPORT_EDIT");
  const reportId = String(form.get("report_id") ?? "");
  const reason = String(form.get("reason") ?? "");
  const supabase = await createClient();
  const { error } = await supabase.rpc("freeze_report_selection", { p_report: reportId, p_reason: reason });
  if (error) fail(reportId, error.message);
  back(reportId, "ok=m09-requested");
}

async function loadCanonical(reportId: string, versionId: string): Promise<CanonicalReport> {
  const supabase = await createClient();
  const { data, error } = await supabase.from("report_versions").select("canonical_json").eq("id", versionId).single();
  if (error || !data) fail(reportId, error?.message ?? "unknown report version");
  return data.canonical_json as CanonicalReport;
}

async function submitEdit(reportId: string, versionId: string, versionHash: string, content: object, reason: string) {
  const supabase = await createClient();
  const { error } = await supabase.rpc("edit_report_version", {
    p_version: versionId, p_hash: versionHash, p: content, p_reason: reason,
  });
  if (error) fail(reportId, error.message);
  back(reportId, "ok=new-version");
}

export async function editStatement(form: FormData) {
  await requirePermission("REPORT_EDIT");
  const raw = formObject(form);
  const parsed = EditStatementSchema.safeParse(raw);
  if (!parsed.success) fail(String(raw.report_id ?? ""), parsed.error.issues[0]?.message ?? "invalid edit");
  const f = parsed.data;
  const content = applyStatementEdit(contentFromCanonical(await loadCanonical(f.report_id, f.version_id)),
                                     f.statement_local_id, f.text, f.editorial_transform);
  await submitEdit(f.report_id, f.version_id, f.version_hash, content, f.reason);
}

export async function moveStatement(form: FormData) {
  await requirePermission("REPORT_EDIT");
  const raw = formObject(form);
  const parsed = StatementRefSchema.safeParse(raw);
  if (!parsed.success) fail(String(raw.report_id ?? ""), parsed.error.issues[0]?.message ?? "invalid reorder");
  const f = parsed.data;
  const delta = raw.direction === "up" ? -1 : 1;
  const content = applyStatementMove(contentFromCanonical(await loadCanonical(f.report_id, f.version_id)), f.statement_local_id, delta);
  await submitEdit(f.report_id, f.version_id, f.version_hash, content, f.reason);
}

export async function removeStatement(form: FormData) {
  await requirePermission("REPORT_EDIT");
  const raw = formObject(form);
  const parsed = StatementRefSchema.safeParse(raw);
  if (!parsed.success) fail(String(raw.report_id ?? ""), parsed.error.issues[0]?.message ?? "invalid removal");
  const f = parsed.data;
  const { content, removed } = applyStatementRemoval(contentFromCanonical(await loadCanonical(f.report_id, f.version_id)),
                                                     f.statement_local_id);
  await submitEdit(f.report_id, f.version_id, f.version_hash, { ...content, remove_source_statement_ids: removed }, f.reason);
}

export async function decideRemovals(form: FormData) {
  await requirePermission("REPORT_EDIT");
  const raw = formObject(form) as Record<string, string>;
  const parsed = VersionActionSchema.safeParse(raw);
  if (!parsed.success) fail(raw.report_id, parsed.error.issues[0]?.message ?? "invalid removal decision");
  const ids = String(raw.proposal_ids ?? "").split(",").filter(Boolean);
  let decisions;
  try {
    decisions = removalDecisions(raw, ids);
  } catch (e) {
    fail(parsed.data.report_id, (e as Error).message);
  }
  const supabase = await createClient();
  const { error } = await supabase.rpc("decide_report_removals", {
    p_version: parsed.data.version_id, p_hash: parsed.data.version_hash, p_decisions: decisions, p_reason: parsed.data.reason,
  });
  if (error) fail(parsed.data.report_id, error.message);
  back(parsed.data.report_id, "ok=removals-decided");
}
