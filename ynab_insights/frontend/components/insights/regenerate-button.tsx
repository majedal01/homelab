"use client";

import * as React from "react";
import { RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { regenerateAllInsights } from "@/app/insights/actions";

export function RegenerateButton({
  budgetId,
}: {
  budgetId: string;
}) {
  const [pending, startTransition] = React.useTransition();

  function onClick(): void {
    startTransition(async () => {
      try {
        const result = await regenerateAllInsights(budgetId);
        toast.success(
          `Generated ${result.run_ids.length} runs`,
          { description: "Feed will refresh momentarily." },
        );
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        toast.error("Regeneration failed", { description: message });
      }
    });
  }

  return (
    <Button variant="outline" size="sm" onClick={onClick} disabled={pending}>
      <RefreshCw
        className={`mr-2 h-3.5 w-3.5 ${pending ? "animate-spin" : ""}`}
      />
      Regenerate
    </Button>
  );
}
