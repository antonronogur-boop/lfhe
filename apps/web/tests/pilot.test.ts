import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import {
  COMPARATOR_METHODS, ComparatorSchema, CostAssumptionSchema, ProviderPriceSchema, CreateCycleSchema, FINDING_CLASSES, STAGES, TimerSchema, UX_SEVERITIES,
  UxFindingSchema, comparatorArgs, currentDisposition, formatDuration, missingLabel, timingByStage,
} from "@/lib/pilot";

const ID = "11111111-1111-4111-8111-111111111111";
const U = "22222222-2222-4222-8222-222222222222";
const migration = readFileSync(join(__dirname, "../../../database/migrations/20261011004100_p7_pilot_instrumentation.sql"), "utf8");

function enumValues(name: string): string[] {
  const m = migration.match(new RegExp(`CREATE TYPE lfhe\\.${name} AS ENUM \\(([^;]*)\\);`));
  return [...(m?.[1] ?? "").matchAll(/'([A-Z_]+)'/g)].map((x) => x[1]);
}

describe("Phase 7 pilot workspace helpers", () => {
  it("mirrors the closed database vocabularies", () => {
    expect([...STAGES]).toEqual(enumValues("pilot_stage"));
    expect([...UX_SEVERITIES]).toEqual(enumValues("pilot_ux_severity"));
    expect([...FINDING_CLASSES]).toEqual(enumValues("pilot_finding_class"));
    expect([...COMPARATOR_METHODS]).toEqual(enumValues("pilot_comparator_method"));
  });

  it("timers carry only a stage — no client-side duration or timestamp exists in the form contract", () => {
    const keys = Object.keys(TimerSchema.shape);
    expect(keys).toEqual(["cycle_id", "stage"]);
    expect(TimerSchema.safeParse({ cycle_id: ID, stage: "QA_RESOLUTION" }).success).toBe(true);
    expect(TimerSchema.safeParse({ cycle_id: ID, stage: "COFFEE" }).success).toBe(false);
  });

  it("LIVE cycles cannot claim replay material", () => {
    const base = { code: "P7C-LIVE-01", information_cutoff: "2026-10-20T10:00", input_scope: "public OSINT, 7 sources",
                   analyst_user_id: U, provider_setup: "anthropic / model" };
    expect(CreateCycleSchema.safeParse({ ...base, pilot_mode: "LIVE", data_boundary: "PUBLIC_OSINT" }).success).toBe(true);
    expect(CreateCycleSchema.safeParse({ ...base, pilot_mode: "LIVE", data_boundary: "AUTHORISED_PUBLIC_REPLAY" }).success).toBe(false);
    expect(CreateCycleSchema.safeParse({ ...base, pilot_mode: "REPLAY", data_boundary: "AUTHORISED_PUBLIC_REPLAY" }).success).toBe(true);
    expect(CreateCycleSchema.safeParse({ ...base, code: "cycle-1", pilot_mode: "LIVE", data_boundary: "SYNTHETIC" }).success).toBe(false);
  });

  it("comparators need an explicit baseline and basis unless the method is NONE", () => {
    const ok = ComparatorSchema.parse({ cycle_id: ID, method: "MATCHED_MANUAL_CONTROL", baseline_minutes: "90",
                                        baseline_basis: "TIMED_MEASUREMENT", comparable_scope: "yes", reference: "manual control run" });
    expect(comparatorArgs(ok)).toEqual({ method: "MATCHED_MANUAL_CONTROL", baseline_analyst_seconds: 5400,
                                         baseline_basis: "TIMED_MEASUREMENT", comparable_scope: true, reference: "manual control run" });
    const none = ComparatorSchema.parse({ cycle_id: ID, method: "NONE", comparable_scope: "no", reference: "no comparator exists" });
    expect(comparatorArgs(none)).toMatchObject({ baseline_analyst_seconds: null, baseline_basis: null });
    expect(ComparatorSchema.safeParse({ cycle_id: ID, method: "MATCHED_MANUAL_CONTROL", comparable_scope: "yes", reference: "x reference" }).success).toBe(false);
    expect(ComparatorSchema.safeParse({ cycle_id: ID, method: "MATCHED_MANUAL_CONTROL", baseline_minutes: "1.5",
                                        baseline_basis: "TIMED_MEASUREMENT", comparable_scope: "yes", reference: "x reference" }).success).toBe(false);
    expect(ComparatorSchema.safeParse({ cycle_id: ID, method: "NONE", baseline_minutes: "30", comparable_scope: "no", reference: "x reference" }).success).toBe(false);
  });

  it("cost assumptions are explicit positive inputs", () => {
    const base = { code: "COST-2026-A", currency: "EUR", loaded_hourly_cost: "55.00", weekly_work_hours: "40", working_weeks_per_year: "46",
                   basis: "organisation's loaded cost table 2026" };
    expect(CostAssumptionSchema.safeParse(base).success).toBe(true);
    expect(CostAssumptionSchema.safeParse({ ...base, loaded_hourly_cost: "0" }).success).toBe(false);
    expect(CostAssumptionSchema.safeParse({ ...base, weekly_work_hours: "90" }).success).toBe(false);
    expect(CostAssumptionSchema.safeParse({ ...base, basis: "" }).success).toBe(false);
  });

  it("provider prices are explicit per-million-token inputs for an allow-listed provider", () => {
    const p = { provider: "anthropic", model: "model-x-1", currency: "USD", input_cost_per_mtok: "3", output_cost_per_mtok: "15.5",
                effective_from: "2026-10-01T00:00", source: "provider price list 2026-10" };
    expect(ProviderPriceSchema.safeParse(p).success).toBe(true);
    expect(ProviderPriceSchema.safeParse({ ...p, provider: "fake" }).success).toBe(false);
    expect(ProviderPriceSchema.safeParse({ ...p, input_cost_per_mtok: "-1" }).success).toBe(false);
  });

  it("UX findings carry severity and class; blank optional fields are dropped", () => {
    const f = UxFindingSchema.parse({ cycle_id: "", area: "QA_VIEW", severity: "BLOCKING", finding_class: "SOFTWARE_DEFECT",
                                      title: "Release button missing", description: "no release button after approval", route: "" });
    expect(f.cycle_id).toBeUndefined();
    expect(f.route).toBeUndefined();
  });

  it("sums only the cycle analyst's closed time and flags open timers", () => {
    const rows = [
      { stage: "REPORT_EDIT", user_id: U, segments: 2, open_segments: 0, active_seconds: "600.5" },
      { stage: "QA_RESOLUTION", user_id: U, segments: 1, open_segments: 1, active_seconds: "120" },
      { stage: "REPORT_EDIT", user_id: ID, segments: 1, open_segments: 0, active_seconds: "999" },
    ];
    const t = timingByStage(rows, U);
    expect(t.total).toBeCloseTo(720.5);
    expect(t.stages.map(([s]) => s)).toEqual(["QA_RESOLUTION", "REPORT_EDIT"]);
    expect(t.open).toBe(true);
    expect(formatDuration(3725)).toBe("1 h 02 min");
    expect(formatDuration(65)).toBe("1 min 05 s");
  });

  it("labels missing measurements and reads the latest disposition", () => {
    expect(missingLabel("REPORT_NOT_AT_TERMINAL_STATE:QA_PASSED")).toContain("QA_PASSED");
    expect(missingLabel("COMPARATOR_METHOD_NOT_RECORDED")).toBe("comparison method not recorded");
    const h = [{ finding_id: ID, disposition: "BACKLOG", seq: 1 }, { finding_id: ID, disposition: "RESOLVED", seq: 3 }];
    expect(currentDisposition(h, ID)).toBe("RESOLVED");
    expect(currentDisposition(h, U)).toBe("OPEN");
  });
});

import { capacityStatement, runSummary, timeByGroup, timeCost } from "@/lib/pilot";

describe("CR7-03 pilot summary helpers", () => {
  it("groups active time by workflow stage group", () => {
    const g = timeByGroup([{ stage: "CLAIM_REVIEW", user_id: "a", active_seconds: 60, open_segments: 0 },
      { stage: "CONTENT_APPROVAL", user_id: "r", active_seconds: "30", open_segments: 0 },
      { stage: "SECURITY_REVIEW", user_id: "s", active_seconds: 20, open_segments: 0 },
      { stage: "RELEASE", user_id: "x", active_seconds: 10, open_segments: 0 }]);
    expect(g).toEqual({ analyst: 60, reviewer: 30, security: 20, release: 10 });
  });
  it("keeps model cost unknown unless every run is priced in one currency", () => {
    const base = { module_code: "M07_INTELLIGENCE_ASSESSOR", provider: "anthropic", model: "claude-sonnet-5-5", status: "SUCCEEDED",
      input_tokens: 1000, output_tokens: 500, is_repair_run: false };
    expect(runSummary([{ ...base, model_cost: "0.01", cost_currency: "USD" }, { ...base, model_cost: null, cost_currency: null }]).cost).toBeNull();
    const s = runSummary([{ ...base, model_cost: "0.01", cost_currency: "USD" }, { ...base, model_cost: "0.02", cost_currency: "USD" }]);
    expect(s.cost?.currency).toBe("USD");
    expect(s.cost?.value).toBeCloseTo(0.03);
    expect(s.tokensIn).toBe(2000);
  });
  it("never presents capacity value without a comparator", () => {
    expect(capacityStatement(null)).toContain("productivity claim not available");
    expect(capacityStatement("NONE")).toContain("observational only");
    expect(timeCost(3600, 6600)).toBe(6600);
    expect(timeCost(3600, null)).toBeNull();
  });
});
