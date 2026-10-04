import { Link } from 'react-router-dom'
import { motion } from 'motion/react'
import Download from '~icons/ph/download-simple'
import Printer from '~icons/ph/printer'
import { ChipLink } from '@/components/ui/Chip'
import { Card, CardHeader, Num } from '@/components/ui/Card'
import { ActionButton } from '@/components/ui/ActionButton'
import { Skeleton } from '@/components/ui/Skeleton'
import { ValueFlash } from '@/components/ui/ValueFlash'
import { useToast } from '@/components/ui/Toast'
import { usePlan } from '@/lib/queries'
import { formatSimDate } from '@/lib/simCalendar'
import { dollars, moneyText } from '@/lib/format'
import { API_BASE } from '@/lib/api'
import { pageItem } from '@/design/motion'
import type { PlanItem } from '@/lib/types'

const STATE: Record<PlanItem['state'], string> = { planned: 'Planned', done: 'Done', blocked: 'Blocked', needs_manager_decision: 'Needs a decision' }

export default function WorkOrders() {
  const { data, isError } = usePlan()
  const toast = useToast()
  const approvalOn = data?.some((p) => p.approval !== undefined) ?? false
  const waiting = approvalOn ? (data ?? []).filter((p) => p.approval === 'proposed' && p.state !== 'needs_manager_decision').length : 0
  // With approval on, only approved items are work orders. Without it (the API has no approval field), everything scheduled is shown as before.
  const orders = data?.filter((p) => p.state !== 'needs_manager_decision' && (!approvalOn || p.approval === 'approved')) ?? []
  const total = orders.reduce((s, p) => s + p.expected_saving, 0)

  async function download() {
    const res = await fetch(`${API_BASE}/work-orders.csv`)
    if (!res.ok) throw new Error(`${res.status}`)
    const name = /filename="?([^";]+)"?/.exec(res.headers.get('content-disposition') ?? '')?.[1] ?? 'work_orders.csv'
    const url = URL.createObjectURL(await res.blob())
    const a = Object.assign(document.createElement('a'), { href: url, download: name })
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url)
    toast.show({ title: 'Work orders downloaded', detail: name, tone: 'calm' })
  }

  return (
    <div>
      <h1 className="m-0 mb-1 text-[28px] [font-weight:var(--w-body)] leading-9 tracking-[-0.01em] text-ink">Work orders</h1>
      <p className="m-0 mb-4 text-sm text-muted">Every approved service, ready to hand to the crews as a spreadsheet.{waiting > 0 && <> <Link to="/plan" className="text-accent-ink underline">{waiting} {waiting === 1 ? 'change is' : 'changes are'} waiting for approval.</Link></>}</p>
      <div className="mb-5 flex flex-wrap items-center gap-2"><ActionButton variant="primary" icon={<Download width={16} height={16} />} onAction={download} successLabel="Downloaded" pendingLabel="Preparing">Download CSV</ActionButton><ChipLink to="/summary" icon={<Printer width={16} height={16} />}>Weekly summary</ChipLink></div>
      <div className="mb-6 grid gap-6 sm:grid-cols-2">
        <motion.div {...pageItem(0)}><Card><div className="text-sm text-muted">Work orders</div>{data ? <Num size="md" value={<ValueFlash value={orders.length} label="Work orders" />} /> : <Skeleton className="h-8 w-16" />}</Card></motion.div>
        <motion.div {...pageItem(1)}><Card><div className="text-sm text-muted">Estimated cost avoided</div>{data ? <Num size="md" value={moneyText(total)} /> : <Skeleton className="h-8 w-24" />}<div className="text-[13px] text-muted">Illustrative: probability of failure times the cost of a breakdown, minus the cost of the service.</div></Card></motion.div>
      </div>
      <motion.div {...pageItem(2)}>
        <Card pad={false}>
          <div className="px-6 pt-5"><CardHeader title="Scheduled services" /></div>
          {isError ? <p role="alert" className="m-0 px-6 pb-5 text-sm text-risk">Could not load the work orders.</p> : !data ? <div className="space-y-2 px-6 pb-5">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-9" />)}</div> : orders.length === 0 ? <p className="m-0 px-6 pb-5 text-sm text-muted">Nothing is scheduled yet.</p> : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <caption className="sr-only">Scheduled services</caption>
                <thead className="text-[13px] text-muted"><tr className="border-b border-line"><th className="px-6 py-2 [font-weight:var(--w-body)]">Date</th><th className="py-2 [font-weight:var(--w-body)]">Unit</th><th className="py-2 [font-weight:var(--w-body)]">Technician</th><th className="py-2 [font-weight:var(--w-body)]">Why</th><th className="py-2 text-right [font-weight:var(--w-body)]">Estimated cost avoided</th><th className="px-6 py-2 [font-weight:var(--w-body)]">State</th></tr></thead>
                <tbody>
                  {orders.map((p) => (
                    <tr key={p.id} className="border-b border-line align-top last:border-b-0">
                      <td className="tnum px-6 py-2.5 text-text">{formatSimDate(p.planned_day)}</td>
                      <td className="tnum"><Link to={`/?unit=${p.unit_id}`} className="text-accent-ink [font-weight:var(--w-strong)]">{p.unit_id}</Link></td>
                      <td className="text-text">{p.technician_name}</td>
                      <td className="max-w-[300px] text-muted">{p.reason}</td>
                      <td className="tnum text-right text-ink">{dollars(p.expected_saving)}</td>
                      <td className="px-6 text-text">{STATE[p.state]}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </motion.div>
    </div>
  )
}
