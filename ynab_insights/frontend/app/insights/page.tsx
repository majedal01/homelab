import { apiFetch, getSelectedBudgetId, qs } from "@/lib/api";
import type { BudgetResponse, InsightResponse } from "@/lib/api-types";
import { Aurora } from "@/components/brand/aurora";
import { InsightFeed } from "@/components/insights/feed";
import { RegenerateButton } from "@/components/insights/regenerate-button";

export const dynamic = "force-dynamic";

const PAGE_SIZE = 20;

interface InsightsSearchParams {
  offset?: string;
  include_dismissed?: string;
}

export default async function InsightsPage({
  searchParams,
}: {
  searchParams: Promise<InsightsSearchParams>;
}) {
  const params = await searchParams;
  const offset = Math.max(0, parseInt(params.offset ?? "0", 10) || 0);
  const includeDismissed = params.include_dismissed === "true";

  const budgets = await apiFetch<BudgetResponse[]>("/budgets").catch(() => []);
  const selected = await getSelectedBudgetId(budgets);

  // Fetch one extra so we know whether a "Older" link should render.
  const insights = await apiFetch<InsightResponse[]>(
    `/api/insights${qs({
      budget_id: selected ?? undefined,
      include_dismissed: includeDismissed,
      limit: PAGE_SIZE + 1,
      offset,
    })}`,
  ).catch(() => [] as InsightResponse[]);

  const hasMore = insights.length > PAGE_SIZE;
  const visible = insights.slice(0, PAGE_SIZE);

  return (
    <>
      <Aurora variant="primary" />
      <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Insights</h1>
          <p className="text-sm text-muted-foreground">
            Forward-looking analysis, pattern detection, and coaching. Cards
            refresh automatically; you can also regenerate on demand.
          </p>
        </div>
        {selected ? <RegenerateButton budgetId={selected} /> : null}
      </div>

      <InsightFeed insights={visible} offset={offset} hasMore={hasMore} />
      </div>
    </>
  );
}
