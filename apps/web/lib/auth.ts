import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";

export type Permission =
  | "SOURCE_READ"
  | "ARTICLE_READ"
  | "SYSTEM_READ"
  | "EVENT_ACTION"
  | "ASSESSMENT_REVIEW"
  | "FINAL_CONFIDENCE_SET"
  | "PROMPT_ACTIVATE"
  | "SOURCE_CREATE"
  | "SOURCE_UPDATE"
  | "SOURCE_APPROVE_COLLECTION_METHOD"
  | "SOURCE_ACTIVATE"
  | "USER_ROLE_MANAGE"
  | "AUDIT_READ"
  | "CLAIM_READ"
  | "CLAIM_REVIEW"
  | "ENTITY_MANAGE"
  | "REPORT_EDIT"
  | "QA_WARNING_ACKNOWLEDGE"
  | "REPORT_CONTENT_APPROVE"
  | "SECURITY_REVIEW"
  | "RELEASE_DECIDE"
  | "PILOT_READ"
  | "PILOT_PARTICIPATE"
  | "PILOT_MANAGE"
  | "PILOT_EVALUATE";

export interface Session {
  userId: string;
  email: string | null;
  permissions: ReadonlySet<string>;
  roles: readonly string[];
}

/**
 * Server-side session guard. UI permission checks only decide what to show;
 * the authoritative check is repeated inside PostgreSQL for every write.
 */
export async function requireSession(): Promise<Session> {
  const session = await getSession();
  if (!session) redirect("/login");
  return session;
}

/** The signed-in session, or null (no redirect) — used by the application shell. */
export async function getSession(): Promise<Session | null> {
  const supabase = await createClient();
  const { data, error } = await supabase.auth.getUser();
  if (error || !data.user) return null;
  const [{ data: perms, error: permError }, { data: roleRows }] = await Promise.all([
    supabase.rpc("my_permissions"),
    supabase.from("user_roles").select("role_code").eq("user_id", data.user.id),
  ]);
  if (permError) throw new Error(`could not load permissions: ${permError.message}`);
  return {
    userId: data.user.id,
    email: data.user.email ?? null,
    permissions: new Set((perms as string[] | null) ?? []),
    roles: ((roleRows ?? []) as { role_code: string }[]).map((r) => r.role_code).sort(),
  };
}

export function can(session: Session, permission: Permission): boolean {
  return session.permissions.has(permission);
}

export async function requirePermission(permission: Permission): Promise<Session> {
  const session = await requireSession();
  if (!can(session, permission)) {
    throw new Error(`permission ${permission} required`);
  }
  return session;
}
