"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { requireSession } from "@/lib/auth";
import { JobRequestSchema, jobFormObject, jobParams, outcomeText } from "@/lib/jobs";
import { createClient } from "@/lib/supabase/server";
import { resolveContext } from "@/lib/workspace";

function back(to: string, query: string): never {
  revalidatePath(to.split("?")[0]);
  redirect(`${to}${to.includes("?") ? "&" : "?"}${query}`);
}

/** CR7-03: request one existing pipeline job for one exact object (HUMAN_ONLY lfhe.request_workflow_job). */
export async function requestJob(form: FormData) {
  await requireSession();
  const raw = jobFormObject(form);
  const to = typeof raw.return_to === "string" && raw.return_to.startsWith("/") ? raw.return_to : "/jobs";
  const parsed = JobRequestSchema.safeParse(raw);
  if (!parsed.success) back(to, `error=${encodeURIComponent(parsed.error.issues[0]?.message ?? "invalid request")}`);
  const f = parsed.data;
  const supabase = await createClient();
  let mc: { report_mode: string; information_cutoff: string } | null = null;
  if (f.ctx) {
    try {
      mc = await resolveContext(supabase, f.ctx);
    } catch (e) {
      back(to, `error=${encodeURIComponent((e as Error).message)}`);
    }
  }
  const { data, error } = await supabase.rpc("request_workflow_job", { p_job_type: f.job_type, p: jobParams(f, mc), p_reason: f.reason });
  if (error) back(to, `error=${encodeURIComponent(error.message.slice(0, 400))}`);
  const r = data as { outcome: string; job_id: string };
  back(to, `ok=${encodeURIComponent(`${f.job_type}: ${outcomeText(r.outcome)}`)}`);
}

/** CR7-03: bulk M02 request for every eligible article text not yet extracted with the active prompt. */
export async function requestPendingExtractions(form: FormData) {
  await requireSession();
  const reason = String(form.get("reason") ?? "").trim();
  const to = "/claims?tab=intake";
  if (reason.length < 5) back(to, "error=a+reason+of+at+least+5+characters+is+required");
  const supabase = await createClient();
  const { data, error } = await supabase.rpc("request_pending_claim_extractions", { p_limit: 50, p_reason: reason });
  if (error) back(to, `error=${encodeURIComponent(error.message.slice(0, 400))}`);
  back(to, `ok=${encodeURIComponent(`${(data as { enqueued: number }).enqueued} extraction job(s) queued`)}`);
}
