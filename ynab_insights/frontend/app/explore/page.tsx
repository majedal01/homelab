import { Aurora } from "@/components/brand/aurora";
import { DemoBanner } from "@/components/demo/demo-banner";
import { ExploreTabs } from "@/components/explore/explore-tabs";
import { AccountsTab } from "@/components/explore/accounts-tab";
import { CategoriesTab } from "@/components/explore/categories-tab";
import { OverviewTab } from "@/components/explore/overview-tab";
import { TransactionsTab } from "@/components/explore/transactions-tab";
import { apiFetch, requireSession } from "@/lib/api";
import type {
  AccountResponse,
  CategoryResponse,
  MonthlyTrendResponse,
  OverviewKPIs,
  PeriodSummaryResponse,
  TransactionResponse,
} from "@/lib/api-types";

export const dynamic = "force-dynamic";

type ExploreView = "overview" | "accounts" | "categories" | "transactions";

interface ExploreSearchParams {
  view?: string;
  // Transactions-tab filters; URL-persisted so deep-links from card detail
  // pages can land directly on a filtered slice.
  date_from?: string;
  date_to?: string;
  category_id?: string;
  account_id?: string;
  payee_contains?: string;
  offset?: string;
}

function viewFromParam(v: string | undefined): ExploreView {
  if (v === "accounts" || v === "categories" || v === "transactions") return v;
  return "overview";
}

function formatRelativeShort(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  if (Number.isNaN(ms)) return iso;
  const mins = Math.round(ms / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  return `${hrs}h ago`;
}

export default async function ExplorePage({
  searchParams,
}: {
  searchParams: Promise<ExploreSearchParams>;
}) {
  const session = await requireSession();
  const params = await searchParams;
  const view = viewFromParam(params.view);

  // Render only the active tab's data fetch to keep the round-trip count
  // honest. Each tab is independently navigable.
  let tabContent: React.ReactNode;
  if (view === "overview") {
    const [kpis, trend, summary] = await Promise.all([
      apiFetch<OverviewKPIs>("/api/snapshot/overview").catch(() => null),
      apiFetch<MonthlyTrendResponse>("/api/snapshot/monthly-trend?months=12").catch(
        () => ({ points: [] }) as MonthlyTrendResponse,
      ),
      apiFetch<PeriodSummaryResponse>("/api/snapshot/summary").catch(() => null),
    ]);
    tabContent = <OverviewTab kpis={kpis} trend={trend.points} summary={summary} />;
  } else if (view === "accounts") {
    const accounts = await apiFetch<AccountResponse[]>("/api/snapshot/accounts").catch(
      () => [] as AccountResponse[],
    );
    tabContent = <AccountsTab accounts={accounts} />;
  } else if (view === "categories") {
    const categories = await apiFetch<CategoryResponse[]>(
      "/api/snapshot/categories",
    ).catch(() => [] as CategoryResponse[]);
    tabContent = <CategoriesTab categories={categories} />;
  } else {
    // transactions
    const offset = Math.max(0, parseInt(params.offset ?? "0", 10) || 0);
    const usp = new URLSearchParams();
    usp.set("limit", "50");
    usp.set("offset", String(offset));
    if (params.date_from) usp.set("date_from", params.date_from);
    if (params.date_to) usp.set("date_to", params.date_to);
    if (params.category_id) usp.set("category_id", params.category_id);
    if (params.account_id) usp.set("account_id", params.account_id);
    if (params.payee_contains) usp.set("payee_contains", params.payee_contains);

    const [transactions, categories, accounts] = await Promise.all([
      apiFetch<TransactionResponse[]>(`/api/snapshot/transactions?${usp.toString()}`).catch(
        () => [] as TransactionResponse[],
      ),
      apiFetch<CategoryResponse[]>("/api/snapshot/categories").catch(
        () => [] as CategoryResponse[],
      ),
      apiFetch<AccountResponse[]>("/api/snapshot/accounts").catch(
        () => [] as AccountResponse[],
      ),
    ]);
    tabContent = (
      <TransactionsTab
        transactions={transactions}
        categories={categories}
        accounts={accounts}
        offset={offset}
      />
    );
  }

  return (
    <>
      <Aurora variant="quiet" />
      <div className="mx-auto flex max-w-5xl flex-col gap-4">
        {session.is_demo && <DemoBanner />}
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Explore</h1>
          <p className="text-sm text-muted-foreground">
            {session.budget_name
              ? `${session.budget_name}${
                  session.last_synced_at
                    ? ` · synced ${formatRelativeShort(session.last_synced_at)}`
                    : ""
                }`
              : "Pick a budget to start."}
          </p>
        </div>
        <ExploreTabs active={view} />
        {tabContent}
      </div>
    </>
  );
}
