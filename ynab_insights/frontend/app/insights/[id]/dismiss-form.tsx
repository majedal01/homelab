"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { dismissInsight } from "@/app/insights/actions";

export function DismissForm({ id }: { id: number }) {
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();

  function onClick(): void {
    startTransition(async () => {
      await dismissInsight(id);
      router.push("/insights");
    });
  }

  return (
    <Button variant="outline" size="sm" onClick={onClick} disabled={pending}>
      <Trash2 className="mr-2 h-3.5 w-3.5" />
      Dismiss
    </Button>
  );
}
