import { z } from "zod";

/**
 * Phase 5 analyst report workspace — pure helpers (form parsing, content reconstruction from the
 * canonical JSON of a report version, provenance-preserving edit helpers, version comparison).
 * PostgreSQL stays authoritative: every edit is re-validated by the HUMAN_ONLY database functions
 * (provenance, attribution, confidence, likelihood, caveats, coverage) and creates a NEW version.
 */
export const REPORT_SECTIONS = [
  "KEY_JUDGMENT", "SIGNIFICANT_DEVELOPMENT", "INDICATOR_WARNING", "TREND_WATCH", "WHAT_TO_WATCH", "CAVEAT",
] as const;
export type ReportSection = (typeof REPORT_SECTIONS)[number];
export const SELECTABLE_SECTIONS: Record<string, readonly ReportSection[]> = {
  ASSESSMENT_VERSION: ["KEY_JUDGMENT", "SIGNIFICANT_DEVELOPMENT", "INDICATOR_WARNING", "WHAT_TO_WATCH"],
  INDICATOR_VERSION: ["INDICATOR_WARNING", "WHAT_TO_WATCH"],
  TREND_VERSION: ["TREND_WATCH"],
};
export const SECTION_KEYS: Record<ReportSection, string> = {
  KEY_JUDGMENT: "key_judgments", SIGNIFICANT_DEVELOPMENT: "significant_developments", INDICATOR_WARNING: "indicators_warning",
  TREND_WATCH: "trend_watch", WHAT_TO_WATCH: "what_to_watch", CAVEAT: "caveats",
};
export const SECTION_TITLES: Record<ReportSection, string> = {
  KEY_JUDGMENT: "Key Judgments", SIGNIFICANT_DEVELOPMENT: "Significant Developments", INDICATOR_WARNING: "Indicators & Warning",
  TREND_WATCH: "Trend Watch", WHAT_TO_WATCH: "What to Watch", CAVEAT: "Caveats",
};
export const EDITORIAL_TRANSFORMS = ["VERBATIM_APPROVED", "PARAPHRASE", "COMPRESSION", "NON_ANALYTIC_FORMATTING"] as const;
export const SELECTION_DECISIONS = ["INCLUDE", "EXCLUDE", "RETURN_FOR_ANALYTICAL_REVISION"] as const;

export interface CanonicalStatement {
  statement_no: number;
  report_statement_local_id: string;
  statement_role: ReportSection;
  text: string;
  sources: string[];
  final_analytic_confidence: string | null;
  likelihood_term: string | null;
  editorial_transform: string;
  contested: boolean;
}
export interface CanonicalItem {
  item_no: number;
  item_local_id: string;
  source_candidate_id: string;
  final_analytic_confidence: string | null;
  pins: Record<string, { id: string; hash: string } | null>;
  statements: CanonicalStatement[];
}
export interface CanonicalReport {
  version_no: number;
  sections: { section: ReportSection; items: CanonicalItem[] }[];
  human_removals: string[];
  length_status: string;
  coverage: { section: ReportSection; count: number; target_min: number | null; target_max: number | null; below_target: boolean; above_target: boolean }[];
}

export interface ContentStatement {
  report_statement_local_id: string;
  text: string;
  statement_role: string;
  source_assessment_statement_ids: string[];
  final_analytic_confidence: string | null;
  likelihood_term: string | null;
  editorial_transform: string;
}
export type Content = Record<string, { item_local_id: string; source_candidate_id: string; statements: ContentStatement[] }[]>;

/** The section-keyed edit shape (same as M09 output) reconstructed from canonical JSON. */
export function contentFromCanonical(c: CanonicalReport): Content {
  const out: Content = {};
  for (const s of c.sections) {
    out[SECTION_KEYS[s.section]] = s.items.map((it) => ({
      item_local_id: it.item_local_id,
      source_candidate_id: it.source_candidate_id,
      statements: it.statements.map((st) => ({
        report_statement_local_id: st.report_statement_local_id, text: st.text, statement_role: st.statement_role,
        source_assessment_statement_ids: [...st.sources], final_analytic_confidence: st.final_analytic_confidence,
        likelihood_term: st.likelihood_term, editorial_transform: st.editorial_transform,
      })),
    }));
  }
  return out;
}

function locate(content: Content, statementLocalId: string) {
  for (const [key, items] of Object.entries(content)) {
    for (const it of items) {
      const idx = it.statements.findIndex((s) => s.report_statement_local_id === statementLocalId);
      if (idx >= 0) return { key, item: it, idx };
    }
  }
  throw new Error(`unknown report statement ${statementLocalId}`);
}

/** Reword one statement; sources, role, confidence and likelihood are carried unchanged. */
export function applyStatementEdit(content: Content, statementLocalId: string, text: string, transform: string): Content {
  const next = structuredClone(content);
  const { item, idx } = locate(next, statementLocalId);
  item.statements[idx] = { ...item.statements[idx], text: text.trim(), editorial_transform: transform };
  return next;
}

/** Move a statement within its item (reorder only). */
export function applyStatementMove(content: Content, statementLocalId: string, delta: -1 | 1): Content {
  const next = structuredClone(content);
  const { item, idx } = locate(next, statementLocalId);
  const to = idx + delta;
  if (to < 0 || to >= item.statements.length) return next;
  [item.statements[idx], item.statements[to]] = [item.statements[to], item.statements[idx]];
  return next;
}

/** HUMAN substantive removal: drop the statement (and an emptied item); sources no longer mapped
 * anywhere are reported as explicitly removed (recorded in the new version's human_removals). */
export function applyStatementRemoval(content: Content, statementLocalId: string): { content: Content; removed: string[] } {
  const next = structuredClone(content);
  const { key, item, idx } = locate(next, statementLocalId);
  const [gone] = item.statements.splice(idx, 1);
  if (item.statements.length === 0) next[key] = next[key].filter((i) => i !== item);
  const stillMapped = new Set(Object.values(next).flat().flatMap((i) => i.statements.flatMap((s) => s.source_assessment_statement_ids)));
  return { content: next, removed: gone.source_assessment_statement_ids.filter((s) => !stillMapped.has(s)) };
}

export interface StatementDiff {
  key: string;
  section: string;
  kind: "added" | "removed" | "changed" | "unchanged";
  before?: string;
  after?: string;
  sourcesChanged: boolean;
}

/** Statement-level comparison of two versions, keyed by section / item / report statement id. */
export function diffVersions(a: CanonicalReport, b: CanonicalReport): StatementDiff[] {
  const flat = (c: CanonicalReport) => {
    const m = new Map<string, { section: string; st: CanonicalStatement }>();
    for (const s of c.sections) for (const it of s.items) for (const st of it.statements)
      m.set(`${s.section}/${it.item_local_id}/${st.report_statement_local_id}`, { section: s.section, st });
    return m;
  };
  const A = flat(a);
  const B = flat(b);
  const keys = [...new Set([...A.keys(), ...B.keys()])].sort();
  return keys.map((key) => {
    const x = A.get(key);
    const y = B.get(key);
    const section = (x ?? y)!.section;
    if (!x) return { key, section, kind: "added", after: y!.st.text, sourcesChanged: true };
    if (!y) return { key, section, kind: "removed", before: x.st.text, sourcesChanged: true };
    const sourcesChanged = [...x.st.sources].sort().join() !== [...y.st.sources].sort().join();
    const changed = x.st.text !== y.st.text || sourcesChanged || x.st.statement_role !== y.st.statement_role;
    return { key, section, kind: changed ? "changed" : "unchanged", before: x.st.text, after: y.st.text, sourcesChanged };
  });
}

/** Visual class / label for confidence: LOW must never look like HIGH; absent ≠ "none". */
export function confidenceLabel(conf: string | null | undefined): { cls: string; label: string } {
  if (!conf) return { cls: "conf-none", label: "no analytic confidence attached" };
  return { cls: `conf-${conf.toLowerCase()}`, label: `${conf.toLowerCase()} confidence (analyst-approved)` };
}

const uuid = z.string().regex(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/, "invalid id");
const hash = z.string().regex(/^[0-9a-f]{64}$/, "invalid hash");
const reason = z.string().trim().min(5, "a reason of at least 5 characters is required");

export const CreateReportSchema = z.object({
  code: z.string().regex(/^RPT-[A-Z0-9][A-Z0-9_-]{1,60}$/, "code must look like RPT-…"),
  title: z.string().trim().min(3).max(300),
  cycle_label: z.string().trim().min(1).max(60),
  report_mode: z.enum(["LIVE", "REPLAY"]),
  information_cutoff: z.string().refine((v) => !Number.isNaN(Date.parse(v)), "invalid cutoff"),
  reason,
});

export const DecideCandidateSchema = z
  .object({
    report_id: uuid,
    candidate_id: uuid,
    object_hash: hash,
    expected_previous_decision_id: z.union([uuid, z.literal("")]).transform((v) => (v === "" ? null : v)),
    decision: z.enum(SELECTION_DECISIONS),
    section: z.union([z.enum(REPORT_SECTIONS), z.literal("")]).transform((v) => (v === "" ? null : v)),
    priority: z.union([z.coerce.number().int().min(1).max(999), z.literal("")]).transform((v) => (v === "" ? null : v)),
    reason,
  })
  .superRefine((f, ctx) => {
    if (f.decision === "INCLUDE" && (!f.section || f.priority === null))
      ctx.addIssue({ code: "custom", message: "INCLUDE needs a section and a priority" });
    if (f.section === "CAVEAT") ctx.addIssue({ code: "custom", message: "CAVEAT is not an assignable section" });
  })
  .transform((f) => (f.decision === "INCLUDE" ? f : { ...f, section: null, priority: null }));

export const VersionActionSchema = z.object({ report_id: uuid, version_id: uuid, version_hash: hash, reason });
export const EditStatementSchema = VersionActionSchema.extend({
  statement_local_id: z.string().regex(/^RS[0-9]{1,3}$/),
  text: z.string().trim().min(1).max(1500),
  editorial_transform: z.enum(EDITORIAL_TRANSFORMS),
});
export const StatementRefSchema = VersionActionSchema.extend({ statement_local_id: z.string().regex(/^RS[0-9]{1,3}$/) });

export function decideCandidateArgs(f: z.infer<typeof DecideCandidateSchema>) {
  return {
    p_candidate: f.candidate_id, p_object_hash: f.object_hash, p_decision: f.decision, p_section: f.section,
    p_priority: f.priority, p_expected_previous_decision: f.expected_previous_decision_id, p_reason: f.reason,
  };
}

/** Removal decisions from a form: one ACCEPT / REJECT radio per proposal id. */
export function removalDecisions(form: Record<string, string | string[]>, proposalIds: string[]) {
  return proposalIds.map((id) => {
    const d = form[`decision_${id}`];
    if (d !== "ACCEPT" && d !== "REJECT") throw new Error("decide every removal proposal");
    return { proposal_id: id, decision: d };
  });
}
