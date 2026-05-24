import { apiFetch, requireSession } from "@/lib/api";
import type { InsightResponse } from "@/lib/api-types";
import { Aurora } from "@/components/brand/aurora";
import { InsightFeed } from "@/components/insights/feed";
import { RegenerateButton } from "@/components/insights/regenerate-button";

export const dynamic = "force-dynamic";

const PAGE_SIZE = 20;

interface InsightsSearchParams {
  offset?: string;
  card_type?: string;
}

export default async function InsightsPage({
  searchParams,
}: {
  searchParams: Promise<InsightsSearchParams>;
}) {
  const session = await requireSession();
  const params = await searchParams;
  const offset = Math.max(0, parseInt(params.offset ?? "0", 10) || 0);

  let insights: InsightResponse[] = [];
  if (session.budget_id) {
    insights = await apiFetch<InsightResponse[]>(
      `/api/insights?limit=${PAGE_SIZE + 1}&offset=${offset}${
        params.card_type ? `&card_type=${encodeURIComponent(params.card_type)}` : ""
      }`,
    ).catch(() => [] as InsightResponse[]);
  }

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
              {session.budget_name
                ? `What's worth your attention. ${session.budget_name}.`
                : "Pick a budget to start."}
            </p>
          </div>
          {session.budget_id && <RegenerateButton />}
        </div>
        <InsightFeed insights={visible} offset={offset} hasMore={hasMore} />
      </div>
    </>
  );
}
