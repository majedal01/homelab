"use client";

import * as React from "react";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { Calendar as CalendarIcon } from "lucide-react";
import type { DateRange } from "react-day-picker";
import { format, parseISO } from "date-fns";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  currentMonth,
  monthBounds,
  previousMonth,
  isoDate,
} from "@/lib/metrics";

type PresetKey = "this-month" | "last-month" | "this-year" | "last-90" | "custom";

interface Preset {
  key: PresetKey;
  label: string;
  range: () => { from: string; to: string };
}

const PRESETS: Preset[] = [
  {
    key: "this-month",
    label: "This month",
    range: () => monthBounds(currentMonth()),
  },
  {
    key: "last-month",
    label: "Last month",
    range: () => monthBounds(previousMonth(currentMonth())),
  },
  {
    key: "this-year",
    label: "This year",
    range: () => {
      const now = new Date();
      return {
        from: isoDate(new Date(now.getFullYear(), 0, 1)),
        to: isoDate(now),
      };
    },
  },
  {
    key: "last-90",
    label: "Last 90 days",
    range: () => {
      const now = new Date();
      const from = new Date(now);
      from.setDate(from.getDate() - 89);
      return { from: isoDate(from), to: isoDate(now) };
    },
  },
];

function presetForRange(from: string | null, to: string | null): PresetKey {
  if (!from || !to) return "this-month";
  for (const preset of PRESETS) {
    const r = preset.range();
    if (r.from === from && r.to === to) return preset.key;
  }
  return "custom";
}

export function DateRangePicker({ className }: { className?: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const dateFrom = searchParams.get("date_from");
  const dateTo = searchParams.get("date_to");

  // Default range when none in URL: this month. Lets the trigger label read
  // sensibly on first paint without the page having to inject params.
  const defaultRange = monthBounds(currentMonth());
  const effectiveFrom = dateFrom ?? defaultRange.from;
  const effectiveTo = dateTo ?? defaultRange.to;
  const activePreset = presetForRange(dateFrom, dateTo);

  const writeRange = React.useCallback(
    (from: string, to: string) => {
      const params = new URLSearchParams(searchParams.toString());
      params.set("date_from", from);
      params.set("date_to", to);
      router.push(`${pathname}?${params.toString()}`, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  const [open, setOpen] = React.useState(false);
  const [draft, setDraft] = React.useState<DateRange | undefined>({
    from: parseISO(effectiveFrom),
    to: parseISO(effectiveTo),
  });

  React.useEffect(() => {
    setDraft({ from: parseISO(effectiveFrom), to: parseISO(effectiveTo) });
  }, [effectiveFrom, effectiveTo]);

  const applyPreset = (preset: Preset) => {
    const r = preset.range();
    writeRange(r.from, r.to);
    setOpen(false);
  };

  const applyDraft = () => {
    if (!draft?.from || !draft?.to) return;
    writeRange(isoDate(draft.from), isoDate(draft.to));
    setOpen(false);
  };

  const triggerLabel =
    activePreset === "custom"
      ? `${format(parseISO(effectiveFrom), "MMM d")} – ${format(
          parseISO(effectiveTo),
          "MMM d, yyyy",
        )}`
      : PRESETS.find((p) => p.key === activePreset)?.label ?? "This month";

  return (
    <div className={cn("inline-flex", className)}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            className="h-9 gap-2 font-normal tabular-nums"
          >
            <CalendarIcon className="h-4 w-4 opacity-70" />
            {triggerLabel}
          </Button>
        </PopoverTrigger>
        <PopoverContent
          align="end"
          className="flex w-auto flex-col gap-3 p-0 sm:flex-row"
        >
          <div className="flex flex-col gap-1 border-b p-3 sm:border-b-0 sm:border-r">
            {PRESETS.map((preset) => (
              <button
                key={preset.key}
                onClick={() => applyPreset(preset)}
                className={cn(
                  "rounded-md px-3 py-1.5 text-left text-sm transition-colors",
                  activePreset === preset.key
                    ? "bg-accent text-accent-foreground"
                    : "hover:bg-accent/50",
                )}
              >
                {preset.label}
              </button>
            ))}
          </div>
          <div className="flex flex-col gap-2 p-3">
            <Calendar
              mode="range"
              defaultMonth={draft?.from}
              selected={draft}
              onSelect={setDraft}
              numberOfMonths={2}
            />
            <div className="flex justify-end gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setOpen(false)}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={applyDraft}
                disabled={!draft?.from || !draft?.to}
              >
                Apply
              </Button>
            </div>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}
