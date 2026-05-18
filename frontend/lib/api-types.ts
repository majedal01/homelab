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
}

export interface HealthResponse {
  status: string;
  version: string;
  env: string;
}
