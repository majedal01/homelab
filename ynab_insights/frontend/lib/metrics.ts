/**
 * KPI and aggregation helpers used by the dashboard, categories, and any
 * future reports page. All functions are pure and take pre-fetched
 * AccountResponse[] / TransactionResponse[] so they can be unit-tested
 * without a backend.
 *
 * Definitions live in ynab_insights/DESIGN.md under "KPI definitions". When
 * a calculation changes here, update that doc.
 */

import type { AccountResponse, TransactionResponse } from "./api-types";

/**
 * YNAB's built-in income category. Positive amounts tagged to it are income
 * (Ready to Assign), not spending. YNAB doesn't allow creating other income
 * categories, so a hardcoded constant is enough — kept in sync with the
 * backend's `app/services/queries.py::INCOME_CATEGORY_NAME`.
 */
export const INCOME_CATEGORY_NAME = "Inflow: Ready to Assign";

function isIncomeCategory(name: string | null): boolean {
  return name === INCOME_CATEGORY_NAME;
}

// ---- date helpers -----------------------------------------------------------

export interface YearMonth {
  year: number;
  month: number; // 0-indexed, matches Date.getMonth()
}

export function currentMonth(today: Date = new Date()): YearMonth {
  return { year: today.getFullYear(), month: today.getMonth() };
}

export function previousMonth({ year, month }: YearMonth): YearMonth {
  return month === 0
    ? { year: year - 1, month: 11 }
    : { year, month: month - 1 };
}

/** First-of-month and last-of-month (inclusive), both as YYYY-MM-DD strings. */
export function monthBounds({ year, month }: YearMonth): {
  from: string;
  to: string;
} {
  const first = new Date(year, month, 1);
  const last = new Date(year, month + 1, 0);
  return { from: isoDate(first), to: isoDate(last) };
}

export function isoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** "Jan", "Feb", ... — labels for chart axes. */
export function monthLabel({ year, month }: YearMonth): string {
  return new Date(year, month, 1).toLocaleString("en-US", { month: "short" });
}

// ---- core KPIs --------------------------------------------------------------

export function netWorth(accounts: AccountResponse[]): number {
  return accounts.filter((a) => !a.closed).reduce((s, a) => s + a.balance_cents, 0);
}

/**
 * Total spending for the window, matching YNAB's "Total Expenses" semantics.
 *
 * Per-category, expenses are the NET of all transaction amounts on that
 * category. The built-in `Inflow: Ready to Assign` category is income, not
 * spending, so it's skipped entirely. Uncategorized rows (category_id =
 * null) are also skipped — they represent unsorted activity that YNAB
 * itself doesn't roll into the Expense column. A category that nets to a
 * refund (Education with +$156) reduces total expenses, mirroring YNAB.
 */
export function spendingFromTransactions(
  transactions: TransactionResponse[],
  onBudgetAccountIds: Set<string>,
): number {
  let total = 0;
  for (const t of transactions) {
    if (t.transfer_account_id) continue;
    if (!onBudgetAccountIds.has(t.account_id)) continue;
    if (t.category_id === null) continue;
    if (isIncomeCategory(t.category_name)) continue;
    total += -t.amount_cents;
  }
  return total;
}

/**
 * Income for the window, matching YNAB's "Total Income".
 *
 * YNAB tags income transactions to the built-in `Inflow: Ready to Assign`
 * category. Some users (or pre-import data) may leave income uncategorized
 * (null category); both shapes count. Negative amounts in the income
 * category are treated as adjustments (e.g. clawed-back deposit) and
 * reduce income.
 */
export function incomeFromTransactions(
  transactions: TransactionResponse[],
  onBudgetAccountIds: Set<string>,
): number {
  let total = 0;
  for (const t of transactions) {
    if (t.transfer_account_id) continue;
    if (!onBudgetAccountIds.has(t.account_id)) continue;
    const isNull = t.category_id === null;
    const isIncomeCat = isIncomeCategory(t.category_name);
    if (!isNull && !isIncomeCat) continue;
    if (isNull && t.amount_cents <= 0) continue;
    total += t.amount_cents;
  }
  return total;
}

/** Returns null when income is not positive (rate is undefined). */
export function savingsRate(incomeCents: number, spendingCents: number): number | null {
  if (incomeCents <= 0) return null;
  return (incomeCents - spendingCents) / incomeCents;
}

export function onBudgetAccountIdSet(accounts: AccountResponse[]): Set<string> {
  return new Set(accounts.filter((a) => a.on_budget && !a.closed).map((a) => a.id));
}

// ---- aggregations -----------------------------------------------------------

export interface CategorySpendRow {
  category_id: string | null;
  category_name: string | null;
  spent_cents: number;
}

/**
 * Net spend per category for a given transaction window. Returns the
 * signed net (positive `spent_cents` = net outflow, negative = net refund)
 * so callers can choose whether to filter for display.
 *
 * Filters baked in:
 * - Transfers (`transfer_account_id` set) excluded.
 * - Off-budget (tracking) account rows excluded.
 * - Positive amounts with a null category excluded (those are income,
 *   not refunds against the Uncategorized bucket).
 *
 * For the dashboard donut, filter `spent_cents > 0` at the display layer
 * to drop refund-net categories. For the categories list, render the
 * signed value so refunds surface visibly.
 */
export function categoryBreakdown(
  transactions: TransactionResponse[],
  onBudgetAccountIds: Set<string>,
): CategorySpendRow[] {
  const byCategory = new Map<string, CategorySpendRow>();
  for (const t of transactions) {
    if (t.transfer_account_id) continue;
    if (!onBudgetAccountIds.has(t.account_id)) continue;
    // YNAB's built-in income category isn't spending — skip it entirely.
    if (isIncomeCategory(t.category_name)) continue;
    // Null-category positives are unclassified income, not refunds against
    // the Uncategorized bucket.
    if (t.category_id === null && t.amount_cents > 0) continue;
    const key = t.category_id ?? "__uncategorized__";
    const entry = byCategory.get(key) ?? {
      category_id: t.category_id,
      category_name: t.category_name,
      spent_cents: 0,
    };
    entry.spent_cents += -t.amount_cents;
    byCategory.set(key, entry);
  }
  return [...byCategory.values()].sort(
    (a, b) => b.spent_cents - a.spent_cents,
  );
}

export interface MonthlyTrendPoint {
  month: string;
  yearMonth: YearMonth;
  spending: number;
  income: number;
}

/**
 * Roll transactions up by month for the trend chart. `months` defines the
 * window in oldest-first order. Transactions outside that window are
 * ignored.
 */
export function monthlyTrend(
  months: YearMonth[],
  transactions: TransactionResponse[],
  onBudgetAccountIds: Set<string>,
): MonthlyTrendPoint[] {
  const points: MonthlyTrendPoint[] = months.map((ym) => ({
    month: monthLabel(ym),
    yearMonth: ym,
    spending: 0,
    income: 0,
  }));
  const index = new Map<string, MonthlyTrendPoint>();
  for (const p of points) {
    index.set(`${p.yearMonth.year}-${p.yearMonth.month}`, p);
  }
  for (const t of transactions) {
    if (t.transfer_account_id) continue;
    if (!onBudgetAccountIds.has(t.account_id)) continue;
    const date = new Date(t.date);
    const key = `${date.getFullYear()}-${date.getMonth()}`;
    const point = index.get(key);
    if (!point) continue;
    if (t.amount_cents < 0) {
      point.spending += -t.amount_cents;
    } else {
      point.income += t.amount_cents;
    }
  }
  return points;
}

/** Build a window of N months ending at `endMonth`, oldest first. */
export function monthsWindow(endMonth: YearMonth, n: number): YearMonth[] {
  const out: YearMonth[] = [];
  let cursor = endMonth;
  for (let i = 0; i < n; i++) {
    out.unshift(cursor);
    cursor = previousMonth(cursor);
  }
  return out;
}

// ---- deltas -----------------------------------------------------------------

export interface DeltaInfo {
  /** Raw difference (current - previous). Can be negative. */
  diff: number;
  /** Percent change as a decimal (e.g. 0.12 = +12%). null when undefined. */
  pct: number | null;
  /**
   * Interpretation for color: "improved" / "worsened" / "neutral". Depends on
   * whether higher is better for the metric.
   */
  direction: "improved" | "worsened" | "neutral";
}

/**
 * Compare two values and report change + sentiment.
 * `higherIsBetter` controls whether an increase reads as good (income, net
 * worth, savings rate) or bad (spending, liabilities).
 */
export function compareValues(
  current: number,
  previous: number,
  higherIsBetter: boolean,
): DeltaInfo {
  const diff = current - previous;
  const pct = previous === 0 ? null : diff / Math.abs(previous);
  let direction: DeltaInfo["direction"];
  if (diff === 0) direction = "neutral";
  else if (diff > 0) direction = higherIsBetter ? "improved" : "worsened";
  else direction = higherIsBetter ? "worsened" : "improved";
  return { diff, pct, direction };
}
