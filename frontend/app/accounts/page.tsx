import { Wallet } from "lucide-react";

import { apiFetch, getSelectedBudgetId, qs } from "@/lib/api";
import type { AccountResponse, BudgetResponse } from "@/lib/api-types";
import { formatDollars } from "@/lib/utils";
import { netWorth } from "@/lib/metrics";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/empty";
import { AccountsGrid } from "@/components/accounts/accounts-grid";

export const dynamic = "force-dynamic";

export default async function AccountsPage() {
  const budgets = await apiFetch<BudgetResponse[]>("/budgets");
  if (!budgets.length) {
    return (
      <EmptyState
        icon={Wallet}
        title="No budgets yet"
        description="Sync from YNAB to see your accounts."
      />
    );
  }
  const selected = (await getSelectedBudgetId(budgets)) ?? budgets[0].id;
  const accounts = await apiFetch<AccountResponse[]>(
    `/accounts${qs({ budget_id: selected })}`,
  );

  const open = accounts.filter((a) => !a.closed);
  const onBudget = open.filter((a) => a.on_budget);
  const tracking = open.filter((a) => !a.on_budget);
  const assets = tracking.filter((a) => a.balance_cents >= 0);
  const liabilities = tracking.filter((a) => a.balance_cents < 0);
  const nw = netWorth(accounts);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Accounts</h1>
          <p className="text-sm text-muted-foreground">
            {open.length} open · click an account to drill into its transactions
          </p>
        </div>
      </div>

      <Card>
        <CardContent className="flex items-baseline justify-between p-6">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Net worth
          </span>
          <span
            className={`font-mono text-3xl font-semibold tabular-nums ${
              nw < 0 ? "text-destructive" : ""
            }`}
          >
            {formatDollars(nw)}
          </span>
        </CardContent>
      </Card>

      <AccountSection title="On-budget" accounts={onBudget} />
      <AccountSection title="Assets" accounts={assets} />
      <AccountSection title="Liabilities" accounts={liabilities} />

      {!open.length ? (
        <EmptyState
          icon={Wallet}
          title="No open accounts"
          description="Trigger a sync to see your accounts."
        />
      ) : null}
    </div>
  );
}

function AccountSection({
  title,
  accounts,
}: {
  title: string;
  accounts: AccountResponse[];
}) {
  if (!accounts.length) return null;
  const total = accounts.reduce((s, a) => s + a.balance_cents, 0);
  return (
    <section className="space-y-3">
      <Card>
        <CardHeader className="flex flex-row items-baseline justify-between pb-3">
          <CardTitle>{title}</CardTitle>
          <div className="flex items-baseline gap-3">
            <Badge variant="secondary">{accounts.length}</Badge>
            <span
              className={`font-mono text-base font-semibold tabular-nums ${
                total < 0 ? "text-destructive" : ""
              }`}
            >
              {formatDollars(total)}
            </span>
          </div>
        </CardHeader>
      </Card>
      <AccountsGrid accounts={accounts} />
    </section>
  );
}
