import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";

export type Permission =
  | "SOURCE_READ"
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
  | "RELEASE_DECIDE";

export interface Session {
  userId: string;
  email: string | null;
  permissions: ReadonlySet<string>;
}

/**
 * Server-side session guard. UI permission checks only decide what to show;
 * the authoritative check is repeated inside PostgreSQL for every write.
 */
export async function requireSession(): Promise<Session> {
  const supabase = await createClient();
  const { data, error } = await supabase.auth.getUser();
  if (error || !data.user) redirect("/login");
  const { data: perms, error: permError } = await supabase.rpc("my_permissions");
  if (permError) throw new Error(`could not load permissions: ${permError.message}`);
  return {
    userId: data.user.id,
    email: data.user.email ?? null,
    permissions: new Set((perms as string[] | null) ?? []),
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
