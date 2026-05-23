"use client";

import * as React from "react";

/**
 * Number count-up. Tween from 0 → target value over `durationMs`. Triggers
 * once per mount when the element enters the viewport. Respects
 * `prefers-reduced-motion` (renders the final value immediately).
 *
 * Prop contract is intentionally narrow: the parent owns formatting so
 * this stays agnostic to dollars, percents, etc.
 */
export interface CountUpProps {
  /** Target numeric value (e.g. raw cents, not formatted dollars). */
  value: number;
  /** Format the interpolated value into the display string. */
  format: (v: number) => string;
  durationMs?: number;
  className?: string;
}

/** Frontloaded ease — most of the motion in the first 40% of the tween. */
function easeOutExpo(t: number): number {
  return t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
}

export function CountUp({
  value,
  format,
  durationMs = 800,
  className,
}: CountUpProps) {
  const [display, setDisplay] = React.useState(() => format(0));
  const ref = React.useRef<HTMLSpanElement | null>(null);
  const playedRef = React.useRef(false);

  React.useEffect(() => {
    if (typeof window === "undefined") return;
    const reduce = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;

    // Once the in-view animation has played once, subsequent value changes
    // (e.g. user picks a new date range) snap straight to the new value.
    // Re-animating on every filter change would feel laggy.
    if (reduce || playedRef.current) {
      setDisplay(format(value));
      return;
    }

    const el = ref.current;
    if (!el) {
      setDisplay(format(value));
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (!entry?.isIntersecting || playedRef.current) return;
        playedRef.current = true;
        const start = performance.now();
        let frame = 0;
        const tick = (now: number) => {
          const t = Math.min(1, (now - start) / durationMs);
          const eased = easeOutExpo(t);
          setDisplay(format(Math.round(value * eased)));
          if (t < 1) frame = requestAnimationFrame(tick);
        };
        frame = requestAnimationFrame(tick);
        observer.disconnect();
        return () => cancelAnimationFrame(frame);
      },
      { threshold: 0.4 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [value, format, durationMs]);

  return (
    <span ref={ref} className={className}>
      {display}
    </span>
  );
}
