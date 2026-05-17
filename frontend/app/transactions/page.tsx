import { apiFetch, qs } from "@/lib/api";
import type {
  AccountResponse,
  BudgetResponse,
  CategoryResponse,
  TransactionResponse,
} from "@/lib/api-types";
import { formatDollars } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

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
    return <p className="text-sm text-muted-foreground">No budgets yet.</p>;
  }
  const selected = budgets[0].id;
  const limit = Math.min(Math.max(parseInt(params.limit ?? "200", 10) || 200, 1), 500);

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

  const accountById = new Map(accounts.map((a) => [a.id, a]));
  const categoryById = new Map(categories.map((c) => [c.id, c]));
  void accountById;
  void categoryById;

  return (
    <div className="space-y-4">
      <form
        method="get"
        action="/transactions"
        className="flex flex-wrap items-end gap-3 rounded-lg border bg-card p-4 text-sm"
      >
        <FilterDate name="date_from" label="From" value={params.date_from} />
        <FilterDate name="date_to" label="To" value={params.date_to} />
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
        <a href="/transactions" className="text-xs text-muted-foreground hover:underline">
          Reset
        </a>
      </form>

      <Card>
        <CardContent className="p-0">
          {transactions.length ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-28">Date</TableHead>
                  <TableHead>Payee</TableHead>
                  <TableHead>Category</TableHead>
                  <TableHead>Account</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {transactions.map((t) => (
                  <TableRow key={t.id}>
                    <TableCell className="whitespace-nowrap text-muted-foreground">
                      {t.date}
                    </TableCell>
                    <TableCell>{t.payee_name ?? "—"}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {t.category_name ?? "Uncategorized"}
                    </TableCell>
                    <TableCell className="text-muted-foreground">{t.account_name}</TableCell>
                    <TableCell
                      className={`text-right font-mono ${
                        t.amount_cents < 0
                          ? "text-destructive"
                          : "text-emerald-600 dark:text-emerald-400"
                      }`}
                    >
                      {formatDollars(t.amount_cents)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="p-8 text-center text-sm text-muted-foreground">
              No transactions match the current filters.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function FilterDate({
  name,
  label,
  value,
}: {
  name: string;
  label: string;
  value?: string;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <input
        type="date"
        name={name}
        defaultValue={value ?? ""}
        className="h-9 rounded-md border border-input bg-background px-2 text-sm"
      />
    </label>
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
