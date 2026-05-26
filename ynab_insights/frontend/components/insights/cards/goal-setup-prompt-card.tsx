import type { GoalSetupPromptData } from "@/lib/api-types";

export function GoalSetupPromptCard({ data }: { data: GoalSetupPromptData }) {
  const top = data.top_categories.slice(0, 3).map((c) => c.category_name);
  return (
    <div className="text-sm text-muted-foreground">
      {top.length > 0 ? (
        <>
          Try setting a target on{" "}
          <span className="text-foreground">{top.join(", ")}</span> to see
          projected trajectories here.
        </>
      ) : (
        <>Set a goal on any category in YNAB to start tracking it here.</>
      )}
    </div>
  );
}
