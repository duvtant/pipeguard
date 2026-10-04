// Adapted from interior.dev (MIT, (c) 2026 ozzy): https://github.com/ddoemonn/interior (slider-detents.tsx)
// Changed per docs/design/COMPONENTS.md: our tokens, a 22 px thumb and 14 px labels (projector-readable), no haptics.
// A real role="slider": arrows step, Shift+arrow or PageUp/PageDown jump to the next snap point, Home/End go to the ends.
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import { motion, useMotionTemplate, useReducedMotion, useSpring } from 'motion/react'
import { cx } from './Card'

const CARRIAGE = { stiffness: 520, damping: 34, mass: 0.45 } as const
const THUMB = 22
const tidy = (v: number) => Math.round(v * 1e6) / 1e6
export type SliderDetent = { value: number; label?: string }
const NONE: readonly (number | SliderDetent)[] = []

function useSlider({ value, onValueChange, min, max, step, detents, pull, disabled, format, labelledBy }: {
  value: number; onValueChange: (v: number) => void; min: number; max: number; step: number
  detents: readonly (number | SliderDetent)[]; pull?: number; disabled: boolean; format: (v: number) => string; labelledBy: string
}) {
  const trackRef = useRef<HTMLDivElement>(null)
  const [dragging, setDragging] = useState(false)
  const list = useMemo<SliderDetent[]>(() => detents.map((d) => (typeof d === 'number' ? { value: d } : d)), [detents])
  const range = max - min
  const grab = pull ?? range * 0.045
  const emit = useRef(onValueChange); emit.current = onValueChange
  const emitted = useRef(value); emitted.current = value
  const held = useRef(false)
  const activeDetent = useMemo(() => list.findIndex((d) => tidy(d.value) === tidy(value)), [list, value])

  const commit = useCallback((next: number) => {
    const settled = Math.min(max, Math.max(min, tidy(next)))
    if (settled !== emitted.current) { emitted.current = settled; emit.current(settled) }
  }, [max, min])

  const capture = useCallback((clientX: number) => {
    const el = trackRef.current
    if (!el || range <= 0) return null
    const rect = el.getBoundingClientRect()
    // The page may be zoomed (projector mode), so measure in the element's own scale.
    const scale = rect.width / el.offsetWidth || 1
    const travel = el.offsetWidth - THUMB
    if (travel <= 0) return null
    const ratio = ((clientX - rect.left) / scale - THUMB / 2) / travel
    const raw = Math.min(max, Math.max(min, min + ratio * range))
    let index = -1, nearest = grab
    for (let i = 0; i < list.length; i++) { const d = Math.abs(raw - list[i].value); if (d <= nearest) { nearest = d; index = i } }
    return index >= 0 ? list[index].value : min + Math.round((raw - min) / step) * step
  }, [grab, list, max, min, range, step])

  const release = useCallback(() => { if (!held.current) return; held.current = false; setDragging(false) }, [])
  const toDetent = useCallback((dir: number) => {
    const sorted = list.map((d) => d.value).toSorted((a, b) => a - b)
    const target = dir > 0 ? sorted.find((d) => d > value + 1e-6) : sorted.findLast((d) => d < value - 1e-6)
    commit(target ?? (dir > 0 ? max : min))
  }, [commit, list, max, min, value])
  useEffect(() => { window.addEventListener('blur', release); return () => window.removeEventListener('blur', release) }, [release])

  const detentLabel = list[activeDetent]?.label
  const valueText = detentLabel ? `${format(value)}, ${detentLabel}` : format(value)
  const percent = range > 0 ? Math.min(1, Math.max(0, (value - min) / range)) : 0

  const trackProps = {
    role: 'slider' as const, tabIndex: disabled ? -1 : 0, 'aria-orientation': 'horizontal' as const,
    'aria-valuemin': min, 'aria-valuemax': max, 'aria-valuenow': value, 'aria-valuetext': valueText, 'aria-disabled': disabled || undefined, 'aria-labelledby': labelledBy,
    style: { touchAction: 'none' as const },
    onPointerDown: (e: React.PointerEvent<HTMLDivElement>) => {
      if (disabled || (e.pointerType === 'mouse' && e.button !== 0)) return
      e.currentTarget.setPointerCapture?.(e.pointerId); e.currentTarget.focus({ preventScroll: true })
      held.current = true; setDragging(true)
      const n = capture(e.clientX); if (n !== null) commit(n)
    },
    onPointerMove: (e: React.PointerEvent<HTMLDivElement>) => { if (!held.current) return; const n = capture(e.clientX); if (n !== null) commit(n) },
    onPointerUp: release, onPointerCancel: release, onLostPointerCapture: release,
    onKeyDown: (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (disabled) return
      const fwd = e.key === 'ArrowRight' || e.key === 'ArrowUp', back = e.key === 'ArrowLeft' || e.key === 'ArrowDown'
      if (fwd || back) { const d = fwd ? 1 : -1; if (e.shiftKey) toDetent(d); else commit(value + d * step) }
      else if (e.key === 'PageUp') toDetent(1)
      else if (e.key === 'PageDown') toDetent(-1)
      else if (e.key === 'Home') commit(min)
      else if (e.key === 'End') commit(max)
      else return
      e.preventDefault()
    },
  }
  return { trackRef, trackProps, detents: list, activeDetent, percent, dragging }
}

/** Labelled slider with snap points ("detents"): crews snap to whole numbers, costs snap back to their default. */
export function Slider({ value, onValueChange, min = 0, max = 100, step = 1, detents = NONE, pull, label, format = String, disabled = false, className }: {
  value: number; onValueChange: (v: number) => void; min?: number; max?: number; step?: number
  detents?: readonly (number | SliderDetent)[]; pull?: number; label: string; format?: (v: number) => string; disabled?: boolean; className?: string
}) {
  const labelId = useId()
  const reduced = useReducedMotion()
  const { trackRef, trackProps, detents: list, activeDetent, percent, dragging } = useSlider({ value, onValueChange, min, max, step, detents, pull, disabled, format, labelledBy: labelId })
  const carriage = useSpring(percent * 100, CARRIAGE)
  const offset = useMotionTemplate`${carriage}%`
  useEffect(() => { const t = percent * 100; if (reduced) carriage.jump(t); else carriage.set(t) }, [carriage, percent, reduced])
  const span = max - min
  const suffix = list[activeDetent]?.label
  // Reserve the width of the longest value so the number changing never shifts the layout.
  const widest = useMemo(() => [format(min), format(max), ...list.map((d) => (d.label ? `${format(d.value)} · ${d.label}` : format(d.value)))].reduce((a, b) => (b.length > a.length ? b : a), ''), [format, list, max, min])

  return (
    <div className={cx('w-full select-none', className)}>
      <div className="mb-1 flex items-baseline justify-between gap-3 text-text">
        <span id={labelId}>{label}</span>
        <span className="grid justify-items-end">
          <span aria-hidden className="invisible col-start-1 row-start-1 whitespace-pre text-sm tnum">{widest}</span>
          <span aria-hidden className="col-start-1 row-start-1 whitespace-pre text-sm tnum [font-weight:var(--w-strong)] text-ink">
            {format(value)}{suffix && <span className="text-muted [font-weight:var(--w-body)]"> · {suffix}</span>}
          </span>
        </span>
      </div>
      <div ref={trackRef} {...trackProps}
        className={cx('relative h-9 w-full rounded-[10px] outline-none focus-visible:ring-2 focus-visible:ring-accent', disabled ? 'pointer-events-none opacity-50' : dragging ? 'cursor-grabbing' : 'cursor-grab')}>
        <div className="pointer-events-none absolute inset-x-0 top-[15px] h-1.5 overflow-hidden rounded-full bg-line">
          <div className="absolute inset-y-0" style={{ left: THUMB / 2, right: THUMB / 2 }}>
            <motion.div className="absolute inset-y-0 left-0 right-0" style={{ x: offset }}><div className="absolute inset-y-0 right-full w-[2000px] bg-accent" /></motion.div>
          </div>
        </div>
        <div className="pointer-events-none absolute inset-y-0" style={{ left: THUMB / 2, right: THUMB / 2 }}>
          {list.map((d) => <span key={d.value} aria-hidden className="absolute top-[24px] block h-1.5 w-0.5 -translate-x-1/2 rounded-full bg-accent/35" style={{ left: span > 0 ? `${((d.value - min) / span) * 100}%` : '0%' }} />)}
        </div>
        <div className="pointer-events-none absolute inset-y-0" style={{ left: THUMB / 2, right: THUMB / 2 }}>
          <motion.div className="absolute inset-y-0 left-0 right-0" style={{ x: offset }}>
            <motion.div className="absolute top-[7px] rounded-full border-[3px] border-accent bg-white shadow-[0_2px_6px_rgba(83,103,235,0.3)]" style={{ width: THUMB, height: THUMB, marginLeft: -THUMB / 2 }}
              initial={false} animate={{ scale: dragging ? 1.1 : 1 }} transition={reduced ? { duration: 0 } : { type: 'spring', stiffness: 700, damping: 46, mass: 0.5 }} />
          </motion.div>
        </div>
      </div>
    </div>
  )
}
