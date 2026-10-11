import { z } from "zod";

/**
 * Public web-app configuration. The web app runs with the Supabase *anon* key
 * plus the signed-in user's session; every privileged action is authorised
 * inside PostgreSQL (HUMAN_ONLY functions). The service_role key must never be
 * available to this app — its presence is treated as a fatal misconfiguration.
 */
const PublicEnv = z.object({
  NEXT_PUBLIC_SUPABASE_URL: z.string().url(),
  NEXT_PUBLIC_SUPABASE_ANON_KEY: z.string().min(20),
});

export type PublicEnvT = z.infer<typeof PublicEnv>;

const FORBIDDEN = ["SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY", "LFHE_DATABASE_URL"];

export function loadPublicEnv(env: Record<string, string | undefined> = process.env): PublicEnvT {
  const leaked = FORBIDDEN.filter((k) => env[k]);
  if (leaked.length > 0) {
    throw new Error(`refusing to start: privileged secret(s) present in web environment: ${leaked.join(", ")}`);
  }
  const parsed = PublicEnv.safeParse(env);
  if (!parsed.success) {
    throw new Error(`invalid web configuration: ${parsed.error.issues.map((i) => i.path.join(".")).join(", ")}`);
  }
  return parsed.data;
}
