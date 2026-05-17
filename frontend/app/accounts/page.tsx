import { apiFetch, qs } from "@/lib/api";
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
  const selected = budgets[0].id;
  const accounts = await apiFetch<AccountResponse[]>(
    `/accounts${qs({ budget_id: selected })}`,
  );

  const open = accounts.filter((a) => !a.closed);
  const onBudget = open.filter((a) => a.on_budget);
  const tracking = open.filter((a) => !a.on_budget);

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <AccountsCard title="On-budget" accounts={onBudget} />
      <AccountsCard title="Tracking" accounts={tracking} muted />
    </div>
  );
}

function AccountsCard({
  title,
  accounts,
  muted = false,
}: {
  title: string;
  accounts: AccountResponse[];
  muted?: boolean;
}) {
  const total = accounts.reduce((s, a) => s + a.balance_cents, 0);
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-baseline justify-between">
          <CardTitle>{title}</CardTitle>
          <span className="font-mono text-sm">{formatDollars(total)}</span>
        </div>
      </CardHeader>
      <CardContent>
        {accounts.length ? (
          <ul className="divide-y divide-border">
            {accounts.map((a) => (
              <li key={a.id} className="flex justify-between py-2 text-sm">
                <Link
                  href={`/transactions?account_id=${a.id}`}
                  className={`hover:underline ${muted ? "text-muted-foreground" : "text-primary"}`}
                >
                  {a.name}
                </Link>
                <span
                  className={`font-mono ${a.balance_cents < 0 ? "text-destructive" : ""}`}
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
