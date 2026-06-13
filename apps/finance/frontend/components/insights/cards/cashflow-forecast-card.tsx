import { formatDollars } from "@/lib/utils";
import type { CashflowForecastData } from "@/lib/api-types";

function Tick({
  label,
  value,
}: {
  label: string;
  value: number;
}) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 text-base font-semibold tabular-nums">
        {formatDollars(value)}
      </div>
    </div>
  );
}

export function CashflowForecastCard({
  data,
}: {
  data: CashflowForecastData;
}) {
  const hasCreditDebt = data.credit_card_debt_cents > 0;
  return (
    <div className="space-y-3 text-sm">
      <div>
        <div className="text-xs uppercase tracking-wide text-muted-foreground">
          Cash today
        </div>
        <div className="mt-1 text-2xl font-semibold tabular-nums">
          {formatDollars(data.starting_balance_cents)}
        </div>
        {hasCreditDebt ? (
          <div className="mt-1 text-xs text-muted-foreground tabular-nums">
            Credit card debt {formatDollars(data.credit_card_debt_cents)}
          </div>
        ) : null}
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Tick label="+30d" value={data.projected_30d_cents} />
        <Tick label="+60d" value={data.projected_60d_cents} />
        <Tick label="+90d" value={data.projected_90d_cents} />
      </div>
      <div className="text-xs text-muted-foreground">
        Based on last {data.lookback_days} days · {formatDollars(data.daily_net_cents)}/day net
      </div>
    </div>
  );
}
