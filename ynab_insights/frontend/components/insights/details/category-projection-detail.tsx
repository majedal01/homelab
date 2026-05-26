import { formatDollars } from "@/lib/utils";
import type { CategoryProjectionData } from "@/lib/api-types";

export function CategoryProjectionDetail({
  data,
}: {
  data: CategoryProjectionData;
}) {
  const pct = Math.abs(data.delta_pct) * 100;
  const dailyPace = data.month_to_date_cents / Math.max(data.days_into_month, 1);
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-4">
        <Stat label="Month-to-date" value={formatDollars(data.month_to_date_cents)} />
        <Stat
          label="Projected month-end"
          value={formatDollars(data.projected_month_end_cents)}
        />
        <Stat label="12mo average" value={formatDollars(data.baseline_monthly_avg_cents)} />
        <Stat label="Daily pace" value={`${formatDollars(Math.round(dailyPace))}/day`} />
      </div>
      <p className="text-sm text-muted-foreground">
        Day {data.days_into_month} of {data.days_in_month}. At this pace,{" "}
        <span className="text-foreground">{data.category_name}</span> would land{" "}
        {pct.toFixed(0)}% {data.direction === "over" ? "over" : "under"} the
        trailing-12-month monthly average.
      </p>
      <div>
        <h2 className="text-sm font-semibold tracking-tight">
          Largest charges this month
        </h2>
        <table className="mt-3 w-full text-sm">
          <thead>
            <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
              <th className="py-2 font-medium">Date</th>
              <th className="py-2 font-medium">Payee</th>
              <th className="py-2 text-right font-medium">Amount</th>
            </tr>
          </thead>
          <tbody>
            {data.top_transactions.map((t) => (
              <tr key={t.id} className="border-b last:border-b-0">
                <td className="py-2 tabular-nums">{t.date}</td>
                <td className="py-2 text-muted-foreground">{t.payee_name ?? "—"}</td>
                <td className="py-2 text-right tabular-nums">
                  {formatDollars(t.amount_cents)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border bg-card p-4">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 text-lg font-semibold tabular-nums">{value}</div>
    </div>
  );
}
