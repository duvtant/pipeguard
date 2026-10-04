import { describe, expect, it } from 'vitest'
import { fleetCsv, impactCsv, logCsv } from './exports'
import { toCsv } from './exportCsv'
import { makeFleet } from '@/mocks/fixtures/fleet'
import { makePlan } from '@/mocks/fixtures/plan'
import { EVENTS } from '@/mocks/fixtures/events'

describe('exports', () => {
  it('fleet: one row per unit, numbers stay numbers, the unit with no crew is flagged and has no service date', () => {
    const units = makeFleet(), f = fleetCsv(units, makePlan(units), 29)
    expect(f.rows).toHaveLength(100); expect(f.filename).toBe('pipeguard_fleet_2026-11-03.csv')
    expect(f.rows.every((r) => r.length === f.columns.length)).toBe(true)
    const eds14 = f.rows.find((r) => r[0] === 'EDS-14')!
    expect(eds14[f.columns.indexOf('Needs a manager decision')]).toBe(true); expect(eds14[f.columns.indexOf('Service date')]).toBe(''); expect(eds14[f.columns.indexOf('Plan approval')]).toBe('')
    expect(typeof eds14[f.columns.indexOf('Days left (likely)')]).toBe('number')
    expect(f.rows.find((r) => r[0] === 'GPR-15')![2]).toBe('Failed')
  })
  it('log: oldest first, readable type names, and text starting with = is made safe in the file', () => {
    const l = logCsv([...EVENTS].reverse(), 29)
    expect(l.rows).toHaveLength(EVENTS.length); expect(l.rows[0][0]).toBe(1); expect(l.rows.every((r) => r.length === l.columns.length)).toBe(true)
    expect(l.rows.some((r) => r[3] === 'Plan changed')).toBe(true)
    expect(toCsv(l.columns, [[1, '2026-11-03', 'X', 'Alert', 'T', '=1+1', 'info']])).toContain("'=1+1")
  })
  it('impact: one row per policy with the assumptions repeated so the file stands alone', () => {
    const sim = { policies: [{ policy: 'pipeguard', breakdowns: 3, planned_services: 40, wasted_services: 2, crew_days: 50, total_cost: 4_520_000.4 }] } as never
    const i = impactCsv(sim, { crews_per_station: 2, cost_breakdown: 200000, cost_service: 20000 }, 29)
    expect(i.rows).toEqual([['PipeGuard', 3, 40, 2, 50, 4520000, 2, 200000, 20000]])
  })
})
