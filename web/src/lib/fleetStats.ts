import type { EventMsg, FleetUnit, PlanItem } from './types'
import { STATUS } from '@/components/ui/status'

export const tileStatus = (u: FleetUnit) => (u.failed ? 'failed' : u.display_status)

/** Units the manager should look at: at risk (including with a sensor issue) or failed. */
export const needingAttention = (units: FleetUnit[]) => units.filter((u) => u.display_status === 'at_risk' || u.failed)

/** One line per station: the worst status wins, in plain words ("1 at risk"). */
const WORST_FIRST = ['failed', 'at_risk', 'watch', 'sensor_issue'] as const
export function stationSummary(units: FleetUnit[]) {
  for (const s of WORST_FIRST) {
    const n = units.filter((u) => tileStatus(u) === s).length
    if (n > 0) return { status: s, text: `${n} ${STATUS[s].label.toLowerCase()}` }
  }
  return { status: 'healthy' as const, text: 'Healthy' }
}

export function planStats(plan: PlanItem[]) {
  return {
    scheduled: plan.filter((p) => p.state === 'planned').length,
    needsDecision: plan.filter((p) => p.state === 'needs_manager_decision' && !p.decision).length,
    completed: plan.filter((p) => p.state === 'done').length,
  }
}

/** Calls derived from the event log: answered; missed (asked, never answered, escalated); open (asked, nothing yet). */
export function callStats(events: EventMsg[]) {
  const asked = new Map<string, EventMsg>()
  const answered = new Set<string>()
  const escalated = new Set<string>()
  for (const e of events) {
    if (!e.unit_id) continue
    if (e.type === 'call_requested') asked.set(e.unit_id, e)
    if (e.type === 'call_answered') answered.add(e.unit_id)
    if (e.type === 'manager_alert' && /missed/i.test(e.title)) escalated.add(e.unit_id)
  }
  const missed = [...asked.keys()].filter((u) => !answered.has(u) && escalated.has(u))
  const open = [...asked.keys()].filter((u) => !answered.has(u) && !escalated.has(u))
  return { answered: answered.size, missed: missed.length, open }
}
