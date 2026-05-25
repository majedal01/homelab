import { formatDollars } from "@/lib/utils";
import type { SpendingAnomalyData } from "@/lib/api-types";

export function SpendingAnomalyDetail({
  data,
}: {
  data: SpendingAnomalyData;
}) {
  const pct = Math.abs(data.deviation_ratio) * 100;
  const isMonthly = data.cycle === "monthly";
  const currentLabel = isMonthly ? "This month" : "This week";
  const baselineLabel = isMonthly ? "12mo average" : "12w average";
  const meanLabel = isMonthly ? "12-month mean" : "12-week mean";
  const txnLabel = isMonthly ? "Top transactions this month" : "Top transactions this week";
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-4">
        <Stat
          label={currentLabel}
          value={formatDollars(data.current_period_spend_cents)}
        />
        <Stat
          label={baselineLabel}
          value={formatDollars(data.baseline_mean_cents)}
        />
        <Stat
          label="Std deviation"
          value={formatDollars(data.baseline_stdev_cents)}
        />
        <Stat label="z-score" value={data.z_score.toFixed(2)} />
      </div>
      <p className="text-sm text-muted-foreground">
        {pct.toFixed(0)}% {data.z_score > 0 ? "above" : "below"} the {meanLabel} for{" "}
        <span className="text-foreground">{data.category_name}</span>, between{" "}
        {data.period_start} and {data.period_end}.
      </p>
      <div>
        <h2 className="text-sm font-semibold tracking-tight">
          {txnLabel}
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
                <td className="py-2 text-muted-foreground">
                  {t.payee_name ?? "—"}
                </td>
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
      <div className="mt-1 text-lg font-semibold tabular-nums">{value}</div>
    </div>
  );
}
