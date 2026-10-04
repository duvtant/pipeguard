import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { setupServer } from 'msw/node'
import { handlers } from './handlers'
import type { Fault, FleetResponse, SimulateResponse } from '@/lib/types'

// REST handlers only: MSW cannot intercept EventSource in Node, so the SSE streams are exercised in the browser (`pnpm dev:mock`).
const server = setupServer(...handlers)
beforeAll(() => server.listen({ onUnhandledFrame: 'error' }))
afterAll(() => server.close())
const post = (url: string, body?: unknown) => fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Admin-Token': 'test-token' }, body: JSON.stringify(body ?? {}) })
const fleet = async () => (await (await fetch('/api/fleet')).json()) as FleetResponse
beforeEach(async () => { await post('/api/admin/reset') })

describe('mock API: plan approval (not in the contract yet)', () => {
  const plan = async () => (await (await fetch('/api/plan')).json()) as { id: number; unit_id: string; approval?: string; planned_day: number }[]
  it('starts fully approved, a simulated call leaves EDS-07 proposed, and approving releases it', async () => {
    expect((await plan()).every((p) => p.approval === 'approved' || p.approval === 'proposed')).toBe(true)
    expect((await plan()).find((p) => p.unit_id === 'EDS-07')!.approval).toBe('approved')
    vi.useFakeTimers(); await post('/api/admin/simulate-call'); await vi.advanceTimersByTimeAsync(7000); vi.useRealTimers()
    const eds = (await plan()).find((p) => p.unit_id === 'EDS-07')!
    expect(eds.approval).toBe('proposed'); expect(eds.planned_day).toBe(32)
    const csv = await (await fetch('/api/work-orders.csv')).text(); expect(csv).not.toContain('EDS-07') // proposed changes are not work orders yet
    expect((await post(`/api/plan/${eds.id}/approve`)).status).toBe(200)
    expect((await plan()).find((p) => p.unit_id === 'EDS-07')!.approval).toBe('approved')
    expect(await (await fetch('/api/work-orders.csv')).text()).toContain('EDS-07')
    const events = (await (await fetch('/api/events')).json()) as { type: string }[]; expect(events.filter((e) => e.type === 'plan_approved')).toHaveLength(1)
    expect((await post(`/api/plan/${eds.id}/approve`)).status).toBe(200) // approving twice is harmless
    expect(((await (await fetch('/api/events')).json()) as { type: string }[]).filter((e) => e.type === 'plan_approved')).toHaveLength(1)
  })
  it('404s for an unknown plan item and approve-all approves everything waiting', async () => {
    expect((await post('/api/plan/9999/approve')).status).toBe(404)
    expect((await (await post('/api/plan/approve-all')).json()).approved).toBe(0)
  })
})

describe('mock API: manager decision on a unit with no free crew (not in the contract yet)', () => {
  type Item = { id: number; unit_id: string; state: string; decision?: string; planned_day: number; approval?: string }
  const plan = async () => (await (await fetch('/api/plan')).json()) as Item[]
  const decide = (id: number, choice: string) => fetch(`/api/plan/${id}/decide`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ choice }) })
  const events = async () => (await (await fetch('/api/events')).json()) as { type: string; unit_id: string }[]
  it('EDS-14 starts as a decision; overtime books it and writes one event, even if chosen twice', async () => {
    const open = (await plan()).find((p) => p.unit_id === 'EDS-14')!
    expect(open.state).toBe('needs_manager_decision'); expect(open.decision).toBeUndefined()
    expect((await decide(open.id, 'overtime')).status).toBe(200)
    const booked = (await plan()).find((p) => p.unit_id === 'EDS-14')!
    expect(booked.state).toBe('planned'); expect(booked.decision).toBe('overtime'); expect(booked.approval).toBe('approved')
    expect((await fleet()).units.find((u: { unit_id: string }) => u.unit_id === 'EDS-14')!.needs_manager_decision).toBe(false)
    expect(await (await fetch('/api/work-orders.csv')).text()).toContain('EDS-14')
    await decide(booked.id, 'overtime')
    expect((await events()).filter((e) => e.type === 'manager_decision' && e.unit_id === 'EDS-14')).toHaveLength(1)
  })
  it('accepting the risk keeps it off the schedule and the CSV, and can be changed to overtime later', async () => {
    const open = (await plan()).find((p) => p.unit_id === 'EDS-14')!
    await decide(open.id, 'defer')
    const d = (await plan()).find((p) => p.unit_id === 'EDS-14')!
    expect(d.decision).toBe('deferred'); expect(d.state).toBe('needs_manager_decision')
    expect(await (await fetch('/api/work-orders.csv')).text()).not.toContain('EDS-14')
    await decide(d.id, 'overtime')
    expect((await plan()).find((p) => p.unit_id === 'EDS-14')!.decision).toBe('overtime')
  })
  it('rejects a bad choice, an unknown item, and an item that needs no decision', async () => {
    const all = await plan()
    expect((await decide(all.find((p) => p.unit_id === 'EDS-14')!.id, 'maybe')).status).toBe(422)
    expect((await decide(9999, 'overtime')).status).toBe(404)
    expect((await decide(all.find((p) => p.state === 'planned')!.id, 'overtime')).status).toBe(409)
  })
})

describe('mock API: technician track record (not in the contract yet)', () => {
  it('serves confirmed and total warning verdicts', async () => {
    const r = (await (await fetch('/api/feedback/stats')).json()) as { total: number; confirmed: number }
    expect(r.total).toBeGreaterThan(0); expect(r.confirmed).toBeLessThanOrEqual(r.total)
  })
})

describe('mock API', () => {
  it('rejects admin and test-mode calls without a token, like the real API', async () => {
    expect((await fetch('/api/admin/reset', { method: 'POST' })).status).toBe(401)
    expect((await fetch('/api/testmode/faults')).status).toBe(401)
    expect((await fetch('/api/settings')).status).toBe(200) // settings are for the manager, not admin-only
  })

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
    await fetch(`/api/testmode/faults/${f1.id}`, { method: 'DELETE', headers: { 'X-Admin-Token': 'test-token' } })
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
