"use client";

import * as React from "react";
import { motion } from "motion/react";
import { Sparkles } from "lucide-react";

import { cn } from "@/lib/utils";

export function SuggestedChips({
  suggestions,
  onPick,
  loading,
}: {
  suggestions: string[];
  onPick: (text: string) => void;
  loading?: boolean;
}) {
  if (loading) {
    return (
      <div className="flex flex-wrap gap-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <span
            key={i}
            className="h-7 w-44 animate-pulse rounded-full bg-muted"
          />
        ))}
      </div>
    );
  }
  if (!suggestions.length) return null;
  return (
    <div className="space-y-2">
      <div className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
        <Sparkles className="h-3.5 w-3.5" />
        Try one of these
      </div>
      <div className="flex flex-wrap gap-2">
        {suggestions.map((s, i) => (
          <motion.button
            key={s}
            type="button"
            onClick={() => onPick(s)}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2, delay: i * 0.04 }}
            className={cn(
              "rounded-full border bg-card px-3 py-1.5 text-xs",
              "hover:bg-accent hover:text-accent-foreground hover:border-accent",
              "transition-colors",
            )}
          >
            {s}
          </motion.button>
        ))}
      </div>
    </div>
  );
}
