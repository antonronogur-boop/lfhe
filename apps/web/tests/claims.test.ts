import { describe, expect, it } from "vitest";

import {
  CLAIM_STATUSES, CLAIM_TYPES, LinkFormSchema, REVIEW_DECISIONS, ReviewFormSchema, StatusFormSchema, formObject,
  reviewRpcArgs, spanContext,
} from "@/lib/claims";

const ID = "11111111-1111-4111-8111-111111111111";
const HASH = "a".repeat(64);

function fd(entries: Record<string, string | string[]>): FormData {
  const f = new FormData();
  for (const [k, v] of Object.entries(entries)) for (const x of [v].flat()) f.append(k, x);
  return f;
}

describe("claim review forms (mirror of the closed database vocabularies)", () => {
  it("uses the canonical enums", () => {
    expect(REVIEW_DECISIONS).toEqual(["APPROVE", "MODIFY_AND_APPROVE", "REJECT", "ESCALATE", "REQUEST_REPROCESSING"]);
    expect(CLAIM_STATUSES).toHaveLength(7);
    expect(CLAIM_TYPES).toHaveLength(17);
  });

  it("binds the decision to the claim hash and the expected previous review", () => {
    const parsed = ReviewFormSchema.parse(formObject(fd({
      claim_id: ID, claim_hash: HASH, expected_previous_review_id: "", decision: "APPROVE", reason: "checked span",
    })));
    expect(reviewRpcArgs(parsed)).toEqual({
      p_claim_id: ID, p_claim_hash: HASH, p_expected_previous_review_id: null, p_decision: "APPROVE",
      p_reason: "checked span", p_modifications: null,
    });
  });

  it("requires modifications exactly for MODIFY_AND_APPROVE", () => {
    const base = { claim_id: ID, claim_hash: HASH, expected_previous_review_id: ID, reason: "restore hedge" };
    expect(() => ReviewFormSchema.parse({ ...base, decision: "MODIFY_AND_APPROVE" })).toThrow();
    expect(() => ReviewFormSchema.parse({ ...base, decision: "APPROVE", claim_text_normalised: "x" })).toThrow();
    const ok = ReviewFormSchema.parse({ ...base, decision: "MODIFY_AND_APPROVE", claim_text_normalised: "It may enter service" });
    expect(reviewRpcArgs(ok).p_modifications).toEqual({ claim_text_normalised: "It may enter service" });
  });

  it("rejects unknown decisions, statuses and short reasons", () => {
    const base = { claim_id: ID, claim_hash: HASH, expected_previous_review_id: "", reason: "long enough" };
    expect(() => ReviewFormSchema.parse({ ...base, decision: "AUTO_APPROVE" })).toThrow();
    expect(() => ReviewFormSchema.parse({ ...base, decision: "APPROVE", reason: "ok" })).toThrow();
    expect(() => StatusFormSchema.parse({ claim_id: ID, expected_current_status: "UNVERIFIED",
      new_status: "TRUE", reason: "because" })).toThrow();
    expect(() => StatusFormSchema.parse({ claim_id: ID, expected_current_status: "UNVERIFIED",
      new_status: "UNVERIFIED", reason: "no change" })).toThrow();
  });

  it("entity links name an entity only when resolved", () => {
    expect(() => LinkFormSchema.parse({ mention_id: ID, resolution: "RESOLVED", entity_id: "", reason: "ctx says so" })).toThrow();
    expect(LinkFormSchema.parse({ mention_id: ID, resolution: "RESOLVED", entity_id: ID, reason: "ctx says so" }).entity_id).toBe(ID);
  });
});

describe("span display uses Unicode code points like the database", () => {
  it("highlights the exact span after astral characters", () => {
    const text = "🛩️ бригада отримала 12 дронів.";
    const cps = Array.from(text);
    const start = cps.indexOf("б");
    const end = start + Array.from("бригада").length;
    expect(spanContext(text, start, end).span).toBe("бригада");
  });
});
