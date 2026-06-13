"use server";

import { revalidatePath } from "next/cache";
import { apiFetch } from "@/lib/api";
import type { GenerateResponse, InsightRunResponse } from "@/lib/api-types";

export interface RegenerationSummary {
  runs: InsightRunResponse[];
  created: number;
  updated: number;
}

/**
 * Server action: fire every registered generator against the session's
 * snapshot. Looks up the resulting `InsightRun` rows so the caller can
 * show created/updated counts.
 */
export async function regenerateAllInsights(): Promise<RegenerationSummary> {
  const generate = await apiFetch<GenerateResponse>("/api/insights/generate", {
    method: "POST",
  });

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
