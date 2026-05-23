"use client";

import * as React from "react";
import { formatDollars } from "@/lib/utils";
import type { GoalTrajectoryData } from "@/lib/api-types";

/**
 * Goal Trajectory detail view. Shows current projection plus an acceleration
 * slider that recomputes the completion date client-side based on additional
 * monthly contributions on top of the current pace.
 */
export function GoalTrajectoryDetail({
  data,
}: {
  data: GoalTrajectoryData;
}) {
  const [extra, setExtra] = React.useState(0);

  const totalMonthly = data.current_monthly_contribution_cents + extra * 100;
  const months =
    totalMonthly > 0 ? Math.ceil(data.remaining_cents / totalMonthly) : null;
  const acceleratedDate = months !== null ? addMonths(new Date(), months) : null;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-4">
        <Stat label="Target" value={formatDollars(data.target_cents)} />
        <Stat label="Progress" value={formatDollars(data.progress_cents)} />
        <Stat label="Remaining" value={formatDollars(data.remaining_cents)} />
        <Stat label="% complete" value={`${data.percent_complete}%`} />
      </div>
      <Progress percent={data.percent_complete} />

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-md border bg-card p-4">
          <div className="text-xs uppercase tracking-wide text-muted-foreground">
            At current pace
          </div>
          <div className="mt-1 text-lg font-semibold tabular-nums">
            {data.projected_completion_date ?? "—"}
          </div>
          <div className="text-xs text-muted-foreground">
            {formatDollars(data.current_monthly_contribution_cents)}/mo
            {data.target_date ? ` · target ${data.target_date}` : ""}
          </div>
        </div>
        <div className="rounded-md border bg-card p-4">
          <div className="text-xs uppercase tracking-wide text-muted-foreground">
            With ${extra}/mo extra
          </div>
          <div className="mt-1 text-lg font-semibold tabular-nums">
            {acceleratedDate ? formatDate(acceleratedDate) : "—"}
          </div>
          <div className="text-xs text-muted-foreground">
            {months !== null
              ? `${months} months at ${formatDollars(totalMonthly)}/mo`
              : "Add a contribution to project completion."}
          </div>
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between text-sm">
          <span>Extra monthly contribution</span>
          <span className="tabular-nums text-muted-foreground">${extra}</span>
        </div>
        <input
          type="range"
          min={0}
          max={1000}
          step={25}
          value={extra}
          onChange={(e) => setExtra(Number(e.target.value))}
          className="mt-1 w-full accent-primary"
          aria-label="Extra monthly contribution"
        />
      </div>
    </div>
  );
}

function Progress({ percent }: { percent: number }) {
  const pct = Math.max(0, Math.min(100, percent));
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
      <div
        className="h-full bg-primary"
        style={{ width: `${pct}%` }}
        aria-label={`${pct}% complete`}
      />
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

function addMonths(start: Date, months: number): Date {
  const result = new Date(start.getFullYear(), start.getMonth() + months, 1);
  return result;
}

function formatDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}
