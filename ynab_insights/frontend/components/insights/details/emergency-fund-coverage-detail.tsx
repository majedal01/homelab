import { formatDollars } from "@/lib/utils";
import type { EmergencyFundCoverageData } from "@/lib/api-types";

export function EmergencyFundCoverageDetail({ data }: { data: EmergencyFundCoverageData }) {
  const pct = Math.max(0, Math.min(data.coverage_months / data.target_months, 1)) * 100;
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <Stat label="Coverage" value={`${data.coverage_months.toFixed(1)} months`} />
        <Stat label="Liquid cash" value={formatDollars(data.cash_balance_cents)} />
        <Stat label="Avg monthly spend" value={`${formatDollars(data.avg_monthly_spending_cents)}/mo`} />
      </div>
      <div className="rounded-md border bg-card p-4">
        <div className="flex items-center justify-between text-xs uppercase tracking-wide text-muted-foreground">
          <span>Progress to {data.target_months}-month target</span>
          <span className="tabular-nums">{Math.round(pct)}%</span>
        </div>
        <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-muted">
          <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        Coverage is your liquid cash (checking, savings, and cash accounts) divided by
        average monthly spending over the last {data.months_of_history} complete months.
        Configured YNAB goals are not required.
      </p>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border bg-card p-4">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-1 text-lg font-semibold tabular-nums">{value}</div>
    </div>
  );
}
