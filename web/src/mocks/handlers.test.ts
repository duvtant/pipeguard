import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest'
import { setupServer } from 'msw/node'
import { handlers } from './handlers'
import type { Fault, FleetResponse, SimulateResponse } from '@/lib/types'

// REST handlers only: MSW cannot intercept EventSource in Node, so the SSE streams are exercised in the browser (`pnpm dev:mock`).
const server = setupServer(...handlers)
beforeAll(() => server.listen({ onUnhandledFrame: 'error' }))
afterAll(() => server.close())
const post = (url: string, body?: unknown) => fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body ?? {}) })
const fleet = async () => (await (await fetch('/api/fleet')).json()) as FleetResponse
beforeEach(async () => { await post('/api/admin/reset') })

describe('mock API', () => {
  it('serves the fleet, a unit detail and a 404 for an unknown unit', async () => {
    const f = await fleet()
    expect(f.units).toHaveLength(100)
    expect((await (await fetch('/api/units/EDS-07')).json()).history).toHaveLength(30)
    expect((await fetch('/api/units/NOPE-00')).status).toBe(404)
  })

  it('Kill sensor: unit turns grey + wrench with low confidence, is idempotent, and ends cleanly', async () => {
    const body = { unit_id: 'EDS-03', sensor: 's4', type: 'dead' }
    const f1 = (await (await post('/api/testmode/faults', body)).json()) as Fault
    const again = (await (await post('/api/testmode/faults', body)).json()) as Fault
    expect(again.id).toBe(f1.id) // same toggle twice: one open fault
    let u = (await fleet()).units.find((x) => x.unit_id === 'EDS-03')!
    expect(u).toMatchObject({ sensor_issue: true, confidence: 'low' })
    expect(['sensor_issue', 'at_risk']).toContain(u.display_status)
    await fetch(`/api/testmode/faults/${f1.id}`, { method: 'DELETE' })
    u = (await fleet()).units.find((x) => x.unit_id === 'EDS-03')!
    expect(u).toMatchObject({ sensor_issue: false, confidence: 'normal' })
  })

  it('records the sensor fault in the decision log with an increasing event id', async () => {
    const before = (await (await fetch('/api/events')).json()).length
    await post('/api/testmode/faults', { unit_id: 'HIN-05', sensor: 's3', type: 'stuck' })
    const events = await (await fetch('/api/events')).json()
    expect(events.length).toBe(before + 1)
    expect(events.at(-1).type).toBe('sensor_issue')
    const after = await (await fetch(`/api/events?after_id=${events.at(-2).event_id}`)).json()
    expect(after).toHaveLength(1)
  })

  it('rejects a fault for an unknown unit with 422', async () => {
    expect((await post('/api/testmode/faults', { unit_id: 'ZZZ-99', sensor: 's3', type: 'dead' })).status).toBe(422)
  })

  it('reset restores the starting state', async () => {
    await post('/api/testmode/faults', { unit_id: 'EDS-03', sensor: 's4', type: 'dead' })
    await post('/api/clock', { action: 'advance', days: 5 })
    await post('/api/admin/reset')
    const f = await fleet()
    expect(f.units.find((x) => x.unit_id === 'EDS-03')!.sensor_issue).toBe(false)
    expect(f.sim_day).toBe(29)
  })

  it('simulate responds to slider changes', async () => {
    const run = async (crews: number) => (await (await post('/api/simulate', { crews_per_station: crews, cost_breakdown: 200000, cost_service: 20000, threshold: null, horizon_days: null })).json()) as SimulateResponse
    expect((await run(1)).policies[2].breakdowns).toBeGreaterThanOrEqual((await run(4)).policies[2].breakdowns)
  })

  it('answers a field call with all-string dynamic variables and the technician language', async () => {
    const r = await (await post('/api/field/t-7d2x9/answer')).json()
    expect(r.language).toBe('fr')
    expect(Object.values(r.dynamic_variables).every((v) => typeof v === 'string')).toBe(true)
    expect(Object.keys(r.dynamic_variables)).toEqual(expect.arrayContaining(['technician_id', 'unit_id', 'rul_low', 'rul_high', 'reason', 'proposed_day', 'call_request_id', 'sim_today']))
  })

  it('exports work orders as CSV', async () => {
    const res = await fetch('/api/work-orders.csv')
    expect(res.headers.get('content-type')).toContain('text/csv')
    expect((await res.text()).split('\n')[0]).toBe('date,station,unit,technician,expected_saving,reason')
  })
})
