// Adapted from interior.dev (MIT, (c) 2026 ozzy): https://github.com/ddoemonn/interior (new-items-pill.tsx)
// Changed per docs/design/COMPONENTS.md: an accent pill with a Phosphor arrow and "N new events" wording. The one passive
// scroll listener we allow (on the list container, for pin detection only; DESIGN.md 9.5).
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import ArrowUp from '~icons/ph/arrow-up'
import { dur, ease } from '@/design/motion'

const useIsoLayoutEffect = typeof window === 'undefined' ? useEffect : useLayoutEffect

/** Keeps your reading position when new items arrive above, counts them, and jumps back to the top on request.
 *  At the top of the list new items simply appear. `itemCount` must count only genuinely new items (de-duplicated). */
export function useNewItems<T extends HTMLElement = HTMLDivElement>({ itemCount, threshold = 24 }: { itemCount: number; threshold?: number }) {
  const ref = useRef<T | null>(null)
  const pinnedRef = useRef(true)
  const prevCount = useRef(itemCount)
  const bottomGap = useRef(0)
  const [unread, setUnread] = useState(0)
  const reduced = useReducedMotion()

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const onScroll = () => {
      bottomGap.current = el.scrollHeight - el.scrollTop
      const next = el.scrollTop <= threshold
      if (next === pinnedRef.current) return
      pinnedRef.current = next
      if (next) setUnread(0)
    }
    onScroll()
    el.addEventListener('scroll', onScroll, { passive: true })
    return () => el.removeEventListener('scroll', onScroll)
  }, [threshold])

  useIsoLayoutEffect(() => {
    const el = ref.current
    const added = itemCount - prevCount.current
    prevCount.current = itemCount
    if (!el || added <= 0) return
    if (pinnedRef.current) { el.scrollTop = 0; bottomGap.current = el.scrollHeight - el.scrollTop; return }
    const target = el.scrollHeight - bottomGap.current // keep what you are reading where it is
    if (target > el.scrollTop) el.scrollTop = target
    setUnread((n) => n + added)
  }, [itemCount])

  const jump = useCallback(() => {
    const el = ref.current
    if (!el) return
    pinnedRef.current = true
    setUnread(0)
    el.focus({ preventScroll: true })
    el.scrollTo({ top: 0, behavior: reduced ? 'auto' : 'smooth' })
  }, [reduced])

  return { scrollProps: { ref, tabIndex: 0, style: { overflowAnchor: 'none' as const } }, unread, jump }
}

export function NewEventsPill({ count, onJump }: { count: number; onJump: () => void }) {
  const reduced = useReducedMotion()
  const [announced, setAnnounced] = useState(0)
  useEffect(() => {
    if (count === 0) { const t = setTimeout(() => setAnnounced(0), 0); return () => clearTimeout(t) }
    const t = setTimeout(() => setAnnounced(count), 700)
    return () => clearTimeout(t)
  }, [count])
  const text = (n: number) => (n > 99 ? '99+ new events' : `${n} new ${n === 1 ? 'event' : 'events'}`)
  return (
    <div className="pointer-events-none absolute inset-x-0 top-2 z-10 flex justify-center">
      <AnimatePresence initial={false}>
        {count > 0 && (
          <motion.button type="button" onClick={onJump} aria-label={text(count)}
            initial={reduced ? { opacity: 0 } : { opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}
            exit={reduced ? { opacity: 0, transition: { duration: 0 } } : { opacity: 0, y: -6, transition: { duration: dur.fast, ease: ease.exit } }}
            transition={reduced ? { duration: 0 } : { duration: dur.base, ease: ease.out }}
            className="pointer-events-auto inline-flex h-8 select-none items-center gap-1.5 rounded-full bg-accent pl-2.5 pr-3.5 text-sm text-white shadow-[0_8px_20px_-8px_rgba(83,103,235,0.6)] outline-none [font-weight:var(--w-strong)] hover:bg-accent-ink">
            <ArrowUp width={14} height={14} aria-hidden />
            <span className="tnum" aria-hidden>{text(count)}</span>
          </motion.button>
        )}
      </AnimatePresence>
      <span role="status" aria-live="polite" className="sr-only">{announced > 0 ? text(announced) : ''}</span>
    </div>
  )
}
