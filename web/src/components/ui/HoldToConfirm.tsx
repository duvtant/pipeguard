// Adapted from interior.dev (MIT, (c) 2026 ozzy): https://github.com/ddoemonn/interior (hold-to-confirm.tsx)
// Changed per docs/design/COMPONENTS.md: 900 ms hold, --risk fill, our pill, Phosphor check, no haptics.
// The fill sweep is the one place linear easing is allowed: a progress sweep must track elapsed time (DESIGN.md 9.5).
import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { animate, motion, useMotionValue, useReducedMotion, useTransform } from 'motion/react'
import Check from '~icons/ph/check'
import { cx } from './Card'

const FACE = { type: 'spring', stiffness: 260, damping: 34, mass: 0.8 } as const
type HoldPhase = 'idle' | 'holding' | 'releasing' | 'committed'

function useHoldToConfirm({ onConfirm, onAbort, duration, steps = 20, releaseRate = 2.5, moveTolerance = 10, disabled = false }: {
  onConfirm: () => void; onAbort?: () => void; duration: number; steps?: number; releaseRate?: number; moveTolerance?: number; disabled?: boolean
}) {
  const [phase, setPhase] = useState<HoldPhase>('idle')
  const phaseRef = useRef<HoldPhase>('idle')
  const down = useRef(false)
  const elapsed = useRef(0)
  const last = useRef(0)
  const raf = useRef(0)
  const origin = useRef<{ x: number; y: number } | null>(null)
  const confirm = useRef(onConfirm); confirm.current = onConfirm
  const abort = useRef(onAbort); abort.current = onAbort
  const move = useCallback((next: HoldPhase) => { phaseRef.current = next; setPhase(next) }, [])

  const reset = useCallback(() => {
    cancelAnimationFrame(raf.current); raf.current = 0
    down.current = false; elapsed.current = 0; origin.current = null
    move('idle')
  }, [move])

  const begin = useCallback((point?: { x: number; y: number }) => {
    if (disabled || phaseRef.current === 'committed' || phaseRef.current === 'holding') return
    origin.current = point ?? null
    down.current = true
    move('holding')
    if (raf.current) return
    last.current = performance.now()
    const loop = (now: number) => {
      // The frame timestamp can be a hair earlier than `last` on the first frame; a negative step must never count.
      const dt = Math.max(0, Math.min(64, now - last.current))
      last.current = now
      elapsed.current += down.current ? dt : -dt * releaseRate
      if (elapsed.current >= duration) {
        raf.current = 0; elapsed.current = duration; down.current = false; origin.current = null
        move('committed'); confirm.current(); return
      }
      if (!down.current && elapsed.current <= 0) { raf.current = 0; elapsed.current = 0; origin.current = null; move('idle'); return }
      raf.current = requestAnimationFrame(loop)
    }
    raf.current = requestAnimationFrame(loop)
  }, [disabled, duration, releaseRate, move])

  const release = useCallback(() => {
    if (phaseRef.current !== 'holding') return
    down.current = false; origin.current = null
    move('releasing'); abort.current?.()
  }, [move])

  // Leaving the window or hiding the tab cancels the hold: it must never complete unattended.
  useEffect(() => {
    const bail = () => release()
    const onVis = () => { if (document.hidden) release() }
    window.addEventListener('blur', bail); document.addEventListener('visibilitychange', onVis)
    return () => { window.removeEventListener('blur', bail); document.removeEventListener('visibilitychange', onVis); cancelAnimationFrame(raf.current); raf.current = 0 }
  }, [release])

  const bind = {
    onPointerDown: (e: React.PointerEvent) => { if (e.pointerType === 'mouse' && e.button !== 0) return; e.currentTarget.setPointerCapture?.(e.pointerId); begin({ x: e.clientX, y: e.clientY }) },
    onPointerMove: (e: React.PointerEvent) => { const from = origin.current; if (phaseRef.current !== 'holding' || !from) return; if (Math.hypot(e.clientX - from.x, e.clientY - from.y) > moveTolerance) release() },
    onPointerUp: release, onPointerCancel: release, onPointerLeave: release,
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === 'Escape') { if (phaseRef.current === 'holding' || phaseRef.current === 'releasing') { e.preventDefault(); reset() } return }
      if (e.repeat) return
      if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); begin() }
    },
    onKeyUp: (e: React.KeyboardEvent) => { if (e.key === ' ' || e.key === 'Enter') release() },
    onBlur: release,
    onClick: (e: React.MouseEvent) => { e.preventDefault(); if (phaseRef.current === 'committed') e.stopPropagation() },
    onContextMenu: (e: React.MouseEvent) => e.preventDefault(),
  }
  return { bind, phase, reset, steps }
}

function Faces({ committed, confirmLabel, children }: { committed: boolean; confirmLabel: string; children: ReactNode }) {
  return (
    <span className="col-start-1 row-start-1 grid">
      <motion.span initial={false} animate={{ opacity: committed ? 0 : 1 }} transition={FACE} className="col-start-1 row-start-1 flex items-center justify-center gap-1.5 whitespace-nowrap">{children}</motion.span>
      <motion.span initial={false} animate={{ opacity: committed ? 1 : 0 }} transition={FACE} className="col-start-1 row-start-1 flex items-center justify-center gap-1.5 whitespace-nowrap">
        <Check width={16} height={16} aria-hidden />{confirmLabel}
      </motion.span>
    </span>
  )
}

/** A button you must press and hold. Releasing early, moving away, switching tabs or pressing Escape cancels it. */
export function HoldToConfirm({ onConfirm, onAbort, children, confirmLabel = 'Confirmed', duration = 900, resetAfter = 1600, releaseRate = 2.5, disabled = false, className }: {
  onConfirm: () => void; onAbort?: () => void; children: ReactNode
  confirmLabel?: string; duration?: number; resetAfter?: number; releaseRate?: number; disabled?: boolean; className?: string
}) {
  const { bind, phase, reset } = useHoldToConfirm({ onConfirm, onAbort, duration, releaseRate, disabled })
  const reduced = useReducedMotion()
  const hintId = useId()
  const committed = phase === 'committed'
  const seconds = Math.round(duration / 100) / 10
  const swept = useMotionValue(0)
  const clipPath = useTransform(swept, (v) => `inset(0 ${(1 - v) * 100}% 0 0)`)

  useEffect(() => {
    if (phase !== 'committed' || resetAfter <= 0) return
    const back = setTimeout(reset, resetAfter)
    return () => clearTimeout(back)
  }, [phase, resetAfter, reset])

  useEffect(() => {
    // Reduced motion: the fill appears instantly, but the full hold is still required.
    if (reduced) { swept.set(phase === 'holding' || phase === 'committed' ? 1 : 0); return }
    if (phase === 'committed') { const c = animate(swept, 1, { duration: 0.12, ease: 'linear' }); return () => c.stop() }
    const from = swept.get()
    if (phase === 'holding') { const c = animate(swept, 1, { duration: (duration * (1 - from)) / 1000, ease: 'linear' }); return () => c.stop() }
    const c = animate(swept, 0, { duration: (duration * from) / releaseRate / 1000, ease: [0.22, 1, 0.36, 1] })
    return () => c.stop()
  }, [phase, duration, releaseRate, reduced, swept])

  return (
    <button type="button" aria-disabled={disabled || committed} aria-describedby={hintId} {...bind}
      style={{ touchAction: 'manipulation', WebkitTouchCallout: 'none' }}
      className={cx('relative isolate inline-grid min-h-9 select-none place-items-center overflow-hidden rounded-full bg-pill px-4 text-sm text-ink [font-weight:var(--w-strong)] outline-none', disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer', className)}>
      <Faces committed={committed} confirmLabel={confirmLabel}>{children}</Faces>
      <motion.span aria-hidden style={{ clipPath }} className="absolute inset-0 grid place-items-center bg-risk px-4 text-white">
        <Faces committed={committed} confirmLabel={confirmLabel}>{children}</Faces>
      </motion.span>
      <span id={hintId} className="sr-only">Press and hold for {seconds} seconds to confirm. Releasing early cancels and nothing happens.</span>
      <span role="status" aria-live="polite" className="sr-only">{committed ? confirmLabel : ''}</span>
    </button>
  )
}
