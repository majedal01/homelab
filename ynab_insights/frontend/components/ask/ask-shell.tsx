"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";
import { MessageSquare, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Composer } from "@/components/ask/composer";
import { SuggestedChips } from "@/components/ask/suggested-chips";
import { MessageBubble, type Turn } from "@/components/ask/message-bubble";
import type { TraceTool } from "@/components/ask/tool-trace";
import { parseAskEvent, readSse } from "@/lib/ask-stream";

const STORAGE_KEY = "ask:turns:v1";

// Curated empty-state suggestions. In v2.5 the /suggestions endpoint is gone;
// these are hand-picked to exercise the agent's primary tools.
const SUGGESTIONS: string[] = [
  "What did I spend the most on last month?",
  "Where did my money go this week?",
  "Am I on track with my savings goals?",
  "Show me my biggest single transaction this year.",
];

function loadTurns(): Turn[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Turn[];
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
    // Quota or storage disabled.
  }
}

function historyFor(turns: Turn[]): { role: "user" | "assistant"; content: string }[] {
  const out: { role: "user" | "assistant"; content: string }[] = [];
  for (const t of turns) {
    if (t.status !== "complete") continue;
    out.push({ role: "user", content: t.question });
    out.push({ role: "assistant", content: t.answer });
  }
  return out;
}

export function AskShell() {
  // useSearchParams forces dynamic rendering and must be inside Suspense.
  return (
    <React.Suspense fallback={null}>
      <AskShellInner />
    </React.Suspense>
  );
}

function AskShellInner() {
  const searchParams = useSearchParams();
  const [turns, setTurns] = React.useState<Turn[]>(() => loadTurns());
  const [input, setInput] = React.useState("");
  const abortRef = React.useRef<AbortController | null>(null);
  const scrollAnchorRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    const prefill = searchParams.get("prefill");
    if (prefill && turns.length === 0 && !input) {
      setInput(prefill);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  React.useEffect(() => {
    saveTurns(turns);
  }, [turns]);

  React.useEffect(() => {
    scrollAnchorRef.current?.scrollIntoView({ block: "end" });
  }, [turns]);

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

      const ctrl = new AbortController();
      abortRef.current = ctrl;

      try {
        const res = await fetch("/api/ask", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ question, history: historyFor(priorTurns) }),
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
                t.id === turnId ? { ...t, answer: t.answer + evt.text } : t,
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
                t.id === turnId ? { ...t, tools: [...t.tools, newTool] } : t,
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
            prev.map((t) => (t.id === turnId ? { ...t, status: "cancelled" } : t)),
          );
          return;
        }
        const message = err instanceof Error ? err.message : String(err);
        setTurns((prev) =>
          prev.map((t) =>
            t.id === turnId ? { ...t, status: "errored", error: message } : t,
          ),
        );
        toast.error("Couldn't answer.", { description: message });
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
            Questions about your money, in plain language.
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
            <h3 className="text-sm font-medium">Ask anything about your money.</h3>
            <p className="max-w-md text-xs text-muted-foreground">
              Answers come from your active YNAB budget. The conversation stays
              in this browser tab.
            </p>
          </div>
          <SuggestedChips
            suggestions={SUGGESTIONS}
            loading={false}
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
