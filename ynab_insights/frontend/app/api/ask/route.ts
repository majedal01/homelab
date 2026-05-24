/**
 * Streaming proxy from the browser to FastAPI's /ask SSE endpoint.
 *
 * Forwards the session cookie so the backend can resolve the session.
 * On client abort, propagates upstream so FastAPI cancels the Anthropic
 * stream and stops billing tokens.
 */

import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const body = await request.text();
  const cookie = request.headers.get("cookie") ?? "";

  const upstream = await fetch(`${BACKEND_URL}/ask`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(cookie ? { cookie } : {}),
    },
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
