import { formatDollars } from "@/lib/utils";
import type { SubscriptionAuditData } from "@/lib/api-types";

export function SubscriptionAuditDetail({
  data,
}: {
  data: SubscriptionAuditData;
}) {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <Stat label="Per charge" value={formatDollars(data.amount_cents)} />
        <Stat label="Per month" value={formatDollars(data.monthly_cost_cents)} />
        <Stat label="Per year" value={formatDollars(data.annual_cost_cents)} />
      </div>
      <div>
        <h2 className="text-sm font-semibold tracking-tight">Recent charges</h2>
        <p className="text-xs text-muted-foreground">
          {data.cadence} cadence · first seen {data.first_seen}, last seen {data.last_seen}
        </p>
        <table className="mt-3 w-full text-sm">
          <thead>
            <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
              <th className="py-2 font-medium">Date</th>
              <th className="py-2 font-medium">Memo</th>
              <th className="py-2 text-right font-medium">Amount</th>
            </tr>
          </thead>
          <tbody>
            {data.occurrences.map((o) => (
              <tr key={o.id} className="border-b last:border-b-0">
                <td className="py-2 tabular-nums">{o.date}</td>
                <td className="py-2 text-muted-foreground">{o.memo ?? "—"}</td>
                <td className="py-2 text-right tabular-nums">
                  {formatDollars(o.amount_cents)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-md border bg-card p-4">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 text-xl font-semibold tabular-nums">{value}</div>
    </div>
  );
}
