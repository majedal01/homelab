"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { regenerateAllInsights } from "@/app/insights/actions";

export function RegenerateButton({
  budgetId,
}: {
  budgetId: string;
}) {
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();

  function onClick(): void {
    startTransition(async () => {
      try {
        const summary = await regenerateAllInsights(budgetId);
        const errored = summary.runs.filter((r) => r.status === "error");
        const description =
          errored.length > 0
            ? `${summary.created} new, ${summary.updated} refreshed, ${errored.length} errored`
            : `${summary.created} new, ${summary.updated} refreshed`;

        if (summary.created === 0 && summary.updated === 0 && errored.length === 0) {
          toast.message("No insights to surface yet", {
            description:
              "Generators ran but found nothing new — sync more data or wait for the next cadence.",
          });
        } else if (errored.length > 0) {
          toast.warning("Regenerated with errors", { description });
        } else {
          toast.success("Regenerated", { description });
        }

        // revalidatePath alone marks the route stale but doesn't re-render
        // the page the user is sitting on. router.refresh() re-fetches the
        // RSC tree so any new/updated cards appear without a manual reload.
        router.refresh();
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        toast.error("Regeneration failed", { description: message });
      }
    });
  }

  return (
    <Button variant="outline" size="sm" onClick={onClick} disabled={pending}>
      <RefreshCw className={`mr-2 h-3.5 w-3.5 ${pending ? "animate-spin" : ""}`} />
      Regenerate
    </Button>
  );
}
