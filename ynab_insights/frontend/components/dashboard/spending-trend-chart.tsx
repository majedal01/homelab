"use client";

import * as React from "react";
import { motion } from "motion/react";
import { BarChart } from "@tremor/react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Tabs,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import type { MonthlyTrendPoint } from "@/lib/metrics";

type WindowKey = "3m" | "6m" | "12m";

export interface SpendingTrendChartProps {
  /**
   * Trend points in oldest-first order, covering the longest window we offer
   * (12 months). The component slices to the active window client-side.
   */
  points: MonthlyTrendPoint[];
  initialWindow?: WindowKey;
}

const WINDOW_LENGTH: Record<WindowKey, number> = { "3m": 3, "6m": 6, "12m": 12 };

function shortDollars(cents: number): string {
  const abs = Math.abs(cents) / 100;
  if (abs >= 1000) return `$${(abs / 1000).toFixed(abs >= 10000 ? 0 : 1)}K`;
  return `$${abs.toFixed(0)}`;
}

export function SpendingTrendChart({
  points,
  initialWindow = "6m",
}: SpendingTrendChartProps) {
  const [windowKey, setWindowKey] = React.useState<WindowKey>(initialWindow);
  const sliced = React.useMemo(() => {
    const n = WINDOW_LENGTH[windowKey];
    return points
      .slice(-n)
      .map((p) => ({
        month: p.month,
        Spending: p.spending / 100,
        Income: p.income / 100,
      }));
  }, [points, windowKey]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: 0.18, ease: "easeOut" }}
    >
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-2 pb-3 sm:items-center">
          <div>
            <CardTitle>Spending trend</CardTitle>
            <p className="text-xs text-muted-foreground">
              On-budget spending and income, by month
            </p>
          </div>
          <Tabs
            value={windowKey}
            onValueChange={(v) => setWindowKey(v as WindowKey)}
          >
            <TabsList>
              <TabsTrigger value="3m">3M</TabsTrigger>
              <TabsTrigger value="6m">6M</TabsTrigger>
              <TabsTrigger value="12m">12M</TabsTrigger>
            </TabsList>
          </Tabs>
        </CardHeader>
        <CardContent>
          <BarChart
            data={sliced}
            index="month"
            categories={["Spending", "Income"]}
            colors={["rose", "emerald"]}
            valueFormatter={(v) => shortDollars(v * 100)}
            yAxisWidth={56}
            showLegend
            className="h-72"
          />
        </CardContent>
      </Card>
    </motion.div>
  );
}
