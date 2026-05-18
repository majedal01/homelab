/**
 * Streaming proxy from the browser to FastAPI's /ask SSE endpoint.
 *
 * The browser never reaches FastAPI directly (no host port); this route
 * pipes the upstream body through without buffering so tokens arrive at
 * the client in real time. When the client aborts, the fetch to FastAPI
 * aborts too — FastAPI cancels its generator, which closes the Anthropic
 * stream and stops billing tokens.
 */

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const body = await request.text();

  const upstream = await fetch(`${BACKEND_URL}/ask`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body,
    // Propagate the client's abort signal upstream.
    signal: request.signal,
    // @ts-expect-error duplex is required for streaming requests in Node 18+
    duplex: "half",
  });

  if (!upstream.ok || !upstream.body) {
    const text = await upstream.text().catch(() => "");
    return new Response(text, {
      status: upstream.status,
      headers: {
        "content-type":
          upstream.headers.get("content-type") ?? "text/plain",
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
