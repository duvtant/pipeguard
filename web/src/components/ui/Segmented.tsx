// Adapted from interior.dev (MIT, (c) 2026 ozzy): https://github.com/ddoemonn/interior (segmented-control.tsx)
// Changed per docs/design/COMPONENTS.md: icon options (label kept for screen readers), a white thumb with an accent ring
// instead of the inverted-label mask, our tokens. A true radiogroup: roving tabindex, Arrow/Home/End keys.
import { useCallback, useEffect, useRef, type ReactNode } from 'react'
import { animate, motion, useMotionValue, useReducedMotion, useTransform } from 'motion/react'
import { cx } from './Card'

const CELL = { type: 'spring', stiffness: 520, damping: 34, mass: 0.45 } as const

export function Segmented<T extends string>({ label, value, onChange, options, className }: {
  label: string; value: T; onChange: (v: T) => void; className?: string
  options: { value: T; label: string; icon: ReactNode; disabled?: boolean }[]
}) {
  const count = Math.max(1, options.length)
  const found = options.findIndex((o) => o.value === value)
  const index = found < 0 ? 0 : found
  const buttons = useRef<(HTMLButtonElement | null)[]>([])
  const reduced = useReducedMotion()
  const pos = useMotionValue(index)
  const thumbX = useTransform(pos, (v) => `${v * 100}%`)

  useEffect(() => {
    if (reduced) { pos.set(index); return }
    const c = animate(pos, index, CELL)
    return () => c.stop()
  }, [index, reduced, pos])

  const seek = useCallback((from: number, dir: number) => {
    let i = from
    for (let k = 0; k < count; k++) { i = (i + dir + count) % count; if (!options[i]?.disabled) return i }
    return from
  }, [count, options])
  const go = (i: number) => { const o = options[i]; if (!o || o.disabled) return; buttons.current[i]?.focus(); onChange(o.value) }
  const onKeyDown = (e: React.KeyboardEvent, i: number) => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { e.preventDefault(); go(seek(i, 1)) }
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { e.preventDefault(); go(seek(i, -1)) }
    else if (e.key === 'Home') { e.preventDefault(); go(seek(count - 1, 1)) }
    else if (e.key === 'End') { e.preventDefault(); go(seek(0, -1)) }
  }

  return (
    <div role="radiogroup" aria-label={label} className={cx('relative inline-block select-none rounded-[10px] border border-line p-0.5', className)}>
      <div className="relative grid" style={{ gridTemplateColumns: `repeat(${count}, minmax(0, 1fr))`, touchAction: 'manipulation' }}>
        <motion.div aria-hidden initial={false} className="pointer-events-none absolute inset-y-0 left-0 rounded-[8px] bg-white shadow-[inset_0_0_0_1px_rgba(83,103,235,0.3)]"
          style={{ width: `${100 / count}%`, x: thumbX }} />
        {options.map((o, i) => {
          const on = i === index
          return (
            <button key={o.value} ref={(n) => { buttons.current[i] = n }} type="button" role="radio" aria-checked={on} aria-label={o.label} title={o.label}
              aria-disabled={o.disabled || undefined} tabIndex={on ? 0 : -1} onClick={() => !o.disabled && onChange(o.value)} onKeyDown={(e) => onKeyDown(e, i)}
              className={cx('relative grid size-8 place-items-center rounded-[8px] transition-colors duration-150', on ? 'text-accent' : 'text-muted hover:text-ink', o.disabled && 'opacity-40')}>
              <span aria-hidden className="grid place-items-center">{o.icon}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
