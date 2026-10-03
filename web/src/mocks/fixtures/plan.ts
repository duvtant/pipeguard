import type { FleetUnit, PlanItem } from '@/lib/types'
import { isoSimDate } from '@/lib/simCalendar'
import { MOCK_SIM_DAY } from './fleet'
import { TECHNICIANS } from './technicians'

// Builds a 7-day plan from the fleet: at-risk units first, then watch units with positive saving.
const COST_BREAKDOWN = 200000
const COST_SERVICE = 20000

export function makePlan(units: FleetUnit[]): PlanItem[] {
  const candidates = units
    .filter((u) => !u.failed && (u.risk_status === 'at_risk' || (u.risk_status === 'watch' && u.p_fail * COST_BREAKDOWN > COST_SERVICE)))
    .sort((a, b) => b.p_fail - a.p_fail)
  const items: PlanItem[] = []
  const slotsUsed = new Map<string, number>()
  let id = 1
  for (const u of candidates) {
    const tech = TECHNICIANS.find((t) => t.station_code === u.station_code && !t.is_backup) ?? TECHNICIANS[0]
    if (u.needs_manager_decision) {
      items.push({ id: id++, unit_id: u.unit_id, station_code: u.station_code, planned_day: MOCK_SIM_DAY, planned_date: isoSimDate(MOCK_SIM_DAY),
        technician_id: tech.id, technician_name: tech.name, expected_saving: Math.round(u.p_fail * COST_BREAKDOWN - COST_SERVICE),
        reason: 'No crew slot free in the next 7 days', state: 'needs_manager_decision' })
      continue
    }
    let day = u.next_service_day ?? MOCK_SIM_DAY + 1
    while ((slotsUsed.get(`${u.station_code}:${day}`) ?? 0) >= 2) day++
    slotsUsed.set(`${u.station_code}:${day}`, (slotsUsed.get(`${u.station_code}:${day}`) ?? 0) + 1)
    items.push({ id: id++, unit_id: u.unit_id, station_code: u.station_code, planned_day: day, planned_date: isoSimDate(day),
      technician_id: tech.id, technician_name: tech.name, expected_saving: Math.round(u.p_fail * COST_BREAKDOWN - COST_SERVICE),
      reason: u.reason, state: 'planned' })
  }
  return items.sort((a, b) => a.planned_day - b.planned_day || b.expected_saving - a.expected_saving)
}
