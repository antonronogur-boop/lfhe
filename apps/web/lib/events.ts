import { z } from "zod";

import { CLAIM_TYPES } from "@/lib/claims";

/**
 * Phase 3 / 4 event workflow form parsing (CR7-03 UI). Mirrors the closed vocabularies for early, readable errors
 * only; the HUMAN_ONLY database functions (create_event, update_event, review_event_version, set_event_state,
 * reject_event, decide_relevance, promote_event_version) stay authoritative and re-validate everything.
 */
export const EVENT_STATES = ["CANDIDATE", "ACTIVE", "DEVELOPING", "CONFIRMED", "CONTESTED", "CLOSED", "REJECTED"] as const;
export const SETTABLE_STATES = ["CANDIDATE", "ACTIVE", "DEVELOPING", "CONFIRMED", "CONTESTED", "CLOSED"] as const;
export const EVENT_ROLES = ["SUPPORTS", "CONTRADICTS", "UPDATES", "CONTEXTUALISES"] as const;
export const DATE_CONFIDENCE = ["HIGH", "MODERATE", "LOW", "UNKNOWN"] as const;
export const EVENT_REVIEW_DECISIONS = ["APPROVE", "REJECT", "ESCALATE", "REQUEST_REPROCESSING"] as const;

const uuid = z.string().uuid();
const reason = z.string().trim().min(5, "a reason of at least 5 characters is required");
const date = z.string().trim().regex(/^\d{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?)?$/, "date as YYYY, YYYY-MM or YYYY-MM-DD")
  .optional().or(z.literal("").transform(() => undefined));

export const EventFormSchema = z.object({
  event_id: uuid.optional(),
  expected_head: uuid.optional(),
  title: z.string().trim().min(3).max(300),
  description: z.string().trim().min(1).max(4000),
  event_type: z.enum(CLAIM_TYPES),
  event_date_start: date,
  event_date_end: date,
  event_date_confidence: z.enum(DATE_CONFIDENCE).default("UNKNOWN"),
  locations: z.string().optional().transform((v) => (v ?? "").split(",").map((x) => x.trim()).filter(Boolean)),
  claims: z.array(z.object({ claim_id: uuid, role: z.enum(EVENT_ROLES) })).min(1, "select at least one claim"),
  reason,
}).refine((f) => f.event_date_start || !f.event_date_end, { message: "an end date needs a start date" })
  .refine((f) => f.event_date_start || f.event_date_confidence === "UNKNOWN", { message: "date confidence needs a start date" });
export type EventForm = z.infer<typeof EventFormSchema>;

/** Collect claim_ids[] + role_<claim id> into the claims array. */
export function eventFormObject(form: FormData): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  const ids: string[] = [];
  for (const [k, v] of form.entries()) {
    if (typeof v !== "string") continue;
    if (k === "claim_ids") ids.push(v);
    else if (!k.startsWith("role_")) out[k] = v;
  }
  out.claims = ids.map((id) => ({ claim_id: id, role: String(form.get(`role_${id}`) ?? "SUPPORTS") }));
  return out;
}

export function eventPayload(f: EventForm) {
  return {
    title: f.title, description: f.description, event_type: f.event_type, event_date_start: f.event_date_start ?? null,
    event_date_end: f.event_date_end ?? null, event_date_confidence: f.event_date_confidence, locations: f.locations, claims: f.claims,
  };
}

export const EventReviewSchema = z.object({
  event_id: uuid, version_id: uuid, version_hash: z.string().regex(/^[0-9a-f]{64}$/), decision: z.enum(EVENT_REVIEW_DECISIONS), reason,
});

export const EventStateSchema = z.object({
  event_id: uuid, expected_state: z.enum(EVENT_STATES), new_state: z.enum([...SETTABLE_STATES, "REJECTED"] as const), reason,
}).refine((f) => f.expected_state !== f.new_state, { message: "the new state equals the current state" });

export const RelevanceDecisionSchema = z.object({
  event_id: uuid, result_id: uuid, action: z.enum(["VALIDATE", "OVERRIDE"]), reason,
  priority_score: z.string().optional().transform((v) => (v === undefined || v === "" ? undefined : Number(v)))
    .refine((v) => v === undefined || (v >= 0 && v <= 5), "priority score 0–5"),
  automatic_assessment_recommended: z.enum(["", "true", "false"]).optional().transform((v) => (v ? v === "true" : undefined)),
}).refine((f) => f.action === "VALIDATE" || f.priority_score !== undefined || f.automatic_assessment_recommended !== undefined,
  { message: "an override changes the priority score or the assessment recommendation" });

export function relevanceOverride(f: z.infer<typeof RelevanceDecisionSchema>) {
  if (f.action === "VALIDATE") return null;
  const o: Record<string, unknown> = {};
  if (f.priority_score !== undefined) o.priority_score = f.priority_score;
  if (f.automatic_assessment_recommended !== undefined) o.automatic_assessment_recommended = f.automatic_assessment_recommended;
  return o;
}

export const PromoteSchema = z.object({
  event_id: uuid, version_id: uuid, version_hash: z.string().regex(/^[0-9a-f]{64}$/), action: z.enum(["PROMOTE", "REQUEST_ASSESSMENT"]), reason,
});
