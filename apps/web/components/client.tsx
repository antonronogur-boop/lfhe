"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { useFormStatus } from "react-dom";

/** Submit button with a pending state: disabled while the server action runs, so a decision cannot be sent twice. */
export function Submit({ children, kind, small, name, value, pendingText = "Working…" }: {
  children: ReactNode; kind?: "primary" | "danger" | "ok" | "ghost"; small?: boolean; name?: string; value?: string; pendingText?: string;
}) {
  const { pending } = useFormStatus();
  return (
    <button type="submit" className={[kind ?? "", small ? "small" : ""].join(" ").trim() || undefined} disabled={pending}
      aria-busy={pending} name={name} value={value}>
      {pending ? pendingText : children}
    </button>
  );
}

export function NavLink({ href, children, count, alert }: { href: string; children: ReactNode; count?: number; alert?: boolean }) {
  const path = usePathname() ?? "/";
  const active = href === "/" ? path === "/" : path === href || path.startsWith(`${href}/`);
  return (
    <a className="nav-link" href={href} aria-current={active ? "page" : undefined}>
      <span>{children}</span>
      {count !== undefined && count > 0 && <span className={`nav-count ${alert ? "alert" : ""}`}>{count}</span>}
    </a>
  );
}
