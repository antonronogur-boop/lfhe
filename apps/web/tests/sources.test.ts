import { describe, expect, it } from "vitest";

import { loadPublicEnv } from "@/lib/env";
import { ReasonSchema, SourceCreateSchema, parseSourceForm } from "@/lib/sources";

const validEnv = {
  NEXT_PUBLIC_SUPABASE_URL: "https://example.supabase.co",
  NEXT_PUBLIC_SUPABASE_ANON_KEY: "public-anon-key-placeholder-000",
};

describe("web environment guard", () => {
  it("accepts the public anon configuration", () => {
    expect(loadPublicEnv(validEnv).NEXT_PUBLIC_SUPABASE_URL).toBe(validEnv.NEXT_PUBLIC_SUPABASE_URL);
  });
  it("refuses to start when a service_role key is present", () => {
    expect(() => loadPublicEnv({ ...validEnv, SUPABASE_SERVICE_ROLE_KEY: "x" })).toThrow(/privileged secret/);
  });
  it("refuses to start when the worker database URL is present", () => {
    expect(() => loadPublicEnv({ ...validEnv, LFHE_DATABASE_URL: "postgresql://x" })).toThrow(/privileged secret/);
  });
  it("rejects missing configuration", () => {
    expect(() => loadPublicEnv({})).toThrow(/invalid web configuration/);
  });
});

function form(fields: Record<string, string>): FormData {
  const f = new FormData();
  for (const [k, v] of Object.entries(fields)) f.set(k, v);
  return f;
}

const base = {
  name: "Synthetic ministry feed",
  canonical_domain: "Feeds.Example.org",
  source_type: "OFFICIAL_GOVERNMENT",
  primary_language: "uk",
  collection_method: "RSS_ATOM",
  collection_config: '{"feed_url": "https://feeds.example.org/rss.xml"}',
};

describe("source form parsing (mirrors DB constraints)", () => {
  it("normalises domain and defaults to the most restrictive retention", () => {
    const p = parseSourceForm(form(base));
    expect(p.canonical_domain).toBe("feeds.example.org");
    expect(p.retention_mode).toBe("METADATA_ONLY");
    expect(p.collection_frequency).toBe("1 hour");
  });
  it("rejects credentials in collection config", () => {
    expect(() =>
      parseSourceForm(form({ ...base, collection_config: '{"feed_url":"https://x.org","Authorization":"Bearer x"}' })),
    ).toThrow(/credentials/);
  });
  it("rejects browser automation (no approved adapter in Phase 1)", () => {
    expect(() => parseSourceForm(form({ ...base, collection_method: "BROWSER_AUTOMATION" }))).toThrow();
  });
  it("rejects invalid JSON config", () => {
    expect(() => parseSourceForm(form({ ...base, collection_config: "{not json" }))).toThrow(/valid JSON/);
  });
  it("does not let the form set active or approval", () => {
    const p = SourceCreateSchema.parse({ ...base, collection_config: {}, active: true });
    expect("active" in p).toBe(false);
  });
  it("requires a meaningful reason for governance actions", () => {
    expect(ReasonSchema.safeParse("ok").success).toBe(false);
    expect(ReasonSchema.safeParse("terms reviewed").success).toBe(true);
  });
});

describe("credential-key rule (mirror of lfhe.credential_key_paths)", () => {
  it("rejects credential-like keys at any depth, including inside arrays", async () => {
    const { credentialKeyPaths, isCredentialKey } = await import("../lib/credentials");
    expect(credentialKeyPaths({ token: "x" })).toEqual(["$.token"]);
    expect(credentialKeyPaths({ options: { token: "x" } })).toEqual(["$.options.token"]);
    expect(credentialKeyPaths({ a: [{ b: { apiKey: "x" } }] })).toEqual(["$.a[0].b.apiKey"]);
    expect(credentialKeyPaths({ feed_url: "https://x.org", options: { max_items: 5, max_tokens: 10 } })).toEqual([]);
    expect(["X-Api-Key", "client_secret", "Authorization", "private_key"].every(isCredentialKey)).toBe(true);
    expect(["keyword", "max_tokens", "monkey"].some(isCredentialKey)).toBe(false);
  });
  it("form parsing rejects nested credentials", () => {
    expect(() =>
      parseSourceForm(form({ ...base, collection_config: '{"feed_url":"https://x.org","options":{"cookie":"a"}}' })),
    ).toThrow(/credentials/);
  });
});
