import { signIn } from "./actions";

export const dynamic = "force-dynamic";

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  const { error } = await searchParams;
  return (
    <main>
      <h1>Sign in</h1>
      {error && <p role="alert" style={{ color: "#a00" }}>Sign-in failed.</p>}
      <form action={signIn} style={{ display: "grid", gap: 8, maxWidth: 320 }}>
        <label>Email <input name="email" type="email" required autoComplete="username" /></label>
        <label>Password <input name="password" type="password" required autoComplete="current-password" /></label>
        <button type="submit">Sign in</button>
      </form>
    </main>
  );
}
