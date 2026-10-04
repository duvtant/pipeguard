import { useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { motion } from 'motion/react'
import Squares from '~icons/ph/squares-four'
import CalendarCheck from '~icons/ph/calendar-check'
import ChartBar from '~icons/ph/chart-bar'
import ListChecks from '~icons/ph/list-checks'
import Users from '~icons/ph/users'
import Clipboard from '~icons/ph/clipboard-text'
import Gear from '~icons/ph/gear'
import Search from '~icons/ph/magnifying-glass'
import Bell from '~icons/ph/bell'
import Clock from '~icons/ph/clock'
import Screen from '~icons/ph/projector-screen'
import Caret from '~icons/ph/caret-down'
import { Avatar } from '@/components/ui/Avatar'
import { cx } from '@/components/ui/Card'
import { useFleet } from '@/lib/queries'
import { formatSimDate } from '@/lib/simCalendar'
import { useProjector } from '@/hooks/useProjector'
import { Banner } from '@/components/ui/Banner'
import { SlideOver } from '@/components/ui/SlideOver'
import List from '~icons/ph/list'
import { ErrorBoundary } from '@/components/ErrorBoundary'

const NAV = [
  { to: '/', label: 'Fleet', Icon: Squares, end: true },
  { to: '/plan', label: 'Plan', Icon: CalendarCheck },
  { to: '/impact', label: 'Impact', Icon: ChartBar },
  { to: '/log', label: 'Decision log', Icon: ListChecks },
]
const WORKFLOWS = [
  { to: '/roster', label: 'Roster', Icon: Users },
  { to: '/orders', label: 'Work orders', Icon: Clipboard },
  { to: '/settings', label: 'Settings', Icon: Gear },
]

function NavItem({ to, label, Icon, end, onNavigate }: { to: string; label: string; Icon: typeof Squares; end?: boolean; onNavigate?: () => void }) {
  // 34px tall, 12px side padding, icon at 24px and text at 53px from the sidebar edge: measured from Mercury.
  return (
    <NavLink to={to} end={end} onClick={onNavigate} className="relative flex h-[34px] items-center gap-3.5 rounded-[10px] px-3 text-sm text-text">
      {({ isActive }) => (
        <>
          {isActive && <motion.span layoutId="nav-pill" className="absolute inset-0 rounded-[10px] bg-pill" transition={{ duration: 0.24, ease: [0.32, 0.72, 0, 1] }} />}
          <Icon width={16} height={16} aria-hidden className={cx('relative flex-none', isActive ? 'text-accent' : 'text-muted')} />
          <span className={cx('relative', isActive && '[font-weight:var(--w-strong)]')}>{label}</span>
        </>
      )}
    </NavLink>
  )
}

// Layout numbers, measured from Mercury's own screens in a 1440px window (docs/design/DESIGN.md 3.5):
// header band 72px + 1px hairline (Mercury 60; made taller at Gate 2 review) (sidebar and content share one line), sidebar 205px, content starts 24px
// from the sidebar and 37px from the right edge, title sits 32px under the header line.
const BAND = 'h-[73px] flex-none border-b border-line'
const CONTENT = 'mx-auto w-full max-w-[1760px] px-4 sm:pl-6 sm:pr-9'

export default function AppShell() {
  const { data } = useFleet()
  const [projector, toggleProjector] = useProjector()
  const search = useRef<HTMLInputElement>(null)
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); search.current?.focus() } }
    addEventListener('keydown', h)
    return () => removeEventListener('keydown', h)
  }, [])
  const { pathname } = useLocation()
  const [menu, setMenu] = useState(false)
  const day = data?.sim_day
  const needsDecision = data?.units.some((u) => u.needs_manager_decision) ?? false

  return (
    <div className="flex min-h-[calc(100vh/var(--zoom))] bg-canvas" style={{ zoom: 'var(--zoom)' }}>
      <aside data-print-hide className="sticky top-0 hidden h-[calc(100vh/var(--zoom))] w-[205px] flex-none flex-col overflow-y-auto border-r border-line bg-shell lg:flex">
        <div className={cx(BAND, 'flex items-center gap-2.5 px-3.5 [font-weight:var(--w-strong)] text-ink')}>
          <img src="/logo-mark.svg" width={28} height={28} alt="" className="rounded-[8px]" />
          PipeGuard
          <Caret width={14} height={14} className="ml-auto text-subtle" aria-hidden />
        </div>
        <div className="flex flex-1 flex-col pb-4 pl-[11px] pr-3.5 pt-[38px]">
          <nav aria-label="Main" className="flex flex-col gap-1">{NAV.map((n) => <NavItem key={n.to} {...n} />)}</nav>
          <div className="px-3 pb-2 pt-6 text-[13px] text-subtle">Workflows</div>
          <nav aria-label="Workflows" className="flex flex-col gap-1">{WORKFLOWS.map((n) => <NavItem key={n.to} {...n} />)}</nav>
          <div className="mt-auto flex items-center gap-2.5 rounded-[10px] px-3 pt-6 text-sm text-muted"><Avatar letter="P" square size={24} tone={0} />Prairie Gas</div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header data-band data-print-hide className={cx(BAND, 'sticky top-0 z-10 bg-canvas')}>
          <div className={cx(CONTENT, 'flex h-full items-center gap-2.5 sm:pr-6')}>
            <button type="button" onClick={() => setMenu(true)} aria-label="Open the menu" className="grid size-9 flex-none place-items-center rounded-full bg-pill text-muted hover:text-ink lg:hidden"><List width={18} height={18} aria-hidden /></button>
            <label className="flex h-9 min-w-0 max-w-[616px] flex-1 items-center gap-2.5 rounded-[10px] border border-line px-3 text-subtle shadow-[0_1px_2px_rgba(83,103,235,0.05)] focus-within:border-accent">
              <Search width={18} height={18} aria-hidden />
              <input ref={search} type="search" placeholder="Search for a unit or a technician" aria-label="Search for a unit or a technician" className="min-w-0 flex-1 bg-transparent py-2 text-sm text-ink outline-none placeholder:text-subtle" />
              <kbd className="hidden rounded-md bg-pill px-1.5 text-[13px] text-muted sm:block">⌘ K</kbd>
            </label>
            <div className="ml-auto flex flex-none items-center gap-2">
              <button type="button" className="hidden h-9 items-center gap-1.5 whitespace-nowrap rounded-full border border-line bg-white px-3.5 text-sm [font-weight:var(--w-strong)] text-accent-ink md:flex">
                <Clock width={18} height={18} aria-hidden />
                {day === undefined ? 'Loading date' : <span className="tnum">{formatSimDate(day)} · Day {day}</span>}
                <Caret width={14} height={14} aria-hidden />
              </button>
              <button type="button" onClick={toggleProjector} aria-pressed={projector} aria-label="Projector mode" title="Projector mode (P)"
                className={cx('grid size-9 place-items-center rounded-full transition-colors', projector ? 'bg-accent text-white' : 'bg-pill text-muted hover:text-ink')}>
                <Screen width={20} height={20} aria-hidden />
              </button>
              <button type="button" aria-label={needsDecision ? 'Notifications, a decision is needed' : 'Notifications'} className="relative grid size-9 place-items-center rounded-full bg-pill text-muted hover:text-ink">
                <Bell width={20} height={20} aria-hidden />
                {needsDecision && <span className="absolute right-[9px] top-2 size-2 rounded-full border-2 border-white bg-risk-fill" />}
              </button>
              <Avatar letter="MR" tone={5} size={36} />
            </div>
          </div>
        </header>
        <SlideOver open={menu} onOpenChange={setMenu} width={300} title="PipeGuard" closeLabel="Close the menu">
          <nav aria-label="Menu" className="flex flex-col gap-1">{[...NAV, ...WORKFLOWS].map((n) => <NavItem key={n.to} {...n} onNavigate={() => setMenu(false)} />)}</nav>
        </SlideOver>
        <Banner />
        <main className={cx(CONTENT, 'flex-1 pb-12 pt-9')}>
          <ErrorBoundary resetKey={pathname}><Outlet /></ErrorBoundary>
        </main>
        <footer data-print-hide className={cx(CONTENT, 'pb-6 text-[13px] text-muted')}>
          Prairie Gas Transmission is a simulated company. Turbine data: NASA C-MAPSS FD001 (stand-in). Costs are illustrative.
        </footer>
      </div>
    </div>
  )
}
