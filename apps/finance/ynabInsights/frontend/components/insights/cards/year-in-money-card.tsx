import { ArrowRight } from "lucide-react";

import { formatDollars } from "@/lib/utils";
import type { YearInMoneyData } from "@/lib/api-types";

/**
 * Compact feed tile for Year in Money. The big artifact is the detail
 * page — this card is just an entry point with a few headline figures.
 */
export function YearInMoneyCard({ data }: { data: YearInMoneyData }) {
  const savings =
    data.savings_rate !== null
      ? `${Math.round(data.savings_rate * 100)}%`
      : "—";
  return (
    <div className="space-y-3 text-sm">
      <div className="grid grid-cols-3 gap-3">
        <Stat label="Income" value={formatDollars(data.total_income_cents)} />
        <Stat label="Spending" value={formatDollars(data.total_spending_cents)} />
        <Stat label="Saved" value={savings} />
      </div>
      {data.biggest_single ? (
        <div className="text-xs text-muted-foreground">
          Largest single: {formatDollars(Math.abs(data.biggest_single.amount_cents))}
          {data.biggest_single.payee_name
            ? ` to ${data.biggest_single.payee_name}`
            : ""}
          .
        </div>
      ) : null}
      <div className="inline-flex items-center text-xs font-medium text-primary">
        Open the full report
        <ArrowRight className="ml-1 h-3 w-3" />
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="mt-0.5 font-mono text-base font-semibold tabular-nums">
        {value}
      </div>
    </div>
  );
}
