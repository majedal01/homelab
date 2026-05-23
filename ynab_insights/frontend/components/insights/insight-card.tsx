"use client";

import * as React from "react";
import Link from "next/link";
import { motion } from "motion/react";
import { Sparkles, X } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { InsightResponse } from "@/lib/api-types";
import { dismissInsight } from "@/app/insights/actions";
import { SubscriptionAuditCard } from "@/components/insights/cards/subscription-audit-card";
import { SpendingAnomalyCard } from "@/components/insights/cards/spending-anomaly-card";
import { CashflowForecastCard } from "@/components/insights/cards/cashflow-forecast-card";
import { GoalTrajectoryCard } from "@/components/insights/cards/goal-trajectory-card";

const CARD_TYPE_LABEL: Record<InsightResponse["card_type"], string> = {
  subscription_audit: "Subscription",
  spending_anomaly: "Anomaly",
  cashflow_forecast: "Forecast",
  goal_trajectory: "Goal",
};

function CardBody({ insight }: { insight: InsightResponse }) {
  const data = insight.structured_data;
  switch (data.card_type) {
    case "subscription_audit":
      return <SubscriptionAuditCard data={data} />;
    case "spending_anomaly":
      return <SpendingAnomalyCard data={data} />;
    case "cashflow_forecast":
      return <CashflowForecastCard data={data} />;
    case "goal_trajectory":
      return <GoalTrajectoryCard data={data} />;
  }
}

export function InsightCard({
  insight,
  index,
}: {
  insight: InsightResponse;
  index: number;
}) {
  const [pending, startTransition] = React.useTransition();

  function onDismiss(e: React.MouseEvent): void {
    e.preventDefault();
    e.stopPropagation();
    startTransition(async () => {
      await dismissInsight(insight.id);
    });
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, delay: Math.min(index, 8) * 0.04 }}
      className={cn("relative", pending && "opacity-50")}
    >
      <Link
        href={`/insights/${insight.id}`}
        className="group block rounded-lg border bg-card p-5 transition-colors hover:border-foreground/30"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            <Badge variant="secondary" className="text-[10px] uppercase tracking-wide">
              {CARD_TYPE_LABEL[insight.card_type]}
            </Badge>
            {insight.llm_enhanced ? (
              <Sparkles
                className="h-3.5 w-3.5 text-muted-foreground"
                aria-label="LLM-enhanced copy"
              />
            ) : null}
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 opacity-0 transition-opacity group-hover:opacity-100"
            aria-label="Dismiss"
            onClick={onDismiss}
            disabled={pending}
          >
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
        <h3 className="mt-2 text-base font-semibold tracking-tight">
          {insight.title}
        </h3>
        <p className="mt-1 text-sm text-muted-foreground">{insight.summary}</p>
        <div className="mt-4">
          <CardBody insight={insight} />
        </div>
      </Link>
    </motion.div>
  );
}
