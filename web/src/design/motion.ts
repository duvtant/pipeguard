// Motion tokens for the `motion` library. CSS equivalents live in tokens.css (DESIGN.md section 9).
// Rules: animate transform and opacity only, never on every live tick, always honour reduced motion.
export const ease = {
  out: [0.22, 1, 0.36, 1],
  fluid: [0.32, 0.72, 0, 1],
  exit: [0.4, 0, 1, 1],
} as const

export const dur = { instant: 0.09, fast: 0.15, base: 0.24, slow: 0.36, chart: 0.8, flash: 1.2 } as const

export const spring = {
  panel: { type: 'spring', stiffness: 380, damping: 34 },
  pop: { type: 'spring', stiffness: 600, damping: 22 }, // the only place a hint of overshoot is allowed
} as const

/** Cards fade up 8px on a route change, staggered 40ms, at most 6 items. */
export const pageItem = (i: number) => ({
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: dur.base, ease: ease.out, delay: Math.min(i, 5) * 0.04 },
})
