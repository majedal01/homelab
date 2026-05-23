"use server";

import { revalidatePath } from "next/cache";
import { apiFetch } from "@/lib/api";
import type { GenerateResponse, InsightResponse } from "@/lib/api-types";

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

/** Server action: fire all generators on demand. */
export async function regenerateAllInsights(
  budgetId: string,
): Promise<GenerateResponse> {
  const result = await apiFetch<GenerateResponse>(
    `/api/insights/generate?budget_id=${encodeURIComponent(budgetId)}`,
    { method: "POST" },
  );
  revalidatePath("/insights");
  return result;
}
