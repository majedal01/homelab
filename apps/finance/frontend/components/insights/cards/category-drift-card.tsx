import { TrendingDown, TrendingUp } from "lucide-react";

import { cn } from "@/lib/utils";
import { formatDollars } from "@/lib/utils";
import type { CategoryDriftData } from "@/lib/api-types";

/**
 * Compact card view for Category Drift. Drift % in hero position; dollar
 * impact muted. 12-point sparkline traces the monthly nets oldest → newest.
 */
export function CategoryDriftCard({ data }: { data: CategoryDriftData }) {
  const isUp = data.direction === "up";
  const pct = `${isUp ? "+" : "−"}${Math.round(Math.abs(data.drift_pct) * 100)}%`;
  const sparklineMax = Math.max(...data.monthly_nets_cents, 1);
  const sparklineW = 120;
  const sparklineH = 32;
  const points = data.monthly_nets_cents
    .map((v, i, arr) => {
      const x = (i / Math.max(1, arr.length - 1)) * sparklineW;
      const y = sparklineH - (v / sparklineMax) * sparklineH;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <div className="grid grid-cols-[1fr_auto] gap-4 text-sm">
      <div>
        <div className="text-xs uppercase tracking-wide text-muted-foreground">
          Drift vs prior year
        </div>
        <div className="mt-1 flex items-baseline gap-2">
          <span
            className={cn(
              "font-mono text-2xl font-semibold tabular-nums",
              isUp ? "text-destructive" : "text-emerald-600 dark:text-emerald-400",
            )}
          >
            {pct}
          </span>
          {isUp ? (
            <TrendingUp className="h-4 w-4 text-destructive" />
          ) : (
            <TrendingDown className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
          )}
        </div>
        <div className="mt-1 text-xs text-muted-foreground">
          {isUp ? "+" : "−"}
          {formatDollars(Math.abs(data.drift_cents_per_month))}/mo over the
          trailing quarter
        </div>
      </div>
      <svg
        viewBox={`0 0 ${sparklineW} ${sparklineH}`}
        width={sparklineW}
        height={sparklineH}
        className="self-end opacity-80"
        aria-hidden
      >
        <polyline
          points={points}
          fill="none"
          stroke="currentColor"
          strokeWidth={1.5}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      </svg>
    </div>
  );
}
