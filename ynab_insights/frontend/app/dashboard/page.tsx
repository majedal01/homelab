import Link from "next/link";
import { Wallet } from "lucide-react";

import { apiFetch, getSelectedBudgetId, qs } from "@/lib/api";
import type {
  AccountResponse,
  BudgetResponse,
  MonthlyTrendResponse,
  PeriodSummaryResponse,
  TransactionResponse,
} from "@/lib/api-types";
import { formatDollars } from "@/lib/utils";
import {
  compareValues,
  currentMonth,
  monthBounds,
  monthLabel,
  monthsWindow,
  netWorth,
  savingsRate,
  type CategorySpendRow,
  type MonthlyTrendPoint,
} from "@/lib/metrics";
import { DateRangePicker } from "@/components/date-range-picker";
import { KpiCard } from "@/components/dashboard/kpi-card";
import { SpendingTrendChart } from "@/components/dashboard/spending-trend-chart";
import { CategoryDonutCard } from "@/components/dashboard/category-donut-card";
import { RecentTransactionsCard } from "@/components/dashboard/recent-transactions-card";
import { EmptyState } from "@/components/empty";

export const dynamic = "force-dynamic";

interface DashboardSearchParams {
  date_from?: string;
  date_to?: string;
}

function isoDaysBetween(fromIso: string, toIso: string): number {
  // Inclusive day count.
  const from = new Date(`${fromIso}T00:00:00Z`).getTime();
  const to = new Date(`${toIso}T00:00:00Z`).getTime();
  return Math.max(1, Math.round((to - from) / 86_400_000) + 1);
}

function shiftIsoDate(iso: string, deltaDays: number): string {
  const base = new Date(`${iso}T00:00:00Z`);
  base.setUTCDate(base.getUTCDate() + deltaDays);
  return base.toISOString().slice(0, 10);
}

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

/**
 * Picks the comparison window for the delta arrows. When the user has
 * "this month" selected (range = full calendar month), compare against the
 * prior calendar month so YNAB-trained eyes see "May vs April" rather
 * than "May vs Mar 31 – Apr 30". For any other range, fall back to the
 * same-length window immediately preceding the selection.
 */
function prevPeriodBounds(
  dateFrom: string,
  dateTo: string,
): { from: string; to: string } {
  const from = new Date(`${dateFrom}T00:00:00Z`);
  const to = new Date(`${dateTo}T00:00:00Z`);
  const fromIsFirst = from.getUTCDate() === 1;
  const toIsLast =
    new Date(
      Date.UTC(to.getUTCFullYear(), to.getUTCMonth() + 1, 0),
    ).getUTCDate() === to.getUTCDate();
  const sameMonth =
    from.getUTCFullYear() === to.getUTCFullYear() &&
    from.getUTCMonth() === to.getUTCMonth();
  if (fromIsFirst && toIsLast && sameMonth) {
    const prevMonthStart = new Date(
      Date.UTC(from.getUTCFullYear(), from.getUTCMonth() - 1, 1),
    );
    const prevMonthEnd = new Date(
      Date.UTC(from.getUTCFullYear(), from.getUTCMonth(), 0),
    );
    return { from: isoDate(prevMonthStart), to: isoDate(prevMonthEnd) };
  }
  const rangeDays = isoDaysBetween(dateFrom, dateTo);
  const prevTo = shiftIsoDate(dateFrom, -1);
  const prevFrom = shiftIsoDate(prevTo, -(rangeDays - 1));
  return { from: prevFrom, to: prevTo };
}

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<DashboardSearchParams>;
}) {
  const params = await searchParams;
  const budgets = await apiFetch<BudgetResponse[]>("/budgets");

  if (!budgets.length) {
    return (
      <EmptyState
        icon={Wallet}
        title="No budgets yet"
        description="Trigger a sync to pull your YNAB budgets into the dashboard."
        action={{ href: "/ask", label: "Ask the agent how to sync" }}
      />
    );
  }

  const selected = (await getSelectedBudgetId(budgets)) ?? budgets[0].id;

  // Default range is this month; the picker writes date_from/date_to into
  // the URL which we honor for every flow-based card on the page (KPIs +
  // donut). Net worth is a balance, not a flow, so it ignores the range.
  const thisMonthBounds = monthBounds(currentMonth());
  const dateFrom = params.date_from ?? thisMonthBounds.from;
  const dateTo = params.date_to ?? thisMonthBounds.to;

  // Comparison period: prior calendar month when the user picked a full
  // month (so "May" compares cleanly against "April"), otherwise the
  // immediately-prior same-length window.
  const { from: prevDateFrom, to: prevDateTo } = prevPeriodBounds(
    dateFrom,
    dateTo,
  );

  // Trend chart always shows the trailing 12 months ending in the current
  // month — independent of the picker, so the user can see the macro shape
  // even while zoomed in on a narrow range.
  const now = currentMonth();

  const [accounts, recentTxns, summary, prevSummary, trendResponse] = await Promise.all([
    apiFetch<AccountResponse[]>(`/accounts${qs({ budget_id: selected })}`),
    apiFetch<TransactionResponse[]>(
      `/transactions${qs({ budget_id: selected, limit: 10 })}`,
    ),
    apiFetch<PeriodSummaryResponse>(
      `/reports/period-summary${qs({
        budget_id: selected,
        date_from: dateFrom,
        date_to: dateTo,
      })}`,
    ),
    apiFetch<PeriodSummaryResponse>(
      `/reports/period-summary${qs({
        budget_id: selected,
        date_from: prevDateFrom,
        date_to: prevDateTo,
      })}`,
    ),
    apiFetch<MonthlyTrendResponse>(
      `/reports/monthly-spending${qs({ budget_id: selected, months: 12 })}`,
    ),
  ]);

  const netWorthCents = netWorth(accounts);

  // KPIs are now driven entirely by the server-side period summary so they
  // (a) honor the date picker and (b) match the donut total below by
  // construction (same query, same row set).
  const spendingNow = summary.spending_cents;
  const incomeNow = summary.income_cents;
  const spendingPrev = prevSummary.spending_cents;
  const incomePrev = prevSummary.income_cents;
  const surplusNow = summary.net_income_cents;
  const surplusPrev = prevSummary.net_income_cents;
  const savingsNow = savingsRate(incomeNow, spendingNow);
  const savingsPrev = savingsRate(incomePrev, spendingPrev);

  const netWorthDelta = null;
  const spendingDelta = compareValues(spendingNow, spendingPrev, false);
  const surplusDelta = compareValues(surplusNow, surplusPrev, true);
  const savingsDelta =
    savingsNow !== null && savingsPrev !== null
      ? compareValues(savingsNow, savingsPrev, true)
      : null;

  // Trend chart: backend monthly aggregates, no 500-limit risk.
  const trendMonths = monthsWindow(now, 12);
  const trendByKey = new Map(
    trendResponse.points.map((p) => [`${p.year}-${p.month}`, p]),
  );
  const trendPoints: MonthlyTrendPoint[] = trendMonths.map((ym) => {
    const row = trendByKey.get(`${ym.year}-${ym.month + 1}`);
    return {
      month: monthLabel(ym),
      yearMonth: ym,
      spending: row?.spending_cents ?? 0,
      income: row?.income_cents ?? 0,
    };
  });

  // Donut shares the period summary's by-category breakdown so the slice
  // total equals the spending KPI. Positive-net (refund) categories are
  // omitted from the slice list since a pie can't render negative values;
  // refunds still show on the Categories page.
  const donutRows: CategorySpendRow[] = summary.by_category
    .map((row) => ({
      category_id: row.category_id,
      category_name: row.category_name,
      spent_cents: -row.net_cents, // net negative → positive spend, net positive → negative
    }))
    .filter((r) => r.spent_cents > 0)
    .sort((a, b) => b.spent_cents - a.spent_cents);
  const donutRangeLabel = `${dateFrom} → ${dateTo}`;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            The numbers, for the selected range.
          </p>
        </div>
        <DateRangePicker />
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          label="Net worth"
          value={formatDollars(netWorthCents)}
          numericValue={netWorthCents}
          formatAnimated={formatDollars}
          delta={netWorthDelta}
          deltaLabel="across all open accounts"
          index={0}
          valueClassName={netWorthCents < 0 ? "text-destructive" : undefined}
        />
        <KpiCard
          label="Spending"
          value={formatDollars(spendingNow)}
          numericValue={spendingNow}
          formatAnimated={formatDollars}
          delta={spendingDelta}
          deltaLabel="vs prior period"
          index={1}
        />
        <KpiCard
          label="Income minus spending"
          value={`${surplusNow >= 0 ? "" : "-"}${formatDollars(Math.abs(surplusNow))}`}
          numericValue={surplusNow}
          formatAnimated={(v) =>
            `${v >= 0 ? "" : "-"}${formatDollars(Math.abs(v))}`
          }
          delta={surplusDelta}
          deltaLabel="vs prior period"
          index={2}
          valueClassName={surplusNow < 0 ? "text-destructive" : undefined}
        />
        <KpiCard
          label="Savings rate"
          value={savingsNow === null ? "—" : `${(savingsNow * 100).toFixed(0)}%`}
          numericValue={
            savingsNow === null ? undefined : Math.round(savingsNow * 100)
          }
          formatAnimated={(v) => `${v}%`}
          delta={savingsDelta}
          deltaLabel="vs prior period"
          index={3}
        />
      </div>

      <SpendingTrendChart points={trendPoints} />

      <div className="grid gap-6 lg:grid-cols-2">
        <CategoryDonutCard
          rows={donutRows}
          rangeLabel={donutRangeLabel}
          totalCentsOverride={summary.spending_cents}
        />
        <RecentTransactionsCard transactions={recentTxns} />
      </div>

      <p className="text-center text-xs text-muted-foreground">
        Mirrors YNAB&apos;s{" "}
        <Link
          href="https://github.com/majedal01/homelab/blob/main/ynab_insights/DESIGN.md"
          className="underline"
        >
          Income vs. Expense report
        </Link>
        .
      </p>
    </div>
  );
}
