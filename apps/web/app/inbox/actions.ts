"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { requirePermission } from "@/lib/auth";
import { AutopilotSchema, BatchEventSchema, batchSummary, parsePicks } from "@/lib/inbox";
import { createClient } from "@/lib/supabase/server";

function back(query: string, to = "/inbox"): never {
  revalidatePath("/inbox"); revalidatePath("/events"); revalidatePath("/reports");
  redirect(`${to}${to.includes("?") ? "&" : "?"}${query}`);
}

/** Confirm (approve + ACTIVE) or reject several candidate events with one audited reason; each is its own audited call. */
export async function decideEvents(form: FormData) {
  await requirePermission("EVENT_ACTION");
  const parsed = BatchEventSchema.safeParse({
    decision: form.get("decision"), reason: form.get("reason"), items: form.getAll("item").map(String) });
  if (!parsed.success) back(`error=${encodeURIComponent(parsed.error.issues[0]?.message ?? "invalid selection")}`);
  const f = parsed.data!;
  const supabase = await createClient();
  let done = 0;
  const failed: { id: string; message: string }[] = [];
  for (const p of parsePicks(f.items)) {
    const step = async (fn: string, args: Record<string, unknown>) => {
      const { error } = await supabase.rpc(fn, args);
      if (error) throw new Error(error.message);
    };
    try {
      if (f.decision === "REJECT") {
        await step("reject_event", { p_event: p.event_id, p_expected_state: "CANDIDATE", p_reason: f.reason, p_proposal: null });
      } else {
        await step("review_event_version", { p_version: p.version_id, p_content_hash: p.version_hash, p_decision: "APPROVE", p_reason: f.reason });
        await step("set_event_state", { p_event: p.event_id, p_expected_state: "CANDIDATE", p_new_state: "ACTIVE", p_reason: f.reason });
      }
      done += 1;
    } catch (e) {
      failed.push({ id: p.event_id, message: (e as Error).message.slice(0, 120) });
    }
  }
  back(failed.length ? `error=${encodeURIComponent(batchSummary(done, failed))}` : `ok=${encodeURIComponent(batchSummary(done, failed))}`);
}

/** Switch the automatic analysis (CR7-05) on for one report, or off. */
export async function setAutopilot(form: FormData) {
  await requirePermission("EVENT_ACTION");
  const parsed = AutopilotSchema.safeParse({
    report_id: String(form.get("report_id") ?? "") || undefined, enabled: form.get("enabled"), reason: form.get("reason") });
  if (!parsed.success || !parsed.data.report_id) back(`error=${encodeURIComponent(parsed.error?.issues[0]?.message ?? "choose a report")}`);
  const f = parsed.data!;
  const supabase = await createClient();
  const { error } = await supabase.rpc("set_report_autopilot", { p_report: f.report_id, p_enabled: f.enabled === "on", p_reason: f.reason });
  if (error) back(`error=${encodeURIComponent(error.message.slice(0, 300))}`);
  back(`ok=${f.enabled === "on" ? "autopilot_on" : "autopilot_off"}`);
}
