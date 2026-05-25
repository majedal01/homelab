"use client";

import * as React from "react";
import { formatDollars } from "@/lib/utils";
import type { CashflowForecastData } from "@/lib/api-types";

/**
 * Detail view for Cashflow Forecast. Sliders run client-side: the backend
 * payload includes each top category's monthly average, and the user can
 * tweak each by a percentage to see how the projected end balance shifts.
 */
export function CashflowForecastDetail({
  data,
}: {
  data: CashflowForecastData;
}) {
  const [adjustments, setAdjustments] = React.useState<Record<string, number>>(
    () => Object.fromEntries(data.top_spending_categories.map((c) => [keyFor(c), 0])),
  );

  // Each adjustment is a percentage trim of that category's monthly outflow.
  // Trim → savings → bump to projection. Math is daily-net based, so convert
  // monthly savings into a 90-day savings figure.
  const monthlySavings = data.top_spending_categories.reduce((acc, c) => {
    const trimPct = adjustments[keyFor(c)] ?? 0;
    // Monthly average is positive cents spent; trimming saves that much.
    return acc + (c.monthly_average_cents * trimPct) / 100;
  }, 0);

  const ninetyDayBoost = Math.round((monthlySavings * 3));
  const projected90 = data.projected_90d_cents + ninetyDayBoost;

  function update(key: string, value: number): void {
    setAdjustments((prev) => ({ ...prev, [key]: value }));
  }

  const hasCreditDebt = data.credit_card_debt_cents > 0;
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-4">
        <Stat label="Cash today" value={formatDollars(data.starting_balance_cents)} />
        <Stat label="+30d" value={formatDollars(data.projected_30d_cents)} />
        <Stat label="+60d" value={formatDollars(data.projected_60d_cents)} />
        <Stat label="+90d" value={formatDollars(data.projected_90d_cents)} />
      </div>
      {hasCreditDebt ? (
        <div className="rounded-md border bg-muted/40 p-3 text-xs text-muted-foreground">
          Credit card balances total{" "}
          <span className="text-foreground tabular-nums">
            {formatDollars(data.credit_card_debt_cents)}
          </span>{" "}
          — shown separately so the cash projection isn&apos;t masked by revolved debt.
        </div>
      ) : null}
      <div className="rounded-md border bg-card p-4">
        <div className="text-xs uppercase tracking-wide text-muted-foreground">
          What-if (after 90 days)
        </div>
        <div className="mt-1 text-2xl font-semibold tabular-nums">
          {formatDollars(projected90)}
        </div>
        <div className="text-xs text-muted-foreground">
          +{formatDollars(ninetyDayBoost)} vs. baseline if you keep the
          adjustments below.
        </div>
      </div>
      <div className="rounded-md bg-muted/40 p-3 text-xs text-muted-foreground">
        Last {data.lookback_days} days:{" "}
        {formatDollars(data.lookback_income_cents)} in,{" "}
        {formatDollars(data.lookback_spending_cents)} out → daily net{" "}
        {formatDollars(data.daily_net_cents)}.
      </div>
      <div>
        <h2 className="text-sm font-semibold tracking-tight">
          Trim your top spending categories
        </h2>
        <p className="text-xs text-muted-foreground">
          Numbers reflect your last {data.lookback_days}-day monthly average.
        </p>
        <div className="mt-3 space-y-3">
          {data.top_spending_categories.map((c) => {
            const key = keyFor(c);
            const trim = adjustments[key] ?? 0;
            return (
              <div key={key} className="space-y-1">
                <div className="flex items-center justify-between text-sm">
                  <span>{c.category_name}</span>
                  <span className="tabular-nums text-muted-foreground">
                    {formatDollars(c.monthly_average_cents)}/mo · trim {trim}%
                  </span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={50}
                  step={5}
                  value={trim}
                  onChange={(e) => update(key, Number(e.target.value))}
                  className="w-full accent-primary"
                  aria-label={`Trim ${c.category_name}`}
                />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function keyFor(c: { category_id: string | null; category_name: string }): string {
  return c.category_id ?? `name:${c.category_name}`;
}

function Stat({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-md border bg-card p-4">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 text-lg font-semibold tabular-nums">{value}</div>
    </div>
  );
}
