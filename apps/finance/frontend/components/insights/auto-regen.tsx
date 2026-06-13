"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Sparkles } from "lucide-react";
import { toast } from "sonner";

import { regenerateAllInsights } from "@/app/insights/actions";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * Fire `regenerateAllInsights` once on mount when the feed is empty.
 * Renders a generating-state skeleton in place of the empty state for
 * the duration. Subsequent visits within the session (insights already
 * populated) short-circuit; the manual Regenerate button still works.
 *
 * Guard against the React 19 strict-mode double-mount via a ref so we
 * don't fire two generates back-to-back.
 */
export function AutoRegen({
  shouldFire,
  cardCount,
}: {
  shouldFire: boolean;
  cardCount: number;
}) {
  const router = useRouter();
  const fired = React.useRef(false);
  const [generating, setGenerating] = React.useState(false);

  React.useEffect(() => {
    if (!shouldFire) return;
    if (fired.current) return;
    fired.current = true;

    setGenerating(true);
    (async () => {
      try {
        const summary = await regenerateAllInsights();
        const errored = summary.runs.filter((r) => r.status === "error").length;
        if (summary.created === 0 && summary.updated === 0 && errored === 0) {
          toast("No insights surfaced from this snapshot.");
        } else if (errored > 0) {
          toast.warning("Regenerated with errors", {
            description: `${summary.created} new · ${errored} errored`,
          });
        } else {
          toast("Insights ready", {
            description: `${summary.created} new`,
          });
        }
        router.refresh();
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        toast.error("Couldn't generate insights.", { description: message });
      } finally {
        setGenerating(false);
      }
    })();
  }, [shouldFire, router]);

  if (!generating) return null;

  return (
    <div className="space-y-4" aria-live="polite">
      <div className="flex items-center gap-2 rounded-md border bg-card/60 backdrop-blur px-4 py-3 text-sm">
        <Sparkles className="h-4 w-4 animate-pulse text-muted-foreground" />
        <span>
          Generating insights from your snapshot…
          {cardCount > 0 ? ` ${cardCount} already live.` : ""}
        </span>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <CardSkeleton key={i} />
        ))}
      </div>
    </div>
  );
}

function CardSkeleton() {
  return (
    <div className="rounded-lg border bg-card/40 backdrop-blur p-5">
      <Skeleton className="h-4 w-20 rounded-full" />
      <Skeleton className="mt-3 h-5 w-3/4" />
      <Skeleton className="mt-2 h-4 w-full" />
      <Skeleton className="mt-1 h-4 w-2/3" />
      <Skeleton className="mt-4 h-16 w-full" />
    </div>
  );
}
