"use client";

import { motion } from "motion/react";
import Link from "next/link";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatDollars } from "@/lib/utils";
import type { TransactionResponse } from "@/lib/api-types";

export function RecentTransactionsCard({
  transactions,
}: {
  transactions: TransactionResponse[];
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: 0.3, ease: "easeOut" }}
    >
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <CardTitle>Recent transactions</CardTitle>
          <Link
            href="/transactions"
            className="text-xs text-primary hover:underline"
          >
            View all
            <Badge variant="secondary" className="ml-2">
              {transactions.length}
            </Badge>
          </Link>
        </CardHeader>
        <CardContent>
          {transactions.length ? (
            <ul className="divide-y divide-border">
              {transactions.map((t) => (
                <li
                  key={t.id}
                  className="flex items-center justify-between gap-4 py-2.5 text-sm"
                >
                  <div className="min-w-0">
                    <div className="truncate font-medium">{t.payee_name ?? "—"}</div>
                    <div className="truncate text-xs text-muted-foreground">
                      {t.date} · {t.account_name}
                      {t.category_name ? ` · ${t.category_name}` : " · Uncategorized"}
                    </div>
                  </div>
                  <div
                    className={`whitespace-nowrap font-mono tabular-nums ${
                      t.amount_cents < 0
                        ? "text-destructive"
                        : "text-emerald-600 dark:text-emerald-400"
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
    </motion.div>
  );
}
