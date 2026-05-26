import { formatDollars } from "@/lib/utils";
import type { DebtPayoffData } from "@/lib/api-types";

export function DebtPayoffCard({ data }: { data: DebtPayoffData }) {
  return (
    <div className="grid grid-cols-2 gap-4 text-sm">
      <div>
        <div className="text-xs uppercase tracking-wide text-muted-foreground">
          Current debt
        </div>
        <div className="mt-1 text-2xl font-semibold tabular-nums">
          {formatDollars(data.current_debt_cents)}
        </div>
      </div>
      <div>
        <div className="text-xs uppercase tracking-wide text-muted-foreground">
          Avg paydown
        </div>
        <div className="mt-1 text-lg font-medium tabular-nums text-muted-foreground">
          {formatDollars(data.avg_monthly_paydown_cents)}/mo
        </div>
      </div>
      <div className="col-span-2 text-xs text-muted-foreground">
        At this pace, paid off by {data.projected_payoff_date} ·{" "}
        {data.projected_months_to_payoff} months
      </div>
    </div>
  );
}
