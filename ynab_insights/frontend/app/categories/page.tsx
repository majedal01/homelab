import Link from "next/link";
import { PieChart } from "lucide-react";

import { apiFetch, getSelectedBudgetId, qs } from "@/lib/api";
import type {
  BudgetResponse,
  CategoryResponse,
  TransactionResponse,
} from "@/lib/api-types";
import { formatDollars } from "@/lib/utils";
import { currentMonth, monthBounds, categoryBreakdown } from "@/lib/metrics";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { DateRangePicker } from "@/components/date-range-picker";
import { EmptyState } from "@/components/empty";

export const dynamic = "force-dynamic";

interface PageSearchParams {
  date_from?: string;
  date_to?: string;
}

export default async function CategoriesPage({
  searchParams,
}: {
  searchParams: Promise<PageSearchParams>;
}) {
  const params = await searchParams;
  const budgets = await apiFetch<BudgetResponse[]>("/budgets");
  if (!budgets.length) {
    return (
      <EmptyState
        icon={PieChart}
        title="No budgets yet"
        description="Sync from YNAB to see your categories."
      />
    );
  }
  const selected = (await getSelectedBudgetId(budgets)) ?? budgets[0].id;

  const defaultBounds = monthBounds(currentMonth());
  const from = params.date_from ?? defaultBounds.from;
  const to = params.date_to ?? defaultBounds.to;

  const [categories, txns] = await Promise.all([
    apiFetch<CategoryResponse[]>(`/categories${qs({ budget_id: selected })}`),
    apiFetch<TransactionResponse[]>(
      `/transactions${qs({
        budget_id: selected,
        date_from: from,
        date_to: to,
        limit: 500,
      })}`,
    ),
  ]);

  const breakdownRows = categoryBreakdown(txns);
  const breakdownById = new Map(
    breakdownRows
      .filter((r) => r.category_id)
      .map((r) => [r.category_id as string, r.spent_cents]),
  );

  const maxSpend = breakdownRows[0]?.spent_cents ?? 0;
  const totalSpend = breakdownRows.reduce((s, r) => s + r.spent_cents, 0);

  const rows = categories
    .map((c) => ({ ...c, spent: breakdownById.get(c.id) ?? 0 }))
    .sort((a, b) => b.spent - a.spent);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Categories</h1>
          <p className="text-sm text-muted-foreground">
            {categories.length} categories · spend column is {from} → {to}
          </p>
        </div>
        <DateRangePicker />
      </div>

      <Card>
        <CardHeader className="flex flex-row items-baseline justify-between pb-3">
          <CardTitle>Total in range</CardTitle>
          <span className="font-mono text-base font-semibold tabular-nums text-destructive">
            {formatDollars(totalSpend)}
          </span>
        </CardHeader>
      </Card>

      <Card>
        <CardContent className="p-0">
          {rows.length ? (
            <ul className="divide-y divide-border">
              {rows.map((row) => {
                const pct = maxSpend ? Math.round((row.spent / maxSpend) * 100) : 0;
                return (
                  <li
                    key={row.id}
                    className="flex flex-col gap-1.5 px-4 py-3 text-sm"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex min-w-0 items-center gap-2">
                        <Link
                          href={`/transactions?category_id=${row.id}`}
                          className="truncate text-primary hover:underline"
                        >
                          {row.name}
                        </Link>
                        {row.hidden ? (
                          <Badge variant="outline" className="text-[10px]">
                            hidden
                          </Badge>
                        ) : null}
                      </div>
                      <span
                        className={`font-mono tabular-nums ${
                          row.spent > 0 ? "text-destructive" : "text-muted-foreground"
                        }`}
                      >
                        {row.spent > 0 ? formatDollars(row.spent) : "—"}
                      </span>
                    </div>
                    {row.spent > 0 ? (
                      <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
                        <div
                          className="h-full rounded-full bg-destructive/70 transition-all"
                          style={{ width: `${pct}%` }}
                          aria-hidden
                        />
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          ) : (
            <EmptyState
              icon={PieChart}
              title="No categories"
              description="Sync from YNAB to populate your category list."
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
