import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

import { loadPublicEnv } from "@/lib/env";

/**
 * Server-side Supabase client bound to the current user's session cookie.
 * Queries run as the PostgreSQL role `authenticated` with the user's JWT, so
 * RLS and the HUMAN_ONLY function checks apply. The `lfhe` schema must be
 * exposed in the Supabase API settings (see docs/runbooks/environments.md).
 */
export async function createClient() {
  const env = loadPublicEnv();
  const cookieStore = await cookies();
  return createServerClient(env.NEXT_PUBLIC_SUPABASE_URL, env.NEXT_PUBLIC_SUPABASE_ANON_KEY, {
    db: { schema: "lfhe" },
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(toSet) {
        try {
          for (const { name, value, options } of toSet) cookieStore.set(name, value, options);
        } catch {
          // Called from a Server Component: cookies are read-only there. Session
          // refresh happens in Server Actions, which may set cookies.
        }
      },
    },
  });
}
