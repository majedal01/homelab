"use client";

import * as React from "react";
import { MessageSquare, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Composer } from "@/components/ask/composer";
import { SuggestedChips } from "@/components/ask/suggested-chips";
import { MessageBubble, type Turn } from "@/components/ask/message-bubble";
import type { TraceTool } from "@/components/ask/tool-trace";
import { parseAskEvent, readSse } from "@/lib/ask-stream";
import type { SuggestionResponse } from "@/lib/api-types";

const STORAGE_KEY = "ask:turns:v1";

function loadTurns(): Turn[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Turn[];
    // Streaming-status turns from a refresh shouldn't stay "streaming".
    return parsed.map((t) =>
      t.status === "streaming" ? { ...t, status: "cancelled" } : t,
    );
  } catch {
    return [];
  }
}

function saveTurns(turns: Turn[]): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(turns));
  } catch {
    // Quota exceeded or storage disabled — silently skip persistence.
  }
}

function historyFor(turns: Turn[]): { role: "user" | "assistant"; content: string }[] {
  // Only completed turns contribute to history; cancelled and errored turns
  // would leave Claude with a dangling user turn that confuses follow-ups.
  const out: { role: "user" | "assistant"; content: string }[] = [];
  for (const t of turns) {
    if (t.status !== "complete") continue;
    out.push({ role: "user", content: t.question });
    out.push({ role: "assistant", content: t.answer });
  }
  return out;
}

export default function AskPage() {
  const [turns, setTurns] = React.useState<Turn[]>(() => loadTurns());
  const [input, setInput] = React.useState("");
  const [suggestions, setSuggestions] = React.useState<string[] | null>(null);
  const abortRef = React.useRef<AbortController | null>(null);
  const scrollAnchorRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    saveTurns(turns);
  }, [turns]);

  React.useEffect(() => {
    scrollAnchorRef.current?.scrollIntoView({ block: "end" });
  }, [turns]);

  // Load suggestions on first paint only (empty-state hint).
  React.useEffect(() => {
    if (turns.length) return;
    let cancelled = false;
    fetch("/api/suggestions", { cache: "no-store" })
      .then((r) => (r.ok ? (r.json() as Promise<SuggestionResponse>) : null))
      .then((data) => {
        if (cancelled || !data) return;
        setSuggestions(data.suggestions);
      })
      .catch(() => {
        if (!cancelled) setSuggestions([]);
      });
    return () => {
      cancelled = true;
    };
  }, [turns.length]);

  const isStreaming = turns.some((t) => t.status === "streaming");

  const submit = React.useCallback(
    async (questionInput: string, regenerateTurnId?: string) => {
      const question = questionInput.trim();
      if (!question) return;

      const turnId =
        regenerateTurnId ??
        (typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : String(Date.now()));

      // Compute priors from the current state snapshot. For regenerate, drop
      // the turn being regenerated and everything after it; for a new turn,
      // priors are everything we've accumulated so far.
      const priorTurns: Turn[] = regenerateTurnId
        ? turns.slice(0, turns.findIndex((t) => t.id === regenerateTurnId))
        : turns;

      setTurns(() => [
        ...priorTurns,
        {
          id: turnId,
          question,
          answer: "",
          tools: [],
          status: "streaming",
        },
      ]);

      setInput("");
      setSuggestions(null);

      const ctrl = new AbortController();
      abortRef.current = ctrl;

      try {
        const res = await fetch("/api/ask", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            question,
            history: historyFor(priorTurns),
          }),
          signal: ctrl.signal,
        });

        if (!res.ok) {
          const text = await res.text().catch(() => "");
          throw new Error(text || `HTTP ${res.status}`);
        }

        let errorMessage: string | null = null;
        for await (const msg of readSse(res, ctrl.signal)) {
          const evt = parseAskEvent(msg);
          if (!evt) continue;
          if (evt.type === "token") {
            setTurns((prev) =>
              prev.map((t) =>
                t.id === turnId
                  ? { ...t, answer: t.answer + evt.text }
                  : t,
              ),
            );
          } else if (evt.type === "tool_use") {
            const newTool: TraceTool = {
              id: evt.id,
              tool: evt.tool,
              input: evt.input,
              pending: true,
            };
            setTurns((prev) =>
              prev.map((t) =>
                t.id === turnId
                  ? { ...t, tools: [...t.tools, newTool] }
                  : t,
              ),
            );
          } else if (evt.type === "tool_result") {
            setTurns((prev) =>
              prev.map((t) =>
                t.id === turnId
                  ? {
                      ...t,
                      tools: t.tools.map((c) =>
                        c.id === evt.id
                          ? {
                              ...c,
                              output: evt.output,
                              is_error: evt.is_error,
                              pending: false,
                            }
                          : c,
                      ),
                    }
                  : t,
              ),
            );
          } else if (evt.type === "done") {
            // No-op: completion is marked when the stream ends.
          } else if (evt.type === "error") {
            errorMessage = evt.message;
          }
        }

        setTurns((prev) =>
          prev.map((t) => {
            if (t.id !== turnId) return t;
            if (ctrl.signal.aborted) {
              return { ...t, status: "cancelled" };
            }
            if (errorMessage) {
              return { ...t, status: "errored", error: errorMessage };
            }
            return { ...t, status: "complete" };
          }),
        );
      } catch (err) {
        if (
          err instanceof DOMException &&
          (err.name === "AbortError" || err.name === "TimeoutError")
        ) {
          setTurns((prev) =>
            prev.map((t) =>
              t.id === turnId ? { ...t, status: "cancelled" } : t,
            ),
          );
          return;
        }
        const message = err instanceof Error ? err.message : String(err);
        setTurns((prev) =>
          prev.map((t) =>
            t.id === turnId
              ? { ...t, status: "errored", error: message }
              : t,
          ),
        );
        toast.error("Ask failed", { description: message });
      } finally {
        abortRef.current = null;
      }
    },
    [turns],
  );

  function cancel() {
    abortRef.current?.abort();
  }

  function clearAll() {
    abortRef.current?.abort();
    setTurns([]);
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Ask</h1>
          <p className="text-sm text-muted-foreground">
            Natural-language questions about your YNAB data. The agent calls
            read-only tools against the local database to answer.
          </p>
        </div>
        {turns.length ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={clearAll}
            className="text-xs text-muted-foreground"
          >
            <Trash2 className="mr-1 h-3.5 w-3.5" />
            Clear conversation
          </Button>
        ) : null}
      </div>

      {turns.length === 0 ? (
        <div className="flex flex-col items-center gap-6 rounded-lg border bg-card p-8">
          <div className="flex flex-col items-center gap-2 text-center">
            <div className="rounded-full bg-muted p-3 text-muted-foreground">
              <MessageSquare className="h-5 w-5" />
            </div>
            <h3 className="text-sm font-medium">Ask anything about your money</h3>
            <p className="max-w-md text-xs text-muted-foreground">
              Multi-turn conversation, streaming responses, visible tool calls.
              The agent answers from your synced data. No questions leave the
              tailnet.
            </p>
          </div>
          <SuggestedChips
            suggestions={suggestions ?? []}
            loading={suggestions === null}
            onPick={(s) => submit(s)}
          />
        </div>
      ) : (
        <div className="space-y-6">
          {turns.map((turn, i) => (
            <MessageBubble
              key={turn.id}
              turn={turn}
              onRegenerate={
                // Only the last turn is regenerable — re-running an earlier
                // turn would invalidate subsequent assistant context.
                i === turns.length - 1 && !isStreaming
                  ? (id) => submit(turn.question, id)
                  : undefined
              }
            />
          ))}
          <div ref={scrollAnchorRef} />
        </div>
      )}

      <div className="sticky bottom-4">
        <Composer
          value={input}
          onChange={setInput}
          onSubmit={() => submit(input)}
          onCancel={cancel}
          isStreaming={isStreaming}
          autoFocus
        />
      </div>
    </div>
  );
}
