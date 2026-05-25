import { apiFetch, requireSession } from "@/lib/api";
import type { InsightResponse } from "@/lib/api-types";
import { Aurora } from "@/components/brand/aurora";
import { DemoBanner } from "@/components/demo/demo-banner";
import { AutoRegen } from "@/components/insights/auto-regen";
import { CardTypeFilter } from "@/components/insights/card-type-filter";
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
  let totalCount = 0;
  let countsByType: Record<string, number> = {};
  if (session.budget_id) {
    insights = await apiFetch<InsightResponse[]>(
      `/api/insights?limit=${PAGE_SIZE + 1}&offset=${offset}${
        params.card_type ? `&card_type=${encodeURIComponent(params.card_type)}` : ""
      }`,
    ).catch(() => [] as InsightResponse[]);

    // Pull the full unfiltered set with a generous limit to count per type
    // for the filter-pill badges. Cheap compared to the LLM-driven generate.
    const all = await apiFetch<InsightResponse[]>("/api/insights?limit=100").catch(
      () => [] as InsightResponse[],
    );
    totalCount = all.length;
    countsByType = all.reduce<Record<string, number>>((acc, i) => {
      acc[i.card_type] = (acc[i.card_type] ?? 0) + 1;
      return acc;
    }, {});
  }

  const hasMore = insights.length > PAGE_SIZE;
  const visible = insights.slice(0, PAGE_SIZE);

  // Auto-regen criteria: budget picked, no insights yet, no filter applied
  // (filtering on an empty feed is a typing-things-into-Google moment, not
  // a "please generate" signal).
  const shouldAutoRegen =
    Boolean(session.budget_id) && totalCount === 0 && !params.card_type;

  return (
    <>
      <Aurora variant="primary" />
      <div className="mx-auto flex max-w-4xl flex-col gap-4">
        {session.is_demo && <DemoBanner />}
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

        {session.budget_id && (
          <CardTypeFilter counts={countsByType} />
        )}

        <AutoRegen shouldFire={shouldAutoRegen} cardCount={totalCount} />

        {!shouldAutoRegen && (
          <InsightFeed insights={visible} offset={offset} hasMore={hasMore} />
        )}
      </div>
    </>
  );
}
