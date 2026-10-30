import { describe, expect, it } from "vitest";

import { ModifyApproveSchema, ReviewAssessmentSchema, modifiedPayload } from "@/lib/assessments";
import { EventFormSchema, RelevanceDecisionSchema, relevanceOverride } from "@/lib/events";
import { JobRequestSchema, jobParams } from "@/lib/jobs";

const U = "11111111-1111-4111-8111-111111111111";
const H = "a".repeat(64);

describe("CR7-03 job requests", () => {
  it("only offers the requestable pipeline jobs; report jobs keep their own human paths", () => {
    expect(JobRequestSchema.safeParse({ job_type: "EDIT_REPORT", return_to: "/x", reason: "reason ok" }).success).toBe(false);
  });
  it("needs an analysis context for M05 / M06 / M07 and the exact version", () => {
    expect(JobRequestSchema.safeParse({ job_type: "BUILD_EVENTS", return_to: "/claims", reason: "group claims", claim_ids: [U] }).success).toBe(false);
    const ok = JobRequestSchema.parse({ job_type: "ASSESS_EVENT", return_to: "/events/x", reason: "assess it", ctx: "live",
      event_version_id: U, event_version_hash: H });
    expect(jobParams(ok, { report_mode: "REPLAY", information_cutoff: "2026-03-01T00:00:00Z" })).toEqual({
      event_version_id: U, event_version_hash: H, report_mode: "REPLAY", information_cutoff: "2026-03-01T00:00:00Z" });
  });
  it("never accepts a typed cutoff — mode and cutoff come only from the server-resolved context", () => {
    const f = JobRequestSchema.parse({ job_type: "BUILD_EVENTS", return_to: "/claims", reason: "group claims", claim_ids: [U], ctx: "live",
      information_cutoff: "2020-01-01" } as Record<string, unknown>);
    expect(jobParams(f, null)).toEqual({ claim_ids: [U] });
  });
});

describe("assessment review", () => {
  it("approval requires a final confidence with a rationale; other decisions must not set it", () => {
    const base = { version_id: U, version_hash: H, reason: "reviewed it" };
    expect(ReviewAssessmentSchema.safeParse({ ...base, decision: "APPROVE" }).success).toBe(false);
    expect(ReviewAssessmentSchema.safeParse({ ...base, decision: "APPROVE", final_confidence: "LOW", confidence_rationale: "short" }).success).toBe(false);
    expect(ReviewAssessmentSchema.safeParse({ ...base, decision: "APPROVE", final_confidence: "LOW",
      confidence_rationale: "Single contradicted official source." }).success).toBe(true);
    expect(ReviewAssessmentSchema.safeParse({ ...base, decision: "REJECT", final_confidence: "HIGH" }).success).toBe(false);
    expect(ModifyApproveSchema.safeParse({ ...base, final_confidence: "LOW", confidence_rationale: "x" }).success).toBe(false);
  });
  it("modify-and-approve keeps the statement structure and changes only edited texts", () => {
    const st = { statement_local_id: "AS1", statement_type: "KNOWN_FACT", statement_text: "Old.", provenance_class: "CASE_EVIDENCE",
      evidence_required: true, uses_baseline: false, attribution_required: true, attribution_text: "X said", supporting_claim_ids: [U],
      contradicting_claim_ids: [], supporting_reference_context_ids: [], premise_statement_local_ids: [], likelihood: null };
    const p = modifiedPayload({ statements: [st], derived_summary: null, indicators_to_watch: null }, { AS1: " New. " });
    expect(p.assessment_statements[0]).toEqual({ ...st, statement_text: "New." });
    expect(p.derived_summary).toEqual({ text: "", source_statement_ids: [] });
  });
});

describe("event forms", () => {
  it("needs at least one claim and consistent dates", () => {
    const base = { title: "Tanker arrival", description: "d", event_type: "DEPLOYMENT", reason: "analyst creates", locations: "" };
    expect(EventFormSchema.safeParse({ ...base, claims: [] }).success).toBe(false);
    expect(EventFormSchema.safeParse({ ...base, claims: [{ claim_id: U, role: "CONTRADICTS" }], event_date_end: "2026-01-01" }).success).toBe(false);
    expect(EventFormSchema.parse({ ...base, claims: [{ claim_id: U, role: "CONTRADICTS" }], locations: "Fort Aster, Base North" }).locations)
      .toEqual(["Fort Aster", "Base North"]);
  });
  it("an override must change something; validate carries no override", () => {
    const base = { event_id: U, result_id: U, reason: "checked the result" };
    expect(RelevanceDecisionSchema.safeParse({ ...base, action: "OVERRIDE" }).success).toBe(false);
    expect(relevanceOverride(RelevanceDecisionSchema.parse({ ...base, action: "VALIDATE" }))).toBeNull();
    expect(relevanceOverride(RelevanceDecisionSchema.parse({ ...base, action: "OVERRIDE", priority_score: "1.5" }))).toEqual({ priority_score: 1.5 });
  });
});

import { AutopilotSchema, BatchEventSchema, batchSummary, parsePicks } from "@/lib/inbox";

describe("CR7-05 inbox", () => {
  const V = "22222222-2222-4222-8222-222222222222";
  const pick = `${U}|${V}|${H}`;
  it("a batch decision needs an audited reason and exact event versions, at most 50", () => {
    expect(BatchEventSchema.safeParse({ decision: "CONFIRM", reason: "reviewed", items: [pick] }).success).toBe(true);
    expect(BatchEventSchema.safeParse({ decision: "CONFIRM", reason: "ok", items: [pick] }).success).toBe(false);
    expect(BatchEventSchema.safeParse({ decision: "CONFIRM", reason: "reviewed", items: [] }).success).toBe(false);
    expect(BatchEventSchema.safeParse({ decision: "CONFIRM", reason: "reviewed", items: ["not-a-pick"] }).success).toBe(false);
    expect(BatchEventSchema.safeParse({ decision: "APPROVE", reason: "reviewed", items: [pick] }).success).toBe(false);
    expect(BatchEventSchema.safeParse({ decision: "REJECT", reason: "reviewed", items: Array(51).fill(pick) }).success).toBe(false);
  });
  it("splits a selection into the exact event, version and hash", () => {
    expect(parsePicks([pick])).toEqual([{ event_id: U, version_id: V, version_hash: H }]);
  });
  it("autopilot is on or off with a reason", () => {
    expect(AutopilotSchema.safeParse({ report_id: U, enabled: "on", reason: "run it" }).success).toBe(true);
    expect(AutopilotSchema.safeParse({ report_id: U, enabled: "maybe", reason: "run it" }).success).toBe(false);
  });
  it("reports partial failures instead of hiding them", () => {
    expect(batchSummary(2, [])).toBe("2 event(s) done");
    expect(batchSummary(1, [{ id: U, message: "stale hash" }])).toContain("1 not done: stale hash");
  });
});
