"use client";

import * as React from "react";
import { Loader2, Send, Square } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export function Composer({
  value,
  onChange,
  onSubmit,
  onCancel,
  isStreaming,
  disabled,
  autoFocus,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  onCancel: () => void;
  isStreaming: boolean;
  disabled?: boolean;
  autoFocus?: boolean;
}) {
  const ref = React.useRef<HTMLTextAreaElement | null>(null);

  // Auto-grow the textarea up to a sensible cap.
  React.useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  function handleKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      if (value.trim() && !isStreaming) onSubmit();
    }
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (value.trim() && !isStreaming) onSubmit();
      }}
      className={cn(
        "relative flex items-end gap-2 rounded-lg border bg-card p-2",
        isStreaming && "ring-1 ring-primary/30",
      )}
    >
      <textarea
        ref={ref}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKey}
        rows={1}
        autoFocus={autoFocus}
        disabled={disabled}
        placeholder="Ask a question about your spending… (Cmd/Ctrl+Enter)"
        className="min-h-[2.5rem] flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none placeholder:text-muted-foreground disabled:opacity-60"
      />
      {isStreaming ? (
        <Button
          type="button"
          size="icon"
          variant="ghost"
          onClick={onCancel}
          aria-label="Cancel"
        >
          <Square className="h-4 w-4" />
        </Button>
      ) : (
        <Button
          type="submit"
          size="icon"
          disabled={disabled || !value.trim()}
          aria-label="Send"
        >
          {disabled ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </Button>
      )}
    </form>
  );
}
