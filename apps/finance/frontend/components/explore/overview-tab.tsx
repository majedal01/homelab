"use client";

import { AreaChart, DonutChart, Legend } from "@tremor/react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type {
  MonthlyTrendPointResponse,
  OverviewKPIs,
  PeriodSummaryResponse,
} from "@/lib/api-types";

export function OverviewTab({
  kpis,
  trend,
  summary,
}: {
  kpis: OverviewKPIs | null;
  trend: MonthlyTrendPointResponse[];
  summary: PeriodSummaryResponse | null;
}) {
  if (kpis === null) {
    return (
      <p className="rounded-md border bg-card/60 backdrop-blur p-4 text-sm text-muted-foreground">
        Couldn&apos;t load overview. Refresh from Settings to retry.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-3 md:grid-cols-4">
        <Kpi label="Net worth" cents={kpis.net_worth_cents} signed />
        <Kpi label="Income this month" cents={kpis.this_month_income_cents} />
        <Kpi label="Spending this month" cents={kpis.this_month_spending_cents} />
        <Kpi
          label="Net this month"
          cents={kpis.this_month_net_cents}
          signed
          tone={kpis.this_month_net_cents >= 0 ? "positive" : "negative"}
          subValue={
            kpis.savings_rate !== null
              ? `${Math.round(kpis.savings_rate * 100)}% savings rate`
              : undefined
          }
        />
      </div>

      <Card>
        <CardContent className="p-5">
          <h2 className="text-sm font-medium">12-month trend</h2>
          <p className="text-xs text-muted-foreground">Income vs spending per month.</p>
          {trend.length > 0 ? (
            <AreaChart
              data={trend.map((p) => ({
                month: `${monthAbbr(p.month)} ${String(p.year).slice(2)}`,
                Income: p.income_cents / 100,
                Spending: p.spending_cents / 100,
              }))}
              index="month"
              categories={["Income", "Spending"]}
              colors={["emerald", "rose"]}
              valueFormatter={(v) => `$${shortMoney(v)}`}
              showLegend={false}
              showAnimation
              className="mt-3 h-56"
            />
          ) : (
            <p className="mt-3 text-sm text-muted-foreground">No transactions in range.</p>
          )}
        </CardContent>
      </Card>

      {summary && summary.by_category.length > 0 && (
        <Card>
          <CardContent className="p-5">
            <h2 className="text-sm font-medium">Where this month went</h2>
            <p className="text-xs text-muted-foreground">
              Net spending per category, on-budget only.
            </p>
            <div className="mt-3 grid items-start gap-3 md:grid-cols-[1fr_auto]">
              <DonutChart
                data={summary.by_category
                  .filter((c) => c.net_cents < 0)
                  .slice(0, 8)
                  .map((c) => ({
                    name: c.category_name ?? "Uncategorized",
                    value: Math.round(-c.net_cents / 100),
                  }))}
                category="value"
                index="name"
                valueFormatter={(v) => `$${shortMoney(v)}`}
                colors={["indigo", "violet", "cyan", "emerald", "amber", "rose", "slate", "fuchsia"]}
                className="h-48"
                showAnimation
              />
              <Legend
                categories={summary.by_category
                  .filter((c) => c.net_cents < 0)
                  .slice(0, 8)
                  .map((c) => c.category_name ?? "Uncategorized")}
                colors={["indigo", "violet", "cyan", "emerald", "amber", "rose", "slate", "fuchsia"]}
                className="max-w-[14rem] flex-wrap"
              />
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function Kpi({
  label,
  cents,
  signed,
  tone,
  subValue,
}: {
  label: string;
  cents: number;
  signed?: boolean;
  tone?: "positive" | "negative";
  subValue?: string;
}) {
  const display = formatDollars(cents, { signed });
  return (
    <Card>
      <CardContent className="p-5">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </p>
        <p
          className={cn(
            "mt-1 text-2xl font-semibold tabular-nums tracking-tight",
            tone === "positive" && "text-emerald-600 dark:text-emerald-400",
            tone === "negative" && "text-rose-600 dark:text-rose-400",
          )}
        >
          {display}
        </p>
        {subValue && (
          <p className="mt-0.5 text-xs text-muted-foreground">{subValue}</p>
        )}
      </CardContent>
    </Card>
  );
}

function formatDollars(cents: number, opts: { signed?: boolean } = {}): string {
  const dollars = cents / 100;
  const abs = Math.abs(dollars);
  const sign = dollars < 0 ? "-" : opts.signed && dollars > 0 ? "+" : "";
  return `${sign}$${abs.toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })}`;
}

function shortMoney(dollars: number): string {
  const abs = Math.abs(dollars);
  if (abs >= 1_000_000) return `${(dollars / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${(dollars / 1_000).toFixed(1)}K`;
  return dollars.toFixed(0);
}

function monthAbbr(m: number): string {
  return ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][
    m - 1
  ];
}
