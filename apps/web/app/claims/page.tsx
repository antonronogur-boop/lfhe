import { can, requireSession } from "@/lib/auth";
import { CLAIM_STATUSES, CLAIM_TYPES, HIGH_IMPACT_REASONS, REVIEW_DECISIONS, spanContext } from "@/lib/claims";
import { createClient } from "@/lib/supabase/server";

import { decideRevalidation, linkMention, markHighImpact, reviewClaim, setClaimStatus } from "./actions";

export const dynamic = "force-dynamic";

interface ClaimRow {
  id: string;
  claim_hash: string;
  claim_local_id: string;
  language_original: string;
  claim_text_original: string;
  claim_text_normalised: string;
  claim_type: string;
  source_statement_status: string;
  attribution: string | null;
  event_date: string | null;
  evidence_type: string;
  evidence_directness: string;
  span_start: number;
  span_end: number;
  span_exact_text: string;
  text_representation_id: string;
  article_snapshot_id: string;
  created_by_model_run_id: string;
  review_flags: string[];
  human_review_required: boolean;
  created_at: string;
}

interface StateRow {
  claim_id: string;
  claim_status: string;
  status_basis: string;
  high_impact: boolean;
  high_impact_reasons: string[];
  revalidation_pending: boolean;
  latest_review_id: string | null;
  review_state: string;
  effective_claim_text_normalised: string;
}

interface MentionRow {
  mention_id: string;
  claim_id: string;
  mention_text_original: string;
  entity_type_hint: string | null;
  resolution_status: string;
  entity_id: string | null;
  candidate_entity_ids: string[] | null;
  method: string | null;
}

const box = { border: "1px solid #ddd", borderRadius: 4, padding: 10, marginBottom: 14 } as const;
const muted = { color: "#666" } as const;

export default async function ClaimsPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; ok?: string; filter?: string }>;
}) {
  const { error, ok, filter } = await searchParams;
  const session = await requireSession();
  if (!can(session, "CLAIM_READ")) {
    return <p>You do not have permission to view claims.</p>;
  }
  const reviewer = can(session, "CLAIM_REVIEW");
  const entityManager = can(session, "ENTITY_MANAGE");
  const supabase = await createClient();

  let query = supabase.from("claims").select("*").order("created_at", { ascending: false }).limit(50);
  if (filter === "review") query = query.eq("human_review_required", true);
  const { data: claimData, error: loadError } = await query;
  const claims = (claimData ?? []) as ClaimRow[];
  const ids = claims.map((c) => c.id);
  const reps = [...new Set(claims.map((c) => c.text_representation_id))];

  const [{ data: stateData }, { data: mentionData }, { data: textData }, { data: revalData }] = await Promise.all([
    supabase.from("claim_state").select("*").in("claim_id", ids),
    supabase.from("entity_mention_resolution").select("*").in("claim_id", ids),
    supabase.from("text_representations").select("id,text_content").in("id", reps),
    supabase.from("claim_revalidations").select("id,claim_id,created_at").in("claim_id", ids),
  ]);
  const state = new Map(((stateData ?? []) as StateRow[]).map((s) => [s.claim_id, s]));
  const texts = new Map(((textData ?? []) as { id: string; text_content: string }[]).map((t) => [t.id, t.text_content]));
  const mentions = (mentionData ?? []) as MentionRow[];
  const revalidations = (revalData ?? []) as { id: string; claim_id: string }[];

  return (
    <main>
      <h1>Claims — human review</h1>
      <p style={muted}>
        Claims are AI-extracted and database-verified against the original-language text. The AI recommends; the
        decision is yours. Every action below is executed by a human-only database function and audited.
      </p>
      <p>
        <a href="/claims">All recent</a> · <a href="/claims?filter=review">Needs human review</a>
      </p>
      {error && <p role="alert" style={{ color: "#a00" }}>Error: {error}</p>}
      {ok && <p style={{ color: "#070" }}>Saved ({ok}). The decision is recorded in the audit log.</p>}
      {loadError && <p role="alert" style={{ color: "#a00" }}>Could not load claims: {loadError.message}</p>}
      {claims.length === 0 && <p>No claims yet.</p>}

      {claims.map((c) => {
        const s = state.get(c.id);
        const text = texts.get(c.text_representation_id);
        const ctx = text ? spanContext(text, c.span_start, c.span_end) : null;
        const pendingReval = s?.revalidation_pending ? revalidations.filter((r) => r.claim_id === c.id) : [];
        return (
          <section key={c.id} style={box}>
            <div style={muted}>
              {c.claim_local_id} · {c.claim_type} · {c.source_statement_status} · {c.evidence_type}/{c.evidence_directness}
              {" "}· lang {c.language_original} · status <strong>{s?.claim_status}</strong> ({s?.status_basis})
              {" "}· review <strong>{s?.review_state}</strong>
              {s?.high_impact && <strong style={{ color: "#a50" }}> · HIGH IMPACT ({s.high_impact_reasons.join(", ")})</strong>}
            </div>
            <p style={{ margin: "6px 0" }}><strong>Normalised:</strong> {s?.effective_claim_text_normalised ?? c.claim_text_normalised}</p>
            <p style={{ margin: "6px 0" }} lang={c.language_original}><strong>Original:</strong> {c.claim_text_original}</p>
            {ctx && (
              <p style={{ margin: "6px 0", background: "#fafafa", padding: 6 }} lang={c.language_original}>
                <span style={muted}>…{ctx.before}</span><mark>{ctx.span}</mark><span style={muted}>{ctx.after}…</span>
                <br />
                <small style={muted}>
                  evidence_span_original: code points [{c.span_start}, {c.span_end}) of text representation{" "}
                  {c.text_representation_id} (snapshot {c.article_snapshot_id}); model run {c.created_by_model_run_id}
                </small>
              </p>
            )}
            {c.attribution && <p style={{ margin: "6px 0" }}><strong>Attribution:</strong> {c.attribution}</p>}
            {c.review_flags.length > 0 && (
              <p style={{ color: "#a00", margin: "6px 0" }}>Review flags: {c.review_flags.join(", ")}</p>
            )}

            {mentions.filter((m) => m.claim_id === c.id).length > 0 && (
              <div style={{ margin: "6px 0" }}>
                <strong>Entity mentions:</strong>
                <ul style={{ margin: 0 }}>
                  {mentions.filter((m) => m.claim_id === c.id).map((m) => (
                    <li key={m.mention_id}>
                      “{m.mention_text_original}” ({m.entity_type_hint ?? "type?"}) — {m.resolution_status}
                      {m.entity_id && <> → {m.entity_id}</>}
                      {m.method && <span style={muted}> [{m.method}]</span>}
                      {m.resolution_status === "AMBIGUOUS" && m.candidate_entity_ids && (
                        <span style={muted}> candidates: {m.candidate_entity_ids.join(", ")}</span>
                      )}
                      {entityManager && m.resolution_status !== "RESOLVED" && (
                        <form action={linkMention} style={{ display: "inline", marginLeft: 8 }}>
                          <input type="hidden" name="mention_id" value={m.mention_id} />
                          <input type="hidden" name="resolution" value="RESOLVED" />
                          <input name="entity_id" placeholder="entity id" required size={38} />
                          <input name="reason" placeholder="evidence for the link" required minLength={5} />
                          <button type="submit">Link</button>
                        </form>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {reviewer && (
              <details>
                <summary>Review decision</summary>
                <form action={reviewClaim} style={{ display: "grid", gap: 4, maxWidth: 720 }}>
                  <input type="hidden" name="claim_id" value={c.id} />
                  <input type="hidden" name="claim_hash" value={c.claim_hash} />
                  <input type="hidden" name="expected_previous_review_id" value={s?.latest_review_id ?? ""} />
                  <label>Decision <select name="decision">{REVIEW_DECISIONS.map((d) => <option key={d}>{d}</option>)}</select></label>
                  <label>Reason <input name="reason" required minLength={5} /></label>
                  <fieldset>
                    <legend>Only for MODIFY_AND_APPROVE (the evidence span cannot be changed)</legend>
                    <label>Normalised text <textarea name="claim_text_normalised" rows={2} /></label>
                    <label>Claim type <select name="claim_type" defaultValue=""><option value="" />
                      {CLAIM_TYPES.map((t) => <option key={t}>{t}</option>)}</select></label>
                    <label>Attribution <input name="attribution" /></label>
                  </fieldset>
                  <button type="submit">Record decision</button>
                </form>
                <form action={setClaimStatus} style={{ marginTop: 6 }}>
                  <input type="hidden" name="claim_id" value={c.id} />
                  <input type="hidden" name="expected_current_status" value={s?.claim_status ?? "UNVERIFIED"} />
                  Status: <select name="new_status">{CLAIM_STATUSES.map((st) => <option key={st}>{st}</option>)}</select>{" "}
                  <input name="reason" placeholder="basis for the status" required minLength={5} />
                  <button type="submit">Set status</button>
                </form>
                <form action={markHighImpact} style={{ marginTop: 6 }}>
                  <input type="hidden" name="claim_id" value={c.id} />
                  <input type="hidden" name="high_impact" value={String(!s?.high_impact)} />
                  {!s?.high_impact && (
                    <select name="reasons" multiple size={3}>{HIGH_IMPACT_REASONS.map((r) => <option key={r}>{r}</option>)}</select>
                  )}{" "}
                  <input name="reason" placeholder="reason" required minLength={5} />
                  <button type="submit">{s?.high_impact ? "Remove high impact" : "Mark high impact"}</button>
                </form>
                {pendingReval.map((r) => (
                  <form key={r.id} action={decideRevalidation} style={{ marginTop: 6, color: "#a50" }}>
                    High-impact revalidation required for the automatically assigned status.{" "}
                    <input type="hidden" name="revalidation_id" value={r.id} />
                    <select name="approve"><option value="true">Confirm status</option><option value="false">Reject (revert)</option></select>{" "}
                    <input name="reason" placeholder="reason" required minLength={5} />
                    <button type="submit">Decide</button>
                  </form>
                ))}
              </details>
            )}
          </section>
        );
      })}
    </main>
  );
}
