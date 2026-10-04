import type { ComponentType, SVGProps } from 'react'
import Octagon from '~icons/ph/warning-octagon-fill'
import Warn from '~icons/ph/warning-fill'
import PhoneCall from '~icons/ph/phone-call'
import CalendarCheck from '~icons/ph/calendar-check'
import Wrench from '~icons/ph/wrench-fill'
import Check from '~icons/ph/check-circle-fill'
import Chat from '~icons/ph/chat-circle-text'
import { SlideOver } from '@/components/ui/SlideOver'
import { Strip } from '@/components/ui/Strip'
import { Num } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { Reveal } from '@/components/ui/Reveal'
import { AreaTrend } from '@/components/ui/charts'
import { RangeBar } from '@/components/ui/RangeBar'
import { Link } from 'react-router-dom'
import { StatusPill } from '@/components/ui/status'
import { tileStatus } from '@/lib/fleetStats'
import { reportCardSummary } from '@/lib/toolCalls'
import { formatSimDate } from '@/lib/simCalendar'
import { useUnit, usePlan } from '@/lib/queries'
import type { EventMsg, FleetUnit, UnitDetail } from '@/lib/types'

type Icon = ComponentType<SVGProps<SVGSVGElement>>
const EVENT_ICON: Partial<Record<EventMsg['type'], Icon>> = {
  status_change: Octagon, manager_alert: Octagon, sensor_issue: Wrench, call_requested: PhoneCall, call_answered: PhoneCall,
  constraint_added: Chat, plan_changed: CalendarCheck, plan_approved: Check, manager_decision: Check, call_summary: Chat, feedback_received: Check, threshold_adjusted: Check, failure: Octagon,
}
const sentence = (s: string) => (/[.!?]$/.test(s) ? s : `${s}.`)
const unitNumber = (id: string) => Number(id.split('-')[1])

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="rounded-[14px] bg-shell px-3.5 py-3 shadow-tile"><div className="text-[13px] text-muted">{label}</div><div className="mt-0.5">{children}</div></div>
}

function Body({ unit }: { unit: UnitDetail }) {
  const failed = unit.failed
  const history = unit.history.map((h) => ({ x: formatSimDate(h.sim_day).replace(/^\w+, /, ''), y: Math.round(h.p_fail * 100) }))
  const events = [...unit.events].sort((a, b) => b.sim_day - a.sim_day || b.event_id - a.event_id)
  return (
    <>
      <h3 className="m-0 text-sm [font-weight:var(--w-strong)] text-ink">Why it was flagged</h3>
      <p className="m-0 mt-1 text-[15px] text-text">{unit.risk_status === 'healthy' && !unit.failed ? 'Nothing unusual. Readings are within the normal range.' : sentence(unit.reason)}</p>
      {unit.sensor_issue && <p className="m-0 mt-2 flex items-center gap-1.5 text-sm text-sens"><Wrench width={14} height={14} aria-hidden />A sensor is faulty, so this prediction has lower confidence.</p>}
      {unit.data_source === 'fallback' && <p className="m-0 mt-2 text-sm text-muted">Showing saved predictions: the live model is not answering.</p>}

      <div className="my-4 grid grid-cols-3 gap-2.5">
        <Fact label="Remaining life">{failed ? <span className="text-[18px] [font-weight:var(--w-strong)] text-ink">Failed</span> : <Num size="sm" value={unit.rul.likely} unit="days" />}</Fact>
        <Fact label="Range">{failed ? <span className="text-[18px] text-muted">None</span> : <Num size="sm" value={unit.rul.low} unit={`to ${unit.rul.high}`} />}</Fact>
        <Fact label="Confidence"><span className="mt-1 block text-[18px] [font-weight:var(--w-strong)] text-ink">{unit.confidence === 'low' ? 'Low' : 'Normal'}</span></Fact>
      </div>

      {!failed && <RangeBar low={unit.rul.low} likely={unit.rul.likely} high={unit.rul.high} lowConfidence={unit.confidence === 'low'} className="mb-4" />}

      <h3 className="m-0 text-sm [font-weight:var(--w-strong)] text-ink">Failure probability, last 30 days</h3>
      <div className="-mx-6 mt-1"><AreaTrend height={130} unit="%" label={`Failure probability for ${unit.unit_id}, last 30 days`} data={history} xTicks={4} /></div>

      {unit.sensors.length > 0 && (
        <>
          <h3 className="m-0 mb-1 mt-5 text-sm [font-weight:var(--w-strong)] text-ink">Sensors that moved most</h3>
          <ul className="m-0 list-none p-0">
            {unit.sensors.slice(0, 3).map((s) => (
              <li key={s.sensor} className="border-t border-line py-2 first:border-t-0">
                <div className="flex items-baseline justify-between gap-3 text-sm"><span className="text-text">{s.label}</span><span className="tnum text-[13px] text-muted">{s.points[s.points.length - 1]?.value}</span></div>
                <div className="-mx-6"><AreaTrend bare height={56} label={`${s.label}, last ${s.points.length} days`} data={s.points.map((p) => ({ x: `Day ${p.sim_day}`, y: p.value }))} /></div>
              </li>
            ))}
          </ul>
        </>
      )}

      {unit.calls.length > 0 && (
        <>
          <h3 className="m-0 mb-2 mt-5 text-sm [font-weight:var(--w-strong)] text-ink">Calls</h3>
          <ul className="m-0 list-none p-0">
            {unit.calls.map((c) => (
              <li key={c.id} className="mb-2 rounded-[12px] bg-shell px-3.5 py-2.5 shadow-tile">
                <div className="flex items-center justify-between text-sm"><b className="[font-weight:var(--w-strong)] text-ink">{c.technician_name}</b><span className="tnum text-[13px] text-muted">{c.duration_secs} s · {c.language.toUpperCase()}</span></div>
                <p className="m-0 mt-0.5 text-[13px] text-muted">{c.summary_en}</p>
                {c.evaluation && c.evaluation.length > 0 && (() => { const r = reportCardSummary(c.evaluation); return <p className="m-0 mt-1 flex items-center gap-1.5 text-[13px] text-muted"><Check width={13} height={13} className={r.failed ? 'text-risk' : 'text-ok'} aria-hidden />Report card: {r.passed} of {r.total} passed{r.failed ? `, ${r.failed} failed` : ''}</p> })()}
              </li>
            ))}
            <li><Link to={`/log?unit=${unit.unit_id}`} className="inline-flex min-h-8 items-center text-sm [font-weight:var(--w-strong)] text-accent-ink">Open in the decision log</Link></li>
          </ul>
        </>
      )}

      <h3 className="m-0 mb-2.5 mt-5 text-sm [font-weight:var(--w-strong)] text-ink">What happened</h3>
      {events.length === 0 ? <p className="m-0 text-sm text-muted">Nothing has happened to this unit yet.</p> : (
        <ol className="m-0 list-none p-0">
          {events.map((e, i) => {
            const I = EVENT_ICON[e.type] ?? Warn
            return (
              <li key={e.event_id} className="relative flex gap-3 pb-4 last:pb-0">
                {i < events.length - 1 && <span aria-hidden className="absolute bottom-0 left-[11px] top-6 w-px bg-line" />}
                <span className="grid size-6 flex-none place-items-center rounded-full bg-accent-soft text-accent"><I width={13} height={13} aria-hidden /></span>
                <div className="min-w-0"><b className="block [font-weight:var(--w-strong)] text-ink">{e.title}</b>
                  <span className="text-[13px] text-muted">{formatSimDate(e.sim_day)} · {e.detail}</span></div>
              </li>
            )
          })}
        </ol>
      )}
    </>
  )
}

function Footer({ unit }: { unit: FleetUnit }) {
  const plan = usePlan().data?.find((p) => p.unit_id === unit.unit_id && p.state !== 'done')
  if (unit.needs_manager_decision) return <Strip tone="attention" title="Needs a manager decision" subtitle="No crew slot is free this week" action="Decide" to={`/plan?unit=${unit.unit_id}`} />
  if (plan?.decision === 'deferred') return <Strip tone="insight" title="Risk accepted for now" subtitle="A manager chose not to book a crew" action="Change" to={`/plan?unit=${unit.unit_id}`} />
  if (plan?.approval === 'proposed') return <Strip tone="insight" title={`Proposed for ${formatSimDate(plan.planned_day)}`} subtitle="Waiting for a manager to approve it" action="Review" to="/plan" />
  if (plan) return <Strip tone="calm" title={`Service booked for ${formatSimDate(plan.planned_day)}`} subtitle={plan.technician_name} action="View plan" to="/plan" />
  if (unit.failed) return <Strip tone="attention" title="This unit has failed" subtitle="It is counted as a breakdown" />
  if (unit.risk_status === 'healthy') return <Strip tone="calm" title="Running normally" subtitle="No action needed" />
  return <Strip tone="insight" title="No service booked yet" subtitle="The planner will schedule it when a crew is free" />
}

function PanelSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <Skeleton className="h-4 w-32" /><Skeleton className="h-10" />
      <div className="grid grid-cols-3 gap-2.5"><Skeleton className="h-[68px]" /><Skeleton className="h-[68px]" /><Skeleton className="h-[68px]" /></div>
      <Skeleton className="h-[140px]" /><Skeleton className="h-24" />
    </div>
  )
}

/** Unit detail slide-over (DESIGN.md 5.9). `summary` is the Fleet row we already have, so the header paints instantly. */
export function UnitPanel({ unitId, summary, open, onClose }: { unitId: string | null; summary?: FleetUnit; open: boolean; onClose: () => void }) {
  const { data: detail, isError } = useUnit(unitId)
  const unit = detail ?? summary
  return (
    <SlideOver open={open} onOpenChange={(o) => !o && onClose()}
      title={unitId ?? ''} headerExtra={unit && <StatusPill status={tileStatus(unit)} />}
      subtitle={unit ? `${unit.station} · Turbine ${unitNumber(unit.unit_id)}` : undefined}
      footer={unit ? <Footer unit={unit} /> : undefined}>
      {isError ? <p className="m-0 text-sm text-risk">Could not load this unit. Check the connection and try again.</p>
        : <Reveal ready={!!detail} skeleton={<PanelSkeleton />} label="Loading unit">{detail && <Body unit={detail} />}</Reveal>}
    </SlideOver>
  )
}
