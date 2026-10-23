import { z } from "zod";

/**
 * Phase 6 QA / approval / security / release workspace — pure helpers.
 * Nothing here decides anything: QA status, warning requirements, eligibility and RELEASED are
 * computed by PostgreSQL (lfhe.record_qa_result, lfhe.release_eligibility, lfhe.release_report) and
 * every authoritative action is a server action calling a HUMAN_ONLY function that re-validates
 * identity, role and the exact (report_version_id, report_version_hash) binding.
 */
export const QA_STATUSES = ["PASS", "PASS_WITH_WARNINGS", "FAIL"] as const;
export const CONTENT_DECISIONS = ["APPROVE", "RETURN_FOR_REVISION", "REJECT"] as const;
export const SECURITY_DECISIONS = ["APPROVED", "RETURN_FOR_REVISION", "REJECTED"] as const;
export const RELEASE_RETURN_DECISIONS = ["RETURN_FOR_REVISION", "REJECT_RELEASE"] as const;
export const SEVERITY_ORDER = ["CRITICAL", "MAJOR", "WARNING", "INFO"] as const;

export interface Finding {
  id: string;
  qa_run_id: string;
  finding_no: number;
  check_id: string;
  layer: "D" | "S";
  status: "PASS" | "WARNING" | "FAIL";
  severity: (typeof SEVERITY_ORDER)[number];
  finding_code: string;
  affected_object_id: string | null;
  affected_statement_id: string | null;
  details: string;
  evidence_refs: { object_type: string; object_id: string }[];
  recommended_action: string;
}

export interface EligibilityCheck { code: string; ok: boolean; [k: string]: unknown }
export interface Eligibility { eligible: boolean; failed: string[]; checks: EligibilityCheck[]; refs: Record<string, unknown> }

/** A finding blocks release when it FAILs (every CRITICAL is a FAIL) — the same rule the database applies. */
export function blocksRelease(f: Pick<Finding, "status" | "severity">): boolean {
  return f.status === "FAIL" || f.severity === "CRITICAL";
}

export function needsAcknowledgement(f: Pick<Finding, "status" | "severity">): boolean {
  return f.status === "WARNING" && f.severity !== "CRITICAL";
}

/** Group non-PASS findings by severity (CRITICAL first), then check id; PASS rows are counted per check. */
export function groupFindings(findings: Finding[]) {
  const issues = findings.filter((f) => f.status !== "PASS");
  const groups = SEVERITY_ORDER.map((sev) => ({
    severity: sev,
    findings: issues.filter((f) => f.severity === sev).sort((a, b) => a.check_id.localeCompare(b.check_id) || a.finding_no - b.finding_no),
  })).filter((g) => g.findings.length > 0);
  const passedChecks = [...new Set(findings.filter((f) => f.status === "PASS").map((f) => `${f.layer}:${f.check_id}`))].sort();
  return { groups, passedChecks, blocking: issues.filter(blocksRelease).length, warnings: issues.filter(needsAcknowledgement).length };
}

const CHECK_LABELS: Record<string, string> = {
  VERSION_EXISTS: "report version exists", HASH_MATCHES: "supplied hash = stored hash", VERSION_CURRENT: "current (latest) version",
  NOT_ALREADY_RELEASED: "not already released", QA_BOUND_TO_VERSION: "current QA belongs to this version / hash",
  M10D_COMPLETE: "M10-D complete", M10S_COMPLETE: "M10-S complete", QA_ACCEPTABLE: "QA PASS, or PASS_WITH_WARNINGS fully acknowledged",
  NO_CRITICAL_FINDING: "no CRITICAL / failing finding", CONTENT_APPROVED: "content approved for this version and QA result",
  SECURITY_APPROVED: "security review APPROVED", NOT_RETURNED_OR_REJECTED: "release candidate not returned / rejected",
  PDF_EXISTS: "release PDF exists", PDF_BOUND_TO_VERSION: "PDF bound to this version / hash", PDF_HASH_VALID: "PDF SHA-256 matches stored bytes",
  TEMPLATE_RENDERER_RESOLVE: "template / renderer identities resolve", MODEL_PROVENANCE_RESOLVES: "prompt / model-run provenance resolves",
  ANALYTICAL_PROVENANCE_RESOLVES: "analytical provenance resolves", MANIFEST_INPUTS_COMPLETE: "manifest inputs complete",
  CALLER_HUMAN_RELEASE_AUTHORITY: "you are a human with RELEASE_DECIDE",
};

/** Checklist rows exactly as returned by the database (never recomputed in the browser). */
export function checklistRows(e: Eligibility | null) {
  if (!e) return [];
  return e.checks.map((c) => ({ code: c.code, ok: c.ok === true, label: CHECK_LABELS[c.code] ?? c.code }));
}

export function workflowLabel(state: string | null | undefined): string {
  return (state ?? "DRAFT_VERSION").replaceAll("_", " ").toLowerCase();
}

/** PostgREST returns bytea as "\x…" hex. */
export function byteaToBytes(v: string): Uint8Array<ArrayBuffer> {
  if (!/^\\x([0-9a-f]{2})*$/i.test(v)) throw new Error("not a bytea hex string");
  const hex = v.slice(2);
  const out = new Uint8Array(new ArrayBuffer(hex.length / 2));
  for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return out;
}

const uuid = z.string().regex(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/, "invalid id");
const hash = z.string().regex(/^[0-9a-f]{64}$/, "invalid hash");
const rationale = z.string().trim().min(10, "a rationale of at least 10 characters is required");
const Bound = z.object({ report_id: uuid, version_id: uuid, version_hash: hash });

export const RequestQaSchema = Bound.extend({ reason: z.string().trim().min(5, "a reason of at least 5 characters is required") });
export const AcknowledgeSchema = Bound.extend({ qa_result_id: uuid, finding_id: uuid, rationale });
export const ContentDecisionSchema = Bound.extend({ qa_result_id: uuid, decision: z.enum(CONTENT_DECISIONS), rationale });
export const SecurityDecisionSchema = Bound.extend({ security_review_id: uuid, status: z.enum(SECURITY_DECISIONS), rationale });
export const ReleaseDecisionSchema = Bound.extend({ decision: z.enum(RELEASE_RETURN_DECISIONS), rationale });
export const ReleaseSchema = Bound.extend({ pdf_artifact_id: uuid, rationale, confirm: z.literal("RELEASE") });
export const PdfRequestSchema = RequestQaSchema;
