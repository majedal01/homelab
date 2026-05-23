"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "motion/react";
import { Sparkles, X } from "lucide-react";
import { toast } from "sonner";

import { cn } from "@/lib/utils";
import { MOTION } from "@/lib/motion";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { InsightResponse } from "@/lib/api-types";
import { dismissInsight, restoreInsight } from "@/app/insights/actions";
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
  const router = useRouter();
  const [hidden, setHidden] = React.useState(false);

  function onDismiss(e: React.MouseEvent): void {
    e.preventDefault();
    e.stopPropagation();
    // Optimistic: hide locally first, then persist. Toast carries an
    // Undo affordance backed by the /restore endpoint.
    setHidden(true);
    void dismissInsight(insight.id).then(() => router.refresh());
    toast("Dismissed", {
      action: {
        label: "Undo",
        onClick: () => {
          setHidden(false);
          void restoreInsight(insight.id).then(() => router.refresh());
        },
      },
      duration: 5000,
    });
  }

  if (hidden) return null;

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
      className="relative"
    >
      <Link
        href={`/insights/${insight.id}`}
        className={cn(
          "group block rounded-lg border bg-card/80 backdrop-blur p-5 shadow-sm",
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
