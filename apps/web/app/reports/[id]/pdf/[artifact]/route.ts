import { createHash } from "node:crypto";

import { NextResponse } from "next/server";

import { can, requireSession } from "@/lib/auth";
import { byteaToBytes } from "@/lib/release";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

/** Download a stored release PDF artifact (bytes exactly as stored; RLS: CLAIM_READ). The SHA-256 is
 * re-checked against the stored hash before the bytes are served. */
export async function GET(_req: Request, { params }: { params: Promise<{ id: string; artifact: string }> }) {
  const { id, artifact } = await params;
  const session = await requireSession();
  if (!can(session, "CLAIM_READ")) return new NextResponse("forbidden", { status: 403 });
  const supabase = await createClient();
  const { data, error } = await supabase.from("release_pdf_artifacts").select("pdf_bytes,pdf_sha256,report_id,report_version_id")
    .eq("id", artifact).eq("report_id", id).single();
  if (error || !data) return new NextResponse("not found", { status: 404 });
  const bytes = byteaToBytes(data.pdf_bytes as string);
  const digest = createHash("sha256").update(bytes).digest("hex");
  if (digest !== data.pdf_sha256) return new NextResponse("stored PDF does not match its SHA-256", { status: 409 });
  return new NextResponse(Buffer.from(bytes), {
    headers: { "content-type": "application/pdf", "content-disposition": `attachment; filename="lfhe-${data.report_version_id}-${digest.slice(0, 12)}.pdf"`,
               "x-content-type-options": "nosniff", "cache-control": "private, no-store" },
  });
}
