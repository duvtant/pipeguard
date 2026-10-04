import type { EventMsg, EventType } from './types'

// The decision log groups events into one "chain" per alert: drift or fault, prediction, call, the technician's answer,
// the plan change, the summary, the feedback. A chain is a story about one unit; system events stand alone.
export interface Chain {
  id: string
  unit_id: string | null
  events: EventMsg[]          // oldest first
  lastId: number
  title: string
  outcome: 'open' | 'replanned' | 'approved' | 'decided' | 'needs_decision' | 'missed' | 'closed' | 'failed' | 'system'
}

const STARTERS = new Set<EventType>(['status_change', 'sensor_issue', 'manager_alert', 'failure'])
const FINISHERS = new Set<EventType>(['plan_changed', 'plan_approved', 'manager_decision', 'feedback_received', 'failure'])
// The API reports a failed turbine either as a `failure` event or as a status change titled "Unit failed".
const isFailure = (e: EventMsg) => e.type === 'failure' || (e.type === 'status_change' && /\bfailed\b/i.test(e.title))

function outcomeOf(events: EventMsg[]): Chain['outcome'] {
  const has = (t: EventType) => events.some((e) => e.type === t)
  if (events.some(isFailure)) return 'failed'
  if (has('manager_decision')) return 'decided'
  if (events.some((e) => e.type === 'manager_alert' && /missed/i.test(e.title))) return 'missed'
  if (events.some((e) => e.type === 'manager_alert')) return 'needs_decision'
  if (has('feedback_received')) return 'closed'
  if (has('plan_approved')) return 'approved'
  if (has('plan_changed')) return 'replanned'
  return 'open'
}

/** Newest chain first. A starter event (a status change, a sensor issue, an alert) opens a new chain for its unit only
 *  once the previous chain for that unit has finished (re-planned, closed or failed); until then it joins the same story. */
export function buildChains(events: EventMsg[]): Chain[] {
  const byUnit = new Map<string, Chain>()
  const chains: Chain[] = []
  // The real backend wrote a "Plan changed" event with no unit on every simulated day. They all go into ONE card, not one card each.
  let planUpdates: Chain | null = null
  for (const e of [...events].sort((a, b) => a.event_id - b.event_id)) {
    if (!e.unit_id && e.type === 'plan_changed') {
      if (!planUpdates) { planUpdates = { id: 'sys-plan', unit_id: null, events: [], lastId: 0, title: 'Plan updates', outcome: 'system' }; chains.push(planUpdates) }
      planUpdates.events.push(e); planUpdates.lastId = Math.max(planUpdates.lastId, e.event_id); continue
    }
    if (!e.unit_id) { chains.push({ id: `sys-${e.event_id}`, unit_id: null, events: [e], lastId: e.event_id, title: e.title, outcome: 'system' }); continue }
    let c = byUnit.get(e.unit_id)
    const finished = c?.events.some((x) => FINISHERS.has(x.type) || isFailure(x))
    if (!c || (STARTERS.has(e.type) && finished)) {
      c = { id: `${e.unit_id}-${e.event_id}`, unit_id: e.unit_id, events: [], lastId: 0, title: e.title, outcome: 'open' }
      byUnit.set(e.unit_id, c); chains.push(c)
    }
    c.events.push(e); c.lastId = Math.max(c.lastId, e.event_id)
  }
  for (const c of chains) if (c.unit_id) c.outcome = outcomeOf(c.events)
  return chains.sort((a, b) => b.lastId - a.lastId)
}

export type LogFilter = 'all' | 'calls' | 'plan' | 'alerts'
const CALL_TYPES = new Set<EventType>(['call_requested', 'call_answered', 'call_summary'])
export function matchesFilter(c: Chain, f: LogFilter): boolean {
  if (f === 'all') return true
  if (f === 'calls') return c.events.some((e) => CALL_TYPES.has(e.type))
  if (f === 'plan') return c.events.some((e) => e.type === 'plan_changed' || e.type === 'plan_approved' || e.type === 'manager_decision')
  return c.events.some((e) => e.severity !== 'info' || e.type === 'manager_alert' || e.type === 'sensor_issue')
}
