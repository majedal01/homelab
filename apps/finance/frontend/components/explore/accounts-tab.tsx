import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { AccountResponse } from "@/lib/api-types";
import { cn } from "@/lib/utils";

export function AccountsTab({ accounts }: { accounts: AccountResponse[] }) {
  if (accounts.length === 0) {
    return (
      <p className="rounded-md border bg-card/60 backdrop-blur p-4 text-sm text-muted-foreground">
        No accounts on this budget.
      </p>
    );
  }

  const onBudget = accounts.filter((a) => a.on_budget && !a.closed);
  const tracking = accounts.filter((a) => !a.on_budget && !a.closed);
  const closed = accounts.filter((a) => a.closed);

  return (
    <div className="flex flex-col gap-4">
      <Section title="On budget" accounts={onBudget} />
      {tracking.length > 0 && <Section title="Tracking" accounts={tracking} />}
      {closed.length > 0 && <Section title="Closed" accounts={closed} dimmed />}
    </div>
  );
}

function Section({
  title,
  accounts,
  dimmed,
}: {
  title: string;
  accounts: AccountResponse[];
  dimmed?: boolean;
}) {
  if (accounts.length === 0) return null;
  const total = accounts.reduce((s, a) => s + a.balance_cents, 0);
  return (
    <Card className={dimmed ? "opacity-70" : undefined}>
      <CardContent className="p-0">
        <header className="flex items-baseline justify-between border-b px-5 py-3">
          <div>
            <h2 className="text-sm font-medium">{title}</h2>
            <p className="text-xs text-muted-foreground">
              {accounts.length} {accounts.length === 1 ? "account" : "accounts"}
            </p>
          </div>
          <p className="text-base font-semibold tabular-nums">{formatDollars(total)}</p>
        </header>
        <ul className="divide-y">
          {accounts.map((a) => (
            <li
              key={a.id}
              className="flex items-center justify-between gap-4 px-5 py-3 text-sm"
            >
              <div className="min-w-0">
                <p className="truncate font-medium">{a.name}</p>
                <p className="text-xs text-muted-foreground">{a.type}</p>
              </div>
              <div className="flex items-center gap-3">
                {a.closed && <Badge variant="outline">Closed</Badge>}
                <span
                  className={cn(
                    "tabular-nums",
                    a.balance_cents < 0 && "text-rose-600 dark:text-rose-400",
                  )}
                >
                  {formatDollars(a.balance_cents)}
                </span>
              </div>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function formatDollars(cents: number): string {
  const d = cents / 100;
  const sign = d < 0 ? "-" : "";
  return `${sign}$${Math.abs(d).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}
