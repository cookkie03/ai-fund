import { type Transition, type Variants } from "motion/react";

/**
 * Standard cubic-bezier settle curve from DESIGN.md:
 * cubic-bezier(0.32, 0.72, 0, 1)
 */
export const SETTLE_EASE = [0.32, 0.72, 0, 1] as const;

export const tileTransition: Transition = {
  duration: 0.26,
  ease: SETTLE_EASE,
};

export const tileEnterVariants: Record<"left" | "right" | "bottom", Variants> = {
  left: {
    initial: { opacity: 0, x: -10 },
    animate: { opacity: 1, x: 0 },
    exit: { opacity: 0 },
  },
  right: {
    initial: { opacity: 0, x: 10 },
    animate: { opacity: 1, x: 0 },
    exit: { opacity: 0 },
  },
  bottom: {
    initial: { opacity: 0, y: 10 },
    animate: { opacity: 1, y: 0 },
    exit: { opacity: 0 },
  },
};

export const rowArriveVariants: Variants = {
  initial: { opacity: 0, y: -4 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0 },
};

export const rowTransition: Transition = {
  duration: 0.26,
  ease: SETTLE_EASE,
};

export const barGrowVariants: Variants = {
  initial: { scaleX: 0, originX: 0 },
  animate: { scaleX: 1, originX: 0 },
};

export const barTransition: Transition = {
  duration: 0.52,
  ease: SETTLE_EASE,
};
