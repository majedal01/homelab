/**
 * Streaming proxy from the browser to FastAPI's /ask SSE endpoint.
 *
 * Forwards the session cookie + the derived X-Forwarded-* trio so the
 * backend can resolve the session and the v2.6e ProxyHeaderMiddleware
 * stays quiet on a properly-fronted request. Header derivation lives
 * in `lib/proxy-headers.ts` and is shared with the catch-all proxy.
 *
 * On client abort, propagates upstream so FastAPI cancels the agent
 * stream and we stop being billed for unused tokens.
 */

import { NextRequest } from "next/server";

import { buildUpstreamHeaders } from "@/lib/proxy-headers";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const body = await request.text();
  const upstreamHeaders = buildUpstreamHeaders(request.headers);
  // SSE always sends JSON; ensure the upstream sees it even if the
  // browser omitted content-type for some reason.
  if (!upstreamHeaders.has("content-type")) {
    upstreamHeaders.set("content-type", "application/json");
  }

  const upstream = await fetch(`${BACKEND_URL}/ask`, {
    method: "POST",
    headers: upstreamHeaders,
    body,
    signal: request.signal,
    // @ts-expect-error duplex required for streaming requests in Node 18+
    duplex: "half",
  });

  if (!upstream.ok || !upstream.body) {
    const text = await upstream.text().catch(() => "");
    return new Response(text, {
      status: upstream.status,
      headers: {
        "content-type": upstream.headers.get("content-type") ?? "text/plain",
      },
    });
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "content-type": "text/event-stream",
      "cache-control": "no-cache, no-transform",
      "x-accel-buffering": "no",
      connection: "keep-alive",
    },
  });
}
