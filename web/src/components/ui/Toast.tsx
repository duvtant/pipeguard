import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import Check from '~icons/ph/check-circle-fill'
import Octagon from '~icons/ph/warning-octagon-fill'
import CalendarCheck from '~icons/ph/calendar-check'
import { dur, ease } from '@/design/motion'

// Toast (DESIGN.md 5.10): a small card bottom right with an icon and one line. Rises 12 px, auto-dismisses after 4 s
// (pauses while hovered), exits down 8 px. Lives inside the app root, above the page, below dialogs (z-40).
export type ToastTone = 'info' | 'calm' | 'attention'
interface ToastItem { id: number; title: string; detail?: string; tone: ToastTone }
const ToastContext = createContext<{ show: (t: Omit<ToastItem, 'id'>) => void }>({ show: () => {} })
export const useToast = () => useContext(ToastContext)

const TONE = {
  info: { Icon: CalendarCheck, cls: 'bg-accent-soft text-accent' },
  calm: { Icon: Check, cls: 'bg-ok-tint text-ok' },
  attention: { Icon: Octagon, cls: 'bg-risk-tint text-risk' },
} as const

function ToastCard({ t, onDone }: { t: ToastItem; onDone: (id: number) => void }) {
  const [paused, setPaused] = useState(false)
  useEffect(() => {
    if (paused) return
    const timer = setTimeout(() => onDone(t.id), 4000)
    return () => clearTimeout(timer)
  }, [paused, t.id, onDone])
  const { Icon, cls } = TONE[t.tone]
  return (
    <motion.li layout initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8, transition: { duration: 0.16, ease: ease.exit } }}
      transition={{ duration: dur.base, ease: ease.out }} onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}
      className="pointer-events-auto flex w-[340px] max-w-[calc(100vw-32px)] items-start gap-3 rounded-[14px] bg-canvas px-4 py-3 shadow-[0_0_0_1px_var(--color-line),0_14px_30px_-12px_rgba(8,9,17,0.28)]">
      <span className={`mt-0.5 grid size-7 flex-none place-items-center rounded-full ${cls}`}><Icon width={15} height={15} aria-hidden /></span>
      <div className="min-w-0 text-sm"><b className="block [font-weight:var(--w-strong)] text-ink">{t.title}</b>{t.detail && <span className="text-[13px] text-muted">{t.detail}</span>}</div>
    </motion.li>
  )
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const next = useRef(1)
  const done = useCallback((id: number) => setItems((l) => l.filter((x) => x.id !== id)), [])
  const show = useCallback((t: Omit<ToastItem, 'id'>) => setItems((l) => [...l.slice(-2), { ...t, id: next.current++ }]), []) // at most 3 at once
  const value = useMemo(() => ({ show }), [show])
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div role="status" aria-live="polite" className="pointer-events-none fixed bottom-5 right-5 z-40" style={{ zoom: 'var(--zoom)' }}>
        <ul className="m-0 flex list-none flex-col gap-2 p-0"><AnimatePresence initial={false}>{items.map((t) => <ToastCard key={t.id} t={t} onDone={done} />)}</AnimatePresence></ul>
      </div>
    </ToastContext.Provider>
  )
}
