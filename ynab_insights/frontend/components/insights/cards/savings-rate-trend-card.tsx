import type { SavingsRateTrendData } from "@/lib/api-types";
import { barColor, barHeightPct, rateRange } from "@/lib/savings-rate";

const DIRECTION_LABEL: Record<SavingsRateTrendData["direction"], string> = {
  up: "trending up",
  down: "trending down",
  flat: "holding steady",
};

function pctLabel(rate: number | null): string {
  return rate === null ? "—" : `${Math.round(rate * 100)}%`;
}

export function SavingsRateTrendCard({ data }: { data: SavingsRateTrendData }) {
  return (
    <div className="space-y-3 text-sm">
      <div className="flex items-end justify-between">
        <div>
          <div className="text-xs uppercase tracking-wide text-muted-foreground">
            Latest month
          </div>
          <div className="mt-1 text-2xl font-semibold tabular-nums">
            {pctLabel(data.latest_savings_rate)}
          </div>
        </div>
        <div className="text-right text-xs text-muted-foreground">
          avg {pctLabel(data.average_savings_rate)} · {DIRECTION_LABEL[data.direction]}
        </div>
      </div>
      <SavingsSparkline points={data.points} />
    </div>
  );
}

function SavingsSparkline({ points }: { points: SavingsRateTrendData["points"] }) {
  // Normalize bar heights across the actual data range so the trend is visible
  // even when every month is negative (a flat row of floored bars otherwise);
  // sign is conveyed by color, not height.
  const [min, max] = rateRange(points);
  return (
    <div className="flex h-10 items-end gap-0.5" aria-hidden>
      {points.map((p, i) => (
        <div
          key={i}
          className={`flex-1 rounded-sm ${barColor(p.savings_rate)}`}
          style={{ height: `${barHeightPct(p.savings_rate, min, max)}%` }}
        />
      ))}
    </div>
  );
}
