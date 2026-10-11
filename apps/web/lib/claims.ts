import { z } from "zod";

/**
 * Form parsing for the human claim-review workflow (Phase 2). Mirrors the
 * closed vocabularies of the database for early, readable errors only;
 * PostgreSQL (HUMAN_ONLY functions, CHECK constraints, enums) stays
 * authoritative and re-validates everything.
 */
export const REVIEW_DECISIONS = ["APPROVE", "MODIFY_AND_APPROVE", "REJECT", "ESCALATE", "REQUEST_REPROCESSING"] as const;
export const CLAIM_STATUSES = [
  "UNVERIFIED", "PARTIALLY_CORROBORATED", "CORROBORATED", "CONFIRMED_PRIMARY", "CONTESTED", "DISPROVEN", "SUPERSEDED",
] as const;
export const CLAIM_TYPES = [
  "OBSERVATION", "ANNOUNCEMENT", "PROCUREMENT", "DEPLOYMENT", "OPERATION", "LOSS", "CAPABILITY", "TEST", "DELIVERY",
  "PRODUCTION", "TRAINING", "POLICY", "DOCTRINE", "ORGANISATION", "TECHNOLOGY", "ASSESSMENT_BY_SOURCE", "OTHER",
] as const;
export const HIGH_IMPACT_REASONS = [
  "SUPPORTS_APPROVED_ASSESSMENT", "SUPPORTS_REPORT_CANDIDATE", "SUPPORTS_KEY_JUDGMENT_CANDIDATE",
  "SUPPORTS_SIGNIFICANT_DEVELOPMENT", "MAY_CHANGE_ANALYTIC_CONFIDENCE", "MAY_CHANGE_TREND", "MAY_CHANGE_INDICATOR",
  "SUPPORTS_HIGH_PRIORITY_EVENT", "SUPPORTS_CRITICAL_PRIORITY_EVENT", "KEY_NUMERICAL_ASSERTION",
  "KEY_CAPABILITY_ASSERTION", "KEY_CAUSAL_ASSERTION",
] as const;

const uuid = z.string().regex(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/, "invalid id");
const reason = z.string().trim().min(5, "a reason of at least 5 characters is required");
const optionalText = z.string().trim().max(4000).optional().transform((v) => (v ? v : undefined));

export const ReviewFormSchema = z
  .object({
    claim_id: uuid,
    claim_hash: z.string().regex(/^[0-9a-f]{64}$/, "invalid claim hash"),
    expected_previous_review_id: z.union([uuid, z.literal("")]).transform((v) => (v === "" ? null : v)),
    decision: z.enum(REVIEW_DECISIONS),
    reason,
    claim_text_normalised: optionalText,
    claim_type: z.union([z.enum(CLAIM_TYPES), z.literal("")]).optional().transform((v) => (v ? v : undefined)),
    attribution: optionalText,
  })
  .transform((f) => {
    const modifications: Record<string, string> = {};
    if (f.claim_text_normalised) modifications.claim_text_normalised = f.claim_text_normalised;
    if (f.claim_type) modifications.claim_type = f.claim_type;
    if (f.attribution) modifications.attribution = f.attribution;
    return { ...f, modifications };
  })
  .refine((f) => (f.decision === "MODIFY_AND_APPROVE") === (Object.keys(f.modifications).length > 0), {
    message: "modifications are required for, and only allowed with, MODIFY_AND_APPROVE",
  });

export type ReviewForm = z.infer<typeof ReviewFormSchema>;

/** Arguments for lfhe.review_claim (HUMAN_ONLY, permission CLAIM_REVIEW). */
export function reviewRpcArgs(f: ReviewForm) {
  return {
    p_claim_id: f.claim_id,
    p_claim_hash: f.claim_hash,
    p_expected_previous_review_id: f.expected_previous_review_id,
    p_decision: f.decision,
    p_reason: f.reason,
    p_modifications: Object.keys(f.modifications).length ? f.modifications : null,
  };
}

export const StatusFormSchema = z.object({
  claim_id: uuid,
  expected_current_status: z.enum(CLAIM_STATUSES),
  new_status: z.enum(CLAIM_STATUSES),
  reason,
}).refine((f) => f.expected_current_status !== f.new_status, { message: "the new status equals the current status" });

export const HighImpactFormSchema = z.object({
  claim_id: uuid,
  high_impact: z.enum(["true", "false"]).transform((v) => v === "true"),
  reasons: z.array(z.enum(HIGH_IMPACT_REASONS)).default([]),
  reason,
});

export const RevalidationFormSchema = z.object({
  revalidation_id: uuid,
  approve: z.enum(["true", "false"]).transform((v) => v === "true"),
  reason,
});

export const LinkFormSchema = z.object({
  mention_id: uuid,
  resolution: z.enum(["RESOLVED", "UNRESOLVED"]),
  entity_id: z.union([uuid, z.literal("")]).transform((v) => (v === "" ? null : v)),
  reason,
}).refine((f) => (f.resolution === "RESOLVED") === (f.entity_id !== null), {
  message: "RESOLVED needs an entity; UNRESOLVED must not name one",
});

export function formObject(form: FormData): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of form.entries()) {
    if (typeof v !== "string") continue;
    if (k === "reasons") (out.reasons = [...((out.reasons as string[]) ?? []), v]);
    else out[k] = v;
  }
  return out;
}

/** Split the original text around the exact evidence span (code-point offsets). */
export function spanContext(text: string, start: number, end: number, radius = 160) {
  const cps = Array.from(text);   // code points, matching the database offset unit
  return {
    before: cps.slice(Math.max(0, start - radius), start).join(""),
    span: cps.slice(start, end).join(""),
    after: cps.slice(end, end + radius).join(""),
  };
}
