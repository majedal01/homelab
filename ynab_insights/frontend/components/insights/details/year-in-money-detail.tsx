"use client";

import * as React from "react";
import { motion } from "motion/react";
import { LineChart } from "@tremor/react";

import { MOTION } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { formatDollars } from "@/lib/utils";
import type { YearInMoneyData } from "@/lib/api-types";

/**
 * The showcase. Six panels stacked, each fading and sliding in as the
 * user scrolls. Restrained Spotify-Wrapped energy: big numbers, generous
 * spacing, the LLM-written narrative in a serif voice contrast at the
 * bottom. Full-page route — chosen over modal so the scroll math stays
 * predictable and the URL is shareable.
 */
export function YearInMoneyDetail({ data }: { data: YearInMoneyData }) {
  return (
    <div className="space-y-16 py-6">
      <Panel index={0}>
        <p className="text-sm uppercase tracking-[0.2em] text-muted-foreground">
          {data.period_kind === "annual" ? "Year in money" : "Quarter in money"}
        </p>
        <h1 className="mt-3 text-5xl font-semibold tracking-tight">
          {data.period_label}
        </h1>
        <div className="mt-10 grid gap-8 sm:grid-cols-2">
          <Hero
            label="Income"
            value={formatDollars(data.total_income_cents)}
            tone="positive"
          />
          <Hero
            label="Spending"
            value={formatDollars(data.total_spending_cents)}
            tone="destructive"
          />
        </div>
        {data.savings_rate !== null ? (
          <div className="mt-6 inline-flex items-center gap-2 rounded-full border bg-card/60 px-3 py-1 text-xs">
            <span className="text-muted-foreground">Savings rate</span>
            <span className="font-mono tabular-nums">
              {Math.round(data.savings_rate * 100)}%
            </span>
          </div>
        ) : null}
      </Panel>

      {data.top_categories.length ? (
        <Panel index={1}>
          <SectionTitle>Where the money went</SectionTitle>
          <ul className="mt-6 space-y-3">
            {data.top_categories.map((c, i) => (
              <CategoryBar key={c.category_id ?? c.category_name} rank={i + 1} entry={c} max={data.top_categories[0].net_spend_cents} />
            ))}
          </ul>
        </Panel>
      ) : null}

      {data.top_payees.length ? (
        <Panel index={2}>
          <SectionTitle>Top payees</SectionTitle>
          <ul className="mt-6 divide-y divide-border text-sm">
            {data.top_payees.map((p, i) => (
              <li
                key={p.payee_id ?? `${p.payee_name}-${i}`}
                className="flex items-baseline justify-between py-3"
              >
                <span className="truncate">
                  <span className="text-muted-foreground tabular-nums">
                    {String(i + 1).padStart(2, "0")}
                  </span>{" "}
                  {p.payee_name}{" "}
                  <span className="text-xs text-muted-foreground">
                    · {p.transaction_count} txn
                  </span>
                </span>
                <span className="font-mono tabular-nums">
                  {formatDollars(p.amount_cents)}
                </span>
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}

      {data.savings_rate_trend.some((v) => v !== null) ? (
        <Panel index={3}>
          <SectionTitle>Saving over time</SectionTitle>
          <LineChart
            data={data.savings_rate_trend.map((v, i) => ({
              month: `M${i + 1}`,
              "Savings rate": v === null ? null : Math.round(v * 100),
            }))}
            index="month"
            categories={["Savings rate"]}
            colors={["indigo"]}
            valueFormatter={(v) => `${v}%`}
            showLegend={false}
            className="mt-6 h-56"
          />
        </Panel>
      ) : null}

      {data.biggest_single ? (
        <Panel index={4}>
          <SectionTitle>The single largest moment</SectionTitle>
          <div className="mt-6 rounded-xl border bg-card/80 p-8">
            <div className="text-xs uppercase tracking-wide text-muted-foreground">
              {data.biggest_single.date}
            </div>
            <div className="mt-2 font-mono text-3xl font-semibold tabular-nums">
              {formatDollars(Math.abs(data.biggest_single.amount_cents))}
            </div>
            <div className="mt-2 text-sm text-muted-foreground">
              to {data.biggest_single.payee_name ?? "an uncategorized payee"}
              {data.biggest_single.category_name
                ? ` · ${data.biggest_single.category_name}`
                : ""}
            </div>
          </div>
        </Panel>
      ) : null}

      <Panel index={5}>
        <SectionTitle>In summary</SectionTitle>
        <p className="mt-6 font-serif text-lg leading-relaxed text-foreground/90">
          {data.narrative}
        </p>
      </Panel>
    </div>
  );
}

function Panel({
  children,
  index,
}: {
  children: React.ReactNode;
  index: number;
}) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.3 }}
      transition={{
        duration: MOTION.d.slow,
        ease: MOTION.e.out as unknown as [number, number, number, number],
        delay: Math.min(index, 4) * 0.03,
      }}
    >
      {children}
    </motion.section>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-sm font-medium uppercase tracking-[0.18em] text-muted-foreground">
      {children}
    </h2>
  );
}

function Hero({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "positive" | "destructive";
}) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div
        className={cn(
          "mt-2 font-mono text-4xl font-semibold tabular-nums",
          tone === "positive" && "text-emerald-600 dark:text-emerald-400",
          tone === "destructive" && "text-destructive",
        )}
      >
        {value}
      </div>
    </div>
  );
}

function CategoryBar({
  entry,
  rank,
  max,
}: {
  entry: { category_name: string; net_spend_cents: number };
  rank: number;
  max: number;
}) {
  const pct = max > 0 ? (entry.net_spend_cents / max) * 100 : 0;
  return (
    <li>
      <div className="flex items-baseline justify-between text-sm">
        <span className="truncate">
          <span className="text-muted-foreground tabular-nums">
            {String(rank).padStart(2, "0")}
          </span>{" "}
          {entry.category_name}
        </span>
        <span className="font-mono tabular-nums">
          {formatDollars(entry.net_spend_cents)}
        </span>
      </div>
      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-primary/70"
          style={{ width: `${Math.min(100, pct)}%` }}
          aria-hidden
        />
      </div>
    </li>
  );
}
