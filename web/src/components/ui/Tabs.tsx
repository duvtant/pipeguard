import { motion } from 'motion/react'
import { useId } from 'react'
import { cx } from './Card'

/** Text tabs; the 2px accent underline slides between tabs (DESIGN.md 5.6, 9.2). */
export function Tabs<T extends string>({ label, value, onChange, tabs }: { label: string; value: T; onChange: (v: T) => void; tabs: { value: T; label: string }[] }) {
  const id = useId()
  return (
    <div role="tablist" aria-label={label} className="flex flex-wrap gap-x-5 gap-y-1">
      {tabs.map((t) => {
        const on = t.value === value
        return (
          <button key={t.value} type="button" role="tab" aria-selected={on} onClick={() => onChange(t.value)}
            className={cx('relative min-h-9 text-sm transition-colors duration-150', on ? '[font-weight:var(--w-strong)] text-ink' : 'text-muted hover:text-ink')}>
            {t.label}
            {on && <motion.span layoutId={`tab-${id}`} className="absolute inset-x-0 bottom-0 h-0.5 rounded-full bg-accent" transition={{ duration: 0.24, ease: [0.32, 0.72, 0, 1] }} />}
          </button>
        )
      })}
    </div>
  )
}
