"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { type Permission, requirePermission } from "@/lib/auth";
import { formObject } from "@/lib/claims";
import {
  BindReportSchema, CloseSchema, ComparatorSchema, CostAssumptionSchema, CreateCycleSchema, ProviderPriceSchema, CycleRefSchema, DisposeSchema, TimerSchema,
  UxFindingSchema, WorkloadSchema, comparatorArgs,
} from "@/lib/pilot";
import { createClient } from "@/lib/supabase/server";

/*
 * Phase 7 pilot server actions (measurement only). The permission check here only gives a readable
 * failure; PostgreSQL re-checks the human identity and PILOT_* permission, writes only pilot_* tables
 * (plus the audit log for low-volume pilot decisions) and uses its own clock for every timer.
 */
function back(cycleId: string | undefined, query: string): never {
  revalidatePath("/pilot");
  redirect(cycleId ? `/pilot/${cycleId}?${query}` : `/pilot?${query}`);
}

function fail(cycleId: string | undefined, message: string): never {
  back(cycleId, `error=${encodeURIComponent(message.slice(0, 400))}`);
}

type Parser<T> = { safeParse: (x: unknown) => { success: true; data: T } | { success: false; error: { issues: { message: string }[] } } };

async function parse<T>(perm: Permission, form: FormData, schema: Parser<T>): Promise<T> {
  await requirePermission(perm);
  const raw = formObject(form);
  const f = schema.safeParse(raw);
  if (!f.success) fail(typeof raw.cycle_id === "string" && raw.cycle_id ? raw.cycle_id : undefined, f.error.issues[0]?.message ?? "invalid input");
  return f.data;
}

async function rpc(cycleId: string | undefined, fn: string, args: Record<string, unknown>) {
  const supabase = await createClient();
  const { data, error } = await supabase.rpc(fn, args);
  if (error) fail(cycleId, error.message);
  return data;
}

export async function createCycle(form: FormData) {
  const f = await parse("PILOT_MANAGE", form, CreateCycleSchema);
  const id = await rpc(undefined, "pilot_create_cycle", { p: { ...f, information_cutoff: new Date(f.information_cutoff).toISOString() } });
  back(id as string, "ok=cycle-created");
}

export async function bindReport(form: FormData) {
  const f = await parse("PILOT_MANAGE", form, BindReportSchema);
  await rpc(f.cycle_id, "pilot_bind_report", { p_cycle: f.cycle_id, p_report: f.report_id });
  back(f.cycle_id, "ok=report-bound");
}

export async function bindChainRuns(form: FormData) {
  const f = await parse("PILOT_MANAGE", form, CycleRefSchema);
  const n = await rpc(f.cycle_id, "pilot_bind_model_runs", { p_cycle: f.cycle_id, p_runs: null, p_binding: "REPORT_CHAIN" });
  back(f.cycle_id, `ok=${n}-model-runs-bound`);
}

export async function startTimer(form: FormData) {
  const f = await parse("PILOT_PARTICIPATE", form, TimerSchema);
  await rpc(f.cycle_id, "pilot_start_timer", { p_cycle: f.cycle_id, p_stage: f.stage });
  back(f.cycle_id, `ok=timer-${f.stage.toLowerCase()}`);
}

export async function stopTimer(form: FormData) {
  const f = await parse("PILOT_PARTICIPATE", form, CycleRefSchema);
  await rpc(f.cycle_id, "pilot_stop_timer", { p_cycle: f.cycle_id });
  back(f.cycle_id, "ok=timer-stopped");
}

export async function recordWorkload(form: FormData) {
  const { cycle_id, ...p } = await parse("PILOT_PARTICIPATE", form, WorkloadSchema);
  await rpc(cycle_id, "pilot_record_workload", { p_cycle: cycle_id, p });
  back(cycle_id, "ok=workload-recorded");
}

export async function recordUxFinding(form: FormData) {
  const f = await parse("PILOT_PARTICIPATE", form, UxFindingSchema);
  await rpc(f.cycle_id, "pilot_record_ux_finding", { p: f });
  back(f.cycle_id, "ok=ux-finding-recorded");
}

export async function disposeUxFinding(form: FormData) {
  const f = await parse("PILOT_MANAGE", form, DisposeSchema);
  await rpc(f.cycle_id, "pilot_dispose_ux_finding", { p_finding: f.finding_id, p_disposition: f.disposition, p_note: f.note });
  back(f.cycle_id, "ok=ux-finding-disposed");
}

export async function recordComparator(form: FormData) {
  const f = await parse("PILOT_MANAGE", form, ComparatorSchema);
  await rpc(f.cycle_id, "pilot_record_comparator", { p_cycle: f.cycle_id, p: comparatorArgs(f) });
  back(f.cycle_id, "ok=comparator-recorded");
}

export async function closeCycle(form: FormData) {
  const f = await parse("PILOT_MANAGE", form, CloseSchema);
  await rpc(f.cycle_id, "pilot_close_cycle", { p_cycle: f.cycle_id, p_outcome: f.outcome, p_note: f.note });
  back(f.cycle_id, `ok=cycle-${f.outcome.toLowerCase()}`);
}

export async function recordCostAssumption(form: FormData) {
  const f = await parse("PILOT_MANAGE", form, CostAssumptionSchema);
  await rpc(undefined, "pilot_record_cost_assumption", { p: f });
  back(undefined, "ok=cost-assumption-recorded");
}

export async function recordProviderPrice(form: FormData) {
  const f = await parse("PILOT_MANAGE", form, ProviderPriceSchema);
  await rpc(undefined, "pilot_record_provider_price", { p: { ...f, effective_from: new Date(f.effective_from).toISOString() } });
  back(undefined, "ok=provider-price-recorded");
}
