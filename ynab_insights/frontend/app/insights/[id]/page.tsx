import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, MessageSquare } from "lucide-react";

import { Aurora } from "@/components/brand/aurora";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { apiFetch, requireSession } from "@/lib/api";
import type { InsightResponse } from "@/lib/api-types";
import { SubscriptionAuditDetail } from "@/components/insights/details/subscription-audit-detail";
import { SpendingAnomalyDetail } from "@/components/insights/details/spending-anomaly-detail";
import { CashflowForecastDetail } from "@/components/insights/details/cashflow-forecast-detail";
import { GoalTrajectoryDetail } from "@/components/insights/details/goal-trajectory-detail";
import { CategoryDriftDetail } from "@/components/insights/details/category-drift-detail";
import { YearInMoneyDetail } from "@/components/insights/details/year-in-money-detail";
import { DismissButton } from "@/components/insights/dismiss-button";

export const dynamic = "force-dynamic";

const CARD_TYPE_LABEL: Record<InsightResponse["card_type"], string> = {
  subscription_audit: "Subscription audit",
  spending_anomaly: "Spending anomaly",
  cashflow_forecast: "Cashflow forecast",
  goal_trajectory: "Goal trajectory",
  category_drift: "Category drift",
  year_in_money: "Year in money",
};

function renderBody(insight: InsightResponse): React.ReactElement {
  const data = insight.structured_data;
  switch (data.card_type) {
    case "subscription_audit":
      return <SubscriptionAuditDetail data={data} />;
    case "spending_anomaly":
      return <SpendingAnomalyDetail data={data} />;
    case "cashflow_forecast":
      return <CashflowForecastDetail data={data} />;
    case "goal_trajectory":
      return <GoalTrajectoryDetail data={data} />;
    case "category_drift":
      return <CategoryDriftDetail data={data} />;
    case "year_in_money":
      return <YearInMoneyDetail data={data} />;
  }
}

function buildAskPrompt(insight: InsightResponse): string {
  const data = insight.structured_data;
  switch (data.card_type) {
    case "subscription_audit":
      return `Tell me about my recurring ${data.payee_name} charges and whether I should keep this subscription.`;
    case "spending_anomaly":
      return `Why has my ${data.category_name} spending changed this week? Walk me through the top transactions.`;
    case "cashflow_forecast":
      return "Based on my last 90 days, where could I trim spending to improve my 90-day balance?";
    case "goal_trajectory":
      return `Am I on track to hit my ${data.category_name} goal? What would help me move faster?`;
    case "category_drift":
      return `What changed about my ${data.category_name} spending over the last year?`;
    case "year_in_money":
      return `Walk me through the standout moments from ${data.period_label}.`;
  }
}

export default async function InsightDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  await requireSession();
  const { id } = await params;
  const numericId = Number(id);
  if (!Number.isFinite(numericId)) {
    notFound();
  }
  let insight: InsightResponse;
  try {
    insight = await apiFetch<InsightResponse>(`/api/insights/${numericId}`);
  } catch {
    notFound();
  }

  const askPrompt = buildAskPrompt(insight);

  return (
    <>
      <Aurora variant="quiet" />
      <div className="mx-auto flex max-w-4xl flex-col gap-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="space-y-1">
            <Button variant="ghost" size="sm" asChild className="-ml-2">
              <Link href="/insights">
                <ArrowLeft className="mr-2 h-3.5 w-3.5" /> Back to feed
              </Link>
            </Button>
            <div className="flex items-center gap-2">
              <Badge variant="secondary" className="text-[10px] uppercase tracking-wide">
                {CARD_TYPE_LABEL[insight.card_type]}
              </Badge>
            </div>
            <h1 className="text-2xl font-semibold tracking-tight">{insight.title}</h1>
            <p className="max-w-2xl text-sm text-muted-foreground">{insight.summary}</p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" asChild>
              <Link href={`/ask?prefill=${encodeURIComponent(askPrompt)}`}>
                <MessageSquare className="mr-2 h-3.5 w-3.5" /> Discuss in Ask
              </Link>
            </Button>
            <DismissButton dedupKey={insight.dedup_key} />
          </div>
        </div>

        {renderBody(insight)}

        <div className="border-t pt-4 text-xs text-muted-foreground">
          Generated {insight.generated_at}
          {insight.refreshed_at !== insight.generated_at
            ? ` · refreshed ${insight.refreshed_at}`
            : ""}
        </div>
      </div>
    </>
  );
}
