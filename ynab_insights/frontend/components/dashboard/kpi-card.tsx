"use client";

import * as React from "react";
import { motion } from "motion/react";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

import { cn, formatDollars } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { CountUp } from "@/components/brand/count-up";
import type { DeltaInfo } from "@/lib/metrics";

/**
 * Format mode for the animated value. Passed as a string discriminator
 * (rather than a `(v) => string` callback) so the dashboard server
 * component can supply it without violating the RSC rule that bans
 * functions in client-component props.
 */
export type KpiFormat = "dollars" | "signed-dollars" | "percent";

const FORMATTERS: Record<KpiFormat, (v: number) => string> = {
  dollars: (v) => formatDollars(v),
  "signed-dollars": (v) =>
    `${v >= 0 ? "" : "-"}${formatDollars(Math.abs(v))}`,
  percent: (v) => `${v}%`,
};

export interface KpiCardProps {
  label: string;
  /** Pre-formatted display string. Required so the SSR pass renders the
   * final value with no flicker before the count-up takes over. */
  value: string;
  delta?: DeltaInfo | null;
  /**
   * Caption appearing below the delta, e.g. "vs last month". Hidden when
   * delta is null.
   */
  deltaLabel?: string;
  /** Index in the stagger sequence. */
  index?: number;
  /** Override the value's color (rarely needed). */
  valueClassName?: string;
  /**
   * Optional numeric counterpart that enables the count-up animation. When
   * provided alongside `format`, the card tweens 0 → numericValue once on
   * first viewport entry. Otherwise the static `value` renders.
   */
  numericValue?: number;
  format?: KpiFormat;
}

const directionStyles: Record<NonNullable<DeltaInfo["direction"]>, string> = {
  improved: "text-emerald-600 dark:text-emerald-400",
  worsened: "text-destructive",
  neutral: "text-muted-foreground",
};

function DirectionIcon({ direction }: { direction: DeltaInfo["direction"] }) {
  if (direction === "improved") return <ArrowUpRight className="h-3.5 w-3.5" />;
  if (direction === "worsened") return <ArrowDownRight className="h-3.5 w-3.5" />;
  return <Minus className="h-3.5 w-3.5" />;
}

function formatPct(pct: number | null): string {
  if (pct === null) return "—";
  const sign = pct > 0 ? "+" : "";
  return `${sign}${(pct * 100).toFixed(1)}%`;
}

export function KpiCard({
  label,
  value,
  delta,
  deltaLabel = "vs last month",
  index = 0,
  valueClassName,
  numericValue,
  format,
}: KpiCardProps) {
  const formatter = format ? FORMATTERS[format] : undefined;
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: index * 0.06, ease: "easeOut" }}
    >
      <Card className="h-full">
        <CardContent className="flex flex-col gap-2 p-6">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {label}
          </span>
          {numericValue !== undefined && formatter ? (
            <CountUp
              value={numericValue}
              format={formatter}
              className={cn(
                "font-mono text-3xl font-semibold tabular-nums",
                valueClassName,
              )}
            />
          ) : (
            <span
              className={cn(
                "font-mono text-3xl font-semibold tabular-nums",
                valueClassName,
              )}
            >
              {value}
            </span>
          )}
          {delta ? (
            <div
              className={cn(
                "inline-flex items-center gap-1 text-xs",
                directionStyles[delta.direction],
              )}
            >
              <DirectionIcon direction={delta.direction} />
              <span className="tabular-nums">{formatPct(delta.pct)}</span>
              <span className="text-muted-foreground">{deltaLabel}</span>
            </div>
          ) : (
            <span className="text-xs text-muted-foreground">{deltaLabel}</span>
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
}
