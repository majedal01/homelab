import { FileSearch } from "lucide-react";

import { apiFetch, getSelectedBudgetId, qs } from "@/lib/api";
import type { BudgetResponse, PeriodSummaryResponse } from "@/lib/api-types";
import { formatDollars } from "@/lib/utils";
import { currentMonth, monthBounds } from "@/lib/metrics";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DateRangePicker } from "@/components/date-range-picker";
import { EmptyState } from "@/components/empty";

export const dynamic = "force-dynamic";

interface ReportsSearchParams {
  date_from?: string;
  date_to?: string;
}

function dollarsSigned(cents: number): string {
  if (cents === 0) return "$0.00";
  if (cents > 0) return `+${formatDollars(cents)}`;
  return `-${formatDollars(Math.abs(cents))}`;
}

export default async function ReportsPage({
  searchParams,
}: {
  searchParams: Promise<ReportsSearchParams>;
}) {
  const params = await searchParams;
  const budgets = await apiFetch<BudgetResponse[]>("/budgets");
  if (!budgets.length) {
    return (
      <EmptyState
        icon={FileSearch}
        title="No budgets yet"
        description="Sync from YNAB before opening the reconciliation report."
      />
    );
  }
  const selected = (await getSelectedBudgetId(budgets)) ?? budgets[0].id;

  const defaultBounds = monthBounds(currentMonth());
  const dateFrom = params.date_from ?? defaultBounds.from;
  const dateTo = params.date_to ?? defaultBounds.to;

  const summary = await apiFetch<PeriodSummaryResponse>(
    `/reports/period-summary${qs({
      budget_id: selected,
      date_from: dateFrom,
      date_to: dateTo,
    })}`,
  );

  // Group categories: net-outflow vs net-refund. Net-zero categories drop
  // out (no transactions). YNAB's report shows expense categories with a
  // negative sign; refund-net rows appear with a positive sign.
  const expenseRows = summary.by_category.filter((r) => r.net_cents < 0);
  const refundRows = summary.by_category.filter((r) => r.net_cents > 0);
  const expenseTotal = expenseRows.reduce((s, r) => s + r.net_cents, 0);
  const refundTotal = refundRows.reduce((s, r) => s + r.net_cents, 0);

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Income vs Expense
          </h1>
          <p className="text-sm text-muted-foreground">
            Same layout as YNAB&apos;s Income vs Expense CSV so you can
            compare row-for-row. {dateFrom} → {dateTo}.
          </p>
        </div>
        <DateRangePicker />
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Headline numbers</CardTitle>
        </CardHeader>
        <CardContent>
          <table className="w-full text-sm">
            <tbody>
              <tr className="border-b">
                <td className="py-2 font-medium">Total Income</td>
                <td className="py-2 text-right font-mono tabular-nums text-emerald-600 dark:text-emerald-400">
                  {dollarsSigned(summary.income_cents)}
                </td>
              </tr>
              <tr className="border-b">
                <td className="py-2 font-medium">Total Expenses</td>
                <td className="py-2 text-right font-mono tabular-nums text-destructive">
                  {dollarsSigned(-summary.spending_cents)}
                </td>
              </tr>
              <tr>
                <td className="py-2 font-medium">Net Income</td>
                <td
                  className={`py-2 text-right font-mono tabular-nums ${
                    summary.net_income_cents >= 0
                      ? "text-emerald-600 dark:text-emerald-400"
                      : "text-destructive"
                  }`}
                >
                  {dollarsSigned(summary.net_income_cents)}
                </td>
              </tr>
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Income sources</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {summary.by_income_source.length ? (
            <table className="w-full text-sm">
              <tbody>
                {summary.by_income_source.map((row) => (
                  <tr
                    key={row.payee_id ?? row.payee_name ?? "no-payee"}
                    className="border-b last:border-b-0"
                  >
                    <td className="px-4 py-2">{row.payee_name ?? "—"}</td>
                    <td className="px-4 py-2 text-right font-mono tabular-nums text-emerald-600 dark:text-emerald-400">
                      {dollarsSigned(row.amount_cents)}
                    </td>
                  </tr>
                ))}
                <tr className="bg-muted/40 font-medium">
                  <td className="px-4 py-2">All Income Sources</td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums">
                    {dollarsSigned(summary.income_cents)}
                  </td>
                </tr>
              </tbody>
            </table>
          ) : (
            <p className="px-4 py-3 text-sm text-muted-foreground">
              No income recorded in this range.
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Categories</CardTitle>
          <p className="text-xs text-muted-foreground">
            Net per category. Refunds posted to expense categories show
            with a positive sign (and reduce Total Expenses).
          </p>
        </CardHeader>
        <CardContent className="p-0">
          {expenseRows.length === 0 && refundRows.length === 0 ? (
            <p className="px-4 py-3 text-sm text-muted-foreground">
              No category activity in this range.
            </p>
          ) : (
            <table className="w-full text-sm">
              <tbody>
                {expenseRows.map((row) => (
                  <tr
                    key={row.category_id ?? row.category_name ?? "row"}
                    className="border-b last:border-b-0"
                  >
                    <td className="px-4 py-2">{row.category_name ?? "—"}</td>
                    <td className="px-4 py-2 text-right font-mono tabular-nums text-destructive">
                      {dollarsSigned(row.net_cents)}
                    </td>
                  </tr>
                ))}
                {refundRows.length ? (
                  <>
                    <tr className="bg-muted/40">
                      <td colSpan={2} className="px-4 py-1.5 text-[11px] uppercase tracking-wide text-muted-foreground">
                        Net refunds
                      </td>
                    </tr>
                    {refundRows.map((row) => (
                      <tr
                        key={row.category_id ?? row.category_name ?? "r"}
                        className="border-b last:border-b-0"
                      >
                        <td className="px-4 py-2">
                          {row.category_name ?? "—"}
                        </td>
                        <td className="px-4 py-2 text-right font-mono tabular-nums text-emerald-600 dark:text-emerald-400">
                          {dollarsSigned(row.net_cents)}
                        </td>
                      </tr>
                    ))}
                  </>
                ) : null}
                <tr className="bg-muted/40 font-medium">
                  <td className="px-4 py-2">Total Expenses</td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums text-destructive">
                    {dollarsSigned(expenseTotal + refundTotal)}
                  </td>
                </tr>
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Reconcile</CardTitle>
          <p className="text-xs text-muted-foreground">
            Diagnostic numbers — included so you can spot where money is
            hiding when the headline totals don&apos;t tie out against YNAB.
          </p>
        </CardHeader>
        <CardContent>
          <table className="w-full text-sm">
            <tbody>
              <tr className="border-b">
                <td className="py-2">Gross outflow (all negatives, on-budget, non-transfer)</td>
                <td className="py-2 text-right font-mono tabular-nums">
                  {formatDollars(summary.gross_outflow_cents)}
                </td>
              </tr>
              <tr className="border-b">
                <td className="py-2">Gross inflow (all positives)</td>
                <td className="py-2 text-right font-mono tabular-nums">
                  {formatDollars(summary.gross_inflow_cents)}
                </td>
              </tr>
              <tr className="border-b">
                <td className="py-2">Uncategorized outflow</td>
                <td className="py-2 text-right font-mono tabular-nums">
                  {formatDollars(summary.uncategorized_outflow_cents)}
                </td>
              </tr>
              <tr className="border-b">
                <td className="py-2">Uncategorized inflow</td>
                <td className="py-2 text-right font-mono tabular-nums">
                  {formatDollars(summary.uncategorized_inflow_cents)}
                </td>
              </tr>
              <tr>
                <td className="py-2">Transaction count (on-budget, non-transfer)</td>
                <td className="py-2 text-right font-mono tabular-nums">
                  {summary.transaction_count}
                </td>
              </tr>
            </tbody>
          </table>
          <p className="mt-3 text-[11px] text-muted-foreground">
            Total Expenses = Gross outflow − Uncategorized outflow − (refunds
            in expense categories). If Gross outflow ≈ YNAB Total Expenses
            but Total Expenses above does not, the gap is in the
            uncategorized buckets — usually transactions whose category was
            deleted in YNAB. If Gross outflow also doesn&apos;t match, the
            gap is in the sync itself or in an excluded account.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
