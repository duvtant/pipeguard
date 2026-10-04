import { describe, expect, it } from 'vitest'
import { displayStatus } from '@/lib/status'
import { formatSimDate, simDate } from '@/lib/simCalendar'
import { SENSOR_LABELS } from '@/lib/sensors'
import { makeFleet, MOCK_SIM_DAY, STATIONS } from './fixtures/fleet'
import { makeDetail } from './fixtures/detail'
import { makePlan } from './fixtures/plan'
import { simulate } from './fixtures/simulate'
import { CALLS, EVENTS } from './fixtures/events'
import { TECHNICIANS } from './fixtures/technicians'

// These lock in the contract (docs/delegation/00_TEAM_CONTRACT.md) so a screen built against the
// fixtures behaves the same against the real API.
describe('fleet fixture', () => {
  const fleet = makeFleet()

  it('has 5 stations x 20 units with unique ids and the contract naming', () => {
    expect(fleet).toHaveLength(100)
    expect(new Set(fleet.map((u) => u.unit_id)).size).toBe(100)
    for (const s of STATIONS) expect(fleet.filter((u) => u.station_code === s.code)).toHaveLength(20)
    expect(fleet.every((u) => /^[A-Z]{3}-\d{2}$/.test(u.unit_id))).toBe(true)
  })

  it('is deterministic', () => {
    expect(makeFleet()).toEqual(fleet)
  })

  it('keeps display_status consistent with decision D1 everywhere', () => {
    for (const u of fleet) expect(u.display_status).toBe(displayStatus(u.risk_status, u.sensor_issue))
  })

  it('covers every case the UI must handle', () => {
    const by = (id: string) => fleet.find((u) => u.unit_id === id)!
    expect(by('EDS-07')).toMatchObject({ display_status: 'at_risk', next_service_day: 32 })
    expect(by('HIN-12')).toMatchObject({ display_status: 'sensor_issue', confidence: 'low' })
    expect(by('WHT-03')).toMatchObject({ display_status: 'at_risk', sensor_issue: true }) // red WITH wrench
    expect(by('GPR-15').failed).toBe(true)
    expect(by('EDS-14').needs_manager_decision).toBe(true)
    expect(by('DRH-09')).toMatchObject({ risk_status: 'watch', confidence: 'low' })
    expect(by('DRH-17').data_source).toBe('fallback')
  })

  it('keeps ranges ordered and within bounds', () => {
    for (const u of fleet) {
      expect(u.rul.low).toBeLessThanOrEqual(u.rul.likely)
      expect(u.rul.likely).toBeLessThanOrEqual(u.rul.high)
      expect(u.p_fail).toBeGreaterThanOrEqual(0)
      expect(u.p_fail).toBeLessThanOrEqual(1)
      expect(u.top_sensors.every((s) => s in SENSOR_LABELS)).toBe(true)
    }
  })
})

describe('simulated calendar', () => {
  it('maps day 0 to a Monday and the mock day to a Tuesday, so Friday is day 32', () => {
    expect(simDate(0).getUTCDay()).toBe(1)
    expect(simDate(MOCK_SIM_DAY).getUTCDay()).toBe(2)
    expect(simDate(32).getUTCDay()).toBe(5)
    expect(formatSimDate(32)).toMatch(/Fri/)
  })
})

describe('plan fixture', () => {
  const plan = makePlan(makeFleet())
  it('never plans failed units and respects 2 crews per station per day', () => {
    expect(plan.find((p) => p.unit_id === 'GPR-15')).toBeUndefined()
    const counts = new Map<string, number>()
    for (const p of plan.filter((x) => x.state === 'planned')) counts.set(`${p.station_code}:${p.planned_day}`, (counts.get(`${p.station_code}:${p.planned_day}`) ?? 0) + 1)
    for (const n of counts.values()) expect(n).toBeLessThanOrEqual(2)
  })
  it('flags the unit with no slot as needs_manager_decision', () => {
    expect(plan.find((p) => p.unit_id === 'EDS-14')?.state).toBe('needs_manager_decision')
  })
})

describe('simulate fixture', () => {
  const base = { cost_breakdown: 200000, cost_service: 20000, threshold: null, horizon_days: null }
  it('totals add up and PipeGuard beats both baselines', () => {
    const r = simulate({ ...base, crews_per_station: 2 })
    for (const p of r.policies) expect(p.total_cost).toBeGreaterThan(0)
    const [rtf, fixed, pg] = r.policies
    expect(pg.total_cost).toBeLessThan(fixed.total_cost)
    expect(fixed.total_cost).toBeLessThan(rtf.total_cost)
    expect(r.tuned.total_cost).toBeLessThanOrEqual(r.default.total_cost)
  })
  it('more crews means fewer PipeGuard breakdowns, and extremes stay sensible', () => {
    const b = (c: number) => simulate({ ...base, crews_per_station: c }).policies[2].breakdowns
    expect(b(1)).toBeGreaterThanOrEqual(b(2))
    expect(b(2)).toBeGreaterThanOrEqual(b(5))
    for (const c of [0, 1, 50]) expect(Number.isFinite(simulate({ ...base, crews_per_station: c }).policies[2].total_cost)).toBe(true)
  })
})

describe('events, calls and roster', () => {
  it('has strictly increasing event ids', () => {
    for (let i = 1; i < EVENTS.length; i++) expect(EVENTS[i].event_id).toBeGreaterThan(EVENTS[i - 1].event_id)
  })
  it('includes a French call with an English summary for the manager', () => {
    const fr = CALLS.find((c) => c.language === 'fr')!
    expect(fr.transcript.length).toBeGreaterThan(0)
    expect(fr.summary_en).not.toBe(fr.summary)
  })
  it('has a French-speaking technician for the French unit and two backups', () => {
    expect(TECHNICIANS.some((t) => t.language === 'fr' && t.station_code === 'GPR')).toBe(true)
    expect(TECHNICIANS.filter((t) => t.is_backup).length).toBeGreaterThanOrEqual(2)
  })
  it('builds a detail view for any unit', () => {
    const d = makeDetail(makeFleet().find((u) => u.unit_id === 'EDS-07')!, EVENTS, CALLS)
    expect(d.history).toHaveLength(30)
    expect(d.sensors).toHaveLength(3)
    expect(d.calls.length).toBe(1)
  })
})
