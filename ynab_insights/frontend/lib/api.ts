/**
 * Server-side fetch helper for calling FastAPI from React Server Components.
 *
 * The browser never hits this code path directly; `apiFetch` is invoked from
 * RSC, which runs in the Next.js container and calls the backend over the
 * Compose-internal network at `http://app:8000`.
 *
 * The `BACKEND_URL` env var points at FastAPI:
 *   - prod/stage container: `http://app:8000`
 *   - local dev:            `http://localhost:8000`
 */

import { cookies } from "next/headers";
import type { BudgetResponse } from "./api-types";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

/** Cookie name used by the budget switcher to persist user's selection. */
export const BUDGET_COOKIE = "budget_id";

/**
 * Returns the budget the user has selected via the switcher, falling back to
 * the first available budget. Returns null when the user has no budgets.
 *
 * Server-only: reads the request cookie store via next/headers. Pages call
 * this once and pass the id into all downstream fetches.
 */
export async function getSelectedBudgetId(
  budgets: BudgetResponse[],
): Promise<string | null> {
  if (!budgets.length) return null;
  const fromCookie = (await cookies()).get(BUDGET_COOKIE)?.value;
  if (fromCookie && budgets.some((b) => b.id === fromCookie)) {
    return fromCookie;
  }
  return budgets[0].id;
}

export interface ApiFetchOptions extends RequestInit {
  /** When true, raise on non-2xx instead of returning the response. */
  throwOnError?: boolean;
  /**
   * Next-specific cache hint. RSC default is to cache forever; we want
   * dashboard reads to revalidate so a fresh sync shows up.
   */
  revalidate?: number;
}

export async function apiFetch<T>(
  path: string,
  options: ApiFetchOptions = {},
): Promise<T> {
  const { throwOnError = true, revalidate = 0, ...init } = options;
  const url = `${BACKEND_URL}${path.startsWith("/") ? path : `/${path}`}`;

  const response = await fetch(url, {
    ...init,
    next: { revalidate },
    headers: { "content-type": "application/json", ...(init.headers ?? {}) },
  });

  if (!response.ok && throwOnError) {
    const text = await response.text().catch(() => "");
    throw new Error(
      `API request failed: ${response.status} ${response.statusText} - ${text}`,
    );
  }
  return (await response.json()) as T;
}

/** Build a query string from an object of optional params, dropping undefined/null. */
export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const entries = Object.entries(params).filter(
    ([, v]) => v !== null && v !== undefined && v !== "",
  ) as [string, string | number | boolean][];
  if (!entries.length) return "";
  const usp = new URLSearchParams();
  for (const [k, v] of entries) usp.set(k, String(v));
  return `?${usp.toString()}`;
}
