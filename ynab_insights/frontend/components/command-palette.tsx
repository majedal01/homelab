"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Command } from "cmdk";
import {
  Compass,
  Inbox,
  MessageSquare,
  RefreshCw,
  Settings,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { toast } from "sonner";

import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";

const CARD_TYPES: { value: string; label: string }[] = [
  { value: "subscription_audit", label: "Subscriptions" },
  { value: "spending_anomaly", label: "Spending anomalies" },
  { value: "cashflow_forecast", label: "Cashflow forecast" },
  {
    value: "goal_trajectory,goal_setup_prompt,emergency_fund_coverage,savings_rate_trend",
    label: "Goals",
  },
  { value: "category_drift", label: "Category drift" },
  { value: "year_in_money", label: "Year in money" },
];

/**
 * Cmd/Ctrl+K palette. Mounted once globally. Holds its own open state.
 */
export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const [pending, setPending] = React.useState(false);

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function run(action: () => void | Promise<void>) {
    return async () => {
      setOpen(false);
      await action();
    };
  }

  function go(href: string) {
    return run(() => router.push(href));
  }

  async function regenerate() {
    setPending(true);
    try {
      const res = await fetch("/api/insights/generate", { method: "POST" });
      if (!res.ok) throw new Error(`${res.status}`);
      toast("Generating insights", { description: "Refresh momentarily." });
      router.refresh();
    } catch (err) {
      toast.error("Couldn't kick off generation", {
        description: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="p-0 overflow-hidden gap-0 max-w-lg">
        <DialogTitle className="sr-only">Command palette</DialogTitle>
        <Command label="Command palette" className="bg-transparent">
          <Command.Input
            placeholder="Search actions…"
            className="w-full border-b bg-transparent px-4 py-3 text-sm outline-none placeholder:text-muted-foreground"
          />
          <Command.List className="max-h-80 overflow-y-auto p-2">
            <Command.Empty className="px-3 py-6 text-center text-sm text-muted-foreground">
              Nothing matches.
            </Command.Empty>

            <Command.Group
              heading="Generate"
              className="text-xs text-muted-foreground [&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-2"
            >
              <PaletteItem
                icon={<RefreshCw className="h-3.5 w-3.5" />}
                label="Regenerate all insights"
                onSelect={run(regenerate)}
                disabled={pending}
              />
            </Command.Group>

            <Command.Group
              heading="Jump to"
              className="text-xs text-muted-foreground [&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-2"
            >
              <PaletteItem
                icon={<Inbox className="h-3.5 w-3.5" />}
                label="Insights"
                onSelect={go("/insights")}
              />
              <PaletteItem
                icon={<Compass className="h-3.5 w-3.5" />}
                label="Explore"
                onSelect={go("/explore")}
              />
              <PaletteItem
                icon={<Compass className="h-3.5 w-3.5" />}
                label="Explore: Accounts"
                onSelect={go("/explore?view=accounts")}
              />
              <PaletteItem
                icon={<Compass className="h-3.5 w-3.5" />}
                label="Explore: Categories"
                onSelect={go("/explore?view=categories")}
              />
              <PaletteItem
                icon={<Compass className="h-3.5 w-3.5" />}
                label="Explore: Transactions"
                onSelect={go("/explore?view=transactions")}
              />
              <PaletteItem
                icon={<MessageSquare className="h-3.5 w-3.5" />}
                label="Ask"
                onSelect={go("/ask")}
              />
              <PaletteItem
                icon={<Settings className="h-3.5 w-3.5" />}
                label="Settings"
                onSelect={go("/settings")}
              />
            </Command.Group>

            <Command.Group
              heading="Filter feed"
              className="text-xs text-muted-foreground [&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-2"
            >
              {CARD_TYPES.map((c) => (
                <PaletteItem
                  key={c.value}
                  icon={
                    c.value === "category_drift" ? (
                      <TrendingUp className="h-3.5 w-3.5" />
                    ) : c.value === "spending_anomaly" ? (
                      <TrendingDown className="h-3.5 w-3.5" />
                    ) : (
                      <Inbox className="h-3.5 w-3.5" />
                    )
                  }
                  label={`Show ${c.label} only`}
                  onSelect={go(`/insights?card_type=${c.value}`)}
                />
              ))}
            </Command.Group>
          </Command.List>
        </Command>
      </DialogContent>
    </Dialog>
  );
}

function PaletteItem({
  icon,
  label,
  onSelect,
  disabled,
}: {
  icon: React.ReactNode;
  label: string;
  onSelect: () => void;
  disabled?: boolean;
}) {
  return (
    <Command.Item
      onSelect={onSelect}
      disabled={disabled}
      className="flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm aria-selected:bg-accent aria-selected:text-accent-foreground data-[disabled=true]:opacity-50"
    >
      <span className="text-muted-foreground">{icon}</span>
      <span>{label}</span>
    </Command.Item>
  );
}
