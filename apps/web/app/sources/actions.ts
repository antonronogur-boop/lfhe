"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { requirePermission } from "@/lib/auth";
import { ReasonSchema, parseSourceForm } from "@/lib/sources";
import { createClient } from "@/lib/supabase/server";

/*
 * Every action:
 *   1. checks the permission server-side (fast, readable failure), then
 *   2. calls a HUMAN_ONLY PostgreSQL function with the user's own session,
 *      which re-checks identity + permission and writes the audit entry.
 * The UI never writes tables directly and never holds the service_role key.
 */

function fail(message: string): never {
  redirect(`/sources?error=${encodeURIComponent(message.slice(0, 300))}`);
}

export async function createSource(form: FormData) {
  await requirePermission("SOURCE_CREATE");
  let payload;
  try {
    payload = parseSourceForm(form);
  } catch (e) {
    fail(e instanceof Error ? e.message : "invalid form");
  }
  const supabase = await createClient();
  const { error } = await supabase.rpc("create_source", { p: payload });
  if (error) fail(error.message);
  revalidatePath("/sources");
  redirect("/sources?ok=created");
}

export async function setCollectionMethodApproval(form: FormData) {
  await requirePermission("SOURCE_APPROVE_COLLECTION_METHOD");
  const id = String(form.get("id") ?? "");
  const approved = form.get("approved") === "true";
  const reason = ReasonSchema.safeParse(form.get("reason"));
  if (!reason.success) fail(reason.error.issues[0]?.message ?? "reason required");
  const supabase = await createClient();
  const { error } = await supabase.rpc("set_collection_method_approval", {
    p_id: id, p_approved: approved, p_reason: reason.data,
  });
  if (error) fail(error.message);
  revalidatePath("/sources");
  redirect("/sources?ok=approval");
}

export async function setSourceActive(form: FormData) {
  await requirePermission("SOURCE_ACTIVATE");
  const id = String(form.get("id") ?? "");
  const active = form.get("active") === "true";
  const reason = ReasonSchema.safeParse(form.get("reason"));
  if (!reason.success) fail(reason.error.issues[0]?.message ?? "reason required");
  const supabase = await createClient();
  const { error } = await supabase.rpc("set_source_active", {
    p_id: id, p_active: active, p_reason: reason.data,
  });
  if (error) fail(error.message);
  revalidatePath("/sources");
  redirect("/sources?ok=active");
}
