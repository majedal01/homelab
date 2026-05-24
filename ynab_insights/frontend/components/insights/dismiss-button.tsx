"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { X } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { dismiss, restore } from "@/lib/dismissals";

export function DismissButton({ dedupKey }: { dedupKey: string }) {
  const router = useRouter();
  function onClick(): void {
    dismiss(dedupKey);
    toast("Dismissed", {
      action: {
        label: "Undo",
        onClick: () => {
          restore(dedupKey);
          router.refresh();
        },
      },
      duration: 5000,
    });
    router.push("/insights");
  }
  return (
    <Button variant="outline" size="sm" onClick={onClick}>
      <X className="mr-2 h-3.5 w-3.5" />
      Dismiss
    </Button>
  );
}
