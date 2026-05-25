"use client";

import * as React from "react";
import { LineChart } from "@tremor/react";

import { cn } from "@/lib/utils";
import { formatDollars } from "@/lib/utils";
import type { CategoryDriftData } from "@/lib/api-types";

/**
 * Detail view: quarterly trend chart over 12 months + summary cards.
 * Transactions list is deferred (the existing transactions endpoint can
 * be linked to with a category_id filter, which the chart caption does).
 */
export function CategoryDriftDetail({ data }: { data: CategoryDriftData }) {
  const isUp = data.direction === "up";
  const pct = `${isUp ? "+" : "−"}${Math.round(Math.abs(data.drift_pct) * 100)}%`;
  const isYoY = data.comparison_kind === "year_over_year";
  const driftLabel = isYoY ? "Drift vs same period last year" : "Drift vs prior 9 months";
  const priorLabel = isYoY ? "Same period, last year" : "Prior 9 months avg";

  const chartData = React.useMemo(() => {
    const labels = ["−11m", "−10m", "−9m", "−8m", "−7m", "−6m", "−5m", "−4m", "−3m", "−2m", "−1m", "now"];
    return data.monthly_nets_cents.map((cents, i) => ({
      month: labels[i] ?? `t-${i}`,
      Spend: cents / 100,
    }));
  }, [data.monthly_nets_cents]);

  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-3">
        <Stat
          label={driftLabel}
          value={pct}
          tone={isUp ? "destructive" : "positive"}
        />
        <Stat
          label="Trailing quarter avg"
          value={`${formatDollars(data.trailing_quarter_avg_cents)} /mo`}
        />
        <Stat
          label={priorLabel}
          value={`${formatDollars(data.prior_three_quarters_avg_cents)} /mo`}
        />
      </div>

      <div className="rounded-md border bg-card p-4">
        <div className="text-xs uppercase tracking-wide text-muted-foreground">
          Monthly net, last 12 months
        </div>
        <LineChart
          data={chartData}
          index="month"
          categories={["Spend"]}
          colors={[isUp ? "rose" : "emerald"]}
          valueFormatter={(v) => `$${v.toFixed(0)}`}
          showLegend={false}
          className="mt-2 h-56"
        />
      </div>

    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "destructive" | "positive";
}) {
  return (
    <div className="rounded-md border bg-card p-4">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div
        className={cn(
          "mt-1 font-mono text-lg font-semibold tabular-nums",
          tone === "destructive" && "text-destructive",
          tone === "positive" && "text-emerald-600 dark:text-emerald-400",
        )}
      >
        {value}
      </div>
    </div>
  );
}
