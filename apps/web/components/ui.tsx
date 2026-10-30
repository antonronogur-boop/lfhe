import type { ReactNode } from "react";

/* Presentation-only building blocks of the analyst workspace. They never decide anything: every
   authoritative check runs again inside PostgreSQL (HUMAN_ONLY functions, RLS). */

export function PageHeader({ title, lede, crumbs, actions, badges }: {
  title: ReactNode; lede?: ReactNode; crumbs?: { href?: string; label: string }[]; actions?: ReactNode; badges?: ReactNode;
}) {
  return (
    <>
      {crumbs && crumbs.length > 0 && (
        <nav className="crumbs" aria-label="Breadcrumb">
          {crumbs.map((c, i) => (
            <span key={i}>{c.href ? <a href={c.href}>{c.label}</a> : <span aria-current="page">{c.label}</span>}
              {i < crumbs.length - 1 && <span aria-hidden> / </span>}</span>
          ))}
        </nav>
      )}
      <div className="page-head">
        <div>
          <div className="row"><h1>{title}</h1>{badges}</div>
          {lede && <p className="lede">{lede}</p>}
        </div>
        {actions && <div className="page-actions">{actions}</div>}
      </div>
    </>
  );
}

export function Card({ title, actions, children, tone, className, id }: {
  title?: ReactNode; actions?: ReactNode; children: ReactNode; tone?: "accent" | "warn" | "danger" | "ok" | "subtle"; className?: string;
  id?: string;
}) {
  const cls = ["card", tone === "subtle" ? "subtle" : tone ? `${tone}-l` : "", className ?? ""].join(" ").trim();
  return (
    <section className={cls} id={id}>
      {(title || actions) && <div className="card-head">{title && <h2>{title}</h2>}{actions && <div className="row">{actions}</div>}</div>}
      {children}
    </section>
  );
}

const TONE: Record<string, string> = {
  // generic workflow states
  PENDING: "neutral", QUEUED: "neutral", RUNNING: "info", SUCCESS: "ok", SUCCEEDED: "ok", FAILED: "danger", SKIPPED: "neutral",
  HUMAN_REVIEW: "warn", NEEDS_HUMAN_REVIEW: "warn",
  // review / approval
  APPROVE: "ok", APPROVED: "ok", MODIFY_AND_APPROVE: "ok", REJECT: "danger", REJECTED: "danger", ESCALATE: "warn", ESCALATED: "warn",
  REQUEST_REPROCESSING: "warn", REPROCESSING_REQUESTED: "warn", PENDING_REVIEW: "warn", UNREVIEWED: "warn", IN_REVIEW: "info",
  DRAFT: "neutral", CHALLENGED: "violet", SUPERSEDED: "neutral",
  // events
  CANDIDATE: "warn", ACTIVE: "accent", DEVELOPING: "info", CONFIRMED: "ok", CONTESTED: "danger", CLOSED: "neutral",
  // claims
  UNVERIFIED: "neutral", PARTIALLY_CORROBORATED: "info", CORROBORATED: "ok", CONFIRMED_PRIMARY: "ok", DISPROVEN: "danger",
  // QA / release
  PASS: "ok", PASS_WITH_WARNINGS: "warn", FAIL: "danger", WARNING: "warn", CRITICAL: "danger", MAJOR: "danger", MINOR: "info", INFO: "neutral",
  RELEASED: "ok", RELEASE_REJECTED: "danger", SECURITY_REJECTED: "danger", CONTENT_REJECTED: "danger",
  // pilot
  OPEN: "info", COMPLETED: "ok", STOPPED: "neutral", BLOCKING: "danger", ENHANCEMENT: "neutral",
  ENQUEUED: "info", ALREADY_ACTIVE: "neutral", ALREADY_COMPLETED: "neutral", REQUEUED_AFTER_FAILURE: "warn", REQUEUED_AFTER_REJECTION: "warn",
  HIGH: "accent", MODERATE: "info", LOW: "warn", LIVE: "info", REPLAY: "violet",
  SUPPORTS: "ok", CONTRADICTS: "danger", UPDATES: "info", CONTEXTUALISES: "neutral",
};

export function Badge({ value, tone, title, children }: { value?: string | null; tone?: string; title?: string; children?: ReactNode }) {
  const label = children ?? (value ?? "—").replaceAll("_", " ");
  return <span className={`badge ${tone ?? TONE[value ?? ""] ?? "neutral"}`} title={title}>{label}</span>;
}

export function EpistemicBadge({ category }: { category: string }) {
  const hint: Record<string, string> = {
    FACT: "FACT — reported / evidenced fact (attribution kept)",
    ASSUMPTION: "ASSUMPTION — a premise the judgement rests on",
    ASSESSMENT: "ASSESSMENT — analytic judgement (likelihood + confidence)",
  };
  return <span className={`badge epi-${category}`} title={hint[category]}>{category}</span>;
}

export function Alert({ kind, title, children }: { kind: "error" | "success" | "warn" | "info"; title?: ReactNode; children?: ReactNode }) {
  return (
    <div className={`alert ${kind}`} role={kind === "error" ? "alert" : "status"}>
      <div>{title && <strong>{title} </strong>}{children}</div>
    </div>
  );
}

/** Standard ?ok= / ?error= feedback after a server action. */
export function Flash({ ok, error, okText }: { ok?: string; error?: string; okText?: string }) {
  return (
    <>
      {error && <Alert kind="error" title="Not recorded.">{error}</Alert>}
      {ok && <Alert kind="success" title="Recorded.">{okText ?? `${ok.replaceAll("_", " ")} — the decision is in the audit log.`}</Alert>}
    </>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="empty"><strong>{title}</strong>{children}</div>;
}

/** Why an action is not available to the current role (shown instead of silently hiding it). */
export function Locked({ children }: { children: ReactNode }) {
  return <div className="locked"><span aria-hidden>🔒</span><span>{children}</span></div>;
}

export function Stat({ label, value, hint, href, tone }: { label: string; value: ReactNode; hint?: ReactNode; href?: string;
  tone?: "alert" | "warn" | "ok" }) {
  const body = <><div className="label">{label}</div><div className="value">{value}</div>{hint && <div className="hint">{hint}</div>}</>;
  return href ? <a className={`stat ${tone ?? ""}`} href={href}>{body}</a> : <div className={`stat ${tone ?? ""}`}>{body}</div>;
}

export function Tabs({ items, current }: { items: { key: string; label: ReactNode; href: string }[]; current: string }) {
  return (
    <nav className="tabs" aria-label="Sections">
      {items.map((t) => <a key={t.key} href={t.href} aria-current={t.key === current ? "page" : undefined}>{t.label}</a>)}
    </nav>
  );
}

export function Chips({ items, current }: { items: { key: string; label: ReactNode; href: string }[]; current: string }) {
  return (
    <nav className="chips" aria-label="Filter">
      {items.map((t) => <a key={t.key} className="chip" href={t.href} aria-current={t.key === current ? "page" : undefined}>{t.label}</a>)}
    </nav>
  );
}

export function KV({ rows }: { rows: [ReactNode, ReactNode][] }) {
  return <dl className="kv">{rows.map(([k, v], i) => <div key={i} style={{ display: "contents" }}><dt>{k}</dt><dd>{v ?? "—"}</dd></div>)}</dl>;
}

export function Short({ id, n = 8 }: { id?: string | null; n?: number }) {
  if (!id) return <span className="muted">—</span>;
  return <code title={id}>{id.slice(0, n)}…</code>;
}

export function When({ at }: { at?: string | null }) {
  if (!at) return <span className="muted">—</span>;
  const d = new Date(at);
  if (Number.isNaN(d.getTime())) return <span>{at}</span>;
  return <time dateTime={d.toISOString()} title={d.toISOString()}>{d.toISOString().replace("T", " ").slice(0, 16)} UTC</time>;
}

/** Native required confirmation: the form cannot be submitted (even without JavaScript) until ticked. */
export function Confirm({ children, name = "confirm" }: { children: ReactNode; name?: string }) {
  return <label className="checkline"><input type="checkbox" name={name} value="yes" required />{children}</label>;
}

export function Steps({ steps }: { steps: { label: string; detail?: ReactNode; state: "done" | "current" | "todo" }[] }) {
  return (
    <ol className="steps" aria-label="Workflow progress" style={{ listStyle: "none", padding: 0 }}>
      {steps.map((s, i) => <li key={i} className={`step ${s.state === "todo" ? "" : s.state}`}
        aria-current={s.state === "current" ? "step" : undefined}><b>{s.label}</b>{s.detail}</li>)}
    </ol>
  );
}
