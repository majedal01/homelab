"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { LogOut, RefreshCw, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { clearAllDismissals } from "@/lib/dismissals";
import type { SessionPublic } from "@/lib/api-types";

export function SettingsPanel({ session }: { session: SessionPublic }) {
  const router = useRouter();
  const [refreshing, setRefreshing] = React.useState(false);
  const [ending, setEnding] = React.useState(false);

  async function refresh() {
    setRefreshing(true);
    try {
      const r = await fetch("/api/session/refresh", { method: "POST" });
      if (!r.ok) {
        toast.error("Couldn't refresh", {
          description: `Backend returned ${r.status}.`,
        });
        return;
      }
      toast("Pulled fresh YNAB data.");
      router.refresh();
    } finally {
      setRefreshing(false);
    }
  }

  async function endSession() {
    setEnding(true);
    try {
      await fetch("/api/session", { method: "DELETE" });
    } finally {
      router.replace("/welcome");
    }
  }

  function clearDismissals() {
    clearAllDismissals();
    toast("Dismissals cleared. Closed cards will come back on next refresh.");
  }

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card>
        <CardContent className="space-y-3 p-5">
          <div>
            <p className="text-xs font-medium uppercase text-muted-foreground">
              Active budget
            </p>
            <p className="text-base">{session.budget_name ?? "Not picked"}</p>
          </div>
          <Row label="Session opened" value={formatDateTime(session.created_at)} />
          <Row
            label="YNAB last synced"
            value={
              session.last_synced_at ? formatDateTime(session.last_synced_at) : "Never"
            }
          />
          <Row label="Session expires" value={formatRelative(session.expires_at)} />
          {session.anthropic_model && (
            <Row label="Model" value={modelLabel(session.anthropic_model)} />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-3 p-5">
          <Button
            variant="outline"
            className="w-full justify-start"
            onClick={refresh}
            disabled={refreshing}
          >
            <RefreshCw className={`mr-2 h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
            Refresh YNAB data
          </Button>
          <Button
            variant="outline"
            className="w-full justify-start"
            onClick={clearDismissals}
          >
            <Trash2 className="mr-2 h-4 w-4" />
            Clear dismissed insights
          </Button>
          <Button
            variant="destructive"
            className="w-full justify-start"
            onClick={endSession}
            disabled={ending}
          >
            <LogOut className="mr-2 h-4 w-4" />
            End session
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium tabular-nums">{value}</span>
    </div>
  );
}

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatRelative(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const diffMs = d.getTime() - Date.now();
  if (diffMs <= 0) return "expired";
  const mins = Math.round(diffMs / 60000);
  if (mins < 60) return `in ${mins} min`;
  const hrs = Math.round(mins / 60);
  return `in ~${hrs} hr`;
}

function modelLabel(modelId: string): string {
  if (modelId.startsWith("claude-haiku")) return "Haiku 4.5";
  if (modelId.startsWith("claude-sonnet")) return "Sonnet 4.6";
  if (modelId.startsWith("claude-opus")) return "Opus 4.8";
  return modelId;
}
