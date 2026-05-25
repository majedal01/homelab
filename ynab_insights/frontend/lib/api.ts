/**
 * Server-side fetch helper for the v2.5 backend.
 *
 * RSC pages call FastAPI directly over the Compose-internal network at
 * `http://app:8000`. The session cookie set by the browser arrives in
 * the incoming Next request; we forward it upstream so FastAPI can
 * resolve the session.
 *
 * The browser never holds tokens. The `sid` cookie is HttpOnly + signed.
 */

import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";

import type { SessionPublic } from "./api-types";
import { buildUpstreamHeaders } from "./proxy-headers";

export type { SessionPublic };

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export class SessionExpiredError extends Error {
  constructor() {
    super("session_expired");
    this.name = "SessionExpiredError";
  }
}

export interface ApiFetchOptions extends RequestInit {
  /** When true (default), throw on non-2xx. 401s always throw SessionExpiredError. */
  throwOnError?: boolean;
  /** Next-specific cache hint; default 0 (no cache). */
  revalidate?: number;
}

/**
 * Server-side fetch to the FastAPI backend with the request's session
 * cookie attached. Use this from RSC and route handlers; the browser
 * never sees BACKEND_URL.
 *
 * On 401 throws SessionExpiredError. Pages can catch + redirect, or use
 * `requireSession()` for the common case.
 */
export async function apiFetch<T>(
  path: string,
  options: ApiFetchOptions = {},
): Promise<T> {
  const { throwOnError = true, revalidate = 0, headers: extraHeaders, ...init } = options;
  const url = `${BACKEND_URL}${path.startsWith("/") ? path : `/${path}`}`;

  // Derive the upstream Headers via the same helper the browser-facing
  // proxy routes use. The incoming RSC request carries X-Forwarded-*
  // from the Cloudflare Tunnel; without forwarding them here, FastAPI's
  // v2.6e ProxyHeaderMiddleware fires "missing X-Forwarded-Proto"
  // warnings for every server-rendered page load.
  const incomingHeaders = await headers();
  const upstreamHeaders = buildUpstreamHeaders(incomingHeaders);
  upstreamHeaders.set("content-type", "application/json");

  // `cookies()` reflects the parsed request cookie jar, which is what
  // FastAPI expects in the `Cookie` header.
  const cookieStore = await cookies();
  const cookieHeader = cookieStore
    .getAll()
    .map((c) => `${c.name}=${c.value}`)
    .join("; ");
  if (cookieHeader) upstreamHeaders.set("cookie", cookieHeader);

  // Caller-supplied headers win over auto-derived ones.
  if (extraHeaders) {
    for (const [k, v] of Object.entries(extraHeaders as Record<string, string>)) {
      upstreamHeaders.set(k, v);
    }
  }

  const response = await fetch(url, {
    ...init,
    next: { revalidate },
    headers: upstreamHeaders,
  });

  if (response.status === 401) {
    throw new SessionExpiredError();
  }
  if (!response.ok && throwOnError) {
    const text = await response.text().catch(() => "");
    throw new Error(
      `API request failed: ${response.status} ${response.statusText} - ${text}`,
    );
  }
  return (await response.json()) as T;
}

/**
 * RSC-friendly session guard. Calls /api/session; redirects to /welcome
 * on 401. Returns the session metadata for pages that want to display
 * it (active budget name, expiry).
 */
export async function requireSession(): Promise<SessionPublic> {
  try {
    return await apiFetch<SessionPublic>("/api/session");
  } catch (err) {
    if (err instanceof SessionExpiredError) {
      // Preserve the path the user was trying to reach so we can return
      // them after token entry. Done via header on the redirect; the
      // welcome page reads `?next=`.
      const hdrs = await headers();
      const next = hdrs.get("x-pathname") ?? "/insights";
      redirect(`/welcome?next=${encodeURIComponent(next)}`);
    }
    throw err;
  }
}

/** Build a query string from an object of optional params, dropping undefined/null. */
export function qs(
  params: Record<string, string | number | boolean | null | undefined>,
): string {
  const entries = Object.entries(params).filter(
    ([, v]) => v !== null && v !== undefined && v !== "",
  ) as [string, string | number | boolean][];
  if (!entries.length) return "";
  const usp = new URLSearchParams();
  for (const [k, v] of entries) usp.set(k, String(v));
  return `?${usp.toString()}`;
}
