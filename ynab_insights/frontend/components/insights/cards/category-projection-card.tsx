import { TrendingDown, TrendingUp } from "lucide-react";
import { formatDollars } from "@/lib/utils";
import type { CategoryProjectionData } from "@/lib/api-types";

export function CategoryProjectionCard({
  data,
}: {
  data: CategoryProjectionData;
}) {
  const isOver = data.direction === "over";
  const pct = Math.abs(data.delta_pct) * 100;
  return (
    <div className="grid grid-cols-2 gap-4 text-sm">
      <div>
        <div className="text-xs uppercase tracking-wide text-muted-foreground">
          Projected month-end
        </div>
        <div className="mt-1 flex items-baseline gap-2">
          <span className="text-2xl font-semibold tabular-nums">
            {formatDollars(data.projected_month_end_cents)}
          </span>
          {isOver ? (
            <TrendingUp className="h-4 w-4 text-destructive" />
          ) : (
            <TrendingDown className="h-4 w-4 text-emerald-600" />
          )}
        </div>
      </div>
      <div>
        <div className="text-xs uppercase tracking-wide text-muted-foreground">
          12mo average
        </div>
        <div className="mt-1 text-lg font-medium tabular-nums text-muted-foreground">
          {formatDollars(data.baseline_monthly_avg_cents)}
        </div>
      </div>
      <div className="col-span-2 text-xs text-muted-foreground">
        {pct.toFixed(0)}% {isOver ? "over" : "under"} typical · day{" "}
        {data.days_into_month} of {data.days_in_month}
      </div>
    </div>
  );
}
