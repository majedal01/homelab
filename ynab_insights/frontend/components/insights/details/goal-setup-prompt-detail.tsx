import { formatDollars } from "@/lib/utils";
import type { GoalSetupPromptData } from "@/lib/api-types";

export function GoalSetupPromptDetail({
  data,
}: {
  data: GoalSetupPromptData;
}) {
  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">
        No goals set in YNAB. Pick a category, open it in YNAB, and set a
        monthly target or a target-by-date goal. We&apos;ll start tracking
        projected trajectories the next time you regenerate insights.
      </p>
      <div>
        <h2 className="text-sm font-semibold tracking-tight">
          Candidate categories
        </h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Your top spending categories, ranked by trailing-12-month average.
          These are good places to set a target.
        </p>
        <table className="mt-3 w-full text-sm">
          <thead>
            <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
              <th className="py-2 font-medium">Category</th>
              <th className="py-2 text-right font-medium">Avg / month</th>
            </tr>
          </thead>
          <tbody>
            {data.top_categories.map((c) => (
              <tr key={c.category_id} className="border-b last:border-b-0">
                <td className="py-2">{c.category_name}</td>
                <td className="py-2 text-right tabular-nums">
                  {formatDollars(c.monthly_avg_spend_cents)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <a
        href="https://app.youneedabudget.com/"
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 text-sm font-medium underline-offset-4 hover:underline"
      >
        Open YNAB
      </a>
    </div>
  );
}
