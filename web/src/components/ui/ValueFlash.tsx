// Adapted from interior.dev (MIT, (c) 2026 ozzy): https://github.com/ddoemonn/interior (value-flash.tsx)
// Changed per docs/design/COMPONENTS.md: no green/red (a rising number is not "good" here), inherits font size,
// raised unit support, no blur, input throttled to one change per 2 s, announces only the settled value.
import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import ArrowUp from '~icons/ph/arrow-up'
import ArrowDown from '~icons/ph/arrow-down'
import { useThrottledValue } from '@/hooks/useThrottledValue'
import { cx } from './Card'

const ROLL = { type: 'spring', stiffness: 460, damping: 32, mass: 0.55 } as const
const STILL = { duration: 0 } as const
// Rising numbers roll upward (new digit arrives from below); falling numbers roll downward. Opacity only for reduced motion.
// 'still' = reduced motion (instant). 'fade' = changes arriving faster than a roll can play: a quick fade instead,
// so rapid taps or a fast slider drag never leave a pile of half-faded digits in the same spot.
type Roll = 'up' | 'down' | 'still' | 'fade'
const FADE_MS = 0.08
const VARIANTS = {
  enter: (d: Roll) => (d === 'still' || d === 'fade' ? { opacity: 0 } : { opacity: 0, y: d === 'down' ? '-0.6em' : '0.6em' }),
  center: { opacity: 1, y: '0em' },
  exit: (d: Roll) => (d === 'still' ? { opacity: 0, transition: STILL }
    : d === 'fade' ? { opacity: 0, transition: { duration: FADE_MS } }
    : { opacity: 0, y: d === 'down' ? '0.5em' : '-0.5em', transition: { duration: 0.14, ease: [0.4, 0, 1, 1] as const } }),
}
const RAPID_MS = 170

/** Marks a number that just changed: the digits roll and a soft accent tint fades out (1.2 s). Use on KPIs,
 *  stat columns and Impact figures only, never on the 100 tiles. */
export function ValueFlash({ value, format, label, hold = 1200, announceAfter = 1500, throttle = 2000, showDirection = false, className }: {
  value: number; format?: (n: number) => string; label?: string
  hold?: number; announceAfter?: number
  /** Minimum ms between displayed changes. 2000 for values pushed by the live stream (so they never flicker);
   *  0 for anything the user changes directly (slider results, a button), which must respond at once. */
  throttle?: number
  /** Optional small arrow. Direction carries no good/bad colour: more at-risk units is bad, more savings is good. */
  showDirection?: boolean; className?: string
}) {
  const shown = useThrottledValue(value, throttle)
  const reduced = useReducedMotion()
  const [flash, setFlash] = useState<{ on: boolean }>({ on: false })
  const prev = useRef(shown)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (Object.is(prev.current, shown)) return
    prev.current = shown
    setFlash({ on: true })
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => setFlash({ on: false }), hold)
  }, [shown, hold])
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current) }, [])

  const text = format ? format(shown) : String(shown)
  // Screen readers get the settled value once, not every intermediate tick.
  const [settled, setSettled] = useState(text)
  useEffect(() => { const t = setTimeout(() => setSettled(text), announceAfter); return () => clearTimeout(t) }, [text, announceAfter])

  // Direction is worked out in the same render that receives the new value. The old digit is still on screen while it
  // leaves, so it needs the NEW direction (passed through AnimatePresence `custom`), not the one it was rendered with.
  const lastShown = useRef(shown)
  const lastAt = useRef(-Infinity)
  const dirRef = useRef<'up' | 'down'>('up')
  const rapidRef = useRef(false)
  if (!Object.is(lastShown.current, shown)) {
    const now = performance.now()
    dirRef.current = shown > lastShown.current ? 'up' : 'down'
    rapidRef.current = now - lastAt.current < RAPID_MS
    lastAt.current = now
    lastShown.current = shown
  }
  const roll: Roll = reduced ? 'still' : rapidRef.current ? 'fade' : dirRef.current // reduced motion: digits never move
  const { on } = flash
  return (
    <span className={cx('relative inline-grid grid-flow-col items-center rounded-md px-1 -mx-1 tnum transition-colors duration-200', on && 'text-accent-ink', className)}>
      <motion.span aria-hidden initial={false} animate={{ opacity: on ? 1 : 0 }} transition={reduced ? STILL : { duration: on ? 0.15 : 0.5 }} className="pointer-events-none absolute inset-0 rounded-md bg-accent-soft" />
      <span aria-hidden className="relative inline-grid overflow-hidden">
        <AnimatePresence initial={false} mode="popLayout" custom={roll}>
          {/* Keyed by the text itself: the leaving digit keeps the OLD number, the arriving one has the new number. */}
          <motion.span key={text} custom={roll} className="col-start-1 row-start-1" variants={VARIANTS} initial="enter" animate="center" exit="exit"
            transition={reduced ? STILL : ROLL}>
            {text}
          </motion.span>
        </AnimatePresence>
      </span>
      {showDirection && on && <span aria-hidden className="relative ml-0.5 text-muted">{dirRef.current === 'up' ? <ArrowUp width="0.5em" height="0.5em" /> : <ArrowDown width="0.5em" height="0.5em" />}</span>}
      <span className="sr-only" aria-live="polite">{label ? `${label}: ${settled}` : settled}</span>
    </span>
  )
}
