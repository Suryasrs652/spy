/**
 * BFF proxy: the browser calls only this same-origin route, never FastAPI
 * directly. It attaches the httpOnly-cookie-derived session's FastAPI
 * access token + organization id server-side, so the access token never
 * reaches client-side JavaScript.
 */
import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://api:8000";

async function handle(req: NextRequest, path: string[]): Promise<NextResponse> {
  const session = await auth();
  if (!session?.accessToken) {
    return NextResponse.json(
      { error: { code: "UNAUTHENTICATED", message: "Not signed in.", request_id: "" } },
      { status: 401 },
    );
  }

  const targetPath = path.join("/");
  const search = req.nextUrl.search;
  const targetUrl = `${API_BASE_URL}/api/v1/${targetPath}${search}`;

  const headers = new Headers();
  headers.set("Authorization", `Bearer ${session.accessToken}`);
  headers.set("X-Organization-Id", session.organizationId);
  const contentType = req.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  const idempotencyKey = req.headers.get("idempotency-key");
  if (idempotencyKey) headers.set("Idempotency-Key", idempotencyKey);

  const hasBody = !["GET", "HEAD"].includes(req.method);
  const body = hasBody ? await req.arrayBuffer() : undefined;

  const upstream = await fetch(targetUrl, {
    method: req.method,
    headers,
    body: body && body.byteLength > 0 ? body : undefined,
    cache: "no-store",
  });

  const responseBody = await upstream.arrayBuffer();
  const responseHeaders = new Headers();
  const upstreamContentType = upstream.headers.get("content-type");
  if (upstreamContentType) responseHeaders.set("content-type", upstreamContentType);

  return new NextResponse(responseBody, { status: upstream.status, headers: responseHeaders });
}

export async function GET(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return handle(req, (await params).path);
}
export async function POST(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return handle(req, (await params).path);
}
export async function PATCH(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return handle(req, (await params).path);
}
export async function PUT(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return handle(req, (await params).path);
}
export async function DELETE(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return handle(req, (await params).path);
}
