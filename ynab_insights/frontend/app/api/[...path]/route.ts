/**
 * Browser-facing proxy to FastAPI.
 *
 * The Next.js container is the only thing that can reach FastAPI
 * (`http://app:8000` on the compose-internal network). Browser code
 * posts to relative `/api/*` paths; this route forwards request + body
 * + cookies upstream and pipes the response back, including Set-Cookie
 * so the `sid` cookie lands in the browser.
 *
 * SSE endpoints (`/ask`) have their own handler at app/api/ask/route.ts
 * because they need streaming. This handler covers everything else
 * under `/api/`.
 */

import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export const dynamic = "force-dynamic";

async function proxy(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const upstreamPath = `/api/${path.join("/")}`;
  const search = request.nextUrl.search;
  const url = `${BACKEND_URL}${upstreamPath}${search}`;

  const upstreamHeaders: Record<string, string> = {};
  const cookie = request.headers.get("cookie");
  if (cookie) upstreamHeaders["cookie"] = cookie;
  const ct = request.headers.get("content-type");
  if (ct) upstreamHeaders["content-type"] = ct;

  // Read body once. GET/HEAD have no body; everything else may.
  const method = request.method;
  const hasBody = method !== "GET" && method !== "HEAD";
  const body = hasBody ? await request.arrayBuffer() : undefined;

  const upstream = await fetch(url, {
    method,
    headers: upstreamHeaders,
    body,
    signal: request.signal,
  });

  // Pass Set-Cookie through unmodified so the signed `sid` lands in the
  // browser. fetch's Headers may fold multiple Set-Cookie into one;
  // Response's setCookie API handles multiple correctly via append.
  const responseHeaders = new Headers();
  upstream.headers.forEach((value, key) => {
    if (key.toLowerCase() === "set-cookie") {
      // Skip; we'll re-emit below to ensure each set-cookie is its own header.
      return;
    }
    responseHeaders.set(key, value);
  });
  const setCookieList = upstream.headers.getSetCookie?.() ?? [];
  for (const sc of setCookieList) {
    responseHeaders.append("set-cookie", sc);
  }

  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
