import { z } from "zod";

/**
 * Phase 7 pilot workspace — pure helpers (measurement only).
 * Pilot records never change analytical, QA, approval, security or release state. Timing uses the
 * database server clock (lfhe.pilot_start_timer / pilot_stop_timer): the UI never submits a
 * duration or a timestamp, so analyst time is never typed in or inferred afterwards. Completeness is
 * computed by lfhe.pilot_cycle_missing_metrics and closing a cycle as COMPLETED fails closed there.
 */
export const PILOT_MODES = ["LIVE", "REPLAY"] as const;
export const DATA_BOUNDARIES = ["PUBLIC_OSINT", "SYNTHETIC", "AUTHORISED_PUBLIC_REPLAY"] as const;
export const STAGES = [
  "SOURCE_REVIEW", "CLAIM_REVIEW", "EVENT_REVIEW", "ASSESSMENT_REVIEW", "REPORT_SELECTION", "REPORT_EDIT", "QA_RESOLUTION",
  "WARNING_HANDLING", "CONTENT_APPROVAL", "SECURITY_REVIEW", "RELEASE", "PROVENANCE_INSPECTION", "CORRECTION", "OTHER",
] as const;
export const UX_AREAS = [
  "SOURCE_REVIEW", "CLAIM_REVIEW", "EVENT_ASSESSMENT", "REPORT_WORKSPACE", "QA_VIEW", "WARNING_HANDLING", "CONTENT_APPROVAL",
  "SECURITY_REVIEW", "RELEASE", "RELEASED_PROVENANCE", "PILOT_WORKSPACE", "OTHER",
] as const;
export const UX_SEVERITIES = ["BLOCKING", "MAJOR", "MINOR", "ENHANCEMENT"] as const;
export const FINDING_CLASSES = [
  "MEASUREMENT", "USABILITY_DEFECT", "SOFTWARE_DEFECT", "ANALYTICAL_DEFECT", "MODEL_PERFORMANCE_LIMITATION", "CONFIGURATION_PROBLEM",
  "FEATURE_REQUEST", "FUTURE_CAPABILITY_OPPORTUNITY",
] as const;
export const COMPARATOR_METHODS = [
  "PRIOR_DOCUMENTED_MANUAL_WORKFLOW", "MATCHED_MANUAL_CONTROL", "MATCHED_HISTORICAL_CYCLE", "CONTROLLED_ANALYST_BENCHMARK",
  "EQUIVALENT_TASK_WITHOUT_LFHE", "NONE",
] as const;
export const BASELINE_BASES = ["TIMED_MEASUREMENT", "DOCUMENTED_RECORD"] as const;
export const DISPOSITIONS = ["RESOLVED", "PATH_DECLARED_UNUSABLE", "BACKLOG", "NOT_A_DEFECT", "REOPENED"] as const;

const uuid = z.string().uuid();
const text = (min: number, max = 4000) => z.string().trim().min(min).max(max);

export const CreateCycleSchema = z.object({
  code: z.string().regex(/^P7C-[A-Z0-9][A-Z0-9_-]{1,40}$/, "code must look like P7C-LIVE-01"),
  pilot_mode: z.enum(PILOT_MODES),
  information_cutoff: z.string().min(10),
  data_boundary: z.enum(DATA_BOUNDARIES),
  input_scope: text(10),
  analyst_user_id: uuid,
  provider_setup: text(3, 500),
}).refine((c) => c.pilot_mode === "REPLAY" || c.data_boundary !== "AUTHORISED_PUBLIC_REPLAY",
          { message: "a LIVE cycle cannot use replay material" });

export const CycleRefSchema = z.object({ cycle_id: uuid });
export const BindReportSchema = z.object({ cycle_id: uuid, report_id: uuid });
export const TimerSchema = z.object({ cycle_id: uuid, stage: z.enum(STAGES) });
export const WorkloadSchema = z.object({
  cycle_id: uuid,
  mental: z.coerce.number().int().min(0).max(100), physical: z.coerce.number().int().min(0).max(100),
  temporal: z.coerce.number().int().min(0).max(100), performance: z.coerce.number().int().min(0).max(100),
  effort: z.coerce.number().int().min(0).max(100), frustration: z.coerce.number().int().min(0).max(100),
  note: z.string().max(2000).optional(),
});
export const UxFindingSchema = z.object({
  cycle_id: uuid.optional().or(z.literal("").transform(() => undefined)),
  area: z.enum(UX_AREAS), severity: z.enum(UX_SEVERITIES), finding_class: z.enum(FINDING_CLASSES),
  title: text(5, 200), description: text(10),
  route: z.string().regex(/^\/[A-Za-z0-9/_[\]-]*$/).optional().or(z.literal("").transform(() => undefined)),
});
export const DisposeSchema = z.object({ cycle_id: uuid.optional().or(z.literal("").transform(() => undefined)), finding_id: uuid,
  disposition: z.enum(DISPOSITIONS), note: text(5) });
export const ComparatorSchema = z.object({
  cycle_id: uuid,
  method: z.enum(COMPARATOR_METHODS),
  baseline_minutes: z.string().optional(),
  baseline_basis: z.enum(BASELINE_BASES).optional().or(z.literal("").transform(() => undefined)),
  comparable_scope: z.enum(["yes", "no"]),
  reference: text(5, 1000),
}).superRefine((c, ctx) => {
  const minutes = c.baseline_minutes ? Number(c.baseline_minutes) : undefined;
  if (c.method === "NONE" && (minutes !== undefined || c.baseline_basis))
    ctx.addIssue({ code: "custom", message: "method NONE records no baseline" });
  if (c.method !== "NONE" && (!minutes || !Number.isInteger(minutes) || minutes <= 0 || !c.baseline_basis))
    ctx.addIssue({ code: "custom", message: "a comparator needs a positive whole-minute baseline and its basis" });
});
export const CloseSchema = z.object({ cycle_id: uuid, outcome: z.enum(["COMPLETED", "STOPPED"]), note: text(10) });
export const CostAssumptionSchema = z.object({
  code: z.string().regex(/^COST-[A-Z0-9][A-Z0-9_-]{1,40}$/),
  currency: z.string().regex(/^[A-Z]{3}$/),
  loaded_hourly_cost: z.string().regex(/^\d+(\.\d{1,2})?$/).refine((v) => Number(v) > 0, "must be > 0"),
  weekly_work_hours: z.string().regex(/^\d+(\.\d{1,2})?$/).refine((v) => Number(v) > 0 && Number(v) <= 80, "0 < hours <= 80"),
  working_weeks_per_year: z.string().regex(/^\d+(\.\d)?$/).refine((v) => Number(v) > 0 && Number(v) <= 52, "0 < weeks <= 52"),
  basis: text(10, 1000),
});

export const ProviderPriceSchema = z.object({
  provider: z.enum(["anthropic"]),
  model: z.string().regex(/^[a-z0-9][a-z0-9._:-]{1,99}$/),
  currency: z.string().regex(/^[A-Z]{3}$/),
  input_cost_per_mtok: z.string().regex(/^\d+(\.\d{1,4})?$/),
  output_cost_per_mtok: z.string().regex(/^\d+(\.\d{1,4})?$/),
  effective_from: z.string().min(10),
  source: text(5, 500),
});

/** Comparator arguments for lfhe.pilot_record_comparator; whole minutes → seconds, no fractional time. */
export function comparatorArgs(c: z.infer<typeof ComparatorSchema>) {
  return {
    method: c.method,
    baseline_analyst_seconds: c.method === "NONE" ? null : Number(c.baseline_minutes) * 60,
    baseline_basis: c.method === "NONE" ? null : c.baseline_basis,
    comparable_scope: c.comparable_scope === "yes",
    reference: c.reference,
  };
}

export interface TimingRow { stage: string; user_id: string; segments: number; open_segments: number; active_seconds: string | number }

/** Analyst active time per stage (closed segments only — the database sums them). */
export function timingByStage(rows: TimingRow[], analystId: string) {
  const out = new Map<string, number>();
  for (const r of rows) if (r.user_id === analystId) out.set(r.stage, (out.get(r.stage) ?? 0) + Number(r.active_seconds));
  const total = [...out.values()].reduce((a, b) => a + b, 0);
  return { stages: [...out.entries()].sort(([a], [b]) => a.localeCompare(b)), total, open: rows.some((r) => r.open_segments > 0) };
}

export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
  return h > 0 ? `${h} h ${String(m).padStart(2, "0")} min` : `${m} min ${String(r).padStart(2, "0")} s`;
}

const MISSING_LABELS: Record<string, string> = {
  REPORT_NOT_BOUND: "no report bound to the cycle",
  ANALYST_TIMING_MISSING: "no closed timing segment by the cycle analyst",
  TIMING_SEGMENT_OPEN: "a timer is still running",
  COMPARATOR_METHOD_NOT_RECORDED: "comparison method not recorded",
  ANALYST_WORKLOAD_MISSING: "analyst workload rating missing",
  MODEL_RUNS_NOT_BOUND: "model runs not bound",
  REPORT_CHAIN_MODEL_RUNS_NOT_BOUND: "some model runs of the report chain are not bound",
  BLOCKING_UX_FINDING_OPEN: "an open BLOCKING UX finding",
  CYCLE_UNKNOWN: "unknown cycle",
};

export function missingLabel(code: string): string {
  if (code.startsWith("REPORT_NOT_AT_TERMINAL_STATE:"))
    return `report not at a terminal pilot state (now: ${code.split(":")[1]})`;
  return MISSING_LABELS[code] ?? code;
}

/** Latest disposition of a UX finding (append-only history; OPEN when none). */
export function currentDisposition(history: { finding_id: string; disposition: string; seq: number }[], findingId: string): string {
  const h = history.filter((d) => d.finding_id === findingId).sort((a, b) => b.seq - a.seq);
  return h[0]?.disposition ?? "OPEN";
}

/* ---- CR7-03 pilot workspace summary (pure; presentation only) ---------------------------------------------------- */
/** Workflow-stage groups used to show who spent the time; a stage group is not a role check. */
export const STAGE_GROUPS: Record<string, readonly string[]> = {
  analyst: ["SOURCE_REVIEW", "CLAIM_REVIEW", "EVENT_REVIEW", "ASSESSMENT_REVIEW", "REPORT_SELECTION", "REPORT_EDIT", "QA_RESOLUTION", "CORRECTION", "OTHER"],
  reviewer: ["WARNING_HANDLING", "CONTENT_APPROVAL"],
  security: ["SECURITY_REVIEW"],
  release: ["RELEASE", "PROVENANCE_INSPECTION"],
};

export interface TimingAll { stage: string; user_id: string; active_seconds: number | string | null; open_segments: number | string | null }

export function timeByGroup(rows: TimingAll[]): Record<string, number> {
  const out: Record<string, number> = { analyst: 0, reviewer: 0, security: 0, release: 0 };
  for (const r of rows) {
    const g = Object.entries(STAGE_GROUPS).find(([, stages]) => stages.includes(r.stage))?.[0] ?? "analyst";
    out[g] += Number(r.active_seconds ?? 0);
  }
  return out;
}

export interface RunSummaryRow { module_code: string; provider: string; model: string; status: string; input_tokens: number | null;
  output_tokens: number | null; model_cost: string | null; cost_currency: string | null; is_repair_run: boolean }

/** AI execution summary; cost stays "unknown" if any run lacks a matching explicit price (never zero). */
export function runSummary(rows: RunSummaryRow[]) {
  const models = [...new Set(rows.map((r) => `${r.provider} / ${r.model}`))];
  const tokensIn = rows.reduce((a, r) => a + (r.input_tokens ?? 0), 0);
  const tokensOut = rows.reduce((a, r) => a + (r.output_tokens ?? 0), 0);
  const priced = rows.filter((r) => r.model_cost !== null);
  const currencies = [...new Set(priced.map((r) => r.cost_currency))];
  const cost = priced.length === rows.length && rows.length > 0 && currencies.length === 1
    ? { value: priced.reduce((a, r) => a + Number(r.model_cost), 0), currency: currencies[0] as string } : null;
  const byModule: Record<string, number> = {};
  for (const r of rows) byModule[r.module_code] = (byModule[r.module_code] ?? 0) + 1;
  return { runs: rows.length, failed: rows.filter((r) => r.status !== "SUCCEEDED").length, repairs: rows.filter((r) => r.is_repair_run).length,
    models, tokensIn, tokensOut, cost, unpriced: rows.length - priced.length, byModule };
}

/** Analyst-time cost at an explicit loaded hourly cost. It is NOT a saving and NOT a capacity value: a capacity value
 *  needs a comparator baseline (hours released); without one the result is observational only. */
export function timeCost(seconds: number, hourly: number | null) {
  return hourly === null ? null : Math.round((seconds / 3600) * hourly * 100) / 100;
}

export function capacityStatement(method: string | null | undefined): string {
  if (!method) return "No comparator recorded — observational only / productivity claim not available.";
  if (method === "NONE") return "Comparator NONE — observational only / productivity claim not available.";
  return `Comparator ${method.replaceAll("_", " ").toLowerCase()} — capacity value can be computed from the timed baseline (not a cash saving).`;
}
