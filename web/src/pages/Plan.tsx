import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { LayoutGroup, motion } from 'motion/react'
import Octagon from '~icons/ph/warning-octagon-fill'
import { Card, CardHeader } from '@/components/ui/Card'
import { Strip } from '@/components/ui/Strip'
import { Skeleton } from '@/components/ui/Skeleton'
import { ActionButton } from '@/components/ui/ActionButton'
import Info from '~icons/ph/info'
import { api } from '@/lib/api'
import { cx } from '@/components/ui/Card'
import { useFleet, usePlan, useSettings, useTechnicians } from '@/lib/queries'
import { formatSimDate } from '@/lib/simCalendar'
import { moneyText } from '@/lib/format'
import { spring } from '@/design/motion'
import type { DecisionChoice, PlanItem } from '@/lib/types'

const DAYS = 7
const STATION_NAME: Record<string, string> = { EDS: 'Edson', HIN: 'Hinton', WHT: 'Whitecourt', GPR: 'Grande Prairie', DRH: 'Drumheller' }

/** Plan items whose day changed since the last render, for the 1.2 s "this just moved" highlight. */
function useMoved(plan: PlanItem[] | undefined) {
  const prev = useRef<Map<number, number> | null>(null)
  const [moved, setMoved] = useState<ReadonlySet<number>>(new Set())
  useEffect(() => {
    if (!plan) return
    const now = new Map(plan.map((p) => [p.id, p.planned_day]))
    const before = prev.current; prev.current = now
    if (!before) return
    const ids = plan.filter((p) => before.has(p.id) && before.get(p.id) !== p.planned_day).map((p) => p.id)
    if (ids.length === 0) return
    const t0 = setTimeout(() => setMoved(new Set(ids)), 0), t1 = setTimeout(() => setMoved(new Set()), 1200)
    return () => { clearTimeout(t0); clearTimeout(t1) }
  }, [plan])
  return moved
}

function Block({ p, moved, proposed }: { p: PlanItem; moved: boolean; proposed: boolean }) {
  // `layoutId` makes a block glide from its old slot to its new one when the plan changes (the demo's signature moment).
  return (
    <motion.div layout layoutId={`plan-${p.id}`} transition={spring.panel}
      className={cx('rounded-[10px] px-2.5 py-1.5 text-[13px] leading-[18px]', proposed ? 'border border-dashed border-accent bg-canvas' : cx('shadow-tile', p.state === 'done' ? 'bg-ok-tint text-ok' : p.state === 'blocked' ? 'bg-sens-tint text-sens' : 'bg-accent-soft text-ink'), moved && 'pg-flash')}>
      <Link to={`/?unit=${p.unit_id}`} className="block rounded [font-weight:var(--w-strong)] text-ink hover:underline" aria-label={`${p.unit_id}, ${formatSimDate(p.planned_day)}, ${p.technician_name}. ${p.reason}${proposed ? '. Proposed, waiting for a manager to approve it.' : ''}`}>{p.unit_id}</Link>
      <span className="block truncate text-muted" title={p.reason}>{proposed ? <b className="[font-weight:var(--w-strong)] text-accent-ink">Proposed</b> : `~${moneyText(p.expected_saving)} avoided`}</span>
    </motion.div>
  )
}

/** The facts a manager needs to decide, in the order they think: how long, what happens, what it costs. Money is always labelled an estimate. */
function DecisionFacts({ item, rul, breakdownCost }: { item: PlanItem; rul?: { low: number; likely: number; high: number }; breakdownCost?: number }) {
  return (
    <ul className="m-0 mt-1 list-none p-0 text-[13px] leading-5 text-muted">
      {rul && <li><b className="[font-weight:var(--w-strong)] text-ink">About {Math.round(rul.likely)} days left</b> (could be {Math.round(rul.low)} to {Math.round(rul.high)}).</li>}
      <li>No crew is free in the next {DAYS} days.</li>
      <li>If it fails first: the station loses compression{breakdownCost ? `, an estimated ${moneyText(breakdownCost)} breakdown` : ''}.</li>
      <li>If it is serviced in time: an estimated {moneyText(item.expected_saving)} avoided.</li>
    </ul>
  )
}

export default function Plan() {
  const { data: plan, isError } = usePlan()
  const { data: fleet } = useFleet()
  const { data: techs } = useTechnicians()
  const { data: settings } = useSettings()
  const moved = useMoved(plan)
  const today = fleet?.sim_day
  const days = useMemo(() => (today === undefined ? [] : Array.from({ length: DAYS }, (_, i) => today + i)), [today])
  const rows = useMemo(() => (techs ?? []).filter((t) => !t.is_backup && t.shift === 'day').sort((a, b) => a.station_code.localeCompare(b.station_code)), [techs])
  const open = plan?.filter((p) => p.state === 'needs_manager_decision' && !p.decision) ?? []
  const deferred = plan?.filter((p) => p.decision === 'deferred') ?? []
  const focus = useSearchParams()[0].get('unit') // "Review" links here with ?unit=EDS-14 so the right card is marked
  const later = plan?.filter((p) => p.state !== 'needs_manager_decision' && today !== undefined && p.planned_day >= today + DAYS).length ?? 0
  const loading = !plan || !techs || today === undefined
  // Approval is only shown when the API really supports it (it sends an `approval` field). Otherwise the page is exactly as before.
  const approvalOn = plan?.some((p) => p.approval !== undefined) ?? false
  const waiting = approvalOn ? (plan ?? []).filter((p) => p.approval === 'proposed' && p.state !== 'needs_manager_decision') : []
  const qc = useQueryClient()
  const refresh = async () => { await qc.invalidateQueries({ queryKey: ['plan'] }); await qc.invalidateQueries({ queryKey: ['fleet'] }); await qc.invalidateQueries({ queryKey: ['events'] }) }
  const decide = (id: number, choice: DecisionChoice) => async () => { await api(`/plan/${id}/decide`, { method: 'POST', body: JSON.stringify({ choice }) }); await refresh() }
  const approve = async () => { await api('/plan/approve-all', { method: 'POST' }); await qc.invalidateQueries({ queryKey: ['plan'] }); await qc.invalidateQueries({ queryKey: ['fleet'] }) }

  return (
    <div>
      <h1 className="m-0 mb-1 text-[28px] [font-weight:var(--w-body)] leading-9 tracking-[-0.01em] text-ink">Plan</h1>
      <p className="m-0 mb-4 text-sm text-muted">The next {DAYS} days by technician. Blocks move on their own when a call changes the plan.</p>
      {waiting.length > 0 && (
        <div role="status" className="mb-5 flex flex-wrap items-center gap-x-3.5 gap-y-2 overflow-hidden rounded-card bg-[image:var(--g-insight)] px-6 py-3.5 shadow-card">
          <span className="grid size-8 flex-none place-items-center rounded-full bg-white/80 text-accent"><Info width={16} height={16} aria-hidden /></span>
          <div className="min-w-0 flex-1">
            <b className="block [font-weight:var(--w-strong)] text-ink">{waiting.length === 1 ? '1 plan change is waiting for your approval' : `${waiting.length} plan changes are waiting for your approval`}</b>
            <span className="text-[13px] text-muted">{waiting.map((w) => `${w.unit_id} on ${formatSimDate(w.planned_day)}`).join(', ')}. Nothing becomes a work order until a manager approves it.</span>
          </div>
          <ActionButton variant="primary" onAction={approve} successLabel="Approved">{waiting.length === 1 ? 'Approve' : `Approve all ${waiting.length}`}</ActionButton>
        </div>
      )}
      {open.map((o) => (
        <div key={o.id} role="group" aria-label={`Decision needed for ${o.unit_id}`} className={cx('mb-5 overflow-hidden rounded-card bg-[image:var(--g-attn)] px-6 py-4 shadow-card', focus === o.unit_id && 'pg-flash')}>
          <div className="flex items-start gap-3.5">
            <span className="grid size-8 flex-none place-items-center rounded-full bg-white/80 text-risk"><Octagon width={16} height={16} aria-hidden /></span>
            <div className="min-w-0 flex-1">
              <b className="block [font-weight:var(--w-strong)] text-ink">{o.unit_id} needs your decision</b>
              <DecisionFacts item={o} rul={fleet?.units.find((u) => u.unit_id === o.unit_id)?.rul} breakdownCost={settings?.cost_breakdown} />
              <div className="mt-3 flex flex-wrap items-center gap-2.5">
                <ActionButton variant="primary" onAction={decide(o.id, 'overtime')} successLabel="Booked">Add an overtime crew</ActionButton>
                <ActionButton onAction={decide(o.id, 'defer')} successLabel="Accepted">Accept the risk for now</ActionButton>
                <Link to={`/?unit=${o.unit_id}`} className="text-sm text-accent-ink underline-offset-2 hover:underline">See the evidence</Link>
              </div>
            </div>
          </div>
        </div>
      ))}
      {deferred.length > 0 && (
        <div className="mb-5 overflow-hidden rounded-card shadow-card">
          {deferred.map((d) => <Strip key={d.id} tone="insight" title={`${d.unit_id}: risk accepted for now`} subtitle="A manager chose not to book a crew. It stays at risk and is not on the schedule." action="Add overtime instead" onAction={() => { void decide(d.id, 'overtime')().then(() => undefined) }} />)}
        </div>
      )}
      <Card pad={false}>
        <div className="px-6 pt-5"><CardHeader title="Week at a glance" /></div>
        {isError ? <p role="alert" className="m-0 px-6 pb-5 text-sm text-risk">Could not load the plan.</p> : loading ? <div className="space-y-2 px-6 pb-5">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-14" />)}</div> : (
          <LayoutGroup>
            <div className="overflow-x-auto pb-4">
              <div role="table" aria-label="Weekly plan by technician" className="grid min-w-[860px] px-6" style={{ gridTemplateColumns: `180px repeat(${DAYS}, minmax(96px, 1fr))` }}>
                <div role="row" className="contents">
                  <div role="columnheader" className="py-2 text-[13px] text-muted">Technician</div>
                  {days.map((d) => <div role="columnheader" key={d} className="tnum py-2 text-[13px] text-muted">{formatSimDate(d)}</div>)}
                </div>
                {/* Units that no crew can take: never silently dropped, always visible. */}
                {open.length > 0 && (
                  <div role="row" className="contents">
                    <div role="rowheader" className="flex items-center gap-2 border-t border-line py-3 text-sm text-risk"><Octagon width={16} height={16} aria-hidden />Open</div>
                    <div role="cell" className="col-span-7 flex flex-wrap gap-2 border-t border-line py-2">
                      {open.map((p) => <Link key={p.id} to={`/?unit=${p.unit_id}`} className="rounded-[10px] bg-risk-tint px-2.5 py-1.5 text-[13px] text-risk shadow-tile [font-weight:var(--w-strong)]" title={p.reason}>{p.unit_id} needs a decision</Link>)}
                    </div>
                  </div>
                )}
                {rows.map((t) => (
                  <Fragment key={t.id}>
                    <div role="row" className="contents">
                      <div role="rowheader" className="border-t border-line py-3 pr-3 text-sm"><span className="block text-ink">{t.name}</span><span className="text-[13px] text-muted">{STATION_NAME[t.station_code]}</span></div>
                      {days.map((d) => {
                        const here = plan.filter((p) => p.technician_id === t.id && p.planned_day === d && p.state !== 'needs_manager_decision')
                        return <div role="cell" key={d} className="flex min-h-[64px] flex-col gap-1.5 border-t border-line py-2 pr-2">{here.map((p) => <Block key={p.id} p={p} moved={moved.has(p.id)} proposed={approvalOn && p.approval === 'proposed'} />)}</div>
                      })}
                    </div>
                  </Fragment>
                ))}
              </div>
            </div>
          </LayoutGroup>
        )}
      </Card>
      {later > 0 && <p className="m-0 mt-3 text-[13px] text-muted">{later} more {later === 1 ? 'service is' : 'services are'} scheduled after this week.</p>}
    </div>
  )
}
