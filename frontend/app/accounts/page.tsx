import { apiFetch, getSelectedBudgetId, qs } from "@/lib/api";
import type { AccountResponse, BudgetResponse } from "@/lib/api-types";
import { formatDollars } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default async function AccountsPage() {
  const budgets = await apiFetch<BudgetResponse[]>("/budgets");
  if (!budgets.length) {
    return <p className="text-sm text-muted-foreground">No budgets yet.</p>;
  }
  const selected = (await getSelectedBudgetId(budgets)) ?? budgets[0].id;
  const accounts = await apiFetch<AccountResponse[]>(
    `/accounts${qs({ budget_id: selected })}`,
  );

  const open = accounts.filter((a) => !a.closed);
  const onBudget = open.filter((a) => a.on_budget);
  const tracking = open.filter((a) => !a.on_budget);
  // Split tracking accounts by balance sign: positive = asset, negative =
  // liability. Zero-balance tracking accounts group with assets.
  const assets = tracking.filter((a) => a.balance_cents >= 0);
  const liabilities = tracking.filter((a) => a.balance_cents < 0);
  const netWorth = open.reduce((s, a) => s + a.balance_cents, 0);

  return (
    <div className="space-y-6">
      <NetWorthTile netWorth={netWorth} />
      <div className="grid gap-6 md:grid-cols-3">
        <AccountsCard title="On-budget" accounts={onBudget} />
        <AccountsCard title="Assets" accounts={assets} />
        <AccountsCard title="Liabilities" accounts={liabilities} />
      </div>
    </div>
  );
}

function NetWorthTile({ netWorth }: { netWorth: number }) {
  return (
    <Card>
      <CardContent className="flex items-baseline justify-between p-6">
        <span className="text-sm font-medium uppercase tracking-wide text-muted-foreground">
          Net Worth
        </span>
        <span
          className={`font-mono text-2xl font-semibold tabular-nums ${
            netWorth < 0 ? "text-destructive" : ""
          }`}
        >
          {formatDollars(netWorth)}
        </span>
      </CardContent>
    </Card>
  );
}

function AccountsCard({
  title,
  accounts,
}: {
  title: string;
  accounts: AccountResponse[];
}) {
  const total = accounts.reduce((s, a) => s + a.balance_cents, 0);
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-baseline justify-between">
          <CardTitle>{title}</CardTitle>
          <span
            className={`font-mono text-base font-semibold tabular-nums ${
              total < 0 ? "text-destructive" : ""
            }`}
          >
            {formatDollars(total)}
          </span>
        </div>
      </CardHeader>
      <CardContent>
        {accounts.length ? (
          <ul className="divide-y divide-border">
            {accounts.map((a) => (
              <li key={a.id} className="flex justify-between py-2 text-sm">
                <Link
                  href={`/transactions?account_id=${a.id}`}
                  className="text-primary hover:underline"
                >
                  {a.name}
                </Link>
                <span
                  className={`font-mono tabular-nums ${a.balance_cents < 0 ? "text-destructive" : ""}`}
                >
                  {formatDollars(a.balance_cents)}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">No accounts.</p>
        )}
      </CardContent>
    </Card>
  );
}
