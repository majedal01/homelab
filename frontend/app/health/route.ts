/**
 * Frontend liveness endpoint. Returns 200 once the Next.js server is up.
 *
 * The Compose stack's smoke check hits the host port (which maps to this
 * Next.js container), so this is what verifies the frontend is serving.
 * Independent of FastAPI's `/api/health` (which goes through the proxy).
 */
export function GET() {
  return Response.json({ status: "ok", service: "frontend" });
}
