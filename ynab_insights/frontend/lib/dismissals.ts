"use client";

/**
 * Client-side dismissal store (v2.5).
 *
 * Server is intentionally stateless about dismissals. Dismissed cards are
 * keyed by `dedup_key` in localStorage and filtered out at render time on
 * the feed. Cross-session persistence comes for free; cross-device is
 * intentionally out of scope (the product is anonymous-by-design).
 */

const KEY = "ynab-insights:dismissed";
const MAX_AGE_MS = 90 * 24 * 60 * 60 * 1000; // 90 days

type Dismissals = Record<string, number>; // dedup_key -> unix epoch ms

function read(): Dismissals {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Dismissals;
    return typeof parsed === "object" && parsed !== null ? parsed : {};
  } catch {
    return {};
  }
}

function write(value: Dismissals): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(value));
  } catch {
    // Quota or private-mode failure. Silent: not load-bearing.
  }
}

/** Return the current dismissal map after garbage-collecting old entries. */
export function loadDismissals(): Dismissals {
  const all = read();
  const cutoff = Date.now() - MAX_AGE_MS;
  const fresh: Dismissals = {};
  let changed = false;
  for (const [key, ts] of Object.entries(all)) {
    if (ts >= cutoff) {
      fresh[key] = ts;
    } else {
      changed = true;
    }
  }
  if (changed) write(fresh);
  return fresh;
}

export function isDismissed(dedupKey: string, dismissals?: Dismissals): boolean {
  const map = dismissals ?? loadDismissals();
  return dedupKey in map;
}

export function dismiss(dedupKey: string): void {
  const map = loadDismissals();
  map[dedupKey] = Date.now();
  write(map);
}

export function restore(dedupKey: string): void {
  const map = loadDismissals();
  delete map[dedupKey];
  write(map);
}

export function clearAllDismissals(): void {
  write({});
}
