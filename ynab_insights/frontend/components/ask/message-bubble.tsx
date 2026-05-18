"use client";

import * as React from "react";
import { motion } from "motion/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Copy, RefreshCcw, AlertTriangle } from "lucide-react";
import { toast } from "sonner";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ToolTrace, type TraceTool } from "@/components/ask/tool-trace";

export type TurnStatus = "streaming" | "complete" | "errored" | "cancelled";

export interface Turn {
  id: string;
  question: string;
  answer: string;
  tools: TraceTool[];
  status: TurnStatus;
  error?: string;
}

export function MessageBubble({
  turn,
  onRegenerate,
}: {
  turn: Turn;
  onRegenerate?: (turnId: string) => void;
}) {
  const isStreaming = turn.status === "streaming";

  return (
    <motion.article
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className="space-y-3"
    >
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-4 py-2 text-sm text-primary-foreground">
          {turn.question}
        </div>
      </div>

      <div className="space-y-2">
        {turn.tools.length ? (
          <ToolTrace
            calls={turn.tools}
            collapsedByDefault={turn.status === "complete" && !turn.error}
          />
        ) : null}

        <div className="rounded-2xl rounded-tl-sm border bg-card px-4 py-3 text-sm leading-relaxed">
          {turn.status === "errored" ? (
            <div className="inline-flex items-center gap-2 text-destructive">
              <AlertTriangle className="h-4 w-4" />
              <span>{turn.error ?? "Something went wrong."}</span>
            </div>
          ) : turn.answer || isStreaming ? (
            <AnswerMarkdown text={turn.answer} streaming={isStreaming} />
          ) : (
            <span className="text-muted-foreground">Thinking…</span>
          )}
        </div>

        {turn.status !== "streaming" ? (
          <div className="flex justify-end gap-1">
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(turn.answer);
                  toast.success("Copied to clipboard");
                } catch {
                  toast.error("Couldn't copy");
                }
              }}
            >
              <Copy className="mr-1 h-3 w-3" /> Copy
            </Button>
            {onRegenerate ? (
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-xs"
                onClick={() => onRegenerate(turn.id)}
              >
                <RefreshCcw className="mr-1 h-3 w-3" /> Regenerate
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
    </motion.article>
  );
}

function AnswerMarkdown({
  text,
  streaming,
}: {
  text: string;
  streaming: boolean;
}) {
  return (
    <div
      className={cn(
        "prose prose-sm max-w-none dark:prose-invert",
        "prose-p:my-2 prose-li:my-0 prose-ul:my-2 prose-ol:my-2",
        "prose-headings:font-semibold prose-headings:my-2",
        "prose-code:rounded prose-code:bg-muted prose-code:px-1 prose-code:py-0.5",
        "prose-pre:bg-muted prose-pre:text-foreground",
      )}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>
        {text || (streaming ? "" : " ")}
      </ReactMarkdown>
      {streaming ? (
        <span className="ml-0.5 inline-block h-3.5 w-1 animate-pulse bg-primary align-middle" />
      ) : null}
    </div>
  );
}
