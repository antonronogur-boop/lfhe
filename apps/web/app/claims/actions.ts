"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { requirePermission } from "@/lib/auth";
import {
  HighImpactFormSchema, LinkFormSchema, ReviewFormSchema, RevalidationFormSchema, StatusFormSchema, formObject,
  reviewRpcArgs,
} from "@/lib/claims";
import { createClient } from "@/lib/supabase/server";

/*
 * Every action checks the permission server-side for a readable failure and then
 * calls a HUMAN_ONLY PostgreSQL function with the user's own session; the
 * database re-checks identity + permission, binds the decision to the exact
 * claim content (hash) and previous review, and writes the audit entry.
 */
function fail(message: string): never {
  redirect(`/claims?error=${encodeURIComponent(message.slice(0, 300))}`);
}

function done(what: string): never {
  revalidatePath("/claims");
  redirect(`/claims?ok=${what}`);
}

export async function reviewClaim(form: FormData) {
  await requirePermission("CLAIM_REVIEW");
  const parsed = ReviewFormSchema.safeParse(formObject(form));
  if (!parsed.success) fail(parsed.error.issues[0]?.message ?? "invalid review");
  const supabase = await createClient();
  const { error } = await supabase.rpc("review_claim", reviewRpcArgs(parsed.data));
  if (error) fail(error.message);
  done("review");
}

export async function setClaimStatus(form: FormData) {
  await requirePermission("CLAIM_REVIEW");
  const parsed = StatusFormSchema.safeParse(formObject(form));
  if (!parsed.success) fail(parsed.error.issues[0]?.message ?? "invalid status change");
  const f = parsed.data;
  const supabase = await createClient();
  const { error } = await supabase.rpc("set_claim_status", {
    p_claim_id: f.claim_id, p_expected_current_status: f.expected_current_status, p_new_status: f.new_status,
    p_reason: f.reason, p_review_id: null,
  });
  if (error) fail(error.message);
  done("status");
}

export async function markHighImpact(form: FormData) {
  await requirePermission("CLAIM_REVIEW");
  const parsed = HighImpactFormSchema.safeParse(formObject(form));
  if (!parsed.success) fail(parsed.error.issues[0]?.message ?? "invalid high-impact change");
  const f = parsed.data;
  const supabase = await createClient();
  const { error } = await supabase.rpc("mark_claim_high_impact", {
    p_claim_id: f.claim_id, p_high_impact: f.high_impact, p_reasons: f.reasons, p_reason: f.reason,
  });
  if (error) fail(error.message);
  done("high_impact");
}

export async function decideRevalidation(form: FormData) {
  await requirePermission("CLAIM_REVIEW");
  const parsed = RevalidationFormSchema.safeParse(formObject(form));
  if (!parsed.success) fail(parsed.error.issues[0]?.message ?? "invalid revalidation decision");
  const f = parsed.data;
  const supabase = await createClient();
  const { error } = await supabase.rpc("decide_high_impact_revalidation", {
    p_revalidation_id: f.revalidation_id, p_approve: f.approve, p_reason: f.reason,
  });
  if (error) fail(error.message);
  done("revalidation");
}

export async function linkMention(form: FormData) {
  await requirePermission("ENTITY_MANAGE");
  const parsed = LinkFormSchema.safeParse(formObject(form));
  if (!parsed.success) fail(parsed.error.issues[0]?.message ?? "invalid entity link");
  const f = parsed.data;
  const supabase = await createClient();
  const { error } = await supabase.rpc("link_entity_mention", {
    p_mention_id: f.mention_id, p_resolution: f.resolution, p_entity_id: f.entity_id, p_reason: f.reason,
  });
  if (error) fail(error.message);
  done("entity_link");
}
