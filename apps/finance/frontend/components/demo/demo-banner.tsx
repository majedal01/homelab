"use client";

import Link from "next/link";
import { Sparkles, X } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Slim top-of-page banner that surfaces "you're in demo mode" + a path
 * out. Rendered by every authed page when `session.is_demo` is true.
 *
 * Closing the banner only hides it for the current page (sessionStorage
 * key). The session is still flagged as demo server-side until the user
 * actually signs in with real credentials.
 */
export function DemoBanner() {
  return (
    <div
      className={cn(
        "rounded-md border border-dashed border-foreground/30 bg-foreground/[0.04]",
        "flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 text-sm",
      )}
    >
      <div className="flex items-center gap-2 text-muted-foreground">
        <Sparkles className="h-3.5 w-3.5" />
        <span>
          <span className="font-medium text-foreground">Demo data.</span> None of
          these numbers are real. Use your own credentials to load yours.
        </span>
      </div>
      <Link
        href="/welcome"
        className="inline-flex items-center gap-1 rounded-md bg-foreground px-3 py-1.5 text-xs font-medium text-background hover:opacity-90"
      >
        Use your own data
        <X className="hidden h-3 w-3" aria-hidden />
      </Link>
    </div>
  );
}
