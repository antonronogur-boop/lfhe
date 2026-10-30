import { Submit } from "@/components/client";
import { Alert } from "@/components/ui";

import { signIn } from "./actions";

export const dynamic = "force-dynamic";

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  const { error } = await searchParams;
  return (
    <main>
      <div style={{ textAlign: "center", marginBottom: 18 }}>
        <div style={{ fontSize: 26, fontWeight: 750, color: "var(--accent)" }}>LFHÉ</div>
        <div className="muted">AI-assisted, human-governed air-domain OSINT workspace</div>
      </div>
      <section className="card">
        <h1 style={{ fontSize: 18 }}>Sign in</h1>
        {error === "missing" && <Alert kind="error">Enter your e-mail address and password.</Alert>}
        {error && error !== "missing" && <Alert kind="error" title="Sign-in failed.">Check the e-mail address and password.</Alert>}
        <form action={signIn} className="form">
          <div className="field"><label htmlFor="email">E-mail</label>
            <input id="email" name="email" type="email" required autoComplete="username" /></div>
          <div className="field"><label htmlFor="password">Password</label>
            <input id="password" name="password" type="password" required autoComplete="current-password" /></div>
          <Submit kind="primary" pendingText="Signing in…">Sign in</Submit>
        </form>
      </section>
      <p className="muted" style={{ fontSize: 12, textAlign: "center" }}>
        DEV / localhost pilot environment. Public OSINT, synthetic and authorised replay material only — never classified data.
      </p>
    </main>
  );
}
