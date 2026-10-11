/**
 * Credential-key rule 'lfhe-credential-keys/1' (CG1-03) — client-side mirror of
 * lfhe.is_credential_key / lfhe.credential_key_paths. The database remains
 * authoritative (BEFORE triggers + CHECK constraints); this only gives early,
 * readable form errors.
 */
const FORBIDDEN_SEGMENTS = new Set([
  "headers", "header", "auth", "authorization", "authentication", "cookies", "cookie",
  "password", "passwords", "passwd", "token", "secret", "secrets", "apikey",
  "credential", "credentials", "bearer",
]);
const FORBIDDEN_LAST_SEGMENTS = new Set(["key", "keys"]);

export function normaliseKey(key: string): string {
  return key
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

export function isCredentialKey(key: string): boolean {
  const segments = normaliseKey(key).split("_");
  return segments.some((s) => FORBIDDEN_SEGMENTS.has(s)) || FORBIDDEN_LAST_SEGMENTS.has(segments[segments.length - 1]);
}

export function credentialKeyPaths(value: unknown, path = "$"): string[] {
  const out: string[] = [];
  if (Array.isArray(value)) {
    value.forEach((v, i) => out.push(...credentialKeyPaths(v, `${path}[${i}]`)));
  } else if (value !== null && typeof value === "object") {
    for (const key of Object.keys(value as Record<string, unknown>).sort()) {
      if (isCredentialKey(key)) out.push(`${path}.${key}`);
      out.push(...credentialKeyPaths((value as Record<string, unknown>)[key], `${path}.${key}`));
    }
  }
  return out;
}

/** CG1-08 mirror of lfhe.url_credential_problems (names only, never values). */
export function urlCredentialProblems(url: string): string[] {
  if (!/^[A-Za-z][A-Za-z0-9+.-]*:\/\//.test(url)) return [];
  const out: string[] = [];
  const authority = /^[A-Za-z][A-Za-z0-9+.-]*:\/\/([^/?#]*)/.exec(url)?.[1] ?? "";
  if (authority.includes("@") || authority.toLowerCase().includes("%40")) out.push("USERINFO");
  const query = /\?([^#]*)/.exec(url)?.[1] ?? "";
  const fragment = /#(.*)$/.exec(url)?.[1] ?? "";
  for (const part of `${query}&${fragment}`.split("&")) {
    if (!part) continue;
    let name = part.split("=")[0].replace(/\+/g, " ");
    try { name = decodeURIComponent(name); } catch { /* inspect raw name */ }
    if (name && isCredentialKey(name)) out.push(`CREDENTIAL_PARAMETER:${name.toLowerCase()}`);
  }
  return out;
}

export function credentialUrlPaths(value: unknown, path = "$"): string[] {
  const out: string[] = [];
  if (typeof value === "string") {
    for (const p of urlCredentialProblems(value)) out.push(`${path} (${p})`);
  } else if (Array.isArray(value)) {
    value.forEach((v, i) => out.push(...credentialUrlPaths(v, `${path}[${i}]`)));
  } else if (value !== null && typeof value === "object") {
    for (const key of Object.keys(value as Record<string, unknown>).sort()) {
      out.push(...credentialUrlPaths((value as Record<string, unknown>)[key], `${path}.${key}`));
    }
  }
  return out;
}
