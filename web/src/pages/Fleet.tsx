import { useCallback, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'motion/react'
import Play from '~icons/ph/play-fill'
import Pause from '~icons/ph/pause-fill'
import PhoneCall from '~icons/ph/phone-call'
import CalendarCheck from '~icons/ph/calendar-check'
import Download from '~icons/ph/download-simple'
import ChartLine from '~icons/ph/chart-line'
import Table from '~icons/ph/table'
import ArrowUp from '~icons/ph/arrow-up-right'
import ArrowDown from '~icons/ph/arrow-down-right'
import CaretRight from '~icons/ph/caret-right'
import Caret from '~icons/ph/caret-down'
import { Card, CardHeader, Num } from '@/components/ui/Card'
import { ChipLink } from '@/components/ui/Chip'
import { ExportButton } from '@/components/ui/ExportButton'
import { fleetCsv } from '@/lib/exports'
import { ActionButton } from '@/components/ui/ActionButton'
import { ValueFlash } from '@/components/ui/ValueFlash'
import { Strip } from '@/components/ui/Strip'
import { Avatar } from '@/components/ui/Avatar'
import { Segmented } from '@/components/ui/Segmented'
import { Tabs } from '@/components/ui/Tabs'
import { UnitTile } from '@/components/ui/UnitTile'
import { UnitPanel } from '@/components/units/UnitPanel'
import { Skeleton } from '@/components/ui/Skeleton'
import { AreaTrend } from '@/components/ui/charts'
import { STATUS, STATUS_ORDER, StatusPill } from '@/components/ui/status'
import { useChangedUnits } from '@/hooks/useChangedUnits'
import CloudSlash from '~icons/ph/cloud-slash'
import Rewind from '~icons/ph/arrow-counter-clockwise'
import { useEvents, useFleet, usePlan, useTrend } from '@/lib/queries'
import { api } from '@/lib/api'
import { callStats, needingAttention, planStats, stationSummary, tileStatus } from '@/lib/fleetStats'
import { formatSimDate } from '@/lib/simCalendar'
import { DEFAULT_CREWS } from '@/lib/config'
import { moneyText } from '@/lib/format'
import { pageItem } from '@/design/motion'
import type { FleetUnit } from '@/lib/types'

const shortDate = (day: number) => formatSimDate(day).replace(/^\w+, /, '')

export default function Fleet() {
  const fleet = useFleet()
  if (fleet.isError && !fleet.data) {
    return (
      <Card className="max-w-[520px]"><div className="flex items-start gap-3"><span className="grid size-8 flex-none place-items-center rounded-full bg-risk-tint text-risk"><CloudSlash width={16} height={16} aria-hidden /></span>
        <div role="alert"><h2 className="m-0 text-[15px] [font-weight:var(--w-strong)] text-ink">Cannot reach the server</h2><p className="m-0 mt-1 text-sm text-muted">There is no fleet data to show yet. We keep trying; you can also try now.</p>
          <div className="mt-3"><ActionButton variant="primary" onAction={async () => { const r = await fleet.refetch(); if (r.isError) throw r.error }}>Try again</ActionButton></div></div></div></Card>
    )
  }
  return <FleetPage fleet={fleet} />
}

function FleetPage({ fleet }: { fleet: ReturnType<typeof useFleet> }) {
  const trend = useTrend()
  const plan = usePlan()
  const events = useEvents()
  const qc = useQueryClient()
  const running = fleet.data?.clock.status === 'running'
  const clock = useMutation({
    mutationFn: (body: { action: 'play' | 'pause' | 'speed' | 'reset'; speed_seconds_per_day?: number }) => api('/clock', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['fleet'] }),
  })

  const units = fleet.data?.units
  const changed = useChangedUnits(units)
  const counts = useMemo(() => Object.fromEntries(STATUS_ORDER.map((s) => [s, (units ?? []).filter((u) => tileStatus(u) === s).length])) as Record<(typeof STATUS_ORDER)[number], number>, [units])
  const speed = String(fleet.data?.clock.speed_seconds_per_day ?? 1)
  const stations = useMemo(() => {
    const m = new Map<string, { code: string; name: string; units: FleetUnit[] }>()
    for (const u of units ?? []) {
      if (!m.has(u.station_code)) m.set(u.station_code, { code: u.station_code, name: u.station, units: [] })
      m.get(u.station_code)!.units.push(u)
    }
    return [...m.values()]
  }, [units])

  // The open unit lives in the URL (?unit=EDS-07): deep-linkable, and Back closes the panel.
  const [params, setParams] = useSearchParams()
  const unitId = params.get('unit')
  const lastUnit = useRef<string | null>(null)
  if (unitId) lastUnit.current = unitId // keep the content while the panel slides out
  const panelId = unitId ?? lastUnit.current
  const selectUnit = useCallback((u: FleetUnit) => setParams({ unit: u.unit_id }), [setParams])
  const closePanel = () => setParams({})

  const [view, setView] = useState<'chart' | 'table'>('chart')
  const [tab, setTab] = useState('all')

  const attention = units ? needingAttention(units) : []
  const t = trend.data ?? []
  const weekAgo = t.length > 7 ? t[t.length - 8].needing_attention : undefined
  const delta = weekAgo === undefined ? undefined : attention.length - weekAgo
  const p = plan.data ? planStats(plan.data) : undefined
  const calls = events.data ? callStats(events.data) : undefined
  const openCall = calls?.open[0]
  const openSaving = plan.data?.find((x) => x.unit_id === openCall)?.expected_saving
  const decisionUnit = units?.find((u) => u.needs_manager_decision)
  const approvalOn = plan.data?.some((x) => x.approval !== undefined) ?? false
  const waitingApproval = approvalOn ? (plan.data ?? []).filter((x) => x.approval === 'proposed' && x.state !== 'needs_manager_decision').length : 0
  const shown = tab === 'all' ? stations : stations.filter((s) => s.code === tab)

  return (
    <div>
      <h1 className="m-0 mb-1 text-[28px] [font-weight:var(--w-body)] leading-9 tracking-[-0.01em] text-ink">Fleet overview</h1>
      <p className="m-0 mb-4 text-sm text-muted" aria-live="polite">
        {fleet.data ? (running ? `Replay running at ${fleet.data.clock.speed_seconds_per_day} s per simulated day · ${formatSimDate(fleet.data.sim_day)}` : `Replay paused · ${formatSimDate(fleet.data.sim_day)} (day ${fleet.data.sim_day})`) : ' '}
        {units?.some((u) => u.data_source === 'fallback') && <span className="ml-2 rounded-full bg-pill px-2 py-0.5 text-[13px]">Some units use precomputed predictions</span>}
      </p>
      <div className="mb-5 flex flex-wrap items-center gap-2">
        <ActionButton variant="primary" icon={running ? <Pause width={16} height={16} /> : <Play width={16} height={16} />}
          onAction={() => clock.mutateAsync({ action: running ? 'pause' : 'play' })} successLabel={running ? 'Paused' : 'Playing'}>
          {running ? 'Pause replay' : 'Play replay'}
        </ActionButton>
        <Segmented label="Replay speed" value={speed} onChange={(v) => clock.mutate({ action: 'speed', speed_seconds_per_day: Number(v) })}
          options={[{ value: '2', label: 'Slow: 2 seconds per day', icon: <span className="text-[13px] [font-weight:var(--w-strong)]">1×</span> },
            { value: '1', label: 'Normal: 1 second per day', icon: <span className="text-[13px] [font-weight:var(--w-strong)]">2×</span> },
            { value: '0.25', label: 'Fast: a quarter second per day', icon: <span className="text-[13px] [font-weight:var(--w-strong)]">8×</span> }]} />
        <ActionButton icon={<Rewind width={16} height={16} />} onAction={() => clock.mutateAsync({ action: 'reset' })} successLabel="Reset">Reset replay</ActionButton>
        <ChipLink to="/test" icon={<PhoneCall width={16} height={16} />}>Simulate call</ChipLink>
        <ChipLink to="/plan" icon={<CalendarCheck width={16} height={16} />}>Open weekly plan</ChipLink>
        <ChipLink to="/orders" icon={<Download width={16} height={16} />}>Work orders</ChipLink>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.45fr_1fr]">
        <motion.div {...pageItem(0)}>
          <Card className="flex h-full flex-col">
            <CardHeader title="Units needing attention" verified actions={
              <Segmented label="View" value={view} onChange={setView} options={[
                { value: 'chart', label: 'Chart', icon: <ChartLine width={18} height={18} /> },
                { value: 'table', label: 'Table', icon: <Table width={18} height={18} /> },
              ]} />} />
            {!units ? <Skeleton className="mt-2 h-[250px]" /> : (
              <>
                <div><Num value={<ValueFlash value={attention.length} label="Units needing attention" />} unit={attention.length === 1 ? 'unit' : 'units'} /></div>
                <div className="my-2.5 flex items-center justify-between text-text">
                  <span className="flex items-center gap-1.5">Last 30 days <Caret width={14} height={14} aria-hidden /></span>
                  {delta !== undefined && (
                    <span className={`flex items-center gap-1 [font-weight:var(--w-strong)] ${delta > 0 ? 'text-risk' : delta < 0 ? 'text-ok' : 'text-muted'}`}>
                      {delta > 0 ? <ArrowUp width={14} height={14} aria-hidden /> : delta < 0 ? <ArrowDown width={14} height={14} aria-hidden /> : null}
                      {delta === 0 ? 'No change this week' : `${delta > 0 ? '+' : '−'}${Math.abs(delta)} this week`}
                    </span>
                  )}
                </div>
                {view === 'chart' ? (
                  <div className="-mx-6 mt-1.5 min-h-[220px] flex-1">
                    <AreaTrend height="100%" label="Units needing attention" xTicks={5}
                      data={t.map((d) => ({ x: shortDate(d.sim_day), y: d.needing_attention }))} />
                  </div>
                ) : (
                  <table className="mt-1 w-full text-left text-sm">
                    <caption className="sr-only">Units needing attention</caption>
                    <thead className="text-[13px] text-muted"><tr><th className="py-2 [font-weight:var(--w-body)]">Unit</th><th className="[font-weight:var(--w-body)]">Status</th><th className="[font-weight:var(--w-body)]">Days left</th><th className="[font-weight:var(--w-body)]">Why</th></tr></thead>
                    <tbody>
                      {attention.map((u) => (
                        <tr key={u.unit_id} className="border-t border-line align-top">
                          <td className="tnum py-2.5 [font-weight:var(--w-strong)] text-ink">{u.unit_id}</td>
                          <td><StatusPill status={tileStatus(u)} /></td>
                          <td className="tnum text-text">{u.failed ? '—' : `${u.rul.low} to ${u.rul.high}`}</td>
                          <td className="text-muted">{u.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </>
            )}
          </Card>
        </motion.div>

        <motion.div {...pageItem(1)}>
          <Card pad={false} className="flex h-full flex-col">
            <div className="px-6 pb-1 pt-5">
              <CardHeader title="Stations" />
              <ul className="m-0 list-none p-0">
                {!units ? [0, 1, 2, 3, 4].map((i) => <li key={i} className="py-3"><Skeleton className="h-9" /></li>) : stations.map((s, i) => {
                  const sum = stationSummary(s.units)
                  return (
                    <li key={s.code} className="flex items-center gap-3 py-2.5">
                      <Avatar letter={s.name[0]} tone={i} />
                      <div className="leading-5 text-ink">{s.name}<br /><span className="text-[13px] text-muted">{s.units.length} units</span></div>
                      <div className="ml-auto"><StatusPill status={sum.status} label={sum.status === 'healthy' ? 'Healthy' : sum.text} /></div>
                    </li>
                  )
                })}
              </ul>
            </div>
            <Strip className="mt-auto" title={`${DEFAULT_CREWS} crews on shift per station`} subtitle="Change crew size in Settings" to="/settings" />
          </Card>
        </motion.div>
      </div>

      <motion.div {...pageItem(2)} className="mt-8">
        <Card>
          <CardHeader title="Turbines" actions={<ExportButton disabled={!units} build={() => (units && fleet.data ? fleetCsv(units, plan.data, fleet.data.sim_day) : null)} />} />
          <div className="mt-1 flex flex-wrap items-center justify-between gap-3">
            <Tabs label="Station" value={tab} onChange={setTab} tabs={[{ value: 'all', label: 'All stations' }, ...stations.map((s) => ({ value: s.code, label: s.name }))]} />
          </div>
          <ul className="m-0 mt-3 flex list-none flex-wrap gap-2 p-0" aria-label="Status legend">
            {STATUS_ORDER.map((s) => <li key={s}><StatusPill status={s} label={`${STATUS[s].label} · ${counts[s]}`} /></li>)}
          </ul>
          {!units ? <Skeleton className="mt-4 h-[140px]" /> : shown.map((s) => (
            <section key={s.code} aria-label={`${s.name} turbines`} className="mt-4">
              {tab === 'all' && <h3 className="m-0 mb-2 text-sm [font-weight:var(--w-strong)] text-muted">{s.name} · {s.units.length} turbines{(['at_risk', 'watch', 'sensor_issue', 'failed'] as const).map((k) => { const n = s.units.filter((u) => tileStatus(u) === k).length; return n ? ` · ${n} ${STATUS[k].label.toLowerCase()}` : '' }).join('')}</h3>}
              <div className="grid grid-cols-5 gap-2 sm:grid-cols-10">
                {s.units.map((u) => <UnitTile key={u.unit_id} unit={u} onSelect={selectUnit} changed={changed.has(u.unit_id)} />)}
              </div>
            </section>
          ))}
        </Card>
      </motion.div>

      <div className="mt-8 grid gap-6 md:grid-cols-2">
        <motion.div {...pageItem(3)}>
          <Card pad={false} className="flex h-full flex-col">
            <div className="px-6 pb-4 pt-5">
              <CardHeader title="This week's plan" />
              <div className={`mt-3.5 grid gap-2 ${approvalOn ? 'grid-cols-4' : 'grid-cols-3'}`}>
                {[['Scheduled', p?.scheduled], ['Needs decision', p?.needsDecision], ...(approvalOn ? [['To approve', waitingApproval]] : []), ['Completed', p?.completed]].map(([l, n]) => (
                  <div key={l as string}><div className="text-sm text-muted">{l}</div>
                    <Num size="sm" value={n === undefined ? '–' : <ValueFlash value={n as number} label={l as string} />} className={l === 'Needs decision' && (n as number) > 0 ? 'text-risk' : undefined} /></div>
                ))}
              </div>
            </div>
            {/* Both can be true at once, so both are shown (a decision never hides an approval waiting). */}
            <div className="mt-auto">
              {p && p.needsDecision > 0 && decisionUnit && <Strip tone="attention" title={p.needsDecision === 1 ? `${decisionUnit.unit_id} needs a manager decision` : `${p.needsDecision} units need a manager decision`} subtitle="No crew slot is free this week" action="Decide" to={`/plan?unit=${decisionUnit.unit_id}`} />}
              {waitingApproval > 0 && <Strip tone="insight" title={waitingApproval === 1 ? '1 plan change is waiting for approval' : `${waitingApproval} plan changes are waiting for approval`} subtitle="The agent proposed it; a manager approves it" action="Review" to="/plan" />}
              {!(p && p.needsDecision > 0 && decisionUnit) && waitingApproval === 0 && <Strip tone="calm" title="Every at-risk unit has a slot" subtitle="Nothing needs a decision" />}
            </div>
          </Card>
        </motion.div>
        <motion.div {...pageItem(4)}>
          <Card className="h-full">
            <CardHeader title="Voice calls" />
            <div className="mt-3.5 grid grid-cols-2 gap-2">
              {[['Answered', calls?.answered], ['Missed', calls?.missed]].map(([l, n]) => (
                <div key={l as string}><div className="text-sm text-muted">{l}</div><Num size="sm" value={n === undefined ? '–' : <ValueFlash value={n as number} label={l as string} />} /></div>
              ))}
            </div>
            <div className="mt-[18px] flex items-center border-t border-line pt-3.5">
              <div><div className="text-sm text-muted">Open</div>
                {openCall ? <span className="tnum">1 call · {openCall}{openSaving ? ` · est. ${moneyText(openSaving)} avoided` : ''}</span> : <span>No open calls</span>}
              </div>
              <Link to="/log" className="ml-auto flex min-h-10 items-center gap-1 [font-weight:var(--w-strong)] text-accent-ink">View <CaretRight width={14} height={14} aria-hidden /></Link>
            </div>
          </Card>
        </motion.div>
      </div>
      <UnitPanel unitId={panelId} summary={units?.find((u) => u.unit_id === panelId)} open={!!unitId} onClose={closePanel} />
      <span className="sr-only" aria-live="polite">{units ? `${attention.length} units need attention` : ''}</span>
    </div>
  )
}
