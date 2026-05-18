import { ListFilter } from "lucide-react";

import { apiFetch, getSelectedBudgetId, qs } from "@/lib/api";
import type {
  AccountResponse,
  BudgetResponse,
  CategoryResponse,
  TransactionResponse,
} from "@/lib/api-types";
import { Card, CardContent } from "@/components/ui/card";
import { DateRangePicker } from "@/components/date-range-picker";
import { TransactionsTable } from "@/components/transactions/transactions-table";
import { EmptyState } from "@/components/empty";

interface PageSearchParams {
  account_id?: string;
  category_id?: string;
  payee_id?: string;
  date_from?: string;
  date_to?: string;
  limit?: string;
}

export const dynamic = "force-dynamic";

export default async function TransactionsPage({
  searchParams,
}: {
  searchParams: Promise<PageSearchParams>;
}) {
  const params = await searchParams;
  const budgets = await apiFetch<BudgetResponse[]>("/budgets");
  if (!budgets.length) {
    return (
      <EmptyState
        icon={ListFilter}
        title="No budgets yet"
        description="Sync from YNAB to see your transactions."
      />
    );
  }
  const selected = (await getSelectedBudgetId(budgets)) ?? budgets[0].id;
  const limit = Math.min(
    Math.max(parseInt(params.limit ?? "200", 10) || 200, 1),
    500,
  );

  const [transactions, accounts, categories] = await Promise.all([
    apiFetch<TransactionResponse[]>(
      `/transactions${qs({
        budget_id: selected,
        account_id: params.account_id,
        category_id: params.category_id,
        payee_id: params.payee_id,
        date_from: params.date_from,
        date_to: params.date_to,
        limit,
      })}`,
    ),
    apiFetch<AccountResponse[]>(`/accounts${qs({ budget_id: selected })}`),
    apiFetch<CategoryResponse[]>(`/categories${qs({ budget_id: selected })}`),
  ]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Transactions</h1>
          <p className="text-sm text-muted-foreground">
            {transactions.length} loaded · sort columns, filter, search
          </p>
        </div>
        <DateRangePicker />
      </div>

      <Card>
        <CardContent className="space-y-3 p-4">
          <form
            method="get"
            action="/transactions"
            className="flex flex-wrap items-end gap-3 text-sm"
          >
            <input
              type="hidden"
              name="date_from"
              value={params.date_from ?? ""}
            />
            <input
              type="hidden"
              name="date_to"
              value={params.date_to ?? ""}
            />
            <FilterSelect
              name="account_id"
              label="Account"
              value={params.account_id}
              options={accounts.map((a) => ({ value: a.id, label: a.name }))}
            />
            <FilterSelect
              name="category_id"
              label="Category"
              value={params.category_id}
              options={categories.map((c) => ({ value: c.id, label: c.name }))}
            />
            <button
              type="submit"
              className="h-9 rounded-md bg-primary px-4 text-sm text-primary-foreground hover:bg-primary/90"
            >
              Apply
            </button>
            <a
              href="/transactions"
              className="text-xs text-muted-foreground hover:underline"
            >
              Reset
            </a>
          </form>
        </CardContent>
      </Card>

      <TransactionsTable data={transactions} />
    </div>
  );
}

function FilterSelect({
  name,
  label,
  value,
  options,
}: {
  name: string;
  label: string;
  value?: string;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <select
        name={name}
        defaultValue={value ?? ""}
        className="h-9 rounded-md border border-input bg-background px-2 text-sm"
      >
        <option value="">(any)</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}
