export default function Loading() {
  return (
    <div aria-busy="true" aria-live="polite">
      <div className="skeleton" style={{ width: 280, height: 24, marginBottom: 14 }} />
      <div className="skeleton" style={{ width: "60%", marginBottom: 22 }} />
      <div className="grid cols-4">{[0, 1, 2, 3].map((i) => <div key={i} className="card"><div className="skeleton" style={{ height: 46 }} /></div>)}</div>
      <div className="card"><div className="skeleton" style={{ marginBottom: 10 }} /><div className="skeleton" style={{ width: "80%" }} /></div>
      <span className="muted">Loading…</span>
    </div>
  );
}
