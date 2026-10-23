import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import {
  AcknowledgeSchema, CONTENT_DECISIONS, ContentDecisionSchema, type Eligibility, type Finding, RELEASE_RETURN_DECISIONS, ReleaseDecisionSchema,
  ReleaseSchema, SECURITY_DECISIONS, SecurityDecisionSchema, blocksRelease, byteaToBytes, checklistRows, groupFindings,
  needsAcknowledgement, workflowLabel,
} from "@/lib/release";

const ID = "11111111-1111-4111-8111-111111111111";
const R = "22222222-2222-4222-8222-222222222222";
const HASH = "c".repeat(64);
const base = { report_id: ID, version_id: R, version_hash: HASH };

function f(over: Partial<Finding>): Finding {
  return { id: R, qa_run_id: ID, finding_no: 1, check_id: "QA-01", layer: "S", status: "PASS", severity: "INFO", finding_code: "X",
           affected_object_id: null, affected_statement_id: null, details: "d", evidence_refs: [], recommended_action: "NO_ACTION", ...over };
}

describe("Phase 6 workspace helpers", () => {
  it("mirrors the closed database decision vocabularies", () => {
    expect(CONTENT_DECISIONS).toEqual(["APPROVE", "RETURN_FOR_REVISION", "REJECT"]);
    expect(SECURITY_DECISIONS).toEqual(["APPROVED", "RETURN_FOR_REVISION", "REJECTED"]);
    expect(RELEASE_RETURN_DECISIONS).toEqual(["RETURN_FOR_REVISION", "REJECT_RELEASE"]);
    expect(RELEASE_RETURN_DECISIONS).not.toContain("APPROVE_FOR_RELEASE" as never);   // release only through release_report
  });

  it("86: groups findings by severity, counts release blockers and acknowledgements like the database", () => {
    const fs = [f({ id: "a", status: "FAIL", severity: "CRITICAL", check_id: "QA-08" }), f({ id: "b", status: "WARNING", severity: "WARNING", check_id: "QA-13" }),
                f({ id: "c", status: "WARNING", severity: "MAJOR", check_id: "S18" }), f({ id: "d", check_id: "QA-02", layer: "D" })];
    const g = groupFindings(fs);
    expect(g.groups.map((x) => x.severity)).toEqual(["CRITICAL", "MAJOR", "WARNING"]);
    expect([g.blocking, g.warnings, g.passedChecks]).toEqual([1, 2, ["D:QA-02"]]);
    expect(blocksRelease({ status: "FAIL", severity: "MAJOR" })).toBe(true);
    expect(needsAcknowledgement({ status: "FAIL", severity: "CRITICAL" })).toBe(false);   // 44: a CRITICAL is never acknowledgeable
  });

  it("89: the release checklist is the database result, never recomputed", () => {
    const e: Eligibility = { eligible: false, failed: ["SECURITY_APPROVED"], refs: {},
      checks: [{ code: "VERSION_EXISTS", ok: true }, { code: "SECURITY_APPROVED", ok: false }, { code: "FUTURE_CHECK", ok: false }] };
    expect(checklistRows(e)).toEqual([{ code: "VERSION_EXISTS", ok: true, label: "report version exists" },
      { code: "SECURITY_APPROVED", ok: false, label: "security review APPROVED" }, { code: "FUTURE_CHECK", ok: false, label: "FUTURE_CHECK" }]);
    expect(checklistRows(null)).toEqual([]);
    expect(workflowLabel("SECURITY_REVIEW_PENDING")).toBe("security review pending");
    expect(workflowLabel(undefined)).toBe("draft version");
  });

  it("88: every action form is bound to an exact version / hash and needs a rationale", () => {
    expect(ContentDecisionSchema.safeParse({ ...base, qa_result_id: ID, decision: "APPROVE", rationale: "checked the findings" }).success).toBe(true);
    expect(ContentDecisionSchema.safeParse({ ...base, version_hash: "abc", qa_result_id: ID, decision: "APPROVE", rationale: "checked the findings" }).success).toBe(false);
    expect(ContentDecisionSchema.safeParse({ ...base, qa_result_id: ID, decision: "APPROVE_FOR_RELEASE", rationale: "checked the findings" }).success).toBe(false);
    expect(AcknowledgeSchema.safeParse({ ...base, qa_result_id: ID, finding_id: R, rationale: "short" }).success).toBe(false);
    expect(SecurityDecisionSchema.safeParse({ ...base, security_review_id: ID, status: "PENDING", rationale: "handling reviewed" }).success).toBe(false);
    expect(ReleaseDecisionSchema.safeParse({ ...base, decision: "APPROVE_FOR_RELEASE", rationale: "release it now please" }).success).toBe(false);
    expect(ReleaseSchema.safeParse({ ...base, pdf_artifact_id: ID, rationale: "all conditions verified" }).success).toBe(false);   // explicit confirmation
    expect(ReleaseSchema.safeParse({ ...base, pdf_artifact_id: ID, rationale: "all conditions verified", confirm: "RELEASE" }).success).toBe(true);
  });

  it("decodes PostgREST bytea exactly", () => {
    expect([...byteaToBytes("\\x255044462d")]).toEqual([0x25, 0x50, 0x44, 0x46, 0x2d]);
    expect(() => byteaToBytes("%PDF")).toThrow();
  });

  it("88 / 91: authority stays server-side and untrusted text is never injected as HTML", () => {
    const dir = join(__dirname, "..", "app", "reports");
    const panels = readFileSync(join(dir, "[id]", "release-panels.tsx"), "utf8");
    const actions = readFileSync(join(dir, "release-actions.ts"), "utf8");
    expect(panels).not.toMatch(/dangerouslySetInnerHTML/);
    expect(actions.startsWith('"use server"')).toBe(true);
    for (const fn of ["request_report_qa", "acknowledge_qa_warning", "decide_report_content", "decide_security_review", "request_release_pdf",
                      "decide_release", "release_report"]) expect(actions).toContain(`"${fn}"`);
    expect(actions).not.toMatch(/\.from\("(report_releases|release_decisions|release_manifests|content_approvals|security_reviews)"\)\.(insert|update|upsert|delete)/);
    expect(panels).not.toMatch(/\.(insert|update|upsert|delete)\(/);
    expect(panels).not.toMatch(/gold|answer.?key|gs-0/i);                                       // 92
  });
});
