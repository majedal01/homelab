"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type {
  AccountResponse,
  CategoryResponse,
  TransactionResponse,
} from "@/lib/api-types";

const PAGE_SIZE = 50;

export function TransactionsTab({
  transactions,
  categories,
  accounts,
  offset,
}: {
  transactions: TransactionResponse[];
  categories: CategoryResponse[];
  accounts: AccountResponse[];
  offset: number;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [payee, setPayee] = React.useState(searchParams.get("payee_contains") ?? "");
  const [category, setCategory] = React.useState(searchParams.get("category_id") ?? "");
  const [account, setAccount] = React.useState(searchParams.get("account_id") ?? "");
  const [dateFrom, setDateFrom] = React.useState(searchParams.get("date_from") ?? "");
  const [dateTo, setDateTo] = React.useState(searchParams.get("date_to") ?? "");

  // Re-sync local state when the URL changes (deep-link from a card detail).
  React.useEffect(() => {
    setPayee(searchParams.get("payee_contains") ?? "");
    setCategory(searchParams.get("category_id") ?? "");
    setAccount(searchParams.get("account_id") ?? "");
    setDateFrom(searchParams.get("date_from") ?? "");
    setDateTo(searchParams.get("date_to") ?? "");
  }, [searchParams]);

  function apply(): void {
    const usp = new URLSearchParams(searchParams.toString());
    usp.set("view", "transactions");
    usp.delete("offset");
    setOrDelete(usp, "payee_contains", payee.trim());
    setOrDelete(usp, "category_id", category);
    setOrDelete(usp, "account_id", account);
    setOrDelete(usp, "date_from", dateFrom);
    setOrDelete(usp, "date_to", dateTo);
    router.push(`${pathname}?${usp.toString()}`);
  }

  function reset(): void {
    router.push(`${pathname}?view=transactions`);
  }

  function changePage(delta: number): void {
    const usp = new URLSearchParams(searchParams.toString());
    const next = Math.max(0, offset + delta);
    if (next === 0) {
      usp.delete("offset");
    } else {
      usp.set("offset", String(next));
    }
    router.push(`${pathname}?${usp.toString()}`);
  }

  const hasMore = transactions.length === PAGE_SIZE;

  return (
    <div className="flex flex-col gap-3">
      <div className="grid gap-2 rounded-lg border bg-card/60 backdrop-blur p-3 md:grid-cols-5">
        <Input
          placeholder="Payee contains…"
          value={payee}
          onChange={(e) => setPayee(e.target.value)}
        />
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="h-9 rounded-md border bg-background px-2 text-sm"
        >
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <select
          value={account}
          onChange={(e) => setAccount(e.target.value)}
          className="h-9 rounded-md border bg-background px-2 text-sm"
        >
          <option value="">All accounts</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>
        <Input
          type="date"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
        />
        <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        <div className="md:col-span-5 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={reset}>
            Reset
          </Button>
          <Button size="sm" onClick={apply}>
            Apply
          </Button>
        </div>
      </div>

      {transactions.length === 0 ? (
        <p className="rounded-md border bg-card/60 backdrop-blur p-4 text-sm text-muted-foreground">
          No transactions match. Try widening the date range or clearing filters.
        </p>
      ) : (
        <Card>
          <CardContent className="p-0">
            <ul className="divide-y">
              {transactions.map((t) => (
                <li key={t.id} className="px-5 py-3">
                  <div className="flex items-baseline justify-between gap-4 text-sm">
                    <div className="min-w-0 flex-1">
                      <p className="truncate">
                        <span className="font-medium">
                          {t.payee_name ?? "(uncategorized payee)"}
                        </span>
                        {t.category_name && (
                          <Link
                            href={`/explore?view=transactions&category_id=${encodeURIComponent(t.category_id ?? "")}`}
                            className="ml-2 text-xs text-muted-foreground hover:underline"
                          >
                            {t.category_name}
                          </Link>
                        )}
                      </p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {t.date} · {t.account_name ?? "Unknown account"}
                        {t.memo && (
                          <span className="ml-1 truncate"> · {t.memo}</span>
                        )}
                      </p>
                    </div>
                    <span
                      className={cn(
                        "tabular-nums",
                        t.amount_cents < 0
                          ? "text-rose-600 dark:text-rose-400"
                          : "text-emerald-600 dark:text-emerald-400",
                      )}
                    >
                      {formatDollars(t.amount_cents)}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      <div className="flex items-center justify-between gap-2 pt-1 text-sm">
        <Button
          variant="ghost"
          size="sm"
          disabled={offset === 0}
          onClick={() => changePage(-PAGE_SIZE)}
        >
          ← Newer
        </Button>
        <span className="text-xs text-muted-foreground">
          Showing {offset + 1}–{offset + transactions.length}
        </span>
        <Button
          variant="ghost"
          size="sm"
          disabled={!hasMore}
          onClick={() => changePage(PAGE_SIZE)}
        >
          Older →
        </Button>
      </div>
    </div>
  );
}

function setOrDelete(usp: URLSearchParams, key: string, value: string): void {
  if (value) {
    usp.set(key, value);
  } else {
    usp.delete(key);
  }
}

function formatDollars(cents: number): string {
  const d = cents / 100;
  const sign = d < 0 ? "-" : d > 0 ? "+" : "";
  return `${sign}$${Math.abs(d).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}
