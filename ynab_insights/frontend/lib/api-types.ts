/**
 * Hand-curated mirror of the FastAPI Pydantic response models (v2.5).
 *
 * Run the live OpenAPI generator against a running backend to refresh
 * (`npm run generate-types`); this committed file is the source of truth
 * for editor types and is verified for drift in CI.
 */

// --- Session (v2.5) ---------------------------------------------------------

export interface BudgetOption {
  id: string;
  name: string;
  last_modified_on: string;
}

export interface CreateSessionResponse {
  sid: string;
  budgets: BudgetOption[];
  created_at: string;
  expires_at: string;
}

export interface SessionPublic {
  sid: string;
  budget_id: string | null;
  budget_name: string | null;
  anthropic_model: string | null;
  is_demo: boolean;
  created_at: string;
  last_active_at: string;
  last_synced_at: string | null;
  expires_at: string;
}

export type LlmProvider = "anthropic" | "openai";

export interface ModelOption {
  value: string;
  label: string;
  tagline: string;
}

/**
 * Per-provider model catalog returned by `GET /api/session/models`. The server
 * (`app/llm`) owns the list and its allow-list; the picker fetches and renders
 * whatever this returns, so the options never drift from what the server
 * accepts. Mirrors `ModelCatalogResponse` in `app/routers/session.py`.
 */
export interface ModelCatalog {
  providers: Record<LlmProvider, ModelOption[]>;
  defaults: Record<LlmProvider, string>;
}

/** Mirror of `app/llm/detect.py::detect_provider`. Returns null on no match. */
export function detectProvider(key: string): LlmProvider | null {
  if (/^sk-ant-[A-Za-z0-9_-]{20,256}$/.test(key)) return "anthropic";
  if (/^sk-(proj-)?[A-Za-z0-9_-]{20,256}$/.test(key)) return "openai";
  return null;
}


export interface SessionErrorBody {
  error: string;
  message: string;
  retry_after_seconds?: number;
}

// --- Ask --------------------------------------------------------------------

export interface ToolCall {
  tool: string;
  input: Record<string, unknown>;
  output: unknown;
  is_error: boolean;
}

export interface AskRequest {
  question: string;
  history?: Array<{ role: "user" | "assistant"; content: string }>;
}

// --- Insights ---------------------------------------------------------------

export interface HealthResponse {
  status: string;
  version?: string;
  env?: string;
}

export type CardType =
  | "subscription_audit"
  | "spending_anomaly"
  | "cashflow_forecast"
  | "category_projection"
  | "debt_payoff"
  | "goal_trajectory"
  | "goal_setup_prompt"
  | "emergency_fund_coverage"
  | "savings_rate_trend"
  | "category_drift"
  | "year_in_money";

export type Cadence = "weekly" | "monthly" | "quarterly" | "yearly";

export interface TransactionRef {
  id: string;
  date: string;
  amount_cents: number;
  payee_name: string | null;
  memo: string | null;
}

export interface SubscriptionAuditData {
  card_type: "subscription_audit";
  payee_id: string;
  payee_name: string;
  cadence: Cadence;
  amount_cents: number;
  monthly_cost_cents: number;
  annual_cost_cents: number;
  occurrences: TransactionRef[];
  first_seen: string;
  last_seen: string;
}

export interface AnomalyTopTransaction {
  id: string;
  date: string;
  amount_cents: number;
  payee_name: string | null;
}

export interface SpendingAnomalyData {
  card_type: "spending_anomaly";
  category_id: string;
  category_name: string;
  cycle: "weekly" | "monthly";
  period_start: string;
  period_end: string;
  current_period_spend_cents: number;
  baseline_mean_cents: number;
  baseline_stdev_cents: number;
  z_score: number;
  deviation_ratio: number;
  top_transactions: AnomalyTopTransaction[];
}

export interface CategoryRate {
  category_id: string | null;
  category_name: string;
  monthly_average_cents: number;
}

export interface CashflowForecastData {
  card_type: "cashflow_forecast";
  starting_balance_cents: number;
  credit_card_debt_cents: number;
  daily_net_cents: number;
  projected_30d_cents: number;
  projected_60d_cents: number;
  projected_90d_cents: number;
  lookback_days: number;
  lookback_income_cents: number;
  lookback_spending_cents: number;
  top_spending_categories: CategoryRate[];
}

export interface CategoryProjectionTopTransaction {
  id: string;
  date: string;
  amount_cents: number;
  payee_name: string | null;
}

export interface CategoryProjectionData {
  card_type: "category_projection";
  category_id: string;
  category_name: string;
  month_start: string;
  days_into_month: number;
  days_in_month: number;
  month_to_date_cents: number;
  projected_month_end_cents: number;
  baseline_monthly_avg_cents: number;
  delta_cents: number;
  delta_pct: number;
  direction: "over" | "under";
  top_transactions: CategoryProjectionTopTransaction[];
}

export interface DebtPayoffData {
  card_type: "debt_payoff";
  account_id: string;
  account_name: string;
  account_type: string;
  current_debt_cents: number;
  avg_monthly_paydown_cents: number;
  lookback_months: number;
  projected_months_to_payoff: number;
  projected_payoff_date: string;
}

export interface GoalSetupPromptCategory {
  category_id: string;
  category_name: string;
  monthly_avg_spend_cents: number;
}

export interface GoalSetupPromptData {
  card_type: "goal_setup_prompt";
  top_categories: GoalSetupPromptCategory[];
}

export interface GoalTrajectoryData {
  card_type: "goal_trajectory";
  category_id: string;
  category_name: string;
  goal_type: string;
  target_cents: number;
  progress_cents: number;
  remaining_cents: number;
  percent_complete: number;
  current_monthly_contribution_cents: number;
  target_date: string | null;
  projected_completion_date: string | null;
  months_to_target: number | null;
  on_track: boolean | null;
}

export interface EmergencyFundCoverageData {
  card_type: "emergency_fund_coverage";
  cash_balance_cents: number;
  avg_monthly_spending_cents: number;
  coverage_months: number;
  months_of_history: number;
  target_months: number;
}

export interface SavingsRatePoint {
  year: number;
  month: number;
  savings_rate: number | null;
}

export interface SavingsRateTrendData {
  card_type: "savings_rate_trend";
  points: SavingsRatePoint[];
  average_savings_rate: number | null;
  latest_savings_rate: number | null;
  direction: "up" | "down" | "flat";
  months_of_history: number;
}

export interface CategoryDriftData {
  card_type: "category_drift";
  category_id: string;
  category_name: string;
  comparison_kind: "quarter_over_quarter" | "year_over_year";
  trailing_quarter_avg_cents: number;
  prior_three_quarters_avg_cents: number;
  drift_pct: number;
  drift_cents_per_month: number;
  direction: "up" | "down";
  monthly_nets_cents: number[];
}

export interface YearInMoneyTopCategoryEntry {
  category_id: string | null;
  category_name: string;
  net_spend_cents: number;
}

export interface YearInMoneyTopPayeeEntry {
  payee_id: string | null;
  payee_name: string;
  transaction_count: number;
  amount_cents: number;
}

export interface YearInMoneyBiggestSingleEntry {
  transaction_id: string;
  date: string;
  amount_cents: number;
  payee_name: string | null;
  category_name: string | null;
}

export interface YearInMoneyData {
  card_type: "year_in_money";
  period_label: string;
  period_kind: "annual" | "quarterly";
  period_start: string;
  period_end: string;
  total_income_cents: number;
  total_spending_cents: number;
  net_income_cents: number;
  savings_rate: number | null;
  top_categories: YearInMoneyTopCategoryEntry[];
  top_payees: YearInMoneyTopPayeeEntry[];
  biggest_single: YearInMoneyBiggestSingleEntry | null;
  savings_rate_trend: (number | null)[];
  largest_category_swing: YearInMoneyTopCategoryEntry | null;
  narrative: string;
}

export type InsightStructuredData =
  | SubscriptionAuditData
  | SpendingAnomalyData
  | CashflowForecastData
  | CategoryProjectionData
  | DebtPayoffData
  | GoalTrajectoryData
  | GoalSetupPromptData
  | EmergencyFundCoverageData
  | SavingsRateTrendData
  | CategoryDriftData
  | YearInMoneyData;

export interface InsightResponse {
  id: number;
  budget_id: string;
  card_type: CardType;
  dedup_key: string;
  title: string;
  summary: string;
  structured_data: InsightStructuredData;
  generated_at: string;
  refreshed_at: string;
  dismissed_at: string | null;
  llm_enhanced: boolean;
}

export interface InsightRunResponse {
  id: number;
  card_type: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  duration_ms: number | null;
  insights_created: number;
  insights_updated: number;
  error: string | null;
}

export interface GenerateResponse {
  run_ids: number[];
}

// --- Snapshot (v2.6) --------------------------------------------------------

export interface AccountResponse {
  id: string;
  name: string;
  type: string;
  on_budget: boolean;
  closed: boolean;
  balance_cents: number;
}

export interface CategoryResponse {
  id: string;
  name: string;
  hidden: boolean;
  goal_type: string | null;
  goal_target_cents: number | null;
  goal_overall_left_cents: number | null;
  goal_percentage_complete: number | null;
  this_month_spend_cents: number;
}

export interface TransactionResponse {
  id: string;
  date: string;
  amount_cents: number;
  account_id: string;
  account_name: string | null;
  category_id: string | null;
  category_name: string | null;
  payee_id: string | null;
  payee_name: string | null;
  memo: string | null;
}

export interface CategoryNetResponse {
  category_id: string | null;
  category_name: string | null;
  net_cents: number;
}

export interface PeriodSummaryResponse {
  date_from: string;
  date_to: string;
  income_cents: number;
  spending_cents: number;
  net_income_cents: number;
  transaction_count: number;
  by_category: CategoryNetResponse[];
}

export interface MonthlyTrendPointResponse {
  year: number;
  month: number;
  income_cents: number;
  spending_cents: number;
}

export interface MonthlyTrendResponse {
  points: MonthlyTrendPointResponse[];
}

export interface OverviewKPIs {
  net_worth_cents: number;
  this_month_income_cents: number;
  this_month_spending_cents: number;
  this_month_net_cents: number;
  savings_rate: number | null;
  transaction_count: number;
}
