import { formatDollars } from "@/lib/utils";
import type { EmergencyFundCoverageData } from "@/lib/api-types";

export function EmergencyFundCoverageCard({ data }: { data: EmergencyFundCoverageData }) {
  const pct = Math.max(0, Math.min(data.coverage_months / data.target_months, 1)) * 100;
  return (
    <div className="space-y-3 text-sm">
      <div className="flex items-end justify-between">
        <div>
          <div className="text-xs uppercase tracking-wide text-muted-foreground">Coverage</div>
          <div className="mt-1 text-2xl font-semibold tabular-nums">
            {data.coverage_months.toFixed(1)} mo
          </div>
        </div>
        <div className="text-right text-xs text-muted-foreground">
          target {data.target_months} mo
        </div>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
      </div>
      <div className="text-xs text-muted-foreground">
        {formatDollars(data.cash_balance_cents)} cash ·{" "}
        {formatDollars(data.avg_monthly_spending_cents)}/mo spend
      </div>
    </div>
  );
}
