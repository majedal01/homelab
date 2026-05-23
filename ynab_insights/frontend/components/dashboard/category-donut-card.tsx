"use client";

import * as React from "react";
import { motion } from "motion/react";
import { DonutChart, Legend } from "@tremor/react";
import Link from "next/link";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDollars } from "@/lib/utils";
import type { CategorySpendRow } from "@/lib/metrics";

const TOP_N = 6;

const TREMOR_COLORS = [
  "indigo",
  "emerald",
  "amber",
  "rose",
  "slate",
  "violet",
  "cyan",
  "lime",
];

export interface CategoryDonutCardProps {
  /** Rows in descending-spend order; this card takes the top N and groups
   * the rest into a single "Other" slice. */
  rows: CategorySpendRow[];
  /** Date range label for the subtitle (e.g. "May 1–17"). */
  rangeLabel?: string;
  /**
   * Authoritative total to display in the donut center. When omitted the
   * card falls back to summing visible slices. The dashboard passes the
   * server's "Total Expenses" so refund-net categories (Education, etc.)
   * — which are excluded from the slice list because a pie can't render
   * negative values — still reduce the headline total, keeping it
   * identical to the "Spending" KPI.
   */
  totalCentsOverride?: number;
}

export function CategoryDonutCard({
  rows,
  rangeLabel,
  totalCentsOverride,
}: CategoryDonutCardProps) {
  const { sliced, sliceSum } = React.useMemo(() => {
    const positive = rows.filter((r) => r.spent_cents > 0);
    if (!positive.length) return { sliced: [], sliceSum: 0 };
    const top = positive.slice(0, TOP_N);
    const rest = positive.slice(TOP_N);
    const otherTotal = rest.reduce((s, r) => s + r.spent_cents, 0);
    const list = top.map((r, i) => ({
      name: r.category_name ?? "Uncategorized",
      category_id: r.category_id,
      value: r.spent_cents / 100,
      cents: r.spent_cents,
      color: TREMOR_COLORS[i % TREMOR_COLORS.length],
    }));
    if (otherTotal > 0) {
      list.push({
        name: "Other",
        category_id: null,
        value: otherTotal / 100,
        cents: otherTotal,
        color: "slate",
      });
    }
    const sum = list.reduce((s, x) => s + x.cents, 0);
    return { sliced: list, sliceSum: sum };
  }, [rows]);

  const total = totalCentsOverride ?? sliceSum;
  const refundOffset = total - sliceSum; // negative when refunds are netted in

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: 0.24, ease: "easeOut" }}
    >
      <Card>
        <CardHeader className="pb-3">
          <CardTitle>Where the money went</CardTitle>
          {rangeLabel ? (
            <p className="text-xs text-muted-foreground">{rangeLabel}</p>
          ) : null}
        </CardHeader>
        <CardContent>
          {sliced.length ? (
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center">
              <div className="relative mx-auto h-48 w-48 shrink-0">
                <DonutChart
                  data={sliced}
                  category="value"
                  index="name"
                  variant="donut"
                  colors={sliced.map((s) => s.color)}
                  valueFormatter={(v) => formatDollars(Math.round(v * 100))}
                  className="h-48 w-48"
                  showLabel={false}
                />
                <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                  <span className="text-xs uppercase tracking-wide text-muted-foreground">
                    Total
                  </span>
                  <span className="font-mono text-lg font-semibold tabular-nums">
                    {formatDollars(total)}
                  </span>
                </div>
              </div>
              <div className="flex-1">
                <Legend
                  categories={sliced.map((s) => s.name)}
                  colors={sliced.map((s) => s.color)}
                  className="!flex-wrap"
                />
                <ul className="mt-3 divide-y divide-border text-sm">
                  {sliced.map((s) => (
                    <li
                      key={s.category_id ?? s.name}
                      className="flex justify-between py-1.5"
                    >
                      {s.category_id ? (
                        <Link
                          href={`/transactions?category_id=${s.category_id}`}
                          className="truncate text-primary hover:underline"
                        >
                          {s.name}
                        </Link>
                      ) : (
                        <span className="truncate text-muted-foreground">
                          {s.name}
                        </span>
                      )}
                      <span className="font-mono tabular-nums">
                        {formatDollars(s.cents)}
                      </span>
                    </li>
                  ))}
                </ul>
                {refundOffset < 0 ? (
                  <p className="mt-2 text-[11px] text-muted-foreground">
                    Includes {formatDollars(refundOffset)} of refunds posted
                    to expense categories.
                  </p>
                ) : null}
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              No spending in this range.
            </p>
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
}
