import { z } from "zod";

/**
 * CR7-05 inbox: batch decisions on events and the report autopilot switch. The browser only names exact event
 * versions (id | version | hash) and one audited reason; the existing HUMAN_ONLY functions (review_event_version,
 * set_event_state, reject_event, set_report_autopilot) re-check the permission, hash and expected state per event.
 */
const reason = z.string().trim().min(5, "a reason of at least 5 characters is required");
const uuid = z.string().uuid();
const item = z.string().regex(/^[0-9a-f-]{36}\|[0-9a-f-]{36}\|[0-9a-f]{64}$/, "invalid selection");

export const BatchEventSchema = z.object({
  decision: z.enum(["CONFIRM", "REJECT"]),
  reason,
  items: z.array(item).min(1, "select at least one event").max(50, "at most 50 events at once"),
});

export const AutopilotSchema = z.object({ report_id: uuid.optional(), enabled: z.enum(["on", "off"]), reason });

export interface EventPick { event_id: string; version_id: string; version_hash: string }

export function parsePicks(items: string[]): EventPick[] {
  return items.map((s) => {
    const [event_id, version_id, version_hash] = s.split("|");
    return { event_id, version_id, version_hash };
  });
}

/** One-line result text for the batch action. */
export function batchSummary(done: number, failed: { id: string; message: string }[]): string {
  return failed.length === 0 ? `${done} event(s) done` : `${done} done, ${failed.length} not done: ${failed.map((f) => f.message).join(" · ")}`.slice(0, 380);
}
