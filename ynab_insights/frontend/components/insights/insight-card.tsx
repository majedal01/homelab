"use client";

import * as React from "react";
import Link from "next/link";
import { motion } from "motion/react";
import { Sparkles, X } from "lucide-react";
import { toast } from "sonner";

import { cn } from "@/lib/utils";
import { MOTION } from "@/lib/motion";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { InsightResponse } from "@/lib/api-types";
import { dismiss as dismissLocal, restore as restoreLocal } from "@/lib/dismissals";
import { SubscriptionAuditCard } from "@/components/insights/cards/subscription-audit-card";
import { SpendingAnomalyCard } from "@/components/insights/cards/spending-anomaly-card";
import { CashflowForecastCard } from "@/components/insights/cards/cashflow-forecast-card";
import { CategoryProjectionCard } from "@/components/insights/cards/category-projection-card";
import { DebtPayoffCard } from "@/components/insights/cards/debt-payoff-card";
import { GoalTrajectoryCard } from "@/components/insights/cards/goal-trajectory-card";
import { GoalSetupPromptCard } from "@/components/insights/cards/goal-setup-prompt-card";
import { CategoryDriftCard } from "@/components/insights/cards/category-drift-card";
import { YearInMoneyCard } from "@/components/insights/cards/year-in-money-card";

const CARD_TYPE_LABEL: Record<InsightResponse["card_type"], string> = {
  subscription_audit: "Subscription",
  spending_anomaly: "Anomaly",
  cashflow_forecast: "Forecast",
  category_projection: "Projection",
  debt_payoff: "Debt",
  goal_trajectory: "Goal",
  goal_setup_prompt: "Goal",
  category_drift: "Drift",
  year_in_money: "Year in money",
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
    case "category_projection":
      return <CategoryProjectionCard data={data} />;
    case "debt_payoff":
      return <DebtPayoffCard data={data} />;
    case "goal_trajectory":
      return <GoalTrajectoryCard data={data} />;
    case "goal_setup_prompt":
      return <GoalSetupPromptCard data={data} />;
    case "category_drift":
      return <CategoryDriftCard data={data} />;
    case "year_in_money":
      return <YearInMoneyCard data={data} />;
  }
}

export function InsightCard({
  insight,
  index,
  onDismissChange,
}: {
  insight: InsightResponse;
  index: number;
  /** Called after we mutate localStorage so the parent can re-filter. */
  onDismissChange?: () => void;
}) {
  function onDismiss(e: React.MouseEvent): void {
    e.preventDefault();
    e.stopPropagation();
    // Dismissals are local-only in v2.5. Write to localStorage; the
    // parent feed re-filters via onDismissChange.
    dismissLocal(insight.dedup_key);
    onDismissChange?.();
    toast("Dismissed", {
      action: {
        label: "Undo",
        onClick: () => {
          restoreLocal(insight.dedup_key);
          onDismissChange?.();
        },
      },
      duration: 5000,
    });
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, x: 80 }}
      transition={{
        duration: MOTION.d.base,
        ease: MOTION.e.out as unknown as [number, number, number, number],
        delay: Math.min(index, 8) * MOTION.stagger,
      }}
      layout
      layoutId={`insight-card-${insight.id}`}
      className="relative h-full"
    >
      <Link
        href={`/insights/${insight.id}`}
        className={cn(
          // h-full + flex column lets the body fill any extra row height
          // the grid hands the cell, so two cards side-by-side always
          // share a baseline. Without this, a short card looks like it
          // has a phantom gap under it.
          "group flex h-full flex-col rounded-lg border bg-card/80 backdrop-blur p-5 shadow-sm",
          "transition-all duration-200",
          "hover:-translate-y-0.5 hover:shadow-md hover:border-foreground/30",
        )}
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
