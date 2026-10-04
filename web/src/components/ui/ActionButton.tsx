// Adapted from interior.dev (MIT, (c) 2026 ozzy): https://github.com/ddoemonn/interior (loading-button.tsx)
// Changed per docs/design/COMPONENTS.md: our two variants, an icon, success in --ok and error in --risk, no blur.
// All four faces share one grid cell, so the button never changes width.
import type { ReactNode } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import Check from '~icons/ph/check-circle-fill'
import Warning from '~icons/ph/warning-fill'
import { useAsyncAction } from '@/hooks/useAsyncAction'
import { cx } from './Card'

const FADE = { type: 'spring', stiffness: 260, damping: 34, mass: 0.8 } as const
const INSTANT = { duration: 0 } as const

// The one decorative-free loop we allow: a spinner, only while a request is pending (DESIGN.md 9.5). Still under reduced motion.
function Spinner({ still }: { still: boolean }) {
  return (
    <motion.svg width="14" height="14" viewBox="0 0 12 12" fill="none" aria-hidden className="shrink-0"
      animate={still ? undefined : { rotate: 360 }} transition={still ? undefined : { duration: 0.85, repeat: Infinity, ease: 'linear' }}>
      <circle cx="6" cy="6" r="4.5" stroke="currentColor" strokeWidth="1.5" strokeOpacity="0.28" />
      <path d="M10.5 6A4.5 4.5 0 0 0 6 1.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </motion.svg>
  )
}

export function ActionButton({ onAction, children, icon, variant = 'chip', pendingLabel, successLabel = 'Done', errorLabel = 'Try again', resetAfter = 1400, disabled, onError, className }: {
  onAction: () => unknown; children: string; icon?: ReactNode; variant?: 'primary' | 'chip'
  pendingLabel?: string; successLabel?: string; errorLabel?: string; resetAfter?: number
  disabled?: boolean; onError?: (error: unknown) => void; className?: string
}) {
  const reduced = useReducedMotion()
  const { status, run, pending } = useAsyncAction({ action: onAction, resetAfter, onError })
  const fade = reduced ? INSTANT : FADE
  const primary = variant === 'primary'
  const label = status === 'pending' ? (pendingLabel ?? children) : status === 'success' ? successLabel : status === 'error' ? errorLabel : children

  const faces = [
    { key: 'idle', text: children, icon, tone: '' },
    { key: 'pending', text: pendingLabel ?? children, icon: <Spinner still={reduced === true || status !== 'pending'} />, tone: primary ? 'text-white/85' : 'text-muted' },
    { key: 'success', text: successLabel, icon: <Check width={16} height={16} />, tone: primary ? '' : 'text-ok' },
    { key: 'error', text: errorLabel, icon: <Warning width={16} height={16} />, tone: primary ? '' : 'text-risk' },
  ]
  // Solid buttons change their background for success and error (white on --ok and --risk both pass 5:1).
  const surface = primary
    ? status === 'success' ? 'bg-ok text-white' : status === 'error' ? 'bg-risk text-white' : 'bg-accent text-white hover:bg-accent-ink'
    : status === 'success' ? 'bg-pill text-ink' // no hover darkening while the green "Done" shows: green on the darker hover grey is under 4.5:1
    : 'bg-pill text-ink hover:bg-line'

  return (
    <>
      <motion.button type="button" disabled={disabled} aria-label={label} aria-busy={pending || undefined} aria-disabled={pending || undefined}
        whileTap={disabled || pending || reduced ? undefined : { scale: 0.98 }}
        onClick={(e) => { if (pending) { e.preventDefault(); return } run() }}
        className={cx('relative inline-flex min-h-8 select-none items-center justify-center rounded-full px-3.5 text-sm outline-none transition-colors duration-150 disabled:opacity-60', primary && '[font-weight:var(--w-strong)]', surface, className)}
        style={{ touchAction: 'manipulation' }}>
        <span aria-hidden className="relative grid place-items-center">
          {faces.map((f) => (
            <motion.span key={f.key} initial={false} animate={f.key === status ? { opacity: 1, y: 0 } : { opacity: 0, y: 3 }} transition={fade}
              className={cx('col-start-1 row-start-1 flex items-center justify-center gap-1.5 whitespace-nowrap', f.tone)}>
              {f.icon}{f.text}
            </motion.span>
          ))}
        </span>
      </motion.button>
      <span role="status" aria-live="polite" className="sr-only">{status === 'success' ? successLabel : status === 'error' ? errorLabel : ''}</span>
    </>
  )
}
