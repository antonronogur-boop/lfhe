"use client";

export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <section className="card danger-l" role="alert">
      <h1>This page could not be displayed</h1>
      <p className="text-2">Nothing was changed: every decision in LFHÉ is a separate, audited database action, and none was sent from this
        page. Reload to try again; if it persists, record a UX finding with the address of this page.</p>
      {error.digest && <p className="muted">Reference: <code>{error.digest}</code></p>}
      <div className="row"><button type="button" className="primary" onClick={() => reset()}>Try again</button><a className="btn" href="/">Dashboard</a></div>
    </section>
  );
}
