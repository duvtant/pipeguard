import type { FleetUnit, PlanItem } from '@/lib/types'
import { isoSimDate } from '@/lib/simCalendar'
import { MOCK_SIM_DAY } from './fleet'
import { TECHNICIANS } from './technicians'

// Builds a 7-day plan from the fleet: at-risk units first, then watch units with positive saving.
const COST_BREAKDOWN = 200000
const COST_SERVICE = 20000

export type Approvals = Record<string, { day: number; status: 'proposed' | 'approved' }>
// What a manager chose for a unit that no crew could take. `overtime` books it on `day` with an extra crew; `deferred` accepts the risk for now.
export type Decisions = Record<string, { choice: 'overtime' | 'deferred'; day: number }>

// `approvals` remembers which units have an unapproved change. Everything else is approved (the schedule as the manager last saw it).
export function makePlan(units: FleetUnit[], crews = 2, approvals: Approvals = {}, decisions: Decisions = {}): PlanItem[] {
  const candidates = units
    .filter((u) => !u.failed && (u.risk_status === 'at_risk' || (u.risk_status === 'watch' && u.p_fail * COST_BREAKDOWN > COST_SERVICE)))
    .sort((a, b) => b.p_fail - a.p_fail)
  const items: PlanItem[] = []
  const slotsUsed = new Map<string, number>()
  let id = 1
  for (const u of candidates) {
    const tech = TECHNICIANS.find((t) => t.station_code === u.station_code && !t.is_backup) ?? TECHNICIANS[0]
    const decided = decisions[u.unit_id]
    if (decided?.choice === 'overtime') {
      // An extra crew: it does not use one of the station's normal slots.
      items.push({ id: id++, unit_id: u.unit_id, station_code: u.station_code, planned_day: decided.day, planned_date: isoSimDate(decided.day),
        technician_id: tech.id, technician_name: tech.name, expected_saving: Math.round(u.p_fail * COST_BREAKDOWN - COST_SERVICE),
        reason: 'Overtime crew approved by a manager', state: 'planned', approval: 'approved', decision: 'overtime' })
      continue
    }
    if (decided?.choice === 'deferred' || u.needs_manager_decision || crews === 0) {
      items.push({ id: id++, unit_id: u.unit_id, station_code: u.station_code, planned_day: MOCK_SIM_DAY, planned_date: isoSimDate(MOCK_SIM_DAY),
        technician_id: tech.id, technician_name: tech.name, expected_saving: Math.round(u.p_fail * COST_BREAKDOWN - COST_SERVICE),
        reason: 'No crew slot free in the next 7 days', state: 'needs_manager_decision', approval: 'proposed', ...(decided?.choice === 'deferred' ? { decision: 'deferred' as const } : {}) })
      continue
    }
    let day = u.next_service_day ?? MOCK_SIM_DAY + 1
    while ((slotsUsed.get(`${u.station_code}:${day}`) ?? 0) >= crews) day++
    slotsUsed.set(`${u.station_code}:${day}`, (slotsUsed.get(`${u.station_code}:${day}`) ?? 0) + 1)
    items.push({ id: id++, unit_id: u.unit_id, station_code: u.station_code, planned_day: day, planned_date: isoSimDate(day),
      technician_id: tech.id, technician_name: tech.name, expected_saving: Math.round(u.p_fail * COST_BREAKDOWN - COST_SERVICE),
      reason: u.reason, state: 'planned' })
  }
  for (const it of items) { if (it.decision) continue; const a = approvals[it.unit_id]; it.approval = a && a.day === it.planned_day ? a.status : 'approved' }
  return items.sort((a, b) => a.planned_day - b.planned_day || b.expected_saving - a.expected_saving)
}
