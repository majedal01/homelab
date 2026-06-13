import type { SavingsRatePoint } from "@/lib/api-types";

/**
 * Helpers for the savings-rate bar charts. Bar height is normalized across the
 * data's own range (not pinned to a 0..100% scale) so a trend is visible even
 * when every month is negative; the sign is shown by color instead.
 */

export function rateRange(points: SavingsRatePoint[]): [number, number] {
  const rates = points
    .map((p) => p.savings_rate)
    .filter((r): r is number => r !== null);
  if (rates.length === 0) return [0, 0];
  return [Math.min(...rates), Math.max(...rates)];
}

export function barHeightPct(rate: number | null, min: number, max: number): number {
  if (rate === null) return 6; // faint stub for months with no income
  if (max === min) return 50; // flat series — a mid-height bar reads better than full
  return 6 + ((rate - min) / (max - min)) * 94; // map [min, max] -> 6%..100%
}

export function barColor(rate: number | null): string {
  if (rate === null) return "bg-muted/40";
  return rate < 0 ? "bg-destructive/60" : "bg-primary/70";
}
