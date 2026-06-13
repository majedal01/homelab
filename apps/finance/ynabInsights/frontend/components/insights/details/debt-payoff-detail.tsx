"use client";

import * as React from "react";
import { formatDollars } from "@/lib/utils";
import type { DebtPayoffData } from "@/lib/api-types";

/**
 * Detail view for Debt Payoff. The slider models accelerated paydown:
 * the user picks an additional $X/month on top of their current pace,
 * and we recompute the projected payoff date.
 */
export function DebtPayoffDetail({ data }: { data: DebtPayoffData }) {
  const [extra, setExtra] = React.useState(0);

  const acceleratedMonthly = data.avg_monthly_paydown_cents + extra * 100;
  const acceleratedMonths =
    acceleratedMonthly > 0
      ? Math.ceil(data.current_debt_cents / acceleratedMonthly)
      : data.projected_months_to_payoff;
  const acceleratedSavedMonths = Math.max(
    data.projected_months_to_payoff - acceleratedMonths,
    0,
  );

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-4">
        <Stat label="Current debt" value={formatDollars(data.current_debt_cents)} />
        <Stat
          label="Monthly paydown"
          value={`${formatDollars(data.avg_monthly_paydown_cents)}/mo`}
        />
        <Stat
          label="Projected payoff"
          value={data.projected_payoff_date}
        />
        <Stat
          label="Months to payoff"
          value={`${data.projected_months_to_payoff} mo`}
        />
      </div>
      <div className="rounded-md border bg-card p-4">
        <div className="text-xs uppercase tracking-wide text-muted-foreground">
          What-if: add to monthly paydown
        </div>
        <div className="mt-2 flex items-center gap-3 text-sm">
          <input
            type="range"
            min={0}
            max={500}
            step={25}
            value={extra}
            onChange={(e) => setExtra(Number(e.target.value))}
            className="w-full accent-primary"
            aria-label="Extra monthly paydown"
          />
          <span className="tabular-nums">+${extra}/mo</span>
        </div>
        <div className="mt-2 text-sm text-muted-foreground">
          Accelerated payoff: {acceleratedMonths} months ({acceleratedSavedMonths}{" "}
          months sooner at +${extra}/mo)
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        Based on average paydown over the last {data.lookback_months} months for{" "}
        <span className="text-foreground">{data.account_name}</span>.
      </p>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border bg-card p-4">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 text-lg font-semibold tabular-nums">{value}</div>
    </div>
  );
}
