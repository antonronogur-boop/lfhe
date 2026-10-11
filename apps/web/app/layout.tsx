import type { ReactNode } from "react";

export const metadata = { title: "LFHÉ — analyst workspace" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, sans-serif", margin: "0 auto", maxWidth: 1200, padding: 16, fontSize: 14 }}>
        <header style={{ borderBottom: "1px solid #ccc", marginBottom: 16, paddingBottom: 8 }}>
          <strong>LFHÉ</strong> — AI-assisted, human-governed OSINT processing ·{" "}
          <a href="/sources">Sources</a> · <a href="/claims">Claims</a>
        </header>
        {children}
      </body>
    </html>
  );
}
