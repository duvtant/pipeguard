import { useState, type ReactNode } from 'react'
import Play from '~icons/ph/play-fill'
import Sliders from '~icons/ph/sliders-horizontal'
import { Card, CardHeader, Num } from '@/components/ui/Card'
import { Chip } from '@/components/ui/Chip'
import { Strip } from '@/components/ui/Strip'
import { Avatar } from '@/components/ui/Avatar'
import { Slider } from '@/components/ui/Slider'
import { Segmented } from '@/components/ui/Segmented'
import ChartLine from '~icons/ph/chart-line'
import TableIcon from '~icons/ph/table'
import { NewEventsPill } from '@/components/ui/NewEventsPill'
import { ActionButton } from '@/components/ui/ActionButton'
import { HoldToConfirm } from '@/components/ui/HoldToConfirm'
import { ValueFlash } from '@/components/ui/ValueFlash'
import { SlideOver } from '@/components/ui/SlideOver'
import { Tabs } from '@/components/ui/Tabs'
import { Skeleton } from '@/components/ui/Skeleton'
import { UnitTile } from '@/components/ui/UnitTile'
import { AreaTrend, CompareChart, DarkTip } from '@/components/ui/charts'
import { STATUS, STATUS_ORDER, StatusPill } from '@/components/ui/status'
import { useProjector } from '@/hooks/useProjector'
import { makeFleet } from '@/mocks/fixtures/fleet'
import type { FleetUnit } from '@/lib/types'

// Every token and component in one place, for the Gate 2 review. Press P (or the button) for projector mode.
const SWATCHES: [string, string, string][] = [
  ['canvas', '#FFFFFF', 'Page and card surface'], ['shell', '#FAFCFE', 'Sidebar'], ['pill', '#F1F3F4', 'Chips, active nav'], ['line', '#E8E9F4', 'Card edge'],
  ['ink', '#080911', 'Headings, key numbers'], ['text', '#2A2C3B', 'Body'], ['muted', '#5B5E70', 'Secondary text'], ['subtle', '#6A6D82', 'Meta text'],
  ['accent', '#5367EB', 'Primary, focus, PipeGuard series'], ['accent-ink', '#3F52D4', 'Links, accent text'], ['accent-soft', '#EEF0FE', 'Selected background'], ['accent-line', '#7C88E8', 'Chart line'],
  ['ok', '#0E7A55', 'Healthy text'], ['warn', '#8F5600', 'Watch text'], ['risk', '#B3204F', 'At risk text'], ['sens', '#555B70', 'Sensor issue text'], ['fail', '#20232F', 'Failed text'],
]
const TYPE: [string, string, string][] = [
  ['Page title', 'text-[38px] leading-[44px] [font-weight:var(--w-body)] tracking-[-0.01em] text-ink', '38 / 44 · 420'],
  ['KPI number', 'text-[46px] leading-[50px] [font-weight:var(--w-strong)] tracking-[-0.02em] tnum text-ink', '46 / 50 · 480'],
  ['Stat number', 'text-[26px] leading-8 [font-weight:var(--w-strong)] tnum text-ink', '26 / 32 · 480'],
  ['Card title', 'text-base [font-weight:var(--w-body)] text-text', '16 / 24 · 420'],
  ['Body', 'text-[15px] text-text', '15 / 22 · 420'],
  ['Secondary', 'text-sm text-muted', '14 / 20 · 420'],
  ['Meta and axis', 'text-[13px] text-muted', '13 / 18 · 420'],
]

const Section = ({ title, note, children }: { title: string; note?: string; children: ReactNode }) => (
  <section className="mt-12">
    <h2 className="m-0 text-[26px] [font-weight:var(--w-body)] leading-8 text-ink">{title}</h2>
    {note && <p className="m-0 mt-1 max-w-[720px] text-sm text-muted">{note}</p>}
    <div className="mt-5">{children}</div>
  </section>
)

export default function Styleguide() {
  const [projector, toggle] = useProjector()
  const [tab, setTab] = useState('a')
  const [v, setV] = useState(2)
  const [seg, setSeg] = useState<'chart' | 'table'>('chart')
  const [n, setN] = useState(3)
  const [feed, setFeed] = useState(12)
  const [open, setOpen] = useState(false)
  const [resets, setResets] = useState(0)
  const units: FleetUnit[] = makeFleet().filter((u) => ['EDS-01', 'EDS-04', 'EDS-07', 'HIN-12', 'GPR-15', 'WHT-03'].includes(u.unit_id)).slice(0, 6)
  const trend = Array.from({ length: 12 }, (_, i) => ({ x: `Day ${i * 3}`, y: Math.round(2 + i * 0.6 + (i % 3)) }))
  const cmp = Array.from({ length: 9 }, (_, i) => ({ x: `Day ${i * 15}`, a: i * i * 2, b: i * 9, c: i * 4 }))

  return (
    <main className="mx-auto max-w-[1230px] px-5 pb-24 pt-8 md:px-10">
      <header className="flex flex-wrap items-center gap-3">
        <img src="/logo-mark.svg" width={40} height={40} alt="" />
        <div><h1 className="m-0 text-[38px] [font-weight:var(--w-body)] leading-[44px] tracking-[-0.01em] text-ink">PipeGuard style guide</h1>
          <p className="m-0 text-muted">Every token and component, as specified in docs/design/DESIGN.md. Light mode only.</p></div>
        <Chip className="ml-auto" primary={projector} onClick={toggle} aria-pressed={projector}>Projector mode (P)</Chip>
      </header>

      <Section title="Colour" note="Every text pair on the canvas passes WCAG AA. Status colours are for status only; the accent is never a status.">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {SWATCHES.map(([n, hex, use]) => (
            <div key={n} className="overflow-hidden rounded-tile shadow-tile">
              <div className="h-14" style={{ background: `var(--color-${n})` }} />
              <div className="p-2.5 text-[13px] leading-[18px]"><b className="[font-weight:var(--w-strong)] text-ink">{n}</b><br /><span className="tnum text-muted">{hex}</span><br /><span className="text-muted">{use}</span></div>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Gradients" note="Three, each with one job. A gradient is never the only signal: every strip has an icon and words.">
        <Card pad={false}>
          <Strip tone="insight" title="2 crews on shift per station" subtitle="Insight: neutral guidance and next steps" />
          <Strip tone="calm" title="Service booked for Fri Nov 6" subtitle="Calm: good news and confirmations" action="View plan" onAction={() => {}} />
          <Strip tone="attention" title="EDS-14 needs a manager decision" subtitle="Attention: a person is needed" action="Review" onAction={() => {}} />
        </Card>
      </Section>

      <Section title="Type" note="Figtree variable, weights 420 and 480, tabular numerals, sentence case. Nothing below 13 px.">
        <Card><div className="flex flex-col gap-4">
          {TYPE.map(([n, c, spec]) => <div key={n} className="flex flex-wrap items-baseline gap-x-6"><span className={c}>{n === 'KPI number' ? '3,240' : n}</span><span className="text-[13px] text-muted">{spec}</span></div>)}
          <div className="flex items-baseline gap-6"><Num value="$3.38" unit="M" /><Num value={3} unit="units" /><span className="text-[13px] text-muted">Raised units</span></div>
        </div></Card>
      </Section>

      <Section title="Status" note="Five statuses. Each has its own colour, icon and label, so colour is never the only signal.">
        <Card><div className="flex flex-wrap gap-2">{STATUS_ORDER.map((s) => <StatusPill key={s} status={s} />)}</div>
          <div className="mt-5 grid grid-cols-3 gap-2 sm:grid-cols-6">{units.map((u) => <UnitTile key={u.unit_id} unit={u} />)}</div>
          <p className="m-0 mt-3 text-sm text-muted">{STATUS_ORDER.map((s) => STATUS[s].label).join(' · ')}. At risk with a sensor issue keeps the red tile and gains a wrench badge (WHT-03).</p>
        </Card>
      </Section>

      <Section title="Buttons, chips, avatars, tabs">
        <Card><div className="flex flex-wrap items-center gap-2.5">
          <Chip primary icon={<Play width={16} height={16} />}>Play replay</Chip>
          <Chip icon={<Sliders width={16} height={16} />}>Reset sliders</Chip>
          <Chip quiet>Quiet</Chip>
          {[0, 1, 2, 3, 4, 5].map((i) => <Avatar key={i} letter={"ABCDEF"[i]} tone={i} />)}
        </div>
          <div className="mt-4"><Tabs label="Example" value={tab} onChange={setTab} tabs={[{ value: 'a', label: 'All stations' }, { value: 'b', label: 'Edson' }, { value: 'c', label: 'Hinton' }]} /></div>
          <Slider className="mt-4" label="Crews per station" value={v} min={0} max={5} step={1} onValueChange={setV} detents={[0, 1, 2, 3, 4, 5]} format={(n) => `${n} crews`} />
          <div className="mt-4 flex items-center gap-3"><Segmented label="View" value={seg} onChange={setSeg} options={[{ value: 'chart', label: 'Chart', icon: <ChartLine width={18} height={18} /> }, { value: 'table', label: 'Table', icon: <TableIcon width={18} height={18} /> }]} /><span className="text-[13px] text-muted">Segmented control: Arrow keys, Home and End work</span></div>
          <div className="relative mt-4 h-12 rounded-[12px] bg-shell shadow-tile"><NewEventsPill count={3} onJump={() => {}} /></div>
        </Card>
      </Section>

      <Section title="Interaction components" note="Adapted from interior.dev (MIT). Try each one. Value Flash marks a change; Action Button never changes width; Hold to Confirm needs a deliberate hold; the slide-over traps focus.">
        <div className="grid gap-5 md:grid-cols-2">
          <Card><CardHeader title="Value Flash" />
            <div className="flex items-center gap-4"><Num value={<ValueFlash value={n} label="Demo value" throttle={0} />} unit="units" />
              <Chip onClick={() => setN((x) => x + 1)}>+1</Chip><Chip onClick={() => setN((x) => Math.max(0, x - 1))}>−1</Chip></div>
            <p className="m-0 mt-2 text-[13px] text-muted">For numbers you change directly (slider results, a button): it responds to every tap. A soft accent tint, no green or red.</p>
            <div className="mt-4 flex items-center gap-4 border-t border-line pt-4"><Num value={<ValueFlash value={feed} label="Live feed value" />} unit="units" />
              <Chip onClick={() => { let i = 0; const t = setInterval(() => { setFeed((x) => x + 1); if (++i >= 10) clearInterval(t) }, 100) }}>Send 10 live updates</Chip></div>
            <p className="m-0 mt-2 text-[13px] text-muted">For numbers pushed by the live stream: changes show at most once every 2 seconds, so a busy feed never flickers. Ten updates in one second become one flash that lands on the right total. A screen reader hears only the settled value.</p></Card>
          <Card><CardHeader title="Action Button" />
            <div className="flex flex-wrap items-center gap-2.5">
              <ActionButton variant="primary" icon={<Play width={16} height={16} />} onAction={() => new Promise((r) => setTimeout(r, 1200))}>Run simulation</ActionButton>
              <ActionButton onAction={() => new Promise((_, rej) => setTimeout(() => rej(new Error('demo')), 900))} onError={() => {}}>Simulate call (fails)</ActionButton>
              <ActionButton onAction={() => new Promise((r) => setTimeout(r, 800))} successLabel="Downloaded">Download work orders</ActionButton></div>
            <p className="m-0 mt-2 text-[13px] text-muted">Idle, pending, success and error share one cell, so the width never changes. A second click while pending is ignored.</p></Card>
          <Card><CardHeader title="Hold to Confirm" />
            <div className="flex items-center gap-4"><HoldToConfirm confirmLabel="Demo reset" onConfirm={() => setResets((x) => x + 1)}>Hold to reset demo</HoldToConfirm>
              <span className="tnum text-sm text-muted">Confirmed {resets} time{resets === 1 ? '' : 's'}</span></div>
            <p className="m-0 mt-2 text-[13px] text-muted">0.9 seconds. Releasing early, moving away, switching tabs or pressing Escape cancels it.</p></Card>
          <Card><CardHeader title="Slide-over" />
            <Chip onClick={() => setOpen(true)}>Open a slide-over</Chip>
            <p className="m-0 mt-2 text-[13px] text-muted">Focus moves in and returns to this button. The page behind is inert. Escape closes it.</p></Card>
        </div>
        <SlideOver open={open} onOpenChange={setOpen} title="Example panel" headerExtra={<StatusPill status="watch" />} subtitle="Slide-over demo"
          footer={<Strip tone="calm" title="Everything is saved" subtitle="Calm strip, edge to edge" />}>
          <p className="m-0 text-[15px]">This is the same panel the Fleet screen uses for a unit. Press Tab to move around: focus stays inside until you close it.</p>
        </SlideOver>
      </Section>

      <Section title="Charts" note="No gridlines or axis lines, a gradient area that bleeds to the card edge, and a dark tooltip with colour keys.">
        <div className="grid gap-5 md:grid-cols-2">
          <Card><CardHeader title="Area trend" /><div className="-mx-7"><AreaTrend label="Example trend" data={trend} height={180} xTicks={4} /></div></Card>
          <Card><CardHeader title="Comparison" /><div className="-mx-7"><CompareChart label="Example comparison" height={180} format={(n) => `$${n}K`} data={cmp.map((d) => ({ x: d.x, run_to_failure: d.a, fixed_schedule: d.b, pipeguard: d.c }))}
            series={[{ key: 'run_to_failure', label: 'Run until it breaks', color: '#B8BCCB', dashed: true }, { key: 'fixed_schedule', label: 'Fixed schedule', color: '#7A8197' }, { key: 'pipeguard', label: 'PipeGuard', color: '#5367EB', strong: true }]} /></div></Card>
        </div>
        <div className="mt-5"><DarkTip title="Day 21" rows={[{ label: 'Run until it breaks', color: '#B8BCCB', value: '$14.2M' }, { label: 'Fixed schedule', color: '#7A8197', value: '$7.1M' }, { label: 'PipeGuard', color: '#5367EB', value: '$2.1M' }]} /></div>
      </Section>

      <Section title="Loading and empty" note="Skeletons are shaped like the final content and do not animate. Empty states are warm, with a small illustration.">
        <div className="grid gap-5 md:grid-cols-2">
          <Card><Skeleton className="h-9 w-40" /><Skeleton className="mt-3 h-[120px]" /></Card>
          <Card className="text-center"><img src="/brand/empty-all-clear.webp" width={240} height={180} alt="" className="mx-auto mix-blend-multiply" /><p className="m-0 text-[15px] text-ink">All clear. Nothing needs attention.</p></Card>
        </div>
      </Section>

      <Section title="Imagery" note="Generated art is used sparingly. UI icons are always Phosphor, never raster.">
        <div className="grid gap-5 sm:grid-cols-3">
          {['insight', 'calm', 'attention'].map((m) => <div key={m}><img src={`/brand/mesh-${m}.webp`} alt="" width={1200} height={800} className="h-32 w-full rounded-tile object-cover shadow-tile" /><p className="m-0 mt-1.5 text-[13px] text-muted">mesh-{m}</p></div>)}
        </div>
        <img src="/brand/sign-in.webp" alt="" width={1600} height={1000} className="mt-5 h-40 w-full rounded-tile object-cover shadow-tile" />
      </Section>
    </main>
  )
}
