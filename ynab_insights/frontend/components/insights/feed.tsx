"use client";

import * as React from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Inbox } from "lucide-react";

import { Button } from "@/components/ui/button";
import { InsightCard } from "@/components/insights/insight-card";
import type { InsightResponse } from "@/lib/api-types";
import { loadDismissals } from "@/lib/dismissals";

const PAGE_SIZE = 20;

export function InsightFeed({
  insights,
  offset,
  hasMore,
}: {
  insights: InsightResponse[];
  offset: number;
  hasMore: boolean;
}) {
  const searchParams = useSearchParams();
  const activeFilter = searchParams.get("card_type");
  // Hydrate dismissals once on mount; subsequent dismisses tell us about
  // themselves via the bumpVersion callback.
  const [dismissed, setDismissed] = React.useState<Set<string> | null>(null);
  React.useEffect(() => {
    setDismissed(new Set(Object.keys(loadDismissals())));
  }, []);

  const onDismissChange = React.useCallback(() => {
    setDismissed(new Set(Object.keys(loadDismissals())));
  }, []);

  // First render: show all incoming insights (no dismissal info yet). Once
  // localStorage is read we re-render with the filter applied.
  const visible =
    dismissed === null ? insights : insights.filter((i) => !dismissed.has(i.dedup_key));

  if (visible.length === 0 && offset === 0) {
    const filterLabel = filterDisplayName(activeFilter);
    return (
      <div className="flex flex-col items-center gap-3 rounded-lg border bg-card/60 backdrop-blur p-12 text-center">
        <div className="rounded-full bg-muted p-3 text-muted-foreground">
          <Inbox className="h-5 w-5" />
        </div>
        {filterLabel ? (
          <>
            <h3 className="text-sm font-medium">No {filterLabel} insights right now.</h3>
            <p className="max-w-sm text-xs text-muted-foreground">
              Switch to All above to see what else is here.
            </p>
          </>
        ) : (
          <>
            <h3 className="text-sm font-medium">Nothing yet.</h3>
            <p className="max-w-sm text-xs text-muted-foreground">
              Hit Regenerate to surface insights from your latest YNAB data.
            </p>
          </>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2">
        {visible.map((insight, i) => (
          <InsightCard
            key={insight.id}
            insight={insight}
            index={i}
            onDismissChange={onDismissChange}
          />
        ))}
      </div>
      <div className="flex items-center justify-between gap-2 pt-2 text-sm">
        {offset > 0 ? (
          <Button variant="ghost" size="sm" asChild>
            <Link href={`/insights${prevOffset(offset)}`}>← Newer</Link>
          </Button>
        ) : (
          <div />
        )}
        {hasMore ? (
          <Button variant="ghost" size="sm" asChild>
            <Link href={`/insights?offset=${offset + PAGE_SIZE}`}>Older →</Link>
          </Button>
        ) : (
          <div />
        )}
      </div>
    </div>
  );
}

function prevOffset(current: number): string {
  const next = Math.max(0, current - PAGE_SIZE);
  return next === 0 ? "" : `?offset=${next}`;
}

function filterDisplayName(cardType: string | null): string | null {
  switch (cardType) {
    case "subscription_audit":
      return "Subscription";
    case "spending_anomaly":
      return "Anomaly";
    case "cashflow_forecast":
      return "Forecast";
    case "goal_trajectory":
      return "Goal";
    case "category_drift":
      return "Drift";
    case "year_in_money":
      return "Year-in-money";
    default:
      return null;
  }
}
