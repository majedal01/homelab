"use client";

import * as React from "react";
import Link from "next/link";
import { motion } from "motion/react";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { formatDollars } from "@/lib/utils";
import type { AccountResponse } from "@/lib/api-types";

const TYPE_LABELS: Record<string, string> = {
  checking: "Checking",
  savings: "Savings",
  cash: "Cash",
  creditCard: "Credit card",
  lineOfCredit: "Line of credit",
  otherAsset: "Asset",
  otherLiability: "Liability",
  mortgage: "Mortgage",
  autoLoan: "Auto loan",
  studentLoan: "Student loan",
  personalLoan: "Personal loan",
  medicalDebt: "Medical debt",
  otherDebt: "Debt",
};

function typeLabel(t: string): string {
  return TYPE_LABELS[t] ?? t;
}

export function AccountsGrid({ accounts }: { accounts: AccountResponse[] }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {accounts.map((a, i) => (
        <motion.div
          key={a.id}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: i * 0.03, ease: "easeOut" }}
        >
          <Link
            href={`/transactions?account_id=${a.id}`}
            className="group block"
          >
            <Card className="transition-all duration-150 group-hover:-translate-y-px group-hover:shadow-sm">
              <CardContent className="flex flex-col gap-2 p-4">
                <div className="flex items-start justify-between gap-2">
                  <span className="truncate text-sm font-medium">{a.name}</span>
                  <Badge variant="outline" className="shrink-0 text-[10px]">
                    {typeLabel(a.type)}
                  </Badge>
                </div>
                <span
                  className={cn(
                    "font-mono text-xl font-semibold tabular-nums",
                    a.balance_cents < 0 ? "text-destructive" : "",
                  )}
                >
                  {formatDollars(a.balance_cents)}
                </span>
              </CardContent>
            </Card>
          </Link>
        </motion.div>
      ))}
    </div>
  );
}
