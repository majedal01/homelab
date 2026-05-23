import { formatDollars } from "@/lib/utils";
import type { GoalTrajectoryData } from "@/lib/api-types";

export function GoalTrajectoryCard({
  data,
}: {
  data: GoalTrajectoryData;
}) {
  const pct = Math.max(0, Math.min(100, data.percent_complete));
  const onTrackLabel =
    data.on_track === null
      ? "no deadline"
      : data.on_track
        ? "on pace"
        : "behind pace";
  return (
    <div className="space-y-3 text-sm">
      <div className="flex items-baseline justify-between gap-3">
        <div className="text-2xl font-semibold tabular-nums">
          {formatDollars(data.progress_cents)}
        </div>
        <div className="text-xs text-muted-foreground tabular-nums">
          / {formatDollars(data.target_cents)}
        </div>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full bg-primary"
          style={{ width: `${pct}%` }}
          aria-label={`${pct}% complete`}
        />
      </div>
      <div className="text-xs text-muted-foreground">
        {pct}% complete · {onTrackLabel}
        {data.projected_completion_date
          ? ` · projected ${data.projected_completion_date}`
          : ""}
      </div>
    </div>
  );
}
