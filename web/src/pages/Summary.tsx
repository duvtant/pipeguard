import { motion } from 'motion/react'
import Printer from '~icons/ph/printer'
import { Card, CardHeader } from '@/components/ui/Card'
import { ActionButton } from '@/components/ui/ActionButton'
import { Skeleton } from '@/components/ui/Skeleton'
import { useEvents, useFleet, usePlan, useSimulate } from '@/lib/queries'
import { POLICY_NAMES } from '@/lib/exports'
import { DEFAULT_COST_BREAKDOWN, DEFAULT_COST_SERVICE, DEFAULT_CREWS } from '@/lib/config'
import { formatSimDate } from '@/lib/simCalendar'
import { dollars, moneyText } from '@/lib/format'
import { pageItem } from '@/design/motion'
import type { EventType } from '@/lib/types'

const DECISION_EVENTS = new Set<EventType>(['plan_changed', 'plan_approved', 'manager_decision'])
const TOP_N = 8
const DEFAULT_REQUEST = { crews_per_station: DEFAULT_CREWS, cost_breakdown: DEFAULT_COST_BREAKDOWN, cost_service: DEFAULT_COST_SERVICE, threshold: null, horizon_days: null }

function Stat({ label, value, tone }: { label: string; value: number | undefined; tone?: 'risk' }) {
  return <div><div className="text-sm text-muted">{label}</div><div className={`tnum text-[22px] leading-7 ${tone === 'risk' && value ? 'text-risk' : 'text-ink'}`}>{value ?? '–'}</div></div>
}

/** One page for a director: print it, or "Save as PDF" from the print dialog. The menu and header are hidden on paper (see index.css). */
export default function Summary() {
  const fleet = useFleet(), plan = usePlan(), events = useEvents(), sim = useSimulate(DEFAULT_REQUEST)
  const today = fleet.data?.sim_day
  const approvalOn = plan.data?.some((p) => p.approval !== undefined) ?? false
  const orders = (plan.data ?? []).filter((p) => p.state !== 'needs_manager_decision' && (!approvalOn || p.approval === 'approved')).sort((a, b) => a.planned_day - b.planned_day)
  const waiting = approvalOn ? (plan.data ?? []).filter((p) => p.approval === 'proposed' && p.state !== 'needs_manager_decision').length : 0
  const open = (plan.data ?? []).filter((p) => p.state === 'needs_manager_decision' && !p.decision).length
  const atRisk = fleet.data?.units.filter((u) => u.display_status === 'at_risk' && !u.failed).length
  const decisions = today === undefined ? [] : (events.data ?? []).filter((e) => DECISION_EVENTS.has(e.type) && e.sim_day > today - 7).sort((a, b) => b.event_id - a.event_id).slice(0, 8)
  const total = orders.reduce((s, p) => s + p.expected_saving, 0)
  // One page: the biggest services by estimated cost avoided. The full list is the Work orders download.
  const top = [...orders].sort((a, b) => b.expected_saving - a.expected_saving).slice(0, TOP_N).sort((a, b) => a.planned_day - b.planned_day || b.expected_saving - a.expected_saving)
  const hidden = orders.length - top.length
  const ready = !!(fleet.data && plan.data)

  return (
    <div>
      <div data-print-hide className="mb-5 flex flex-wrap items-end gap-x-6 gap-y-3">
        <div className="min-w-0 flex-1">
          <h1 className="m-0 mb-1 text-[28px] [font-weight:var(--w-body)] leading-9 tracking-[-0.01em] text-ink">Weekly summary</h1>
          <p className="m-0 text-sm text-muted">One page for your director. Print it, or choose &ldquo;Save as PDF&rdquo; in the print window.</p>
        </div>
        <ActionButton variant="primary" icon={<Printer width={16} height={16} />} disabled={!ready} onAction={() => window.print()} successLabel="Opened">Print or save as PDF</ActionButton>
      </div>

      <motion.div {...pageItem(0)}>
        <Card className="mx-auto max-w-[900px] print:max-w-none print:p-1">
          <header className="border-b border-line pb-4 print:pb-3">
            <div className="text-sm text-muted">Prairie Gas Transmission · PipeGuard weekly summary</div>
            <h2 className="m-0 mt-1 text-[22px] [font-weight:var(--w-body)] leading-7 text-ink">{today === undefined ? <Skeleton className="h-7 w-72" /> : `Week of ${formatSimDate(today)}`}</h2>
            <p className="m-0 mt-1 text-[15px] leading-6 text-text">{sim.data ? sim.data.headline.text : <span className="text-muted">&nbsp;</span>}</p>
          </header>

          <section aria-label="This week at a glance" className="grid grid-cols-2 gap-4 border-b border-line py-4 print:grid-cols-4 print:py-3 sm:grid-cols-4">
            <Stat label="Units at risk" value={atRisk} />
            <Stat label="Services booked" value={ready ? orders.length : undefined} />
            <Stat label="Waiting for approval" value={ready ? waiting : undefined} />
            <Stat label="Need your decision" value={ready ? open : undefined} tone="risk" />
          </section>

          <section aria-label="Services this week" className="border-b border-line py-4 print:py-3">
            <CardHeader title={orders.length > TOP_N ? `Services booked: the ${TOP_N} largest` : 'Services booked'} />
            {!plan.data ? <Skeleton className="h-24" /> : orders.length === 0 ? <p className="m-0 text-sm text-muted">No services are booked.</p> : (
              <table className="mt-1 w-full text-left text-sm print:text-[12px]">
                <caption className="sr-only">Approved services this week</caption>
                <thead className="text-[13px] text-muted"><tr className="border-b border-line"><th className="py-2 pr-3 [font-weight:var(--w-body)]">Date</th><th className="[font-weight:var(--w-body)]">Unit</th><th className="[font-weight:var(--w-body)]">Technician</th><th className="[font-weight:var(--w-body)]">Reason</th><th className="text-right [font-weight:var(--w-body)]">Est. avoided</th></tr></thead>
                <tbody className="[&_td]:py-2">{top.map((p) => (
                  <tr key={p.id} className="break-inside-avoid border-b border-line align-middle">
                    <td className="tnum whitespace-nowrap pr-3 text-text">{formatSimDate(p.planned_day)}</td><td className="tnum whitespace-nowrap pr-3 [font-weight:var(--w-strong)] text-ink">{p.unit_id}</td>
                    <td className="whitespace-nowrap pr-3 text-text">{p.technician_name}</td><td className="max-w-[280px] pr-3 text-muted">{p.reason}</td><td className="tnum text-right text-ink">{dollars(p.expected_saving)}</td>
                  </tr>))}
                  <tr className="border-t border-line"><td colSpan={4} className="text-muted">{hidden > 0 ? `${hidden} more in the Work orders download. Total for all ${orders.length}, estimated` : 'Total, estimated'}</td><td className="tnum text-right [font-weight:var(--w-strong)] text-ink">{dollars(total)}</td></tr>
                </tbody>
              </table>
            )}
          </section>

          <section aria-label="Decisions this week" className="border-b border-line py-4 print:py-3">
            <CardHeader title="Decisions this week" />
            {!events.data ? <Skeleton className="h-20" /> : decisions.length === 0 ? <p className="m-0 text-sm text-muted">No plan changes or approvals this week.</p> : (
              <ul className="m-0 list-none p-0 text-sm">{decisions.map((e) => (
                <li key={e.event_id} className="flex gap-3 break-inside-avoid py-1.5"><span className="tnum w-[78px] flex-none text-muted">{formatSimDate(e.sim_day)}</span><span className="text-text"><b className="[font-weight:var(--w-strong)] text-ink">{e.title}.</b> {e.detail}</span></li>
              ))}</ul>
            )}
          </section>

          <section aria-label="Estimated cost" className="py-4 print:py-3">
            <CardHeader title="Estimated cost over the replay" />
            {!sim.data ? <Skeleton className="h-16" /> : (
              <div className="grid grid-cols-3 gap-4">{sim.data.policies.map((r) => (
                <div key={r.policy}><div className={`text-sm ${r.policy === 'pipeguard' ? '[font-weight:var(--w-strong)] text-accent-ink' : 'text-muted'}`}>{POLICY_NAMES[r.policy]}</div>
                  <div className="tnum text-[22px] leading-7 text-ink print:text-lg">{moneyText(r.total_cost)}</div><div className="tnum text-[13px] text-muted">{r.breakdowns} breakdowns, {r.wasted_services} wasted</div></div>
              ))}</div>
            )}
          </section>
          <p className="m-0 border-t border-line pt-3 text-[13px] text-muted">Dollar amounts are estimates from illustrative costs (a breakdown {dollars(DEFAULT_COST_BREAKDOWN)}, a planned service {dollars(DEFAULT_COST_SERVICE)}), not accounting figures. Prairie Gas is a simulated company; turbine data is the NASA C-MAPSS FD001 set. PipeGuard recommends; people approve and decide.</p>
        </Card>
      </motion.div>
    </div>
  )
}
