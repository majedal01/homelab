"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import type { BudgetResponse } from "@/lib/api-types";

export function BudgetSwitcher({
  budgets,
  selected,
}: {
  budgets: BudgetResponse[];
  selected: string | null;
}) {
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();

  if (!budgets.length) return null;
  if (budgets.length === 1) {
    return (
      <span
        className="hidden sm:inline-block max-w-[10rem] truncate text-xs text-muted-foreground"
        title={budgets[0].name}
      >
        {budgets[0].name}
      </span>
    );
  }

  return (
    <select
      aria-label="Select budget"
      value={selected ?? budgets[0].id}
      disabled={pending}
      onChange={async (e) => {
        const value = e.target.value;
        await fetch("/api/budget", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ budget_id: value }),
        });
        startTransition(() => router.refresh());
      }}
      className="h-8 max-w-[10rem] truncate rounded-md border border-input bg-background px-2 text-xs"
    >
      {budgets.map((b) => (
        <option key={b.id} value={b.id}>
          {b.name}
        </option>
      ))}
    </select>
  );
}
