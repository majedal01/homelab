import Link from "next/link";
import { Inbox } from "lucide-react";

import { Button } from "@/components/ui/button";
import { InsightCard } from "@/components/insights/insight-card";
import type { InsightResponse } from "@/lib/api-types";

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
  if (insights.length === 0 && offset === 0) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-lg border bg-card p-12 text-center">
        <div className="rounded-full bg-muted p-3 text-muted-foreground">
          <Inbox className="h-5 w-5" />
        </div>
        <h3 className="text-sm font-medium">No insights yet</h3>
        <p className="max-w-sm text-xs text-muted-foreground">
          Once your YNAB data has been synced, the generators will surface
          subscription audits, spending anomalies, cashflow forecasts, and
          goal progress here. You can also generate them on demand below.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2">
        {insights.map((insight, i) => (
          <InsightCard key={insight.id} insight={insight} index={i} />
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
