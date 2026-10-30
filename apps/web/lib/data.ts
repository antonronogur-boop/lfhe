import { createClient } from "@/lib/supabase/server";

/* Read models shared by the workspace pages. Everything is read under RLS with the user's own session. */
type Client = Awaited<ReturnType<typeof createClient>>;

export interface ClaimRow {
  id: string; claim_hash: string; claim_local_id: string; language_original: string; claim_text_original: string;
  claim_text_normalised: string; claim_type: string; source_statement_status: string; attribution: string | null;
  event_date: string | null; evidence_type: string; evidence_directness: string; span_start: number; span_end: number;
  span_exact_text: string; text_representation_id: string; article_snapshot_id: string; created_by_model_run_id: string;
  review_flags: string[]; human_review_required: boolean; created_at: string;
}

export interface ClaimStateRow {
  claim_id: string; claim_status: string; status_basis: string; high_impact: boolean; high_impact_reasons: string[];
  revalidation_pending: boolean; latest_review_id: string | null; latest_review_decision: string | null; review_state: string;
  effective_claim_text_normalised: string; effective_claim_type: string; effective_attribution: string | null;
}

export interface SnapshotInfo {
  id: string; article_id: string; title_original: string | null; final_url: string; language: string | null;
  publication_datetime: string | null; public_availability_datetime: string | null; public_availability_basis: string;
  system_retrieval_datetime: string; source_id: string; source_name: string; retention_mode_applied: string;
}

/** Snapshot → article → source for provenance display. */
export async function snapshotInfo(supabase: Client, snapshotIds: string[]): Promise<Map<string, SnapshotInfo>> {
  const out = new Map<string, SnapshotInfo>();
  if (snapshotIds.length === 0) return out;
  const { data: snaps } = await supabase.from("article_snapshots")
    .select("id,article_id,title_original,final_url,language,publication_datetime,public_availability_datetime,public_availability_basis,system_retrieval_datetime,retention_mode_applied")
    .in("id", [...new Set(snapshotIds)]);
  const s = (snaps ?? []) as Omit<SnapshotInfo, "source_id" | "source_name">[];
  const { data: arts } = await supabase.from("articles").select("id,source_id").in("id", [...new Set(s.map((x) => x.article_id))]);
  const artSrc = new Map(((arts ?? []) as { id: string; source_id: string }[]).map((a) => [a.id, a.source_id]));
  const { data: srcs } = await supabase.from("sources").select("id,name").in("id", [...new Set([...artSrc.values()])]);
  const srcName = new Map(((srcs ?? []) as { id: string; name: string }[]).map((x) => [x.id, x.name]));
  for (const x of s) {
    const sid = artSrc.get(x.article_id) ?? "";
    out.set(x.id, { ...x, source_id: sid, source_name: srcName.get(sid) ?? "(source not visible)" });
  }
  return out;
}

/** Events (head versions) a claim belongs to, with its role. */
export async function eventsForClaims(supabase: Client, claimIds: string[]) {
  const out = new Map<string, { event_id: string; title: string; role: string; version_no: number; state: string | null }[]>();
  if (claimIds.length === 0) return out;
  const { data: ec } = await supabase.from("event_claims").select("claim_id,role,event_version_id").in("claim_id", claimIds);
  const rows = (ec ?? []) as { claim_id: string; role: string; event_version_id: string }[];
  if (rows.length === 0) return out;
  const { data: vs } = await supabase.from("event_versions").select("id,event_id,version_no,title")
    .in("id", [...new Set(rows.map((r) => r.event_version_id))]);
  const ver = new Map(((vs ?? []) as { id: string; event_id: string; version_no: number; title: string }[]).map((v) => [v.id, v]));
  const { data: heads } = await supabase.from("event_heads").select("event_id,head_version_id,state")
    .in("event_id", [...new Set([...ver.values()].map((v) => v.event_id))]);
  const head = new Map(((heads ?? []) as { event_id: string; head_version_id: string; state: string }[]).map((h) => [h.event_id, h]));
  for (const r of rows) {
    const v = ver.get(r.event_version_id);
    if (!v || head.get(v.event_id)?.head_version_id !== v.id) continue;            // only the current head version
    const list = out.get(r.claim_id) ?? [];
    list.push({ event_id: v.event_id, title: v.title, role: r.role, version_no: v.version_no, state: head.get(v.event_id)?.state ?? null });
    out.set(r.claim_id, list);
  }
  return out;
}

export function fmtCutoff(at: string | null | undefined): string {
  if (!at) return "—";
  return new Date(at).toISOString().replace("T", " ").slice(0, 16) + " UTC";
}
