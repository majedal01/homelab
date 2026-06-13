/**
 * Centralized motion tokens.
 *
 * Single source of truth for durations, easings, and stagger values. If a
 * card feels too snappy or too sluggish, change it here once and the
 * adjustment propagates through every component that imports `MOTION`.
 */

import type { Transition } from "motion/react";

const fastEase = [0.16, 1, 0.3, 1] as const;
const standardEase = [0.4, 0, 0.2, 1] as const;

export const MOTION = {
  /** Durations in seconds (Framer Motion convention). */
  d: {
    instant: 0.12,
    fast: 0.2,
    base: 0.28,
    slow: 0.42,
    hero: 0.68,
  },
  /** Easing curves. */
  e: {
    /** Expo-out — default for card/detail springs and most reveals. */
    out: fastEase,
    /** Material standard — symmetric in-out. */
    inOut: standardEase,
  },
  /** Card → detail morph and other layout transitions. */
  spring: {
    type: "spring",
    stiffness: 380,
    damping: 32,
  } satisfies Transition,
  /** Stagger between sibling cards on feed entrance. */
  stagger: 0.05,
} as const;

/** Convenience: a Transition object for the "appear" gesture. */
export const APPEAR_TRANSITION: Transition = {
  duration: MOTION.d.base,
  ease: MOTION.e.out as unknown as [number, number, number, number],
};
