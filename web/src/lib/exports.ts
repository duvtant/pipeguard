import { isoSimDate } from './simCalendar'
import type { CsvFile } from './exportCsv'
import type { EventMsg, EventType, FleetUnit, PlanItem, Policy, SimulateRequest, SimulateResponse } from './types'

// What a manager would want in Excel. Each builder takes data the page already has and returns a tidy table: one row per thing,
// plain-word column names, real numbers in number columns (so they sort and sum), and the simulated date as YYYY-MM-DD.

export const POLICY_NAMES: Record<Policy, string> = { run_to_failure: 'Reactive: run until it breaks', fixed_schedule: 'Your routine today: fixed schedule', pipeguard: 'PipeGuard' }

const STATUS_WORDS = { healthy: 'Healthy', watch: 'Watch', at_risk: 'At risk', sensor_issue: 'Sensor issue', failed: 'Failed' } as const
const EVENT_WORDS: Record<EventType, string> = {
  status_change: 'Status change', sensor_issue: 'Sensor issue', call_requested: 'Call requested', call_answered: 'Call answered', constraint_added: 'Availability recorded',
  plan_changed: 'Plan changed', plan_approved: 'Plan approved', manager_decision: 'Manager decision', call_summary: 'Call summary', feedback_received: 'Feedback received',
  threshold_adjusted: 'Threshold adjusted', failure: 'Failure', manager_alert: 'Manager alert',
}

const stamp = (day: number) => isoSimDate(day)

export function fleetCsv(units: FleetUnit[], plan: PlanItem[] | undefined, simDay: number): CsvFile {
  const byUnit = new Map((plan ?? []).filter((p) => p.state !== 'done').map((p) => [p.unit_id, p]))
  return {
    filename: `pipeguard_fleet_${stamp(simDay)}.csv`,
    columns: ['Unit', 'Station', 'Status', 'Days left (likely)', 'Days left (low)', 'Days left (high)', 'Failure risk (%)', 'Confidence', 'Reason', 'Needs a manager decision', 'Service date', 'Plan approval'],
    rows: units.map((u) => {
      const p = byUnit.get(u.unit_id)
      const servicing = p && p.state !== 'needs_manager_decision' ? p : undefined
      return [u.unit_id, u.station, STATUS_WORDS[u.failed ? 'failed' : u.display_status], Math.round(u.rul.likely), Math.round(u.rul.low), Math.round(u.rul.high),
        Math.round(u.p_fail * 1000) / 10, u.confidence === 'low' ? 'Low' : 'Normal', u.reason, u.needs_manager_decision, servicing ? servicing.planned_date : '',
        servicing?.approval === 'approved' ? 'Approved' : servicing?.approval === 'proposed' ? 'Proposed' : '']
    }),
  }
}

export function logCsv(events: EventMsg[], simDay: number): CsvFile {
  return {
    filename: `pipeguard_decision_log_${stamp(simDay)}.csv`,
    columns: ['Event id', 'Date', 'Unit', 'Type', 'Title', 'Detail', 'Severity'],
    rows: [...events].sort((a, b) => a.event_id - b.event_id).map((e) => [e.event_id, stamp(e.sim_day), e.unit_id ?? '', EVENT_WORDS[e.type] ?? e.type, e.title, e.detail, e.severity]),
  }
}

export function impactCsv(sim: SimulateResponse, req: Pick<SimulateRequest, 'crews_per_station' | 'cost_breakdown' | 'cost_service'>, simDay: number): CsvFile {
  return {
    filename: `pipeguard_impact_${stamp(simDay)}.csv`,
    columns: ['Policy', 'Breakdowns', 'Planned services', 'Wasted services', 'Crew days', 'Estimated total cost ($)', 'Crews per station', 'Breakdown cost assumed ($)', 'Service cost assumed ($)'],
    rows: sim.policies.map((r) => [POLICY_NAMES[r.policy], r.breakdowns, r.planned_services, r.wasted_services, r.crew_days, Math.round(r.total_cost), req.crews_per_station, req.cost_breakdown, req.cost_service]),
  }
}
