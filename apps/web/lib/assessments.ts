import { z } from "zod";

/**
 * Phase 4 human analytical review (CR7-03 UI). Mirrors the closed rules for readable errors only; the HUMAN_ONLY
 * functions review_assessment / modify_and_approve_assessment / dispose_challenge_flag stay authoritative:
 * M08 must have challenged the exact version, APPROVE needs FINAL_CONFIDENCE_SET and a final analytic confidence
 * with a rationale (≥ 20 characters), and the version hash must match.
 */
export const ASSESSMENT_DECISIONS = ["APPROVE", "REJECT", "ESCALATE", "REQUEST_REPROCESSING"] as const;
export const CONFIDENCE = ["HIGH", "MODERATE", "LOW"] as const;
export const FLAG_DISPOSITIONS = ["ACCEPTED", "REJECTED", "ACKNOWLEDGED", "REPROCESSING_REQUESTED", "ESCALATED"] as const;

const uuid = z.string().uuid();
const hash = z.string().regex(/^[0-9a-f]{64}$/);
const reason = z.string().trim().min(5, "a reason of at least 5 characters is required");

export const ReviewAssessmentSchema = z.object({
  version_id: uuid, version_hash: hash, decision: z.enum(ASSESSMENT_DECISIONS), reason,
  final_confidence: z.enum(CONFIDENCE).optional().or(z.literal("").transform(() => undefined)),
  confidence_rationale: z.string().trim().optional(),
}).superRefine((f, ctx) => {
  if (f.decision === "APPROVE") {
    if (!f.final_confidence) ctx.addIssue({ code: "custom", message: "approval sets the final analytic confidence" });
    if ((f.confidence_rationale ?? "").length < 20) ctx.addIssue({ code: "custom", message: "the confidence rationale needs at least 20 characters" });
  } else if (f.final_confidence) {
    ctx.addIssue({ code: "custom", message: "final confidence is set only by an approval" });
  }
});

export const ModifyApproveSchema = z.object({
  version_id: uuid, version_hash: hash, reason, final_confidence: z.enum(CONFIDENCE),
  confidence_rationale: z.string().trim().min(20, "the confidence rationale needs at least 20 characters"),
});

export const DisposeFlagSchema = z.object({ version_id: uuid, flag_id: uuid, disposition: z.enum(FLAG_DISPOSITIONS), reason });

export interface StoredStatement {
  statement_local_id: string; statement_type: string; statement_text: string; provenance_class: string; evidence_required: boolean;
  uses_baseline: boolean; attribution_required: boolean; attribution_text: string | null; supporting_claim_ids: string[];
  contradicting_claim_ids: string[]; supporting_reference_context_ids: string[]; premise_statement_local_ids: string[];
  likelihood: { term: string; rationale: string } | null;
}

/** MODIFY_AND_APPROVE payload: the stored statement structure (types, evidence, premises, likelihood) is kept; only the
 *  texts the reviewer edited change. The database re-validates provenance and writes a NEW immutable version. */
export function modifiedPayload(content: { statements: StoredStatement[]; derived_summary: unknown; indicators_to_watch: unknown },
                                edits: Record<string, string>) {
  return {
    assessment_statements: content.statements.map((s) => ({
      ...s, statement_text: (edits[s.statement_local_id] ?? s.statement_text).trim(),
    })),
    derived_summary: content.derived_summary ?? { text: "", source_statement_ids: [] },
    indicators_to_watch: content.indicators_to_watch ?? [],
  };
}

export function editsFrom(form: FormData): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of form.entries()) if (k.startsWith("text_") && typeof v === "string") out[k.slice(5)] = v;
  return out;
}
