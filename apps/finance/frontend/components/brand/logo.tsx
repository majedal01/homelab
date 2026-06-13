/**
 * YNAB Insights brand mark.
 *
 * A seven-dot constellation with hairline connectors, asymmetric so it
 * leans subtly forward — the visual anchor for "spotting patterns".
 * Single-color via `currentColor` so it inherits text color and adapts
 * to light/dark without alt artwork. SVG-only; favicons reuse the same
 * geometry with a stroke-widened variant (`logo-favicon.svg`).
 */

export interface LogoMarkProps extends React.SVGProps<SVGSVGElement> {
  size?: number;
}

const POINTS = [
  // x, y on a 24x24 viewBox. Path slopes up-right.
  [3, 18],
  [8, 13],
  [12, 16],
  [15, 10],
  [18, 12],
  [20, 6],
  [22, 9],
] as const;

const STROKE_PATH = POINTS.map(
  ([x, y], i) => `${i === 0 ? "M" : "L"}${x} ${y}`,
).join(" ");

export function LogoMark({ size = 24, ...rest }: LogoMarkProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      <path d={STROKE_PATH} strokeWidth={1} opacity={0.55} />
      {POINTS.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r={1.35} fill="currentColor" />
      ))}
    </svg>
  );
}

export function LogoLockup({
  size = 24,
  showWordmark = true,
  className,
}: {
  size?: number;
  showWordmark?: boolean;
  className?: string;
}) {
  return (
    <span
      className={
        "inline-flex items-center gap-2 font-semibold tracking-tight " +
        (className ?? "")
      }
    >
      <LogoMark size={size} />
      {showWordmark ? <span>YNAB Insights</span> : null}
    </span>
  );
}
