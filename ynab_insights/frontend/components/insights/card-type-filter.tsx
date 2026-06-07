"use client";

import * as React from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { cn } from "@/lib/utils";

// The Goals pill groups every goals-family card type so they share one
// filter. list_insights accepts the comma-separated value.
const GOALS_GROUP =
  "goal_trajectory,goal_setup_prompt,emergency_fund_coverage,savings_rate_trend";

const FILTERS: { value: string | null; label: string }[] = [
  { value: null, label: "All" },
  { value: "subscription_audit", label: "Subscriptions" },
  { value: "spending_anomaly", label: "Anomalies" },
  { value: "cashflow_forecast", label: "Forecast" },
  { value: GOALS_GROUP, label: "Goals" },
  { value: "category_drift", label: "Drift" },
  { value: "year_in_money", label: "Year in money" },
];

/**
 * Sticky segmented filter above the insights feed. URL persists the
 * selection via `?card_type=` so back/forward + shareable links work.
 * On overflow (narrow viewports) the row scrolls horizontally rather
 * than wrapping; the visible affordance is a faint right-edge fade.
 */
export function CardTypeFilter({
  counts,
}: {
  counts?: Partial<Record<string, number>>;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const active = searchParams.get("card_type");
  const [pending, startTransition] = React.useTransition();

  function select(value: string | null): void {
    const params = new URLSearchParams(searchParams.toString());
    if (value === null) {
      params.delete("card_type");
    } else {
      params.set("card_type", value);
    }
    // Drop any pagination offset; switching filters should reset to page 1.
    params.delete("offset");
    const query = params.toString();
    startTransition(() => {
      router.push(query ? `${pathname}?${query}` : pathname);
    });
  }

  return (
    <div
      className={cn(
        "sticky top-14 z-30 -mx-4 mb-2 border-b bg-background/85 px-4 backdrop-blur",
        "supports-[backdrop-filter]:bg-background/60",
        pending && "opacity-80",
      )}
    >
      <div
        role="tablist"
        aria-label="Filter insights by type"
        className="flex gap-1.5 overflow-x-auto py-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {FILTERS.map((f) => {
          const isActive = (f.value ?? null) === (active ?? null);
          // Grouped pills (comma-separated value) sum their members' counts.
          const count = f.value
            ? f.value.split(",").reduce((sum, v) => sum + (counts?.[v] ?? 0), 0)
            : undefined;
          return (
            <button
              key={f.label}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => select(f.value)}
              className={cn(
                "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium",
                "transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                isActive
                  ? "border-foreground bg-foreground text-background"
                  : "border-border bg-background text-muted-foreground hover:border-foreground/30 hover:text-foreground",
              )}
            >
              {f.label}
              {count !== undefined && count > 0 && (
                <span
                  className={cn(
                    "inline-flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[10px] tabular-nums",
                    isActive
                      ? "bg-background/20 text-background"
                      : "bg-muted text-muted-foreground",
                  )}
                >
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
