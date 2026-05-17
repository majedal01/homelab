import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format integer cents as a USD-style string with the sign in the
 * conventional position: `-$1,234.56` rather than `$-1,234.56`.
 * Mirrors the `dollars` Jinja filter in the backend.
 */
export function formatDollars(cents: number | null | undefined): string {
  if (cents === null || cents === undefined) return "—";
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents) / 100;
  return `${sign}$${abs.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function firstOfMonth(d: Date = new Date()): string {
  return new Date(d.getFullYear(), d.getMonth(), 1)
    .toISOString()
    .slice(0, 10);
}

export function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}
