import type { ReactNode } from 'react'
import SealCheck from '~icons/ph/seal-check-fill'

export const cx = (...a: (string | false | null | undefined)[]) => a.filter(Boolean).join(' ')

/** White card, 18px radius, lavender-glow edge instead of a grey border (DESIGN.md 3.4, 5.3). */
export function Card({ children, className, pad = true }: { children: ReactNode; className?: string; pad?: boolean }) {
  return <section className={cx('relative overflow-hidden rounded-card bg-canvas shadow-card', pad && 'px-6 py-5', className)}>{children}</section>
}

export function CardHeader({ title, verified, actions, className }: { title: ReactNode; verified?: boolean; actions?: ReactNode; className?: string }) {
  return (
    <div className={cx('mb-1 flex items-center gap-2 text-[15px] text-text', className)}>
      <h2 className="m-0 text-[15px] [font-weight:var(--w-body)]">{title}</h2>
      {verified && <SealCheck width={18} height={18} className="text-accent" aria-label="Verified" role="img" />}
      {actions && <div className="ml-auto flex items-center gap-2">{actions}</div>}
    </div>
  )
}

/** Big number with a small raised unit: `3ᵘⁿⁱᵗˢ` (DESIGN.md 3.3). */
export function Num({ value, unit, size = 'lg', className }: { value: ReactNode; unit?: string; size?: 'lg' | 'md' | 'sm'; className?: string }) {
  const s = size === 'lg' ? 'text-[32px] leading-9' : size === 'md' ? 'text-2xl leading-7' : 'text-[22px] leading-7'
  return (
    <span className={cx('tnum [font-weight:var(--w-strong)] tracking-[-0.02em] text-ink', s, className)}>
      {value}
      {unit && <sup className="relative top-[0.55em] ml-1 align-top text-[max(13px,0.4em)] [font-weight:var(--w-strong)] leading-none tracking-normal text-muted">{unit}</sup>}
    </span>
  )
}
