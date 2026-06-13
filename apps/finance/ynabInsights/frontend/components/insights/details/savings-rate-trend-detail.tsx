import type { SavingsRateTrendData } from "@/lib/api-types";
import { barColor, barHeightPct, rateRange } from "@/lib/savings-rate";

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

const DIRECTION_LABEL: Record<SavingsRateTrendData["direction"], string> = {
  up: "trending up",
  down: "trending down",
  flat: "holding steady",
};

function pctLabel(rate: number | null): string {
  return rate === null ? "—" : `${Math.round(rate * 100)}%`;
}

export function SavingsRateTrendDetail({ data }: { data: SavingsRateTrendData }) {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <Stat label="Latest month" value={pctLabel(data.latest_savings_rate)} />
        <Stat label="Average" value={pctLabel(data.average_savings_rate)} />
        <Stat label="Trend" value={DIRECTION_LABEL[data.direction]} />
      </div>
      <div className="rounded-md border bg-card p-4">
        <div className="text-xs uppercase tracking-wide text-muted-foreground">
          Monthly savings rate
        </div>
        <div className="mt-3 flex h-32 items-end gap-1">
          {(() => {
            const [min, max] = rateRange(data.points);
            return data.points.map((p, i) => (
              <div key={i} className="flex flex-1 flex-col items-center gap-1">
                <div
                  className={`w-full rounded-sm ${barColor(p.savings_rate)}`}
                  style={{ height: `${barHeightPct(p.savings_rate, min, max)}%` }}
                  title={`${MONTHS[p.month - 1]} ${p.year}: ${pctLabel(p.savings_rate)}`}
                />
                <span className="text-[9px] text-muted-foreground">{MONTHS[p.month - 1]}</span>
              </div>
            ));
          })()}
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        Savings rate is (income − spending) ÷ income for each month with income, over the
        last {data.months_of_history} months. Months with no recorded income are shown as gaps.
      </p>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border bg-card p-4">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-1 text-lg font-semibold capitalize tabular-nums">{value}</div>
    </div>
  );
}
