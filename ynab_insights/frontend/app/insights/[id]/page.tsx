import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, Compass, MessageSquare } from "lucide-react";

import { Aurora } from "@/components/brand/aurora";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { apiFetch, requireSession } from "@/lib/api";
import type { InsightResponse } from "@/lib/api-types";
import { SubscriptionAuditDetail } from "@/components/insights/details/subscription-audit-detail";
import { SpendingAnomalyDetail } from "@/components/insights/details/spending-anomaly-detail";
import { CashflowForecastDetail } from "@/components/insights/details/cashflow-forecast-detail";
import { CategoryProjectionDetail } from "@/components/insights/details/category-projection-detail";
import { DebtPayoffDetail } from "@/components/insights/details/debt-payoff-detail";
import { GoalTrajectoryDetail } from "@/components/insights/details/goal-trajectory-detail";
import { GoalSetupPromptDetail } from "@/components/insights/details/goal-setup-prompt-detail";
import { EmergencyFundCoverageDetail } from "@/components/insights/details/emergency-fund-coverage-detail";
import { SavingsRateTrendDetail } from "@/components/insights/details/savings-rate-trend-detail";
import { CategoryDriftDetail } from "@/components/insights/details/category-drift-detail";
import { YearInMoneyDetail } from "@/components/insights/details/year-in-money-detail";
import { DismissButton } from "@/components/insights/dismiss-button";

export const dynamic = "force-dynamic";

const CARD_TYPE_LABEL: Record<InsightResponse["card_type"], string> = {
  subscription_audit: "Subscription audit",
  spending_anomaly: "Spending anomaly",
  cashflow_forecast: "Cashflow forecast",
  category_projection: "Category projection",
  debt_payoff: "Debt payoff",
  goal_trajectory: "Goal trajectory",
  goal_setup_prompt: "Set goals to track",
  emergency_fund_coverage: "Emergency fund",
  savings_rate_trend: "Savings rate",
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
    case "category_projection":
      return <CategoryProjectionDetail data={data} />;
    case "debt_payoff":
      return <DebtPayoffDetail data={data} />;
    case "goal_trajectory":
      return <GoalTrajectoryDetail data={data} />;
    case "goal_setup_prompt":
      return <GoalSetupPromptDetail data={data} />;
    case "emergency_fund_coverage":
      return <EmergencyFundCoverageDetail data={data} />;
    case "savings_rate_trend":
      return <SavingsRateTrendDetail data={data} />;
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
    case "category_projection":
      return `Why is ${data.category_name} pacing ${data.direction} usual this month? Where can I trim?`;
    case "debt_payoff":
      return `Walk me through paydown strategies for ${data.account_name}. What's realistic if I add $100/mo?`;
    case "goal_setup_prompt":
      return "What categories make sense to set goals on first? Suggest targets I could enter in YNAB.";
    case "emergency_fund_coverage":
      return `My cash covers about ${data.coverage_months.toFixed(1)} months of expenses. How can I build toward ${data.target_months} months faster?`;
    case "savings_rate_trend":
      return "How is my savings rate trending over the last year, and what would move it up?";
    case "category_drift":
      return `What changed about my ${data.category_name} spending over the last year?`;
    case "year_in_money":
      return `Walk me through the standout moments from ${data.period_label}.`;
  }
}

/**
 * Build the deep-link from a card detail page into the matching /explore
 * slice. Returns null when the card type doesn't have a useful raw-data
 * view (e.g. cashflow forecast aggregates many categories at once).
 */
function buildExploreLink(insight: InsightResponse): { href: string; label: string } | null {
  const data = insight.structured_data;
  switch (data.card_type) {
    case "subscription_audit":
      return {
        href: `/explore?view=transactions&payee_contains=${encodeURIComponent(data.payee_name)}`,
        label: `Show all ${data.payee_name} charges`,
      };
    case "spending_anomaly": {
      const periodWord = data.cycle === "monthly" ? "month" : "week";
      return {
        href: `/explore?view=transactions&category_id=${encodeURIComponent(data.category_id)}&date_from=${encodeURIComponent(data.period_start)}&date_to=${encodeURIComponent(data.period_end)}`,
        label: `Open this ${periodWord}'s ${data.category_name} transactions`,
      };
    }
    case "category_projection":
      return {
        href: `/explore?view=transactions&category_id=${encodeURIComponent(data.category_id)}&date_from=${encodeURIComponent(data.month_start)}`,
        label: `Open this month's ${data.category_name} transactions`,
      };
    case "category_drift":
      return {
        href: `/explore?view=transactions&category_id=${encodeURIComponent(data.category_id)}`,
        label: `Show all ${data.category_name} transactions`,
      };
    case "goal_trajectory":
      return {
        href: `/explore?view=categories`,
        label: "Open in Categories",
      };
    case "goal_setup_prompt":
      return {
        href: `/explore?view=categories`,
        label: "Open in Categories",
      };
    case "emergency_fund_coverage":
      return {
        href: `/explore?view=accounts`,
        label: "Open accounts",
      };
    case "savings_rate_trend":
      return {
        href: `/explore?view=overview`,
        label: "Open overview",
      };
    case "debt_payoff":
      return {
        href: `/explore?view=accounts`,
        label: `Open ${data.account_name}`,
      };
    case "cashflow_forecast":
      return null;
    case "year_in_money":
      return {
        href: `/explore?view=transactions&date_from=${encodeURIComponent(data.period_start)}&date_to=${encodeURIComponent(data.period_end)}`,
        label: `Browse transactions from ${data.period_label}`,
      };
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
  const exploreLink = buildExploreLink(insight);

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
          <div className="flex flex-wrap gap-2">
            {exploreLink && (
              <Button variant="outline" size="sm" asChild>
                <Link href={exploreLink.href}>
                  <Compass className="mr-2 h-3.5 w-3.5" /> {exploreLink.label}
                </Link>
              </Button>
            )}
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
