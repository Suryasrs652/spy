/**
 * Unauthenticated passthrough to FastAPI's public `/api/v1/auth/*`
 * endpoints (signup, verify-email, forgot-password, reset-password) — the
 * ones a browser must be able to call before it has a session, so they
 * can't go through the session-gated BFF proxy at /api/proxy/*.
 *
 * Restricted to an explicit allowlist rather than open-proxying all of
 * `/api/v1/*` without credentials.
 */
import { NextRequest, NextResponse } from "next/server";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://api:8000";

const ALLOWED_PATHS = new Set(["signup", "verify-email", "forgot-password", "reset-password"]);

export async function POST(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const action = path[0];
  if (path.length !== 1 || !ALLOWED_PATHS.has(action)) {
    return NextResponse.json(
      { error: { code: "NOT_FOUND", message: "Unknown action.", request_id: "" } },
      { status: 404 },
    );
  }

  const targetUrl = `${API_BASE_URL}/api/v1/auth/${action}`;
  const body = await req.arrayBuffer();

  // Preserve the real client IP for FastAPI's rate limiter (§100) — without
  // this every request would appear to come from the Next.js server itself.
  const forwardedFor = req.headers.get("x-forwarded-for") ?? req.headers.get("x-real-ip") ?? "";

  const upstream = await fetch(targetUrl, {
    method: "POST",
    headers: {
      "Content-Type": req.headers.get("content-type") ?? "application/json",
      ...(forwardedFor ? { "X-Forwarded-For": forwardedFor } : {}),
    },
    body,
    cache: "no-store",
  });

  const responseBody = await upstream.arrayBuffer();
  const responseHeaders = new Headers();
  const upstreamContentType = upstream.headers.get("content-type");
  if (upstreamContentType) responseHeaders.set("content-type", upstreamContentType);

  return new NextResponse(responseBody, { status: upstream.status, headers: responseHeaders });
}
