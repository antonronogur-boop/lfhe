import { can, requireSession } from "@/lib/auth";
import { COLLECTION_METHODS, RETENTION_MODES, SOURCE_TYPES } from "@/lib/sources";
import { createClient } from "@/lib/supabase/server";

import { Flash, PageHeader } from "@/components/ui";
import { createSource, setCollectionMethodApproval, setSourceActive } from "./actions";

export const dynamic = "force-dynamic";

interface SourceRow {
  id: string;
  name: string;
  canonical_domain: string;
  source_type: string;
  primary_language: string;
  collection_method: string;
  collection_method_approved: boolean;
  retention_mode: string;
  active: boolean;
  updated_at: string;
}


export default async function SourcesPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; ok?: string }>;
}) {
  const { error, ok } = await searchParams;
  const session = await requireSession();
  if (!can(session, "SOURCE_READ")) {
    return <p>You do not have permission to view the source registry.</p>;
  }

  const supabase = await createClient();
  const { data, error: loadError } = await supabase
    .from("sources")
    .select("id,name,canonical_domain,source_type,primary_language,collection_method,collection_method_approved,retention_mode,active,updated_at")
    .order("name");
  const sources = (data ?? []) as SourceRow[];

  return (
    <main>
      <PageHeader title="Source registry" crumbs={[{ href: "/", label: "Dashboard" }, { label: "Sources" }]}
        lede="Approved public sources only. Collection method approval and activation are separate, audited human decisions; the collector reads only active, approved sources." />
      <Flash ok={ok} error={error} />
      {loadError && <Flash error={`Could not load sources: ${loadError.message}`} />}
      <div className="table-wrap"><table className="table">
        <thead>
          <tr>
            {["Name", "Domain", "Type", "Lang", "Method", "Approved", "Retention", "Active", "Actions"].map((h) => (
              <th key={h} >{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sources.map((s) => (
            <tr key={s.id}>
              <td>{s.name}</td>
              <td>{s.canonical_domain}</td>
              <td>{s.source_type}</td>
              <td>{s.primary_language}</td>
              <td>{s.collection_method}</td>
              <td>{s.collection_method_approved ? "yes" : "no"}</td>
              <td>{s.retention_mode}</td>
              <td>{s.active ? "ACTIVE" : "inactive"}</td>
              <td>
                {can(session, "SOURCE_APPROVE_COLLECTION_METHOD") && (
                  <form action={setCollectionMethodApproval} style={{ marginBottom: 4 }}>
                    <input type="hidden" name="id" value={s.id} />
                    <input type="hidden" name="approved" value={String(!s.collection_method_approved)} />
                    <input name="reason" placeholder="terms / legal basis" required minLength={5} />
                    <button type="submit">{s.collection_method_approved ? "Revoke method" : "Approve method"}</button>
                  </form>
                )}
                {can(session, "SOURCE_ACTIVATE") && (
                  <form action={setSourceActive}>
                    <input type="hidden" name="id" value={s.id} />
                    <input type="hidden" name="active" value={String(!s.active)} />
                    <input name="reason" placeholder="reason" required minLength={5} />
                    <button type="submit" disabled={!s.active && !s.collection_method_approved}>
                      {s.active ? "Deactivate" : "Activate"}
                    </button>
                  </form>
                )}
              </td>
            </tr>
          ))}
          {sources.length === 0 && (
            <tr><td colSpan={9}>No sources registered yet (initial source list K-05 is pending).</td></tr>
          )}
        </tbody>
      </table></div>

      {can(session, "SOURCE_CREATE") && (
        <section className="card" style={{ marginTop: 16 }}>
          <h2>Register a source</h2>
          <p style={{ color: "#555" }}>
            New sources start inactive with an unapproved collection method. A reviewer must approve the
            method (terms / legal basis) before the source can be activated.
          </p>
          <form action={createSource} className="form" style={{ maxWidth: 640 }}>
            <label>Name <input name="name" required /></label>
            <label>Canonical domain <input name="canonical_domain" required placeholder="example.org" /></label>
            <label>Owner organisation <input name="owner_organisation" /></label>
            <label>Owner country (ISO-2) <input name="owner_country" maxLength={2} /></label>
            <label>Source type <select name="source_type">{SOURCE_TYPES.map((t) => <option key={t}>{t}</option>)}</select></label>
            <label>Official status <select name="official_status"><option>NON_OFFICIAL</option><option>SEMI_OFFICIAL</option><option>OFFICIAL</option></select></label>
            <label>Primary language (BCP-47) <input name="primary_language" required placeholder="uk" /></label>
            <label>Collection method <select name="collection_method">{COLLECTION_METHODS.map((m) => <option key={m}>{m}</option>)}</select></label>
            <label>Collection config (JSON, no credentials)
              <textarea name="collection_config" rows={3} defaultValue={'{"feed_url": "https://"}'} />
            </label>
            <label>Frequency <input name="collection_frequency" defaultValue="1 hour" /></label>
            <label>Retention mode <select name="retention_mode">{RETENTION_MODES.map((m) => <option key={m}>{m}</option>)}</select></label>
            <label>Terms notes <textarea name="terms_notes" rows={2} /></label>
            <button type="submit">Register (inactive)</button>
          </form>
        </section>
      )}
    </main>
  );
}
