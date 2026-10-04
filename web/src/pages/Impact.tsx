import { useState } from 'react'
import { motion } from 'motion/react'
import Sliders from '~icons/ph/sliders-horizontal'
import ChartLine from '~icons/ph/chart-line'
import Table from '~icons/ph/table'
import { Card, CardHeader, Num } from '@/components/ui/Card'
import { Chip } from '@/components/ui/Chip'
import { ExportButton } from '@/components/ui/ExportButton'
import { impactCsv, POLICY_NAMES as NAMES } from '@/lib/exports'
import { ValueFlash } from '@/components/ui/ValueFlash'
import { Strip } from '@/components/ui/Strip'
import { Segmented } from '@/components/ui/Segmented'
import { Skeleton } from '@/components/ui/Skeleton'
import { Slider } from '@/components/ui/Slider'
import { CompareChart } from '@/components/ui/charts'
import { useFeedbackStats, useFleet, useModel, useSimulate } from '@/lib/queries'
import { useDebounced } from '@/hooks/useDebounced'
import { DEFAULT_COST_BREAKDOWN, DEFAULT_COST_SERVICE, DEFAULT_CREWS } from '@/lib/config'
import { dollars, money, moneyText } from '@/lib/format'
import { pageItem } from '@/design/motion'
import type { Policy } from '@/lib/types'

const CREW_DETENTS = [0, 1, 2, 3, 4, 5] as const

/** The API's headline sentence, with "88 of 100" picked out. If the number is not in the text, it is shown as it came. */
function Claim({ text, key_ }: { text: string; key_: string }) {
  const at = text.indexOf(key_)
  if (at < 0) return <>{text}</>
  return <>{text.slice(0, at)}<b className="[font-weight:var(--w-strong)] text-ink">{key_}</b>{text.slice(at + key_.length)}</>
}

export default function Impact() {
  const [crews, setCrews] = useState(DEFAULT_CREWS)
  const [cb, setCb] = useState(DEFAULT_COST_BREAKDOWN)
  const [cs, setCs] = useState(DEFAULT_COST_SERVICE)
  const [view, setView] = useState<'chart' | 'table'>('chart')

  // ~200ms debounce; TanStack Query cancels the superseded request through its abort signal.
  const req = useDebounced({ crews_per_station: crews, cost_breakdown: cb, cost_service: cs, threshold: null, horizon_days: null }, 200)
  const sim = useSimulate(req)
  const model = useModel()
  const track = useFeedbackStats().data
  const simDay = useFleet().data?.sim_day ?? 0
  const data = sim.data
  const stale = sim.isFetching || req.crews_per_station !== crews || req.cost_breakdown !== cb || req.cost_service !== cs

  const cost = (p: Policy) => data?.policies.find((x) => x.policy === p)?.total_cost ?? 0
  const saving = data ? data.default.total_cost - data.tuned.total_cost : 0
  const defaults = crews === DEFAULT_CREWS && cb === DEFAULT_COST_BREAKDOWN && cs === DEFAULT_COST_SERVICE

  return (
    <div>
      <h1 className="m-0 mb-1 text-[28px] [font-weight:var(--w-body)] leading-9 tracking-[-0.01em] text-ink">Impact</h1>
      {/* Same shape as every other page: a title and one line under it. The claim is that line, with its key number picked out. */}
      <p className="m-0 mb-5 max-w-[760px] text-[15px] leading-6 text-muted" aria-live="polite">
        {data ? <Claim text={data.headline.text} key_={`${data.headline.actioned} of ${data.headline.total}`} /> : sim.isError ? <span className="text-risk">Could not run the simulation. <button type="button" onClick={() => sim.refetch()} className="text-accent-ink underline">Try again</button></span> : 'Running the simulation…'}
      </p>

      <div className="grid gap-6 xl:grid-cols-[1.45fr_1fr]">
        <motion.div {...pageItem(0)}>
          <Card className="h-full">
            <CardHeader title="Estimated total cost over the replay" verified actions={<>
              <ExportButton disabled={!data || stale} build={() => (data ? impactCsv(data, req, simDay) : null)} />
              <Segmented label="View" value={view} onChange={setView} options={[
                { value: 'chart', label: 'Chart', icon: <ChartLine width={18} height={18} /> },
                { value: 'table', label: 'Table', icon: <Table width={18} height={18} /> },
              ]} /></>} />
            {!data ? <Skeleton className="mt-2 h-[300px]" /> : (
              <div className={stale ? 'opacity-60 transition-opacity duration-150' : 'transition-opacity duration-150'} aria-busy={stale}>
                <div className="mt-1.5 flex flex-wrap gap-x-[34px] gap-y-3">
                  {(['run_to_failure', 'fixed_schedule', 'pipeguard'] as Policy[]).map((p) => {
                    const pg = p === 'pipeguard'
                    return (
                      <div key={p}>
                        <div className={pg ? '[font-weight:var(--w-strong)] text-accent-ink' : 'text-muted'}>{NAMES[p]}</div>
                        <Num value={<ValueFlash value={cost(p)} format={(n) => money(n).value} label={NAMES[p]} throttle={0} />} unit={money(cost(p)).unit} size={pg ? 'lg' : 'md'} className={pg ? undefined : 'text-muted'} />
                      </div>
                    )
                  })}
                </div>
                {view === 'chart' && !data.series?.length ? (
                  // The server does not send the cost-over-time series yet (an optional part of /api/simulate): show the three yearly totals as bars.
                  <ul aria-label="Total cost by approach" className="m-0 mt-5 flex list-none flex-col gap-4 p-0">
                    {(['run_to_failure', 'fixed_schedule', 'pipeguard'] as Policy[]).map((pol) => {
                      const top = Math.max(...data.policies.map((r) => r.total_cost), 1)
                      return (
                        <li key={pol}>
                          <div className="mb-1 flex items-baseline justify-between text-sm"><span className={pol === 'pipeguard' ? '[font-weight:var(--w-strong)] text-accent-ink' : 'text-muted'}>{NAMES[pol]}</span><span className="tnum text-ink">{moneyText(cost(pol))}</span></div>
                          <div className="h-3 rounded-full bg-pill"><div className={`h-3 rounded-full ${pol === 'pipeguard' ? 'bg-accent' : pol === 'fixed_schedule' ? 'bg-[#7A8197]' : 'bg-[#B8BCCB]'}`} style={{ width: `${Math.max(2, (cost(pol) / top) * 100)}%` }} /></div>
                        </li>
                      )
                    })}
                  </ul>
                ) : view === 'chart' ? (
                  <div className="-mx-6 mt-3.5">
                    <CompareChart height={220} label="Cumulative cost by policy over the replay" format={moneyText}
                      data={(data.series ?? []).map((d) => ({ x: `Day ${d.sim_day}`, run_to_failure: d.run_to_failure, fixed_schedule: d.fixed_schedule, pipeguard: d.pipeguard }))}
                      series={[
                        { key: 'run_to_failure', label: NAMES.run_to_failure, color: '#B8BCCB', dashed: true },
                        { key: 'fixed_schedule', label: NAMES.fixed_schedule, color: '#7A8197' },
                        { key: 'pipeguard', label: NAMES.pipeguard, color: '#5367EB', strong: true },
                      ]} />
                  </div>
                ) : (
                  <table className="mt-3.5 w-full text-left text-sm">
                    <caption className="sr-only">Cost and outcomes by policy</caption>
                    <thead className="text-[13px] text-muted"><tr><th className="py-2 [font-weight:var(--w-body)]">Policy</th><th className="text-right [font-weight:var(--w-body)]">Breakdowns</th><th className="text-right [font-weight:var(--w-body)]">Services</th><th className="text-right [font-weight:var(--w-body)]">Wasted</th><th className="text-right [font-weight:var(--w-body)]">Total cost</th></tr></thead>
                    <tbody>
                      {data.policies.map((r) => (
                        <tr key={r.policy} className="border-t border-line">
                          <td className={`py-2.5 ${r.policy === 'pipeguard' ? '[font-weight:var(--w-strong)] text-accent-ink' : 'text-text'}`}>{NAMES[r.policy]}</td>
                          <td className="tnum text-right">{r.breakdowns}</td><td className="tnum text-right">{r.planned_services}</td><td className="tnum text-right">{r.wasted_services}</td>
                          <td className="tnum text-right [font-weight:var(--w-strong)] text-ink">{dollars(r.total_cost)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}
          </Card>
        </motion.div>

        <motion.div {...pageItem(1)}>
          <Card pad={false} className="flex h-full flex-col">
            <div className="px-6 pb-5 pt-5">
              <CardHeader title="What if?" actions={<span className={defaults ? 'invisible' : undefined}><Chip icon={<Sliders width={16} height={16} />} onClick={() => { setCrews(DEFAULT_CREWS); setCb(DEFAULT_COST_BREAKDOWN); setCs(DEFAULT_COST_SERVICE) }}>Reset</Chip></span>} />
              <p className="m-0 text-sm text-muted">Drag a slider to try your own numbers{data && <span className="tnum"> · {data.computed_ms} ms</span>}</p>
              <Slider className="mt-4" label="Crews per station" value={crews} min={0} max={5} step={1} onValueChange={setCrews} detents={CREW_DETENTS} format={(v) => `${v} ${v === 1 ? 'crew' : 'crews'}`} />
              <Slider className="mt-3" label="Cost of a breakdown" value={cb} min={50_000} max={500_000} step={10_000} onValueChange={setCb} detents={[{ value: DEFAULT_COST_BREAKDOWN, label: 'default' }]} format={dollars} />
              <Slider className="mt-3" label="Cost of a planned service" value={cs} min={5_000} max={60_000} step={1_000} onValueChange={setCs} detents={[{ value: DEFAULT_COST_SERVICE, label: 'default' }]} format={dollars} />
            </div>
            {data && (saving > 0
              ? <Strip tone="calm" className="mt-auto" title={`Self-tuned beats default by ${moneyText(saving)}`} subtitle={`Threshold ${data.tuned.threshold.toFixed(2)} vs ${data.default.threshold.toFixed(2)}`} />
              : saving < 0
                ? <Strip tone="insight" className="mt-auto" title={`Self-tuned costs ${moneyText(-saving)} more, and warns earlier`} subtitle={`${data.headline.actioned} of ${data.headline.total} failures get the full ${data.headline.lead_days} days of warning`} />
                : <Strip tone="insight" className="mt-auto" title="Self-tuned matches the default" subtitle={`Threshold ${data.tuned.threshold.toFixed(2)} vs ${data.default.threshold.toFixed(2)}`} />)}
          </Card>
        </motion.div>
      </div>

      <motion.div {...pageItem(2)} className="mt-8">
        <Card>
          <CardHeader title="Default settings vs self-tuned" verified />
          {!data ? <Skeleton className="h-[110px]" /> : (
            <div className={`grid gap-6 sm:grid-cols-[1fr_1fr_1fr] ${stale ? 'opacity-60' : ''} transition-opacity duration-150`}>
              <div><div className="text-sm text-muted">Default settings</div>
                <Num size="md" className="text-muted" value={<ValueFlash value={data.default.total_cost} format={(n) => money(n).value} label="Default total cost" throttle={0} />} unit={money(data.default.total_cost).unit} />
                <div className="tnum mt-1 text-[13px] text-muted">Alert threshold {data.default.threshold.toFixed(2)} · plan {data.default.horizon_days} days ahead</div></div>
              <div><div className="text-sm [font-weight:var(--w-strong)] text-accent-ink">Self-tuned</div>
                <Num size="md" value={<ValueFlash value={data.tuned.total_cost} format={(n) => money(n).value} label="Self-tuned total cost" throttle={0} />} unit={money(data.tuned.total_cost).unit} />
                <div className="tnum mt-1 text-[13px] text-muted">Alert threshold {data.tuned.threshold.toFixed(2)} · plan {data.tuned.horizon_days} days ahead</div></div>
              <div className="rounded-[14px] bg-[image:var(--g-calm)] px-4 py-3"><div className="text-sm text-muted">{saving > 0 ? 'Saved by self-tuning' : saving < 0 ? 'Extra cost of self-tuning' : 'Difference'}</div>
                <Num size="md" value={<ValueFlash value={Math.abs(saving)} format={(n) => money(n).value} label="Saving from self-tuning" throttle={0} />} unit={money(Math.abs(saving)).unit} />
                <div className="mt-1 text-[13px] text-muted">{saving < 0 ? `It books earlier, so ${data.headline.actioned} of ${data.headline.total} failures get the full ${data.headline.lead_days} days of warning.` : 'The system measured its own results and adjusted its threshold.'}</div></div>
            </div>
          )}
        </Card>
      </motion.div>

      <div className={`mt-8 grid gap-6 ${track && track.total > 0 ? 'md:grid-cols-3' : 'md:grid-cols-2'}`}>
        <motion.div {...pageItem(2)}>
          <Card className="h-full">
            <CardHeader title="Failures caught early" />
            {data ? <><Num value={<ValueFlash value={data.headline.actioned} label="Failures caught early" throttle={0} />} unit={`of ${data.headline.total}`} />
              <p className="m-0 mt-1.5 text-sm text-muted">Flagged at least {data.headline.lead_days} days before failure and serviced in time.</p></> : <Skeleton className="h-[72px]" />}
          </Card>
        </motion.div>
        <motion.div {...pageItem(3)}>
          <Card className="h-full">
            <CardHeader title="Prediction error" />
            {model.data ? <><Num value={<ValueFlash value={model.data.rmse} label="Prediction error" />} unit="cycles" />
              <p className="m-0 mt-1.5 text-sm text-muted">Down from {model.data.baseline_rmse} for the simple baseline model.</p></> : <Skeleton className="h-[72px]" />}
          </Card>
        </motion.div>
        {track && track.total > 0 && (
          <motion.div {...pageItem(4)}>
            <Card className="h-full">
              <CardHeader title="Warnings technicians confirmed" />
              <Num value={<ValueFlash value={track.confirmed} label="Warnings confirmed" />} unit={`of ${track.total}`} />
              <p className="m-0 mt-1.5 text-sm text-muted">After a job, the technician says if the warning was right. The rest were false alarms, and the system learns from them.</p>
            </Card>
          </motion.div>
        )}
      </div>

      <motion.details {...pageItem(4)} className="group mt-8 rounded-card bg-canvas px-6 py-4 shadow-card">
        <summary className="flex min-h-8 cursor-pointer list-none items-center gap-2 text-[15px] text-text marker:hidden"><span className="[font-weight:var(--w-strong)] text-ink">How this is calculated</span><span className="text-[13px] text-muted group-open:hidden">Show assumptions</span></summary>
        <ul className="m-0 mt-3 list-disc pl-5 text-sm text-muted">
          <li className="mt-1">The fleet is the public NASA C-MAPSS FD001 turbofan dataset standing in for gas turbines. Prairie Gas and its costs are simulated.</li>
          <li className="mt-1">Dollar figures are illustrative: a breakdown and a planned service cost what the sliders say.</li>
          <li className="mt-1">&ldquo;Your routine today&rdquo; is a fixed schedule: service every unit every N days. &ldquo;Reactive&rdquo; is run until it breaks. Both and PipeGuard are replayed on the same fleet and the same days.</li>
          <li className="mt-1">The tuned threshold was found on cross-fitted predictions (each engine is scored by models that never saw it), so the improvement is not a result of testing on training data.</li>
          <li className="mt-1">Crew capacity limits how many services can happen per station per day.</li>
        </ul>
      </motion.details>
    </div>
  )
}
