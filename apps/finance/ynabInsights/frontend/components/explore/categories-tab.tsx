"use client";

import * as React from "react";
import Link from "next/link";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import type { CategoryResponse } from "@/lib/api-types";

export function CategoriesTab({ categories }: { categories: CategoryResponse[] }) {
  const [query, setQuery] = React.useState("");
  const filtered = React.useMemo(() => {
    const needle = query.trim().toLowerCase();
    const sorted = [...categories].sort(
      (a, b) => b.this_month_spend_cents - a.this_month_spend_cents,
    );
    if (!needle) return sorted;
    return sorted.filter((c) => c.name.toLowerCase().includes(needle));
  }, [categories, query]);

  return (
    <div className="flex flex-col gap-3">
      <Input
        placeholder="Filter by name…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className="max-w-sm"
      />
      {filtered.length === 0 ? (
        <p className="rounded-md border bg-card/60 backdrop-blur p-4 text-sm text-muted-foreground">
          No matches.
        </p>
      ) : (
        <Card>
          <CardContent className="p-0">
            <ul className="divide-y">
              {filtered.map((c) => (
                <li key={c.id} className="px-5 py-3">
                  <Link
                    href={`/explore?view=transactions&category_id=${encodeURIComponent(c.id)}`}
                    className="flex items-center justify-between gap-4 text-sm hover:opacity-80"
                  >
                    <div className="min-w-0">
                      <p className="truncate font-medium">{c.name}</p>
                      {c.goal_target_cents !== null && c.goal_target_cents > 0 && (
                        <p className="mt-0.5 text-xs text-muted-foreground">
                          Goal {formatDollars(c.goal_target_cents)}
                          {c.goal_percentage_complete !== null
                            ? ` · ${c.goal_percentage_complete}% complete`
                            : ""}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-3">
                      {c.goal_percentage_complete !== null &&
                        c.goal_percentage_complete >= 100 && (
                          <Badge variant="secondary">Goal met</Badge>
                        )}
                      <span className="tabular-nums">
                        {c.this_month_spend_cents > 0
                          ? formatDollars(c.this_month_spend_cents)
                          : "—"}
                      </span>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function formatDollars(cents: number): string {
  const d = cents / 100;
  return `$${d.toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })}`;
}
