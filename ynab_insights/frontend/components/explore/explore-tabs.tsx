"use client";

import Link from "next/link";

import { cn } from "@/lib/utils";

const TABS: { value: string; label: string }[] = [
  { value: "overview", label: "Overview" },
  { value: "accounts", label: "Accounts" },
  { value: "categories", label: "Categories" },
  { value: "transactions", label: "Transactions" },
];

export function ExploreTabs({ active }: { active: string }) {
  return (
    <div className="sticky top-14 z-30 -mx-4 border-b bg-background/85 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <nav
        role="tablist"
        aria-label="Explore views"
        className="flex gap-1 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {TABS.map((t) => {
          const isActive = t.value === active;
          return (
            <Link
              key={t.value}
              href={t.value === "overview" ? "/explore" : `/explore?view=${t.value}`}
              role="tab"
              aria-selected={isActive}
              className={cn(
                "relative px-4 py-3 text-sm font-medium transition-colors",
                isActive
                  ? "text-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {t.label}
              {isActive && (
                <span
                  aria-hidden
                  className="absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-foreground"
                />
              )}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
