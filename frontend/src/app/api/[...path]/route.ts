/**
 * Server-side proxy for all /api/* requests.
 * Adds X-API-Key from the server-only API_KEY env var so the key is never
 * exposed in the client-side bundle (FIN-018).
 */
import { NextRequest, NextResponse } from "next/server";

const BACKEND =
  process.env.API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000";

const API_KEY = process.env.API_KEY || process.env.NEXT_PUBLIC_API_KEY || "";

function buildHeaders(incoming: Headers): Headers {
  const out = new Headers();
  // Forward Content-Type only
  const ct = incoming.get("content-type");
  if (ct) out.set("content-type", ct);
  if (API_KEY) out.set("x-api-key", API_KEY);
  return out;
}

async function proxy(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
  method: string,
): Promise<NextResponse> {
  const { path } = await params;
  const joined = path.join("/");
  const search = request.nextUrl.search;
  const url = `${BACKEND}/api/${joined}${search}`;

  const headers = buildHeaders(request.headers);
  const init: RequestInit = { method, headers, cache: "no-store" };

  if (method !== "GET" && method !== "HEAD") {
    init.body = await request.text();
  }

  try {
    const upstream = await fetch(url, init);
    const body = await upstream.text();
    return new NextResponse(body, {
      status: upstream.status,
      headers: { "content-type": upstream.headers.get("content-type") || "application/json" },
    });
  } catch (err) {
    return NextResponse.json({ detail: "Upstream error" }, { status: 502 });
  }
}

export function GET(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(req, ctx, "GET");
}
export function POST(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(req, ctx, "POST");
}
export function PUT(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(req, ctx, "PUT");
}
export function DELETE(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(req, ctx, "DELETE");
}
