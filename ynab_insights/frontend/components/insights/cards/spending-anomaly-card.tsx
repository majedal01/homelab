import { TrendingDown, TrendingUp } from "lucide-react";
import { formatDollars } from "@/lib/utils";
import type { SpendingAnomalyData } from "@/lib/api-types";

export function SpendingAnomalyCard({
  data,
}: {
  data: SpendingAnomalyData;
}) {
  const isUp = data.z_score > 0;
  const pct = Math.abs(data.deviation_ratio) * 100;
  return (
    <div className="grid grid-cols-2 gap-4 text-sm">
      <div>
        <div className="text-xs uppercase tracking-wide text-muted-foreground">
          This week
        </div>
        <div className="mt-1 flex items-baseline gap-2">
          <span className="text-2xl font-semibold tabular-nums">
            {formatDollars(data.current_week_spend_cents)}
          </span>
          {isUp ? (
            <TrendingUp className="h-4 w-4 text-destructive" />
          ) : (
            <TrendingDown className="h-4 w-4 text-emerald-600" />
          )}
        </div>
      </div>
      <div>
        <div className="text-xs uppercase tracking-wide text-muted-foreground">
          12-week average
        </div>
        <div className="mt-1 text-lg font-medium tabular-nums text-muted-foreground">
          {formatDollars(data.baseline_mean_cents)}
        </div>
      </div>
      <div className="col-span-2 text-xs text-muted-foreground">
        {pct.toFixed(0)}% {isUp ? "above" : "below"} typical · z = {data.z_score.toFixed(1)}
      </div>
    </div>
  );
}
