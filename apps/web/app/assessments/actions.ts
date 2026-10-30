"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import {
  DisposeFlagSchema, ModifyApproveSchema, ReviewAssessmentSchema, type StoredStatement, editsFrom, modifiedPayload,
} from "@/lib/assessments";
import { requirePermission } from "@/lib/auth";
import { formObject } from "@/lib/claims";
import { createClient } from "@/lib/supabase/server";

/*
 * Phase 4 human analytical review server actions (CR7-03 UI). Each calls an existing HUMAN_ONLY function with the
 * user's own session. The frontend cannot approve anything by itself: the database requires a human identity, the
 * permission(s), the M08 challenge, the exact version hash and a final analytic confidence with rationale.
 */
function go(path: string, q: string): never {
  revalidatePath("/assessments");
  revalidatePath("/events");
  redirect(`${path}?${q}`);
}
function fail(path: string, m: string): never {
  go(path, `error=${encodeURIComponent(m.slice(0, 400))}`);
}

export async function reviewAssessment(form: FormData) {
  await requirePermission("ASSESSMENT_REVIEW");
  const raw = formObject(form);
  const path = `/assessments/${String(raw.version_id ?? "")}`;
  const parsed = ReviewAssessmentSchema.safeParse(raw);
  if (!parsed.success) fail(path, parsed.error.issues[0]?.message ?? "invalid review");
  const f = parsed.data;
  const supabase = await createClient();
  const { error } = await supabase.rpc("review_assessment", {
    p_version: f.version_id, p_hash: f.version_hash, p_decision: f.decision, p_final_confidence: f.final_confidence ?? null,
    p_confidence_rationale: f.decision === "APPROVE" ? f.confidence_rationale : null, p_reason: f.reason,
  });
  if (error) fail(path, error.message);
  go(path, `ok=assessment_${f.decision.toLowerCase()}`);
}

export async function modifyAndApprove(form: FormData) {
  await requirePermission("ASSESSMENT_REVIEW");
  const raw = formObject(form);
  const path = `/assessments/${String(raw.version_id ?? "")}`;
  const parsed = ModifyApproveSchema.safeParse(raw);
  if (!parsed.success) fail(path, parsed.error.issues[0]?.message ?? "invalid modification");
  const f = parsed.data;
  const supabase = await createClient();
  const { data: v } = await supabase.from("assessment_versions").select("content,content_hash").eq("id", f.version_id).single();
  if (!v || v.content_hash !== f.version_hash) fail(path, "VERSION_HASH_MISMATCH: reload the assessment");
  const content = v!.content as { statements: StoredStatement[]; derived_summary: unknown; indicators_to_watch: unknown };
  const edits = editsFrom(form);
  const changed = content.statements.filter((s) => edits[s.statement_local_id] !== undefined && edits[s.statement_local_id].trim() !== s.statement_text);
  if (changed.length === 0) fail(path, "no statement text was changed — use APPROVE instead");
  const { data, error } = await supabase.rpc("modify_and_approve_assessment", {
    p_version: f.version_id, p_hash: f.version_hash, p: modifiedPayload(content, edits), p_final_confidence: f.final_confidence,
    p_confidence_rationale: f.confidence_rationale, p_reason: f.reason,
  });
  if (error) fail(path, error.message);
  go(`/assessments/${(data as { assessment_version_id: string }).assessment_version_id}`, "ok=modified_and_approved");
}

export async function disposeFlag(form: FormData) {
  await requirePermission("ASSESSMENT_REVIEW");
  const raw = formObject(form);
  const path = `/assessments/${String(raw.version_id ?? "")}`;
  const parsed = DisposeFlagSchema.safeParse(raw);
  if (!parsed.success) fail(path, parsed.error.issues[0]?.message ?? "invalid disposition");
  const f = parsed.data;
  const supabase = await createClient();
  const { error } = await supabase.rpc("dispose_challenge_flag", { p_flag: f.flag_id, p_disposition: f.disposition, p_reason: f.reason });
  if (error) fail(path, error.message);
  go(path, "ok=challenge_flag_disposed");
}
