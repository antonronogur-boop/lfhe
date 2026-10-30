"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { requirePermission } from "@/lib/auth";
import { formObject } from "@/lib/claims";
import {
  EventFormSchema, EventReviewSchema, EventStateSchema, PromoteSchema, RelevanceDecisionSchema, eventFormObject, eventPayload,
  relevanceOverride,
} from "@/lib/events";
import { createClient } from "@/lib/supabase/server";

/*
 * Event workflow server actions (CR7-03 UI). Each one checks the permission for a readable failure and calls an
 * existing HUMAN_ONLY Phase 3 / 4 function with the user's own session; the database re-checks the human identity,
 * the permission, the exact version / hash / expected state and writes the audit entry.
 */
function go(path: string, query: string): never {
  revalidatePath("/events");
  redirect(`${path}${path.includes("?") ? "&" : "?"}${query}`);
}

function fail(path: string, m: string): never {
  go(path, `error=${encodeURIComponent(m.slice(0, 400))}`);
}

async function call(path: string, fn: string, args: Record<string, unknown>) {
  const supabase = await createClient();
  const { data, error } = await supabase.rpc(fn, args);
  if (error) fail(path, error.message);
  return data;
}

export async function createEvent(form: FormData) {
  await requirePermission("EVENT_ACTION");
  const parsed = EventFormSchema.safeParse(eventFormObject(form));
  if (!parsed.success) fail("/events/new", parsed.error.issues[0]?.message ?? "invalid event");
  const id = await call("/events/new", "create_event", { p: eventPayload(parsed.data), p_reason: parsed.data.reason, p_proposal: null });
  go(`/events/${id as string}`, "ok=event_created");
}

export async function updateEvent(form: FormData) {
  await requirePermission("EVENT_ACTION");
  const raw = eventFormObject(form);
  const path = `/events/${String(raw.event_id ?? "")}`;
  const parsed = EventFormSchema.safeParse(raw);
  if (!parsed.success || !parsed.data.event_id || !parsed.data.expected_head) fail(path, parsed.error?.issues[0]?.message ?? "invalid update");
  const f = parsed.data!;
  await call(path, "update_event", { p_event: f.event_id, p_expected_head: f.expected_head, p: eventPayload(f), p_reason: f.reason, p_proposal: null });
  go(path, "ok=new_event_version");
}

export async function reviewEventVersion(form: FormData) {
  await requirePermission("EVENT_ACTION");
  const raw = formObject(form);
  const path = `/events/${String(raw.event_id ?? "")}`;
  const parsed = EventReviewSchema.safeParse(raw);
  if (!parsed.success) fail(path, parsed.error.issues[0]?.message ?? "invalid review");
  const f = parsed.data;
  await call(path, "review_event_version", { p_version: f.version_id, p_content_hash: f.version_hash, p_decision: f.decision, p_reason: f.reason });
  go(path, "ok=event_version_reviewed");
}

export async function setEventState(form: FormData) {
  await requirePermission("EVENT_ACTION");
  const raw = formObject(form);
  const path = `/events/${String(raw.event_id ?? "")}`;
  const parsed = EventStateSchema.safeParse(raw);
  if (!parsed.success) fail(path, parsed.error.issues[0]?.message ?? "invalid state change");
  const f = parsed.data;
  if (f.new_state === "REJECTED") {
    await call(path, "reject_event", { p_event: f.event_id, p_expected_state: f.expected_state, p_reason: f.reason, p_proposal: null });
  } else {
    await call(path, "set_event_state", { p_event: f.event_id, p_expected_state: f.expected_state, p_new_state: f.new_state, p_reason: f.reason });
  }
  go(path, "ok=event_state");
}

export async function decideRelevance(form: FormData) {
  await requirePermission("ASSESSMENT_REVIEW");
  const raw = formObject(form);
  const path = `/events/${String(raw.event_id ?? "")}`;
  const parsed = RelevanceDecisionSchema.safeParse(raw);
  if (!parsed.success) fail(path, parsed.error.issues[0]?.message ?? "invalid relevance decision");
  const f = parsed.data;
  await call(path, "decide_relevance", { p_result: f.result_id, p_action: f.action, p_override: relevanceOverride(f), p_reason: f.reason });
  go(path, "ok=relevance_decision");
}

export async function promoteEvent(form: FormData) {
  await requirePermission("ASSESSMENT_REVIEW");
  const raw = formObject(form);
  const path = `/events/${String(raw.event_id ?? "")}`;
  const parsed = PromoteSchema.safeParse(raw);
  if (!parsed.success) fail(path, parsed.error.issues[0]?.message ?? "invalid promotion");
  const f = parsed.data;
  await call(path, "promote_event_version", { p_version: f.version_id, p_hash: f.version_hash, p_action: f.action, p_reason: f.reason });
  go(path, `ok=${f.action === "PROMOTE" ? "event_promoted" : "manual_assessment_request_recorded"}`);
}
