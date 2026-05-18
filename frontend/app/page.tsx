import { apiFetch, getSelectedBudgetId, qs } from "@/lib/api";
import type {
  AccountResponse,
  BudgetResponse,
  TransactionResponse,
} from "@/lib/api-types";
import { formatDollars, firstOfMonth, todayIso } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import Link from "next/link";

interface CategorySpendRow {
  category_id: string | null;
  category_name: string | null;
  spent_cents: number;
}

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const budgets = await apiFetch<BudgetResponse[]>("/budgets");

  if (!budgets.length) {
    return (
      <div className="rounded-lg border bg-card p-8 text-center text-sm text-muted-foreground">
        No budgets yet. Trigger a sync to pull from YNAB.
      </div>
    );
  }

  const selected = (await getSelectedBudgetId(budgets)) ?? budgets[0].id;
  const from = firstOfMonth();
  const to = todayIso();

  const [accountsAll, recent] = await Promise.all([
    apiFetch<AccountResponse[]>(`/accounts${qs({ budget_id: selected })}`),
    apiFetch<TransactionResponse[]>(
      `/transactions${qs({ budget_id: selected, limit: 20 })}`,
    ),
  ]);

  const onBudget = accountsAll.filter((a) => a.on_budget && !a.closed);
  const tracking = accountsAll.filter((a) => !a.on_budget && !a.closed);
  const onBudgetTotal = onBudget.reduce((s, a) => s + a.balance_cents, 0);
  const trackingTotal = tracking.reduce((s, a) => s + a.balance_cents, 0);

  // Aggregate this-month spending by category from the wider transaction set.
  // A proper /reports endpoint replaces this client-side roll-up in v2.2.
  const monthly = await apiFetch<TransactionResponse[]>(
    `/transactions${qs({
      budget_id: selected,
      date_from: from,
      date_to: to,
      limit: 500,
    })}`,
  );
  const byCategory = new Map<string, CategorySpendRow>();
  for (const t of monthly) {
    if (t.amount_cents >= 0) continue;
    const key = t.category_id ?? "__uncategorized__";
    const entry = byCategory.get(key) ?? {
      category_id: t.category_id,
      category_name: t.category_name,
      spent_cents: 0,
    };
    entry.spent_cents += t.amount_cents;
    byCategory.set(key, entry);
  }
  const monthlySpend = [...byCategory.values()].sort(
    (a, b) => a.spent_cents - b.spent_cents,
  );

  return (
    <div className="space-y-6">
      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-baseline justify-between">
              <CardTitle>On-budget</CardTitle>
              <span className="font-mono text-base font-semibold tabular-nums">
                {formatDollars(onBudgetTotal)}
              </span>
            </div>
          </CardHeader>
          <CardContent>
            {onBudget.length ? (
              <ul className="divide-y divide-border">
                {onBudget.map((a) => (
                  <li key={a.id} className="flex justify-between py-2 text-sm">
                    <span>{a.name}</span>
                    <span
                      className={`font-mono ${a.balance_cents < 0 ? "text-destructive" : ""}`}
                    >
                      {formatDollars(a.balance_cents)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">No on-budget accounts.</p>
            )}
            {tracking.length > 0 && (
              <>
                <div className="mt-4 flex items-baseline justify-between">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Tracking
                  </h3>
                  <span className="font-mono text-sm font-semibold tabular-nums text-muted-foreground">
                    {formatDollars(trackingTotal)}
                  </span>
                </div>
                <ul className="mt-1 divide-y divide-border">
                  {tracking.map((a) => (
                    <li key={a.id} className="flex justify-between py-2 text-sm text-muted-foreground">
                      <span>{a.name}</span>
                      <span className="font-mono">{formatDollars(a.balance_cents)}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle>This Month by Category</CardTitle>
            <p className="text-xs text-muted-foreground">{from} to {to}</p>
          </CardHeader>
          <CardContent>
            {monthlySpend.length ? (
              <ul className="divide-y divide-border">
                {monthlySpend.map((row) => (
                  <li
                    key={row.category_id ?? "__uncat__"}
                    className="flex justify-between py-2 text-sm"
                  >
                    {row.category_id ? (
                      <Link
                        href={`/categories?id=${row.category_id}`}
                        className="text-primary hover:underline"
                      >
                        {row.category_name}
                      </Link>
                    ) : (
                      <span className="text-muted-foreground">Uncategorized</span>
                    )}
                    <span className="font-mono text-destructive">
                      {formatDollars(-row.spent_cents)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">No spending this month yet.</p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <CardTitle>Recent Transactions</CardTitle>
          <Badge variant="secondary">{recent.length}</Badge>
        </CardHeader>
        <CardContent>
          {recent.length ? (
            <ul className="divide-y divide-border">
              {recent.map((t) => (
                <li key={t.id} className="flex justify-between gap-4 py-2 text-sm">
                  <div className="min-w-0">
                    <div className="truncate">{t.payee_name ?? "—"}</div>
                    <div className="truncate text-xs text-muted-foreground">
                      {t.date} · {t.account_name}
                      {t.category_name ? ` · ${t.category_name}` : " · Uncategorized"}
                      {t.memo ? ` · ${t.memo}` : ""}
                    </div>
                  </div>
                  <div
                    className={`font-mono whitespace-nowrap ${
                      t.amount_cents < 0 ? "text-destructive" : "text-emerald-600 dark:text-emerald-400"
                    }`}
                  >
                    {formatDollars(t.amount_cents)}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">No transactions yet.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
