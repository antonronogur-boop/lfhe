import { describe, expect, it } from "vitest";

import {
  type CanonicalReport, DecideCandidateSchema, EditStatementSchema, REPORT_SECTIONS, SECTION_KEYS, SELECTABLE_SECTIONS,
  applyStatementEdit, applyStatementMove, applyStatementRemoval, confidenceLabel, contentFromCanonical, decideCandidateArgs,
  diffVersions, removalDecisions,
} from "@/lib/reports";

const ID = "11111111-1111-4111-8111-111111111111";
const S1 = "22222222-2222-4222-8222-222222222222";
const S2 = "33333333-3333-4333-8333-333333333333";
const S3 = "44444444-4444-4444-8444-444444444444";
const HASH = "b".repeat(64);

function report(): CanonicalReport {
  const st = (id: string, text: string, sources: string[], role = "KEY_JUDGMENT") => ({
    statement_no: 1, report_statement_local_id: id, statement_role: role as never, text, sources,
    final_analytic_confidence: "LOW", likelihood_term: null, editorial_transform: "PARAPHRASE", contested: false,
  });
  return {
    version_no: 1, human_removals: [], length_status: "WITHIN_LIMIT", coverage: [],
    sections: [
      { section: "KEY_JUDGMENT", items: [{ item_no: 1, item_local_id: "KJ1", source_candidate_id: ID, final_analytic_confidence: "LOW",
        pins: {}, statements: [st("RS1", "Judgment.", [S1]), st("RS2", "Fact.", [S2]), st("RS3", "Caveat.", [S3], "CAVEAT")] }] },
      { section: "WHAT_TO_WATCH", items: [] },
    ],
  };
}

describe("report workspace helpers (Phase 5)", () => {
  it("mirrors the closed database vocabularies", () => {
    expect(REPORT_SECTIONS).toEqual(["KEY_JUDGMENT", "SIGNIFICANT_DEVELOPMENT", "INDICATOR_WARNING", "TREND_WATCH", "WHAT_TO_WATCH", "CAVEAT"]);
    expect(Object.values(SECTION_KEYS)).toEqual(["key_judgments", "significant_developments", "indicators_warning", "trend_watch",
                                                 "what_to_watch", "caveats"]);
    expect(SELECTABLE_SECTIONS.TREND_VERSION).toEqual(["TREND_WATCH"]);
    expect(Object.values(SELECTABLE_SECTIONS).flat()).not.toContain("CAVEAT");
  });

  it("rebuilds the edit shape from canonical JSON with every source mapping kept", () => {
    const c = contentFromCanonical(report());
    expect(c.key_judgments[0].statements.map((s) => s.source_assessment_statement_ids)).toEqual([[S1], [S2], [S3]]);
    expect(c.what_to_watch).toEqual([]);
  });

  it("rewording keeps sources, role, confidence and likelihood (52: provenance survives a human edit)", () => {
    const c = applyStatementEdit(contentFromCanonical(report()), "RS1", "  Shorter judgment. ", "COMPRESSION");
    const s = c.key_judgments[0].statements[0];
    expect([s.text, s.editorial_transform, s.source_assessment_statement_ids, s.final_analytic_confidence, s.statement_role])
      .toEqual(["Shorter judgment.", "COMPRESSION", [S1], "LOW", "KEY_JUDGMENT"]);
    expect(() => applyStatementEdit(contentFromCanonical(report()), "RS9", "x", "PARAPHRASE")).toThrow();
  });

  it("reorders within an item and records explicit human removals", () => {
    const moved = applyStatementMove(contentFromCanonical(report()), "RS2", -1);
    expect(moved.key_judgments[0].statements.map((s) => s.report_statement_local_id)).toEqual(["RS2", "RS1", "RS3"]);
    const { content, removed } = applyStatementRemoval(contentFromCanonical(report()), "RS2");
    expect(removed).toEqual([S2]);
    expect(content.key_judgments[0].statements.map((s) => s.report_statement_local_id)).toEqual(["RS1", "RS3"]);
  });

  it("compares versions statement by statement (53)", () => {
    const a = report();
    const b = report();
    b.sections[0].items[0].statements[0].text = "Changed judgment.";
    b.sections[0].items[0].statements.splice(1, 1);
    const d = diffVersions(a, b);
    expect(d.find((x) => x.key.endsWith("RS1"))?.kind).toBe("changed");
    expect(d.find((x) => x.key.endsWith("RS2"))?.kind).toBe("removed");
    expect(d.find((x) => x.key.endsWith("RS3"))?.kind).toBe("unchanged");
  });

  it("never renders low or missing confidence like high confidence", () => {
    expect(confidenceLabel("LOW")).toEqual({ cls: "conf-low", label: "low confidence (analyst-approved)" });
    expect(confidenceLabel("HIGH").cls).not.toBe(confidenceLabel("LOW").cls);
    expect(confidenceLabel(null).label).toBe("no analytic confidence attached");
  });

  it("binds selection decisions to the candidate hash and the previous decision (51)", () => {
    const ok = DecideCandidateSchema.parse({ report_id: ID, candidate_id: ID, object_hash: HASH, expected_previous_decision_id: "",
                                             decision: "INCLUDE", section: "KEY_JUDGMENT", priority: "2", reason: "lead judgment" });
    expect(decideCandidateArgs(ok)).toEqual({ p_candidate: ID, p_object_hash: HASH, p_decision: "INCLUDE", p_section: "KEY_JUDGMENT",
                                              p_priority: 2, p_expected_previous_decision: null, p_reason: "lead judgment" });
    const ex = DecideCandidateSchema.parse({ report_id: ID, candidate_id: ID, object_hash: HASH, expected_previous_decision_id: ID,
                                             decision: "EXCLUDE", section: "KEY_JUDGMENT", priority: "3", reason: "out of scope" });
    expect([ex.section, ex.priority]).toEqual([null, null]);
    expect(() => DecideCandidateSchema.parse({ report_id: ID, candidate_id: ID, object_hash: HASH, expected_previous_decision_id: "",
                                               decision: "INCLUDE", section: "", priority: "", reason: "missing section" })).toThrow();
    expect(() => DecideCandidateSchema.parse({ report_id: ID, candidate_id: ID, object_hash: HASH, expected_previous_decision_id: "",
                                               decision: "INCLUDE", section: "CAVEAT", priority: "1", reason: "caveat section" })).toThrow();
    expect(() => EditStatementSchema.parse({ report_id: ID, version_id: ID, version_hash: "x", statement_local_id: "RS1", text: "t",
                                             editorial_transform: "PARAPHRASE", reason: "short" })).toThrow();
  });

  it("requires a decision for every removal proposal", () => {
    expect(removalDecisions({ decision_a: "ACCEPT", decision_b: "REJECT" }, ["a", "b"])).toEqual([
      { proposal_id: "a", decision: "ACCEPT" }, { proposal_id: "b", decision: "REJECT" }]);
    expect(() => removalDecisions({ decision_a: "ACCEPT" }, ["a", "b"])).toThrow();
  });
});
