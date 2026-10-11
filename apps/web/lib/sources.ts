import { z } from "zod";
import { credentialKeyPaths, credentialUrlPaths } from "./credentials";

/**
 * Client-side mirror of the database constraints on lfhe.sources. It exists
 * for early, readable form errors only; PostgreSQL remains authoritative and
 * re-validates everything (CHECK constraints + lfhe.create_source).
 */
export const COLLECTION_METHODS = ["OFFICIAL_API", "RSS_ATOM", "STRUCTURED_FEED", "HTTP_FETCH"] as const;
export const SOURCE_TYPES = [
  "OFFICIAL_GOVERNMENT", "OFFICIAL_MILITARY", "INTERNATIONAL_ORGANISATION",
  "INDUSTRY", "WIRE_SERVICE", "MEDIA", "THINK_TANK", "OTHER",
] as const;
export const RETENTION_MODES = ["METADATA_ONLY", "PERMITTED_EXCERPT", "FULL"] as const;

const domain = /^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$/;

export const SourceCreateSchema = z.object({
  name: z.string().trim().min(2).max(200),
  canonical_domain: z.string().trim().toLowerCase().regex(domain, "invalid domain"),
  owner_organisation: z.string().trim().max(200).optional(),
  owner_country: z.string().trim().toUpperCase().regex(/^[A-Z]{2}$/, "ISO 3166-1 alpha-2").optional(),
  source_type: z.enum(SOURCE_TYPES),
  official_status: z.enum(["OFFICIAL", "SEMI_OFFICIAL", "NON_OFFICIAL"]).default("NON_OFFICIAL"),
  primary_language: z.string().trim().regex(/^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$/, "BCP-47 tag"),
  collection_method: z.enum(COLLECTION_METHODS),
  collection_config: z
    .record(z.string(), z.unknown())
    .refine((cfg) => credentialKeyPaths(cfg).length === 0,
      "collection config must not contain credentials or headers (at any depth)")
    .refine((cfg) => credentialUrlPaths(cfg).length === 0,
      "collection config URLs must not contain credentials (userinfo or credential parameters)"),
  collection_frequency: z.string().regex(/^\d+ (minutes|hour|hours|day|days)$/).default("1 hour"),
  retention_mode: z.enum(RETENTION_MODES).default("METADATA_ONLY"),
  terms_notes: z.string().trim().max(4000).optional(),
});

export type SourceCreate = z.infer<typeof SourceCreateSchema>;

/** Parse an HTML form submission into the lfhe.create_source(p jsonb) payload. */
export function parseSourceForm(form: FormData): SourceCreate {
  const raw: Record<string, unknown> = {};
  for (const [k, v] of form.entries()) {
    if (typeof v === "string" && v.trim() !== "") raw[k] = v;
  }
  const cfgText = typeof raw.collection_config === "string" ? raw.collection_config : "{}";
  try {
    raw.collection_config = JSON.parse(cfgText);
  } catch {
    throw new Error("collection_config must be valid JSON");
  }
  return SourceCreateSchema.parse(raw);
}

export const ReasonSchema = z.string().trim().min(5, "a reason of at least 5 characters is required");
