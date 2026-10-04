import type { ReactNode } from 'react'
import { cx } from './Card'
import Info from '~icons/ph/info'
import Check from '~icons/ph/check-circle-fill'
import Octagon from '~icons/ph/warning-octagon-fill'
import { Link } from 'react-router-dom'
import ArrowRight from '~icons/ph/arrow-right'

// Insight strip: the gradient footer inside a card where the product says what to do next.
// A gradient is never the only signal: every strip carries an icon and words (DESIGN.md 3.2, 5.4).
const TONE = {
  insight: { bg: 'bg-[image:var(--g-insight)]', icon: 'text-accent', Icon: Info },
  calm: { bg: 'bg-[image:var(--g-calm)]', icon: 'text-ok', Icon: Check },
  attention: { bg: 'bg-[image:var(--g-attn)]', icon: 'text-risk', Icon: Octagon },
} as const

export function Strip({
  tone = 'insight', title, subtitle, icon, action, onAction, to, className,
}: {
  tone?: keyof typeof TONE; title: ReactNode; subtitle?: ReactNode; icon?: ReactNode
  /** Optional trailing control. A short label makes a pill ("Review"); without one it is a circular arrow.
   *  Give `to` (a route) or `onAction`; with neither, the strip is informational and has no control. */
  action?: string; onAction?: () => void; to?: string; className?: string
}) {
  const t = TONE[tone]
  const cls = cx(
    'ml-auto flex flex-none items-center justify-center bg-white/70 [font-weight:var(--w-strong)] text-ink transition-[background-color,transform] duration-150 ease-[var(--ease-out)] hover:bg-white active:scale-[0.98]',
    action ? 'h-8 gap-1.5 rounded-full px-3.5 text-sm' : 'size-8 rounded-full',
  )
  const inner = <><ArrowRight width={action ? 14 : 16} height={action ? 14 : 16} aria-hidden />{action}</>
  return (
    <div className={cx('flex items-center gap-3 px-6 py-3 text-ink', t.bg, className)}>
      <span className={cx('grid size-8 flex-none place-items-center rounded-full bg-white/80', t.icon)}>
        {icon ?? <t.Icon width={16} height={16} aria-hidden />}
      </span>
      <div className="min-w-0">
        <b className="block [font-weight:var(--w-strong)]">{title}</b>
        {subtitle && <span className="text-[13px] text-muted">{subtitle}</span>}
      </div>
      {to ? <Link to={to} className={cls} aria-label={action ? undefined : `Open: ${typeof title === 'string' ? title : 'details'}`}>{inner}</Link>
        : onAction ? <button type="button" onClick={onAction} className={cls} aria-label={action ? undefined : 'Open'}>{inner}</button> : null}
    </div>
  )
}
