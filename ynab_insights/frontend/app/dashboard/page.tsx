import Link from "next/link";
import { Wallet } from "lucide-react";

import { apiFetch, getSelectedBudgetId, qs } from "@/lib/api";
import type {
  AccountResponse,
  BudgetResponse,
  MonthlyTrendResponse,
  TransactionResponse,
} from "@/lib/api-types";
import { formatDollars } from "@/lib/utils";
import {
  categoryBreakdown,
  compareValues,
  currentMonth,
  incomeFromTransactions,
  monthBounds,
  monthLabel,
  monthsWindow,
  netWorth,
  onBudgetAccountIdSet,
  previousMonth,
  savingsRate,
  spendingFromTransactions,
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

  const now = currentMonth();
  const last = previousMonth(now);
  const thisMonthBounds = monthBounds(now);
  const lastMonthBounds = monthBounds(last);

  // Donut respects the URL date range when set; otherwise uses this-month.
  // KPIs always reflect this-month-vs-last-month for stable comparability.
  const donutFrom = params.date_from ?? thisMonthBounds.from;
  const donutTo = params.date_to ?? thisMonthBounds.to;

  // The trend chart spans 12 months — too many transactions to roll up
  // client-side under the `/transactions?limit=500` cap. Fetched as a
  // pre-aggregated series so the response size is bounded by months.
  const [accounts, recentTxns, thisMonthTxns, lastMonthTxns, trendResponse, donutTxns] =
    await Promise.all([
      apiFetch<AccountResponse[]>(`/accounts${qs({ budget_id: selected })}`),
      apiFetch<TransactionResponse[]>(
        `/transactions${qs({ budget_id: selected, limit: 10 })}`,
      ),
      apiFetch<TransactionResponse[]>(
        `/transactions${qs({
          budget_id: selected,
          date_from: thisMonthBounds.from,
          date_to: thisMonthBounds.to,
          limit: 500,
        })}`,
      ),
      apiFetch<TransactionResponse[]>(
        `/transactions${qs({
          budget_id: selected,
          date_from: lastMonthBounds.from,
          date_to: lastMonthBounds.to,
          limit: 500,
        })}`,
      ),
      apiFetch<MonthlyTrendResponse>(
        `/reports/monthly-spending${qs({ budget_id: selected, months: 12 })}`,
      ),
      params.date_from || params.date_to
        ? apiFetch<TransactionResponse[]>(
            `/transactions${qs({
              budget_id: selected,
              date_from: donutFrom,
              date_to: donutTo,
              limit: 500,
            })}`,
          )
        : Promise.resolve(null as TransactionResponse[] | null),
    ]);

  const onBudgetIds = onBudgetAccountIdSet(accounts);

  const netWorthCents = netWorth(accounts);
  const spendingThis = spendingFromTransactions(thisMonthTxns, onBudgetIds);
  const incomeThis = incomeFromTransactions(thisMonthTxns, onBudgetIds);
  const spendingLast = spendingFromTransactions(lastMonthTxns, onBudgetIds);
  const incomeLast = incomeFromTransactions(lastMonthTxns, onBudgetIds);

  const surplusThis = incomeThis - spendingThis;
  const surplusLast = incomeLast - spendingLast;

  const savingsThis = savingsRate(incomeThis, spendingThis);
  const savingsLast = savingsRate(incomeLast, spendingLast);

  const netWorthDelta = null;
  const spendingDelta = compareValues(spendingThis, spendingLast, false);
  const surplusDelta = compareValues(surplusThis, surplusLast, true);
  const savingsDelta =
    savingsThis !== null && savingsLast !== null
      ? compareValues(savingsThis, savingsLast, true)
      : null;

  // Convert the aggregated trend payload (1-indexed month numbers) into the
  // 0-indexed YearMonth that the chart component expects, padding any
  // missing months that the backend already omitted (it returns one row per
  // requested month, so this should be a no-op in practice).
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

  const donutRows = categoryBreakdown(donutTxns ?? thisMonthTxns);
  const donutRangeLabel = `${donutFrom} → ${donutTo}`;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Net worth · this month at a glance · drill in below
          </p>
        </div>
        <DateRangePicker />
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          label="Net worth"
          value={formatDollars(netWorthCents)}
          delta={netWorthDelta}
          deltaLabel="across all open accounts"
          index={0}
          valueClassName={netWorthCents < 0 ? "text-destructive" : undefined}
        />
        <KpiCard
          label="This month spending"
          value={formatDollars(spendingThis)}
          delta={spendingDelta}
          index={1}
        />
        <KpiCard
          label="Income minus spending"
          value={`${surplusThis >= 0 ? "" : "-"}${formatDollars(Math.abs(surplusThis))}`}
          delta={surplusDelta}
          index={2}
          valueClassName={surplusThis < 0 ? "text-destructive" : undefined}
        />
        <KpiCard
          label="Savings rate"
          value={savingsThis === null ? "—" : `${(savingsThis * 100).toFixed(0)}%`}
          delta={savingsDelta}
          index={3}
        />
      </div>

      <SpendingTrendChart points={trendPoints} />

      <div className="grid gap-6 lg:grid-cols-2">
        <CategoryDonutCard rows={donutRows} rangeLabel={donutRangeLabel} />
        <RecentTransactionsCard transactions={recentTxns} />
      </div>

      <p className="text-center text-xs text-muted-foreground">
        Numbers reflect the currently selected budget. Definitions in{" "}
        <Link
          href="https://github.com/majedal01/homelab/blob/main/ynab_insights/DESIGN.md"
          className="underline"
        >
          docs
        </Link>
        .
      </p>
    </div>
  );
}
