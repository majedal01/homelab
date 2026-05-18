"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import type { AskResult } from "@/lib/api-types";

export default function AskPage() {
  const [question, setQuestion] = React.useState("");
  const [result, setResult] = React.useState<AskResult | null>(null);
  const [isPending, setIsPending] = React.useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!question.trim()) return;
    setIsPending(true);
    setResult(null);
    try {
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ question }),
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(detail || `HTTP ${res.status}`);
      }
      const data = (await res.json()) as AskResult;
      setResult(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      toast.error("Ask failed", { description: message });
    } finally {
      setIsPending(false);
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle>Ask</CardTitle>
          <p className="text-xs text-muted-foreground">
            Natural-language questions about your YNAB data. The agent calls
            read-only tools against the local database to answer.
          </p>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="flex gap-2">
            <Input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="What did I spend most on this month?"
              disabled={isPending}
              required
              minLength={1}
              maxLength={1000}
            />
            <Button type="submit" disabled={isPending}>
              {isPending ? "Thinking..." : "Ask"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {isPending && (
        <Card>
          <CardContent className="space-y-3 p-6">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-4 w-2/3" />
          </CardContent>
        </Card>
      )}

      {result && (
        <Card>
          <CardContent className="space-y-3 p-6">
            <div className="whitespace-pre-wrap text-sm leading-relaxed">{result.answer}</div>
            {result.tool_calls.length > 0 && (
              <details className="text-xs">
                <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                  {result.tool_calls.length} tool call(s) over {result.turns_used} turn(s)
                </summary>
                <div className="mt-2 space-y-2">
                  {result.tool_calls.map((tc, i) => (
                    <div key={i} className="rounded-md bg-muted p-2 font-mono text-xs">
                      <div className={tc.is_error ? "font-semibold text-destructive" : "font-semibold"}>
                        {tc.tool}
                        {tc.is_error && " (error)"}
                      </div>
                      <details className="mt-1">
                        <summary className="cursor-pointer text-muted-foreground">input</summary>
                        <pre className="mt-1 overflow-x-auto whitespace-pre-wrap">
                          {JSON.stringify(tc.input, null, 2)}
                        </pre>
                      </details>
                      <details className="mt-1">
                        <summary className="cursor-pointer text-muted-foreground">output</summary>
                        <pre className="mt-1 overflow-x-auto whitespace-pre-wrap">
                          {JSON.stringify(tc.output, null, 2)}
                        </pre>
                      </details>
                    </div>
                  ))}
                </div>
              </details>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
