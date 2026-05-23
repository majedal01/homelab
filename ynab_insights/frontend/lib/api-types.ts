/**
 * Generated types for the FastAPI backend.
 *
 * Run `npm run generate-types` against a live FastAPI instance to refresh this
 * file from the live OpenAPI schema. The hand-curated subset below mirrors the
 * server's Pydantic response models (app/schemas/*.py) and the agent's
 * AskResult. CI verifies the generated file is in sync.
 */

export interface BudgetResponse {
  id: string;
  name: string;
  currency: string;
  last_modified_on: string;
}

export interface AccountResponse {
  id: string;
  budget_id: string;
  name: string;
  type: string;
  balance_cents: number;
  on_budget: boolean;
  closed: boolean;
}

export interface CategoryResponse {
  id: string;
  budget_id: string;
  category_group_id: string | null;
  name: string;
  hidden: boolean;
}

export interface PayeeResponse {
  id: string;
  budget_id: string;
  name: string;
  transfer_account_id: string | null;
}

export interface TransactionResponse {
  id: string;
  budget_id: string;
  account_id: string;
  account_name: string;
  category_id: string | null;
  category_name: string | null;
  payee_id: string | null;
  payee_name: string | null;
  transfer_account_id: string | null;
  date: string;
  amount_cents: number;
  memo: string | null;
  cleared: string;
  approved: boolean;
}

export interface SyncResult {
  budgets: number;
  accounts: number;
  categories: number;
  payees: number;
  transactions: number;
}

export interface ToolCall {
  tool: string;
  input: Record<string, unknown>;
  output: unknown;
  is_error: boolean;
}

export interface AskResult {
  question: string;
  answer: string;
  tool_calls: ToolCall[];
  turns_used: number;
  stop_reason: string;
}

export interface AskRequest {
  question: string;
  budget_id?: string | null;
  /**
   * Prior conversation in Anthropic message format. Frontend persists this
   * in sessionStorage and posts on every request; backend stays stateless.
   */
  history?: Array<{ role: "user" | "assistant"; content: string }>;
}

export interface SuggestionResponse {
  suggestions: string[];
}

export interface HealthResponse {
  status: string;
  version: string;
  env: string;
}

export type CardType =
  | "subscription_audit"
  | "spending_anomaly"
  | "cashflow_forecast"
  | "goal_trajectory";

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
  week_start: string;
  week_end: string;
  current_week_spend_cents: number;
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
  daily_net_cents: number;
  projected_30d_cents: number;
  projected_60d_cents: number;
  projected_90d_cents: number;
  lookback_days: number;
  top_spending_categories: CategoryRate[];
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

export type InsightStructuredData =
  | SubscriptionAuditData
  | SpendingAnomalyData
  | CashflowForecastData
  | GoalTrajectoryData;

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

export interface MonthlyTrendPointResponse {
  year: number;
  month: number; // 1-indexed (Jan = 1)
  spending_cents: number;
  income_cents: number;
}

export interface MonthlyTrendResponse {
  points: MonthlyTrendPointResponse[];
}
