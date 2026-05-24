"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, Settings } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { ThemeToggle } from "@/components/theme-toggle";
import { LogoMark } from "@/components/brand/logo";

const NAV_ITEMS: { href: string; label: string }[] = [
  { href: "/insights", label: "Insights" },
  { href: "/ask", label: "Ask" },
];

function NavLink({
  href,
  label,
  onClick,
}: {
  href: string;
  label: string;
  onClick?: () => void;
}) {
  const pathname = usePathname();
  const isActive = pathname.startsWith(href);
  return (
    <Link
      href={href}
      onClick={onClick}
      className={cn(
        "px-3 py-2 text-sm font-medium rounded-md transition-colors",
        isActive
          ? "bg-accent text-accent-foreground"
          : "text-muted-foreground hover:text-foreground hover:bg-accent/50",
      )}
    >
      {label}
    </Link>
  );
}

export function Nav() {
  const pathname = usePathname();
  // Hide the nav on the welcome page so it doesn't compete with the centered card.
  if (pathname === "/welcome") return null;

  return (
    <header className="sticky top-0 z-40 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container flex h-14 items-center">
        <Link
          href="/insights"
          className="mr-6 inline-flex items-center gap-2 font-semibold tracking-tight"
        >
          <LogoMark size={20} className="text-foreground" />
          YNAB Insights
        </Link>
        <nav className="hidden md:flex items-center gap-1 flex-1">
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.href} {...item} />
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <Link
            href="/settings"
            aria-label="Settings"
            className={cn(
              "inline-flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground transition-colors",
              "hover:bg-accent hover:text-foreground",
              pathname.startsWith("/settings") && "text-foreground",
            )}
          >
            <Settings className="h-4 w-4" />
          </Link>
          <ThemeToggle />
          <Sheet>
            <SheetTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="md:hidden"
                aria-label="Open menu"
              >
                <Menu className="h-5 w-5" />
              </Button>
            </SheetTrigger>
            <SheetContent side="right" className="w-72">
              <SheetHeader>
                <SheetTitle>Menu</SheetTitle>
              </SheetHeader>
              <nav className="mt-6 flex flex-col gap-1">
                {NAV_ITEMS.map((item) => (
                  <SheetClose asChild key={item.href}>
                    <NavLink {...item} />
                  </SheetClose>
                ))}
                <SheetClose asChild>
                  <NavLink href="/settings" label="Settings" />
                </SheetClose>
              </nav>
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </header>
  );
}
