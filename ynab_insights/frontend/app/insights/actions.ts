"use server";

import { revalidatePath } from "next/cache";
import { apiFetch } from "@/lib/api";
import type {
  GenerateResponse,
  InsightResponse,
  InsightRunResponse,
} from "@/lib/api-types";

export interface RegenerationSummary {
  runs: InsightRunResponse[];
  created: number;
  updated: number;
}

/**
 * Server action: dismiss an insight and revalidate the feed and detail
 * routes so the user sees the card disappear on navigation.
 */
export async function dismissInsight(id: number): Promise<void> {
  await apiFetch<InsightResponse>(`/api/insights/${id}/dismiss`, {
    method: "POST",
  });
  revalidatePath("/insights");
  revalidatePath(`/insights/${id}`);
}

/**
 * Server action: fire every registered generator. Looks up the resulting
 * `InsightRun` rows so the caller can show created/updated counts (otherwise
 * the user clicks the button and sees no change, since most invocations
 * refresh the same cards rather than producing new ones).
 */
export async function regenerateAllInsights(
  budgetId: string,
): Promise<RegenerationSummary> {
  const generate = await apiFetch<GenerateResponse>(
    `/api/insights/generate?budget_id=${encodeURIComponent(budgetId)}`,
    { method: "POST" },
  );

  // Pull the most recent runs and pick out the ones we just kicked off.
  const recent = await apiFetch<InsightRunResponse[]>(
    `/api/insights/runs?limit=${Math.max(generate.run_ids.length * 2, 10)}`,
  );
  const ids = new Set(generate.run_ids);
  const runs = recent.filter((r) => ids.has(r.id));
  const created = runs.reduce((s, r) => s + r.insights_created, 0);
  const updated = runs.reduce((s, r) => s + r.insights_updated, 0);

  revalidatePath("/insights");
  return { runs, created, updated };
}
