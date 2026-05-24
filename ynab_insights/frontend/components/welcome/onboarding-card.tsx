"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, ExternalLink, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
  ANTHROPIC_MODELS,
  DEFAULT_ANTHROPIC_MODEL,
  type BudgetOption,
  type CreateSessionResponse,
  type SessionErrorBody,
} from "@/lib/api-types";

type Step = "tokens" | "budget";

interface OnboardingCardProps {
  next?: string;
}

export function OnboardingCard({ next }: OnboardingCardProps) {
  const router = useRouter();
  const [step, setStep] = React.useState<Step>("tokens");
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [budgets, setBudgets] = React.useState<BudgetOption[]>([]);
  const [selectedBudget, setSelectedBudget] = React.useState<string | null>(null);
  const [model, setModel] = React.useState<string>(DEFAULT_ANTHROPIC_MODEL);

  async function onTokenSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const ynabToken = (form.get("ynab_token") ?? "").toString().trim();
    const anthropicKey = (form.get("anthropic_key") ?? "").toString().trim();
    try {
      const response = await fetch("/api/session", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          ynab_token: ynabToken,
          anthropic_key: anthropicKey,
          anthropic_model: model,
        }),
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as
          | { detail?: SessionErrorBody }
          | null;
        setError(messageFor(body?.detail) ?? `Sign-in failed (${response.status}).`);
        return;
      }
      const data = (await response.json()) as CreateSessionResponse;
      setBudgets(data.budgets);
      setSelectedBudget(pickDefault(data.budgets));
      setStep("budget");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Network error.");
    } finally {
      setSubmitting(false);
    }
  }

  async function onBudgetSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedBudget) return;
    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch("/api/session/budget", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ budget_id: selectedBudget }),
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as
          | { detail?: SessionErrorBody }
          | null;
        setError(messageFor(body?.detail) ?? `Couldn't pull that budget (${response.status}).`);
        return;
      }
      router.push(next || "/insights");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Network error.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card className="bg-card/80 backdrop-blur">
      <CardContent className="p-6">
        {step === "tokens" ? (
          <form onSubmit={onTokenSubmit} className="space-y-4">
            <div>
              <h1 className="text-xl font-semibold tracking-tight">Sign in with your keys.</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                Bring your own YNAB token and Anthropic key. We hold them in memory only.
              </p>
            </div>
            <Field
              name="ynab_token"
              label="YNAB personal access token"
              placeholder="64-character hex string"
              hint="From YNAB account settings"
              hintHref="https://app.ynab.com/settings/developer"
              required
              autoFocus
            />
            <Field
              name="anthropic_key"
              label="Anthropic API key"
              placeholder="sk-ant-..."
              hint="From console.anthropic.com"
              hintHref="https://console.anthropic.com/settings/keys"
              required
            />
            <ModelPicker value={model} onChange={setModel} disabled={submitting} />
            {error && (
              <p className="text-sm text-destructive" role="alert">
                {error}
              </p>
            )}
            <Button type="submit" disabled={submitting} className="w-full">
              {submitting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Verifying…
                </>
              ) : (
                <>
                  Continue
                  <ArrowRight className="ml-2 h-4 w-4" />
                </>
              )}
            </Button>
          </form>
        ) : (
          <form onSubmit={onBudgetSubmit} className="space-y-4">
            <div>
              <h1 className="text-xl font-semibold tracking-tight">Pick a budget.</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                Your YNAB account has {budgets.length}. The session holds one at a time;
                you can switch later by signing out and back in.
              </p>
            </div>
            <ul className="space-y-2">
              {budgets.map((b) => (
                <li key={b.id}>
                  <label
                    className={
                      "flex cursor-pointer items-center gap-3 rounded-md border bg-background px-3 py-2.5 text-sm transition-colors " +
                      (selectedBudget === b.id ? "border-primary" : "hover:border-foreground/30")
                    }
                  >
                    <input
                      type="radio"
                      name="budget"
                      value={b.id}
                      checked={selectedBudget === b.id}
                      onChange={() => setSelectedBudget(b.id)}
                      className="h-4 w-4"
                    />
                    <span className="flex-1 truncate font-medium">{b.name}</span>
                    <span className="text-xs text-muted-foreground">
                      modified {formatModified(b.last_modified_on)}
                    </span>
                  </label>
                </li>
              ))}
            </ul>
            {error && (
              <p className="text-sm text-destructive" role="alert">
                {error}
              </p>
            )}
            <Button
              type="submit"
              disabled={submitting || !selectedBudget}
              className="w-full"
            >
              {submitting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Pulling your data…
                </>
              ) : (
                <>
                  Open insights
                  <ArrowRight className="ml-2 h-4 w-4" />
                </>
              )}
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}

interface FieldProps {
  name: string;
  label: string;
  placeholder?: string;
  hint?: string;
  hintHref?: string;
  required?: boolean;
  autoFocus?: boolean;
}

function Field({ name, label, placeholder, hint, hintHref, required, autoFocus }: FieldProps) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={name} className="block text-sm font-medium">
        {label}
      </label>
      <Input
        id={name}
        name={name}
        type="password"
        autoComplete="off"
        placeholder={placeholder}
        required={required}
        autoFocus={autoFocus}
      />
      {hint && (
        <p className="text-xs text-muted-foreground">
          {hintHref ? (
            <a
              href={hintHref}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 underline-offset-4 hover:underline"
            >
              {hint}
              <ExternalLink className="h-3 w-3" />
            </a>
          ) : (
            hint
          )}
        </p>
      )}
    </div>
  );
}

function ModelPicker({
  value,
  onChange,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="space-y-1.5">
      <span className="block text-sm font-medium">Model</span>
      <div className="grid gap-1.5 sm:grid-cols-3">
        {ANTHROPIC_MODELS.map((m) => {
          const active = m.value === value;
          return (
            <button
              key={m.value}
              type="button"
              onClick={() => onChange(m.value)}
              disabled={disabled}
              aria-pressed={active}
              className={cn(
                "flex flex-col items-start gap-0.5 rounded-md border p-2.5 text-left text-xs transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                active
                  ? "border-foreground bg-foreground/5"
                  : "border-border bg-background hover:border-foreground/30",
                disabled && "opacity-60",
              )}
            >
              <span className="text-sm font-medium">{m.label}</span>
              <span className="text-muted-foreground">{m.tagline}</span>
            </button>
          );
        })}
      </div>
      <p className="text-xs text-muted-foreground">
        You can&apos;t switch mid-session. End the session in Settings to re-pick.
      </p>
    </div>
  );
}

function messageFor(detail: SessionErrorBody | undefined | null): string | null {
  if (!detail) return null;
  // Backend already returns user-facing copy; fall back to the code if missing.
  return detail.message || detail.error;
}

function pickDefault(budgets: BudgetOption[]): string | null {
  if (budgets.length === 0) return null;
  return [...budgets].sort((a, b) =>
    a.last_modified_on < b.last_modified_on ? 1 : -1,
  )[0].id;
}

function formatModified(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}
