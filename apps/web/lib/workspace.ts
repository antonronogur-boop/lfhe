import type { Session } from "@/lib/auth";
import { can } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";

type Client = Awaited<ReturnType<typeof createClient>>;

/** Exact row count for a filtered read (RLS applies: a role only counts what it may read). */
export async function countOf(query: PromiseLike<{ count: number | null; error: unknown }>): Promise<number> {
  const { count, error } = await query;
  return error ? 0 : count ?? 0;
}

export interface QueueCounts {
  claimsToReview: number; eventsCandidate: number; assessmentsInReview: number; failedJobs: number; activeJobs: number;
  qaToAcknowledge: number; contentToApprove: number; securityPending: number; releaseReady: number; openCycles: number;
  blockingUx: number;
}

/** Live work queues (real database state) for the navigation and the dashboard. */
export async function queueCounts(supabase: Client, session: Session): Promise<QueueCounts> {
  const head = { count: "exact" as const, head: true };
  const reads = can(session, "CLAIM_READ");
  const z = Promise.resolve(0);
  const wf = (state: string) => countOf(supabase.from("report_version_workflow").select("report_version_id", head)
    .eq("workflow_state", state).eq("is_latest", true));
  const [claimsToReview, eventsCandidate, assessmentsInReview, failedJobs, activeJobs, qaToAcknowledge, contentQa, contentWarn,
    securityPending, releaseReady, openCycles, blockingUx] = await Promise.all([
    reads ? countOf(supabase.from("claim_state").select("claim_id", head).eq("review_state", "PENDING")) : z,
    reads ? countOf(supabase.from("event_heads").select("event_id", head).eq("state", "CANDIDATE").eq("is_current", true)) : z,
    reads ? countOf(supabase.from("assessment_version_states").select("assessment_version_id", head).in("state", ["IN_REVIEW", "ESCALATED"])) : z,
    can(session, "SYSTEM_READ") ? countOf(supabase.from("processing_jobs").select("id", head).eq("status", "FAILED")) : z,
    can(session, "SYSTEM_READ") ? countOf(supabase.from("processing_jobs").select("id", head).in("status", ["PENDING", "RUNNING"])) : z,
    reads ? wf("QA_PASSED_WITH_WARNINGS") : z,
    reads ? wf("QA_PASSED") : z,
    reads ? wf("WARNING_ACKNOWLEDGED") : z,
    reads ? wf("SECURITY_REVIEW_PENDING") : z,
    reads ? wf("SECURITY_APPROVED") : z,
    can(session, "PILOT_READ") ? countOf(supabase.from("pilot_cycles").select("id", head).eq("status", "OPEN")) : z,
    can(session, "PILOT_READ") ? openBlockingFindings(supabase).then((f) => f.length) : z,
  ]);
  return { claimsToReview, eventsCandidate, assessmentsInReview, failedJobs, activeJobs, qaToAcknowledge,
    contentToApprove: contentQa + contentWarn, securityPending, releaseReady, openCycles, blockingUx };
}

/** The analysis context (mode + cutoff) used when requesting M04–M07: an open report's cutoff, or LIVE now. */
export interface AnalysisContext { key: string; label: string; report_mode: "LIVE" | "REPLAY"; information_cutoff: string }

export async function analysisContexts(supabase: Client): Promise<AnalysisContext[]> {
  const { data } = await supabase.from("reports").select("id,code,report_mode,information_cutoff,created_at")
    .order("created_at", { ascending: false }).limit(20);
  const reports = (data ?? []) as { id: string; code: string; report_mode: "LIVE" | "REPLAY"; information_cutoff: string }[];
  return [
    ...reports.map((r) => ({ key: r.id, label: `${r.code} · ${r.report_mode} · cutoff ${r.information_cutoff.replace("T", " ").slice(0, 16)}`,
      report_mode: r.report_mode, information_cutoff: r.information_cutoff })),
    { key: "live", label: "LIVE · cutoff = now (no report)", report_mode: "LIVE", information_cutoff: new Date().toISOString() },
  ];
}

/** Resolve a posted context key on the server (never trust a posted cutoff). */
export async function resolveContext(supabase: Client, key: string): Promise<{ report_mode: string; information_cutoff: string }> {
  if (key === "live") return { report_mode: "LIVE", information_cutoff: new Date().toISOString() };
  const { data, error } = await supabase.from("reports").select("report_mode,information_cutoff").eq("id", key).single();
  if (error || !data) throw new Error("unknown analysis context (report)");
  return data as { report_mode: string; information_cutoff: string };
}

/** BLOCKING UX findings whose latest disposition is none / REOPENED / BACKLOG (the closed completeness rule). */
export async function openBlockingFindings(supabase: Client): Promise<{ id: string; title: string; cycle_id: string | null }[]> {
  const { data } = await supabase.from("pilot_ux_findings").select("id,title,cycle_id").eq("severity", "BLOCKING");
  const findings = (data ?? []) as { id: string; title: string; cycle_id: string | null }[];
  if (findings.length === 0) return [];
  const { data: disp } = await supabase.from("pilot_ux_finding_dispositions").select("finding_id,disposition,seq")
    .in("finding_id", findings.map((f) => f.id)).order("seq", { ascending: true });
  const latest = new Map<string, string>();
  for (const d of (disp ?? []) as { finding_id: string; disposition: string }[]) latest.set(d.finding_id, d.disposition);
  return findings.filter((f) => ["OPEN", "REOPENED", "BACKLOG"].includes(latest.get(f.id) ?? "OPEN"));
}
