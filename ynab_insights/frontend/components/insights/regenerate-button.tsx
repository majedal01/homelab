"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { regenerateAllInsights } from "@/app/insights/actions";

export function RegenerateButton() {
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();

  function onClick(): void {
    startTransition(async () => {
      try {
        const summary = await regenerateAllInsights();
        const errored = summary.runs.filter((r) => r.status === "error");
        const description =
          errored.length > 0
            ? `${summary.created} new · ${summary.updated} refreshed · ${errored.length} errored`
            : `${summary.created} new · ${summary.updated} refreshed`;

        if (summary.created === 0 && summary.updated === 0 && errored.length === 0) {
          toast("Nothing new to surface.");
        } else if (errored.length > 0) {
          toast.warning("Regenerated with errors", { description });
        } else {
          toast("Regenerated", { description });
        }
        router.refresh();
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        toast.error("Couldn't regenerate.", { description: message });
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
