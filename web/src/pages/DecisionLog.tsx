import { useMemo, useState, type ComponentType, type SVGProps } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { motion } from 'motion/react'
import Octagon from '~icons/ph/warning-octagon-fill'
import Warn from '~icons/ph/warning-fill'
import PhoneCall from '~icons/ph/phone-call'
import CalendarCheck from '~icons/ph/calendar-check'
import Wrench from '~icons/ph/wrench-fill'
import Check from '~icons/ph/check-circle-fill'
import Chat from '~icons/ph/chat-circle-text'
import MagnifyingGlass from '~icons/ph/magnifying-glass'
import X from '~icons/ph/x'
import CaretDown from '~icons/ph/caret-down'
import { Card } from '@/components/ui/Card'
import { Tabs } from '@/components/ui/Tabs'
import { Skeleton } from '@/components/ui/Skeleton'
import { NewEventsPill, useNewItems } from '@/components/ui/NewEventsPill'
import { useEvents, useFleet, useUnit } from '@/lib/queries'
import { ExportButton } from '@/components/ui/ExportButton'
import { logCsv } from '@/lib/exports'
import { buildChains, matchesFilter, type Chain, type LogFilter } from '@/lib/chains'
import { formatSimDate } from '@/lib/simCalendar'
import { cx } from '@/components/ui/Card'
import { dur, ease } from '@/design/motion'
import type { CallRecord, EventMsg, PolicyCheck } from '@/lib/types'
import { criteriaName, guardrailLabel, reportCardSummary, toolCallsByTurn } from '@/lib/toolCalls'
import ClipboardText from '~icons/ph/clipboard-text'
import ShieldWarning from '~icons/ph/shield-warning'
import Gear from '~icons/ph/gear-six'
import ShieldCheck from '~icons/ph/shield-check'
import XCircle from '~icons/ph/x-circle'

type Icon = ComponentType<SVGProps<SVGSVGElement>>
const ICON: Partial<Record<EventMsg['type'], Icon>> = {
  status_change: Octagon, manager_alert: Octagon, failure: Octagon, sensor_issue: Wrench, call_requested: PhoneCall, call_answered: PhoneCall,
  constraint_added: Chat, plan_changed: CalendarCheck, plan_approved: Check, manager_decision: Check, call_summary: Chat, feedback_received: Check, threshold_adjusted: Check,
}
const OUTCOME: Record<Chain['outcome'], { label: string; cls: string; Icon: Icon }> = {
  open: { label: 'In progress', cls: 'bg-pill text-text', Icon: Warn },
  replanned: { label: 'Re-planned', cls: 'bg-ok-tint text-ok', Icon: CalendarCheck },
  approved: { label: 'Approved by a manager', cls: 'bg-ok-tint text-ok', Icon: Check },
  decided: { label: 'Decided by a manager', cls: 'bg-ok-tint text-ok', Icon: Check },
  closed: { label: 'Closed', cls: 'bg-ok-tint text-ok', Icon: Check },
  needs_decision: { label: 'Needs a decision', cls: 'bg-risk-tint text-risk', Icon: Octagon },
  missed: { label: 'Call missed', cls: 'bg-warn-tint text-warn', Icon: PhoneCall },
  failed: { label: 'Failed', cls: 'bg-fail-tint text-fail', Icon: Octagon },
  system: { label: 'System', cls: 'bg-accent-soft text-accent-ink', Icon: Check },
}
const TABS: { value: LogFilter; label: string }[] = [{ value: 'all', label: 'Everything' }, { value: 'calls', label: 'Calls' }, { value: 'plan', label: 'Plan changes' }, { value: 'alerts', label: 'Alerts' }]
const mmss = (s: number) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`

function ReportCard({ results }: { results: NonNullable<CallRecord['evaluation']> }) {
  const sum = reportCardSummary(results)
  return (
    <div className="mt-3 rounded-[12px] bg-canvas p-3 shadow-tile">
      <div className="mb-1 flex items-center gap-2 text-sm [font-weight:var(--w-strong)] text-ink"><ClipboardText width={16} height={16} className="text-accent" aria-hidden />Call report card
        <span className="tnum text-[13px] [font-weight:var(--w-body)] text-muted">{sum.passed} of {sum.total} passed{sum.failed > 0 ? `, ${sum.failed} failed` : ''}{sum.unknown > 0 ? `, ${sum.unknown} unclear` : ''}</span></div>
      <ul className="m-0 list-none p-0">
        {results.map((r) => (
          <li key={r.criteria_id} className="flex items-start gap-2.5 py-1 text-sm">
            {r.result === 'success' ? <Check width={16} height={16} className="mt-0.5 flex-none text-ok" aria-hidden /> : r.result === 'failure' ? <XCircle width={16} height={16} className="mt-0.5 flex-none text-risk" aria-hidden /> : <Warn width={16} height={16} className="mt-0.5 flex-none text-warn" aria-hidden />}
            <span><b className="[font-weight:var(--w-strong)] text-ink">{criteriaName(r.criteria_id)}</b><span className="sr-only">{r.result === 'success' ? ': passed' : r.result === 'failure' ? ': failed' : ': unclear'}</span>{r.rationale && <span className="block text-[13px] text-muted">{r.rationale}</span>}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function Transcript({ call }: { call: CallRecord }) {
  const french = call.language === 'fr'
  const tools = toolCallsByTurn(call.transcript)
  return (
    <div className={cx('mt-2 grid gap-4 rounded-[12px] bg-shell p-4 shadow-tile', french && 'md:grid-cols-[1.4fr_1fr]')}>
      <div>
        <div className="mb-2 text-[13px] text-muted">{call.technician_name} · {french ? 'French' : 'English'} · {call.duration_secs} s</div>
        <ol className="m-0 flex max-h-[260px] list-none flex-col gap-2 overflow-y-auto p-0" aria-label={`Transcript of the call with ${call.technician_name}`}>
          {call.transcript.map((t, i) => (
            <li key={i} className="flex gap-3 text-sm"><span className="tnum w-9 flex-none pt-0.5 text-[13px] text-muted">{mmss(t.time_in_call_secs)}</span>
              <span className="min-w-0"><b className="[font-weight:var(--w-strong)] text-ink">{t.role === 'agent' ? 'PipeGuard' : call.technician_name.split(' ')[0]}</b><span className="block text-text">{t.message}</span>
                {tools[i].map((tc, k) => (
                  <span key={k} className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 rounded-[10px] bg-canvas px-2.5 py-1.5 text-[13px] shadow-tile" aria-label={`The agent used the tool ${tc.name}, ${tc.status === 'worked' ? 'it worked' : tc.status === 'failed' ? 'it failed' : 'no result yet'}`}>
                    <Gear width={14} height={14} className="flex-none text-accent" aria-hidden /><b className="[font-weight:var(--w-strong)] text-ink">{tc.name}</b>
                    <span className="min-w-0 break-words text-muted">{tc.args.map(([a, v]) => `${a}: ${v}`).join(' · ')}</span>
                    <span className={cx('inline-flex items-center gap-1', tc.status === 'worked' ? 'text-ok' : tc.status === 'failed' ? 'text-risk' : 'text-muted')}>
                      {tc.status === 'worked' ? <Check width={13} height={13} aria-hidden /> : tc.status === 'failed' ? <XCircle width={13} height={13} aria-hidden /> : null}{tc.status === 'worked' ? 'worked' : tc.status === 'failed' ? 'failed' : 'no result'}{tc.seconds !== undefined ? ` · ${tc.seconds.toFixed(1)} s` : ''}</span>
                  </span>
                ))}
                {t.triggered_guardrails?.map((g, k) => (
                  <span key={`g${k}`} className="mt-1.5 flex items-center gap-1.5 rounded-[10px] bg-warn-tint px-2.5 py-1.5 text-[13px] text-warn"><ShieldWarning width={14} height={14} className="flex-none" aria-hidden />Safety stop: {guardrailLabel(g)} fired on this turn</span>
                ))}</span></li>
          ))}
        </ol>
        {call.evaluation && call.evaluation.length > 0 && <ReportCard results={call.evaluation} />}
      </div>
      {french && <div className="border-t border-line pt-3 md:border-l md:border-t-0 md:pl-4 md:pt-0"><div className="mb-1 text-[13px] text-muted">English summary</div><p className="m-0 text-sm text-text">{call.summary_en}</p></div>}
    </div>
  )
}

/** The policy gate's reasoning: every rule that had to pass before the agent was allowed to act, with the result in words and an icon. */
function SafetyChecks({ checks }: { checks: PolicyCheck[] }) {
  const [open, setOpen] = useState(false)
  const failed = checks.filter((k) => !k.passed).length
  return (
    <div className="mt-3 border-t border-line pt-3">
      <button type="button" aria-expanded={open} onClick={() => setOpen((v) => !v)} className="inline-flex min-h-8 items-center gap-1.5 text-sm [font-weight:var(--w-strong)] text-accent-ink">
        <ShieldCheck width={16} height={16} aria-hidden />{failed === 0 ? `Why it was allowed to call: ${checks.length} of ${checks.length} checks passed` : `Why it did not call: ${failed} of ${checks.length} checks failed`}
        <CaretDown width={14} height={14} aria-hidden className={cx('transition-transform duration-150', open && 'rotate-180')} />
      </button>
      {open && (
        <ul className="m-0 mt-2 list-none p-0">
          {checks.map((k) => (
            <li key={k.rule} className="flex items-start gap-2.5 py-1.5 text-sm">
              {k.passed ? <Check width={16} height={16} className="mt-0.5 flex-none text-ok" aria-hidden /> : <XCircle width={16} height={16} className="mt-0.5 flex-none text-risk" aria-hidden />}
              <span><b className="[font-weight:var(--w-strong)] text-ink">{k.rule}</b><span className="sr-only">{k.passed ? ': passed' : ': failed'}</span><span className="block text-[13px] text-muted">{k.detail}</span></span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function ChainCard({ c }: { c: Chain }) {
  const [open, setOpen] = useState(false)
  const hasCall = c.events.some((e) => e.type === 'call_answered')
  const detail = useUnit(open && c.unit_id ? c.unit_id : null)
  const o = OUTCOME[c.outcome]
  const first = c.events[0]
  const checks = c.events.map((e) => (e.payload?.checks as PolicyCheck[] | undefined) ?? []).find((x) => x.length > 0) ?? []
  return (
    <motion.li layout="position" initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: dur.base, ease: ease.out }} className="list-none">
      <Card>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          {c.unit_id ? <Link to={`/?unit=${c.unit_id}`} className="tnum text-[17px] [font-weight:var(--w-strong)] text-ink hover:underline">{c.unit_id}</Link> : <span className="text-[17px] [font-weight:var(--w-strong)] text-ink">System</span>}
          <span className={cx('inline-flex items-center gap-1.5 rounded-full py-[3px] pl-2 pr-2.5 text-[13px] font-semibold', o.cls)}><o.Icon width={14} height={14} aria-hidden />{o.label}</span>
          <span className="tnum ml-auto text-[13px] text-muted">{formatSimDate(c.events[c.events.length - 1].sim_day)}</span>
        </div>
        <p className="m-0 mt-1 text-sm text-muted">{first.detail}</p>
        <ol className="m-0 mt-3 list-none p-0">
          {c.events.map((e, i) => {
            const I = ICON[e.type] ?? Warn
            return (
              <li key={e.event_id} className="relative flex gap-3 pb-3 last:pb-0">
                {i < c.events.length - 1 && <span aria-hidden className="absolute bottom-0 left-[11px] top-6 w-px bg-line" />}
                <span className="grid size-6 flex-none place-items-center rounded-full bg-accent-soft text-accent"><I width={13} height={13} aria-hidden /></span>
                <div className="min-w-0"><b className="block text-sm [font-weight:var(--w-strong)] text-ink">{e.title}</b><span className="text-[13px] text-muted">{formatSimDate(e.sim_day)} · {e.detail}</span></div>
              </li>
            )
          })}
        </ol>
        {checks.length > 0 && <SafetyChecks checks={checks} />}
        {hasCall && c.unit_id && (
          <div className="mt-3 border-t border-line pt-3">
            <button type="button" aria-expanded={open} onClick={() => setOpen((v) => !v)} className="inline-flex min-h-8 items-center gap-1.5 text-sm [font-weight:var(--w-strong)] text-accent-ink">
              {open ? 'Hide transcript' : 'Show transcript'}<CaretDown width={14} height={14} aria-hidden className={cx('transition-transform duration-150', open && 'rotate-180')} />
            </button>
            {open && (detail.isLoading ? <Skeleton className="mt-2 h-24" /> : detail.data && detail.data.calls.length > 0
              ? detail.data.calls.map((call) => <Transcript key={call.id} call={call} />)
              : <p className="m-0 mt-2 text-sm text-muted" role="status">Transcript pending: it arrives within about a minute of the call ending.</p>)}
          </div>
        )}
      </Card>
    </motion.li>
  )
}

export default function DecisionLog() {
  const { data: events, isError } = useEvents()
  const simDay = useFleet().data?.sim_day ?? 0
  const [params, setParams] = useSearchParams()
  const unit = params.get('unit') ?? ''
  const [filter, setFilter] = useState<LogFilter>('all')
  const chains = useMemo(() => buildChains(events ?? []), [events])
  const shown = useMemo(() => chains.filter((c) => matchesFilter(c, filter) && (!unit || c.unit_id?.toLowerCase().includes(unit.toLowerCase()))), [chains, filter, unit])
  // New activity lands at the top; if you are reading further down, the list keeps your place and offers a jump.
  const { scrollProps, unread, jump } = useNewItems<HTMLUListElement>({ itemCount: events?.length ?? 0 })
  const setUnit = (v: string) => setParams(v ? { unit: v } : {}, { replace: true })

  return (
    <div>
      <h1 className="m-0 mb-1 text-[28px] [font-weight:var(--w-body)] leading-9 tracking-[-0.01em] text-ink">Decision log</h1>
      <p className="m-0 mb-4 text-sm text-muted">Every alert as one story: what drifted, who was called, what they said, how the plan changed.</p>
      <div className="mb-3 flex flex-wrap items-center gap-x-6 gap-y-2">
        <Tabs label="Filter" value={filter} onChange={setFilter} tabs={TABS} />
        <label className="ml-auto flex h-9 items-center gap-2 rounded-[10px] border border-line px-3 text-subtle focus-within:border-accent">
          <MagnifyingGlass width={16} height={16} aria-hidden />
          <input value={unit} onChange={(e) => setUnit(e.target.value)} placeholder="Filter by unit, e.g. EDS-07" aria-label="Filter by unit" className="w-[200px] bg-transparent py-2 text-sm text-ink outline-none placeholder:text-subtle" />
          {unit && <button type="button" onClick={() => setUnit('')} aria-label="Clear the unit filter" className="grid size-6 place-items-center rounded-full text-muted hover:bg-pill"><X width={14} height={14} aria-hidden /></button>}
        </label>
        {/* Exports what is on screen: the same filter and unit, every event inside the visible stories. */}
        <ExportButton disabled={!events || shown.length === 0} build={() => logCsv(shown.flatMap((c) => c.events), simDay)} />
      </div>
      <div className="relative">
        <NewEventsPill count={unread} onJump={jump} />
        <ul {...scrollProps} aria-label="Decision log" className="m-0 flex max-h-[calc(100vh-290px)] min-h-[320px] list-none flex-col gap-4 overflow-y-auto p-1 outline-none focus-visible:ring-2 focus-visible:ring-accent">
          {isError ? <li role="alert" className="text-sm text-risk">Could not load the decision log.</li>
            : !events ? [0, 1, 2].map((i) => <li key={i} className="list-none"><Skeleton className="h-36" /></li>)
            : shown.length === 0 ? <li className="list-none px-1 text-sm text-muted">{chains.length === 0 ? 'Nothing has happened yet. Alerts and calls will appear here as they happen.' : 'No alerts match this filter.'}</li>
            : shown.map((c) => <ChainCard key={c.id} c={c} />)}
        </ul>
      </div>
    </div>
  )
}
