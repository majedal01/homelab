"use client";

import * as React from "react";
import { AnimatePresence, motion } from "motion/react";
import { ChevronDown, ChevronRight, Wrench, AlertTriangle, CheckCircle2 } from "lucide-react";

import { cn } from "@/lib/utils";

export interface TraceTool {
  id: string;
  tool: string;
  input: Record<string, unknown>;
  output?: unknown;
  is_error?: boolean;
  /** True while we've seen tool_use but not yet tool_result. */
  pending: boolean;
}

export function ToolTrace({
  calls,
  collapsedByDefault = false,
}: {
  calls: TraceTool[];
  collapsedByDefault?: boolean;
}) {
  const [groupOpen, setGroupOpen] = React.useState(!collapsedByDefault);

  if (!calls.length) return null;

  return (
    <div className="rounded-md border bg-card/60">
      <button
        type="button"
        onClick={() => setGroupOpen((s) => !s)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-xs text-muted-foreground hover:text-foreground"
      >
        <span className="inline-flex items-center gap-1.5">
          <Wrench className="h-3.5 w-3.5" />
          {calls.length} tool {calls.length === 1 ? "call" : "calls"}
          {calls.some((c) => c.pending) ? " · running…" : ""}
        </span>
        {groupOpen ? (
          <ChevronDown className="h-3.5 w-3.5" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5" />
        )}
      </button>
      <AnimatePresence initial={false}>
        {groupOpen ? (
          <motion.div
            key="content"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="overflow-hidden"
          >
            <ul className="divide-y divide-border border-t">
              <AnimatePresence initial={false}>
                {calls.map((c) => (
                  <motion.li
                    key={c.id}
                    initial={{ opacity: 0, x: -4 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.22, ease: "easeOut" }}
                    layout
                  >
                    <ToolCallRow call={c} />
                  </motion.li>
                ))}
              </AnimatePresence>
            </ul>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

function ToolCallRow({ call }: { call: TraceTool }) {
  const [open, setOpen] = React.useState(false);

  let StatusIcon: React.ComponentType<{ className?: string }>;
  let statusClass: string;
  if (call.pending) {
    StatusIcon = SpinnerDot;
    statusClass = "text-muted-foreground";
  } else if (call.is_error) {
    StatusIcon = AlertTriangle;
    statusClass = "text-destructive";
  } else {
    StatusIcon = CheckCircle2;
    statusClass = "text-emerald-600 dark:text-emerald-400";
  }

  return (
    <div className="px-3 py-2">
      <button
        type="button"
        onClick={() => setOpen((s) => !s)}
        className="flex w-full items-center justify-between gap-2 text-left text-xs"
      >
        <span className="inline-flex items-center gap-1.5">
          <StatusIcon className={cn("h-3.5 w-3.5 shrink-0", statusClass)} />
          <span className="font-mono">{call.tool}</span>
        </span>
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
        )}
      </button>
      {open ? (
        <div className="mt-2 space-y-2 text-[11px]">
          <div>
            <div className="mb-1 text-muted-foreground">input</div>
            <pre className="overflow-x-auto rounded bg-muted p-2 font-mono text-[11px] leading-relaxed">
              {JSON.stringify(call.input, null, 2)}
            </pre>
          </div>
          {call.pending ? (
            <div className="text-xs text-muted-foreground">running…</div>
          ) : (
            <div>
              <div className="mb-1 text-muted-foreground">output</div>
              <pre
                className={cn(
                  "max-h-64 overflow-auto rounded bg-muted p-2 font-mono text-[11px] leading-relaxed",
                  call.is_error ? "text-destructive" : "",
                )}
              >
                {typeof call.output === "string"
                  ? call.output
                  : JSON.stringify(call.output, null, 2)}
              </pre>
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}

function SpinnerDot({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-block h-2 w-2 animate-pulse rounded-full bg-muted-foreground",
        className,
      )}
    />
  );
}
