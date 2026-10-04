// Adapted from interior.dev (MIT, (c) 2026 ozzy): https://github.com/ddoemonn/interior
// Original: drawer.tsx. Kept: focus trap, focus return to the trigger, inert background, scroll lock,
// Escape, drag-to-dismiss (touch only here). Changed per docs/design/COMPONENTS.md: our tokens, no blur,
// z-30, ReactNode title with a header slot, footer bleed, spring { 380, 34 }.
import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { animate, motion, useDragControls, useMotionValue, useReducedMotion, useTransform } from 'motion/react'
import X from '~icons/ph/x'
import { spring } from '@/design/motion'

const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])'
type Inertable = HTMLElement & { inert?: boolean }
type DragInfo = { offset: { x: number; y: number }; velocity: { x: number; y: number } }

function useSlideOver({ open, onOpenChange, width }: { open: boolean; onOpenChange: (open: boolean) => void; width: number }) {
  const [dragging, setDragging] = useState(false)
  const away = width + 24
  const x = useMotionValue(open ? 0 : away)
  const veil = useTransform(x, (v) => 1 - Math.min(1, Math.abs(v) / width))
  const rootRef = useRef<HTMLDivElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const returnTo = useRef<HTMLElement | null>(null)
  const anim = useRef<{ stop: () => void } | null>(null)
  const live = useRef(open)
  live.current = open
  const changed = useRef(onOpenChange)
  changed.current = onOpenChange
  const reduced = useReducedMotion()
  const controls = useDragControls()
  const close = useCallback(() => changed.current(false), [])

  const glide = useCallback((to: number) => {
    anim.current?.stop()
    anim.current = animate(x, to, reduced ? { duration: 0 } : spring.panel)
  }, [x, reduced])

  useEffect(() => { glide(open ? 0 : away); return () => anim.current?.stop() }, [open, away, glide])

  // The closed panel is inert so it cannot take focus.
  useEffect(() => {
    const panel = panelRef.current as Inertable | null
    if (!panel) return
    panel.inert = !open
    return () => { panel.inert = false }
  }, [open])

  // Focus moves into the panel on open and returns to whatever opened it on close.
  useEffect(() => {
    if (open) {
      const active = document.activeElement
      returnTo.current = active instanceof HTMLElement ? active : null
      const panel = panelRef.current
      if (!panel) return
      const first = panel.querySelector<HTMLElement>(FOCUSABLE)
      ;(first ?? panel).focus({ preventScroll: true })
      return
    }
    const target = returnTo.current
    returnTo.current = null
    if (target && target.isConnected) target.focus({ preventScroll: true })
  }, [open])

  // Lock page scroll without the layout jumping when the scrollbar disappears.
  useEffect(() => {
    if (!open) return
    const root = document.documentElement
    const overflow = root.style.overflow, padding = root.style.paddingRight
    const gutter = window.innerWidth - root.clientWidth
    root.style.overflow = 'hidden'
    if (gutter > 0) root.style.paddingRight = `${gutter}px`
    return () => { root.style.overflow = overflow; root.style.paddingRight = padding }
  }, [open])

  // Everything behind the panel (the whole app) becomes inert: not clickable, not focusable, hidden from screen readers.
  useEffect(() => {
    const shell = rootRef.current
    if (!open || !shell) return
    const muted: Inertable[] = []
    for (const node of Array.from(document.body.children)) {
      if (!(node instanceof HTMLElement) || node.contains(shell)) continue
      const el = node as Inertable
      if (el.inert) continue
      el.inert = true
      muted.push(el)
    }
    return () => { for (const el of muted) el.inert = false }
  }, [open])

  // Escape closes the panel even if focus is somewhere unexpected.
  useEffect(() => {
    if (!open) return
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') close() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [open, close])

  const onKeyDown = useCallback((event: React.KeyboardEvent) => {
    const panel = panelRef.current
    if (!panel) return
    if (event.key === 'Escape') return // handled by the page-level listener above
    if (event.key !== 'Tab') return
    const nodes = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE))
    if (nodes.length === 0) { event.preventDefault(); panel.focus({ preventScroll: true }); return }
    const first = nodes[0], last = nodes[nodes.length - 1], active = document.activeElement
    if (event.shiftKey && (active === first || active === panel)) { event.preventDefault(); last.focus() }
    else if (!event.shiftKey && active === last) { event.preventDefault(); first.focus() }
  }, [])

  const onDragEnd = useCallback((_e: unknown, info: DragInfo) => {
    setDragging(false)
    if (info.offset.x > width * 0.38 || info.velocity.x > 520) { close(); return }
    glide(0)
  }, [width, glide, close])

  return {
    dragging, x, veil, close, rootRef, panelRef,
    // Drag to dismiss is for touch only; a mouse user has the close button, the scrim and Escape.
    startDrag: (e: React.PointerEvent) => { if (live.current && e.pointerType !== 'mouse') controls.start(e) },
    panelProps: {
      tabIndex: -1, role: 'dialog' as const, 'aria-modal': true, onKeyDown,
      drag: 'x' as const, dragControls: controls, dragListener: false, dragMomentum: false,
      dragConstraints: { left: 0, right: 0 }, dragElastic: { top: 0, bottom: 0, left: 0, right: 1 },
      onDragStart: () => setDragging(true), onDragEnd,
    },
  }
}

export function SlideOver({ open, onOpenChange, title, headerExtra, subtitle, children, footer, width = 430, closeLabel = 'Close panel' }: {
  open: boolean; onOpenChange: (open: boolean) => void
  title: ReactNode; headerExtra?: ReactNode; subtitle?: ReactNode
  children: ReactNode
  /** Rendered edge to edge at the bottom (no padding), so a gradient strip can run the full panel width. */
  footer?: ReactNode
  width?: number; closeLabel?: string
}) {
  const titleId = useId()
  const hintId = useId()
  const so = useSlideOver({ open, onOpenChange, width })
  // This app is client-rendered only, so the portal target exists on the first render. That matters: the focus
  // logic runs on mount, and a panel opened by a deep link (?unit=...) must already be in the DOM to receive focus.
  const host = typeof document === 'undefined' ? null : document.body

  const tree = (
    // Portal sits outside the app root, so it carries projector zoom itself.
    <div ref={so.rootRef} className={`fixed inset-0 z-30 overflow-hidden ${open ? '' : 'pointer-events-none'}`} style={{ zoom: 'var(--zoom)' }}>
      <motion.div aria-hidden style={{ opacity: so.veil }} onClick={so.close} className="absolute inset-0 bg-[rgba(250,252,254,0.7)]" />
      <motion.div
        ref={so.panelRef} aria-labelledby={titleId} aria-describedby={hintId}
        style={{ x: so.x, width, maxWidth: 'calc(100% - 24px)', touchAction: 'pan-y' }}
        className={`absolute inset-y-0 right-0 flex flex-col rounded-l-[16px] bg-canvas shadow-panel outline-none ${so.dragging ? 'select-none' : ''}`}
        {...so.panelProps}
      >
        <header onPointerDown={so.startDrag} className="flex-none px-6 pb-1 pt-5">
          <div className="flex items-center gap-2.5">
            <h2 id={titleId} className="m-0 min-w-0 truncate text-[22px] leading-7 [font-weight:var(--w-strong)] text-ink">{title}</h2>
            {headerExtra}
            <button type="button" onPointerDown={(e) => e.stopPropagation()} onClick={so.close} aria-label={closeLabel}
              className="-mr-2 ml-auto grid size-9 flex-none place-items-center rounded-full text-muted transition-colors duration-150 hover:bg-pill hover:text-ink">
              <X width={20} height={20} aria-hidden />
            </button>
          </div>
          {subtitle && <p className="m-0 mt-0.5 text-sm text-muted">{subtitle}</p>}
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-6 pb-5 pt-3">{children}</div>
        {footer && <div className="flex-none overflow-hidden rounded-bl-[16px]">{footer}</div>}
        <span id={hintId} className="sr-only">Press Escape to close this panel.</span>
      </motion.div>
    </div>
  )
  return host ? createPortal(tree, host) : null
}
