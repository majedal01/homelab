import type { SavingsRateTrendData } from "@/lib/api-types";

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
  return (
    <div className="flex h-10 items-end gap-0.5" aria-hidden>
      {points.map((p, i) => {
        const rate = p.savings_rate;
        if (rate === null) {
          return <div key={i} className="flex-1 rounded-sm bg-muted/40" style={{ height: "8%" }} />;
        }
        const height = Math.max(4, Math.min(rate, 1) * 100);
        const color = rate < 0 ? "bg-destructive/60" : "bg-primary/70";
        return (
          <div
            key={i}
            className={`flex-1 rounded-sm ${color}`}
            style={{ height: `${height}%` }}
          />
        );
      })}
    </div>
  );
}
