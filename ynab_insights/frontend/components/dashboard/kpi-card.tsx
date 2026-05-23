"use client";

import * as React from "react";
import { motion } from "motion/react";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import type { DeltaInfo } from "@/lib/metrics";

export interface KpiCardProps {
  label: string;
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
}: KpiCardProps) {
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
          <span
            className={cn(
              "font-mono text-3xl font-semibold tabular-nums",
              valueClassName,
            )}
          >
            {value}
          </span>
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
