import { formatDollars } from "@/lib/utils";
import type { SubscriptionAuditData } from "@/lib/api-types";

export function SubscriptionAuditCard({
  data,
}: {
  data: SubscriptionAuditData;
}) {
  return (
    <dl className="grid grid-cols-2 gap-4 text-sm">
      <div>
        <dt className="text-xs uppercase tracking-wide text-muted-foreground">
          Monthly
        </dt>
        <dd className="mt-1 text-2xl font-semibold tabular-nums">
          {formatDollars(data.monthly_cost_cents)}
        </dd>
      </div>
      <div>
        <dt className="text-xs uppercase tracking-wide text-muted-foreground">
          Annual
        </dt>
        <dd className="mt-1 text-lg font-medium tabular-nums text-muted-foreground">
          {formatDollars(data.annual_cost_cents)}
        </dd>
      </div>
      <div className="col-span-2 flex items-center gap-2 text-xs text-muted-foreground">
        <span>{data.cadence}</span>
        <span>·</span>
        <span>{data.occurrences.length} charges in last 90d</span>
      </div>
    </dl>
  );
}
