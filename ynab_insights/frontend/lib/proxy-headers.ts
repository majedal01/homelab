/**
 * Build the `Headers` we send upstream to FastAPI from a browser-facing
 * Next.js request.
 *
 * The Cloudflare Tunnel terminates TLS and routes to the Next container;
 * Next then proxies `/api/*` to FastAPI on the compose-internal network.
 * FastAPI needs the original protocol / host / client IP to set the
 * cookie Secure flag, recognize the public hostname, and bucket rate
 * limits by real client address — but Next.js doesn't auto-forward
 * anything beyond the request method and body.
 *
 * Trust model:
 * - Cloudflare strips client-supplied `CF-Connecting-IP` and `CF-Ray`
 *   before forwarding, so seeing those headers reliably means "request
 *   came through the tunnel."
 * - We explicitly STRIP every inbound `X-Forwarded-*` before re-setting
 *   them. A browser could trivially try to spoof X-Forwarded-Proto=https
 *   in dev; we always derive the value ourselves.
 */

import type { NextRequest } from "next/server";

/** Build upstream headers, preserving everything safe and re-deriving the
 *  forwarded chain server-side. */
export function buildUpstreamHeaders(request: NextRequest): Headers {
  const incoming = request.headers;

  // CF sets these on every tunnel-routed request and strips any
  // client-supplied versions. Their presence is the "behind CF" signal.
  const cfClientIp = incoming.get("cf-connecting-ip");
  const cfRay = incoming.get("cf-ray");
  const behindCloudflare = !!(cfClientIp || cfRay);

  const upstream = new Headers();
  for (const [key, value] of incoming.entries()) {
    const lower = key.toLowerCase();
    // Never trust client-supplied forwarding metadata; we set ours below.
    if (lower.startsWith("x-forwarded-")) continue;
    // Hop-by-hop headers that don't belong on the upstream request.
    if (lower === "host" || lower === "connection" || lower === "keep-alive") continue;
    upstream.set(key, value);
  }

  // X-Forwarded-Proto. Prefer what an upstream trusted proxy already
  // set. If absent and we're behind CF, the tunnel terminated TLS so
  // the original scheme was https. If absent and not behind CF (local
  // dev), fall through to http.
  const xfProto = incoming.get("x-forwarded-proto");
  if (xfProto) {
    upstream.set("x-forwarded-proto", xfProto);
  } else if (behindCloudflare) {
    upstream.set("x-forwarded-proto", "https");
  } else {
    upstream.set("x-forwarded-proto", "http");
  }

  // X-Forwarded-Host. The browser's Host header carries the public name
  // (ynab.majed.fyi); CF preserves it on tunnel-routed requests.
  const host = incoming.get("host");
  if (host) upstream.set("x-forwarded-host", host);

  // X-Forwarded-For. CF-Connecting-IP is the real client IP and is
  // trustworthy (CF strips client-supplied copies). Fall back to any
  // existing X-Forwarded-For chain from another upstream proxy.
  const existingXff = incoming.get("x-forwarded-for");
  if (cfClientIp) {
    upstream.set("x-forwarded-for", cfClientIp);
  } else if (existingXff) {
    upstream.set("x-forwarded-for", existingXff);
  }

  return upstream;
}
