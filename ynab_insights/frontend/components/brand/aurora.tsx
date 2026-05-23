/**
 * Ambient aurora wash.
 *
 * Three radial gradients on absolutely-positioned divs, blurred heavily
 * and translated slowly via CSS keyframes. Sits inside a fixed-position,
 * `pointer-events-none`, `z-index: -1` container so it never affects
 * layout or hit-testing.
 *
 * Variants:
 *   - "primary"  — feed page; three washes, full motion
 *   - "quiet"    — detail + Ask; one wash, no motion
 *
 * Palette + opacity values match the table in DESIGN.md ("Aurora
 * background" section). Tune there first, here second.
 */

import { cn } from "@/lib/utils";

export interface AuroraProps {
  variant?: "primary" | "quiet";
  className?: string;
}

export function Aurora({ variant = "primary", className }: AuroraProps) {
  if (variant === "quiet") {
    return (
      <div
        aria-hidden="true"
        className={cn(
          "pointer-events-none fixed inset-0 -z-10 overflow-hidden",
          className,
        )}
      >
        <div className="aurora-wash aurora-wash--indigo aurora-wash--quiet" />
      </div>
    );
  }

  return (
    <div
      aria-hidden="true"
      className={cn(
        "pointer-events-none fixed inset-0 -z-10 overflow-hidden",
        className,
      )}
    >
      <div className="aurora-wash aurora-wash--indigo" />
      <div className="aurora-wash aurora-wash--violet" />
      <div className="aurora-wash aurora-wash--cyan" />
    </div>
  );
}
