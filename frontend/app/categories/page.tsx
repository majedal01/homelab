import { apiFetch, qs } from "@/lib/api";
import type {
  BudgetResponse,
  CategoryResponse,
  TransactionResponse,
} from "@/lib/api-types";
import { formatDollars, firstOfMonth, todayIso } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default async function CategoriesPage() {
  const budgets = await apiFetch<BudgetResponse[]>("/budgets");
  if (!budgets.length) {
    return <p className="text-sm text-muted-foreground">No budgets yet.</p>;
  }
  const selected = budgets[0].id;
  const from = firstOfMonth();
  const to = todayIso();

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

  const spendByCategory = new Map<string, number>();
  for (const t of txns) {
    if (t.amount_cents >= 0 || !t.category_id) continue;
    spendByCategory.set(
      t.category_id,
      (spendByCategory.get(t.category_id) ?? 0) + t.amount_cents,
    );
  }

  const rows = categories
    .map((c) => ({ ...c, spent_cents: spendByCategory.get(c.id) ?? 0 }))
    .sort((a, b) => a.spent_cents - b.spent_cents);

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-baseline justify-between">
          <CardTitle>Categories</CardTitle>
          <Badge variant="secondary">{categories.length}</Badge>
        </div>
        <p className="text-xs text-muted-foreground">
          Spend column is {from} to {to}
        </p>
      </CardHeader>
      <CardContent>
        <ul className="divide-y divide-border">
          {rows.map((row) => (
            <li key={row.id} className="flex items-center justify-between gap-4 py-2 text-sm">
              <div className="min-w-0 flex items-center gap-2">
                <Link
                  href={`/transactions?category_id=${row.id}`}
                  className="truncate text-primary hover:underline"
                >
                  {row.name}
                </Link>
                {row.hidden && (
                  <Badge variant="outline" className="text-xs">
                    hidden
                  </Badge>
                )}
              </div>
              <span
                className={`font-mono ${row.spent_cents < 0 ? "text-destructive" : "text-muted-foreground"}`}
              >
                {row.spent_cents < 0 ? formatDollars(-row.spent_cents) : "—"}
              </span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
