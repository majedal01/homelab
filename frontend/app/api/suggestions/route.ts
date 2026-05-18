/**
 * Server-side proxy for FastAPI's /suggestions endpoint.
 *
 * GET /api/suggestions?budget_id=... → backend /suggestions?budget_id=...
 * Returns SuggestionResponse JSON.
 */

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const upstream = new URL(`${BACKEND_URL}/suggestions`);
  for (const [k, v] of url.searchParams) {
    upstream.searchParams.set(k, v);
  }
  const response = await fetch(upstream, {
    headers: { accept: "application/json" },
    signal: request.signal,
  });
  const text = await response.text();
  return new Response(text, {
    status: response.status,
    headers: {
      "content-type":
        response.headers.get("content-type") ?? "application/json",
    },
  });
}
