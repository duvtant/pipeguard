import { http, HttpResponse, delay, type JsonBodyType } from 'msw'
import type { ClockState, EventMsg, Fault, FleetUnit, SimulateRequest } from '@/lib/types'
import { displayStatus } from '@/lib/status'
import { formatSimDate, isoSimDate } from '@/lib/simCalendar'
import { makeFleet, MOCK_SIM_DAY } from './fixtures/fleet'
import { makeDetail } from './fixtures/detail'
import { makePlan } from './fixtures/plan'
import { CALLS, EVENTS } from './fixtures/events'
import { TECHNICIANS } from './fixtures/technicians'
import { simulate } from './fixtures/simulate'

// REST handlers only. The SSE streams live in sse-handlers.ts (browser only).
// In-memory mock backend. Mutating endpoints (Test mode faults, clock, reset) change this state so
// the dashboard reacts the way it will against the real API. Resets on page reload.
type Db = { units: FleetUnit[]; events: EventMsg[]; faults: Fault[]; clock: ClockState; nextEventId: number; nextFaultId: number }
const fresh = (): Db => ({
  units: makeFleet(), events: structuredClone(EVENTS), faults: [],
  clock: { status: 'paused', speed_seconds_per_day: 1, sim_day: MOCK_SIM_DAY },
  nextEventId: EVENTS.length + 1, nextFaultId: 1,
})
let db = fresh()

export const pushEvent = (e: Omit<EventMsg, 'event_id'>) => { const ev = { ...e, event_id: db.nextEventId++ }; db.events.push(ev); return ev }
const json = <T extends JsonBodyType>(body: T, init?: ResponseInit) => HttpResponse.json(body, init)

export const handlers = [
  http.get('/api/health', () => json({ status: 'ok', service: 'mock' })),
  http.get('/api/fleet', () => json({ sim_day: db.clock.sim_day, clock: db.clock, units: db.units })),
  http.get('/api/units/:id', ({ params }) => {
    const u = db.units.find((x) => x.unit_id === params.id)
    return u ? json(makeDetail(u)) : json({ detail: 'unknown unit' }, { status: 404 })
  }),
  http.get('/api/plan', () => json(makePlan(db.units))),
  http.get('/api/events', ({ request }) => {
    const after = Number(new URL(request.url).searchParams.get('after_id') ?? 0)
    return json(db.events.filter((e) => e.event_id > after))
  }),
  http.get('/api/technicians', () => json(TECHNICIANS)),
  http.get('/api/calls/:id', ({ params }) => {
    const c = CALLS.find((x) => String(x.id) === params.id)
    return c ? json(c) : json({ detail: 'unknown call' }, { status: 404 })
  }),
  http.get('/api/work-orders.csv', () => {
    const rows = makePlan(db.units).map((p) => [isoSimDate(p.planned_day), p.station_code, p.unit_id, p.technician_name, p.expected_saving, `"${p.reason}"`].join(','))
    const csv = ['date,station,unit,technician,expected_saving,reason', ...rows].join('\n')
    return new HttpResponse(csv, { headers: { 'Content-Type': 'text/csv', 'Content-Disposition': `attachment; filename="work_orders_day_${db.clock.sim_day}.csv"` } })
  }),

  // Impact tab: a little latency so debounce/cancel logic is actually exercised.
  http.post('/api/simulate', async ({ request }) => {
    await delay(150)
    return json(simulate((await request.json()) as SimulateRequest))
  }),
  http.get('/api/impact', () => json(simulate({ crews_per_station: 2, cost_breakdown: 200000, cost_service: 20000, threshold: null, horizon_days: null }))),

  http.post('/api/clock', async ({ request }) => {
    const body = (await request.json()) as { action: 'play' | 'pause' | 'speed' | 'reset' | 'advance'; speed_seconds_per_day?: number; days?: number }
    if (body.action === 'play') db.clock.status = 'running'
    if (body.action === 'pause') db.clock.status = 'paused'
    if (body.action === 'speed' && body.speed_seconds_per_day) db.clock.speed_seconds_per_day = body.speed_seconds_per_day
    if (body.action === 'advance') db.clock.sim_day += body.days ?? 1
    if (body.action === 'reset') db = fresh()
    return json(db.clock)
  }),

  // Test mode (needs X-Admin-Token on the real API)
  http.post('/api/testmode/faults', async ({ request }) => {
    const b = (await request.json()) as { unit_id: string; sensor: string; type: Fault['type'] }
    const u = db.units.find((x) => x.unit_id === b.unit_id)
    if (!u) return json({ detail: 'unknown unit' }, { status: 422 })
    if (db.faults.some((f) => f.unit_id === b.unit_id && f.sensor === b.sensor && f.end_day === null)) return json(db.faults.find((f) => f.unit_id === b.unit_id && f.sensor === b.sensor)!)
    const fault: Fault = { id: db.nextFaultId++, ...b, start_day: db.clock.sim_day, end_day: null, source: 'toggle' }
    db.faults.push(fault)
    u.sensor_issue = true; u.confidence = 'low'; u.display_status = displayStatus(u.risk_status, true)
    pushEvent({ type: 'sensor_issue', sim_day: db.clock.sim_day, unit_id: u.unit_id, title: 'Sensor issue',
      detail: `${u.unit_id}: sensor offline. Prediction still running, lower confidence. Instrument check requested. No crew call.`, severity: 'warning', payload: {} })
    return json(fault)
  }),
  http.delete('/api/testmode/faults/:id', ({ params }) => {
    const f = db.faults.find((x) => String(x.id) === params.id)
    if (!f) return json({ detail: 'unknown fault' }, { status: 404 })
    f.end_day = db.clock.sim_day
    const u = db.units.find((x) => x.unit_id === f.unit_id)!
    if (!db.faults.some((x) => x.unit_id === f.unit_id && x.end_day === null)) { u.sensor_issue = false; u.confidence = 'normal'; u.display_status = displayStatus(u.risk_status, false) }
    return json(f)
  }),
  http.get('/api/testmode/faults', () => json(db.faults)),
  http.post('/api/admin/reset', () => { db = fresh(); return json({ ok: true }) }),
  http.post('/api/admin/simulate-call', () => {
    const base = db.clock.sim_day
    pushEvent({ type: 'call_requested', sim_day: base, unit_id: 'EDS-07', title: 'Calling technician', detail: 'Calling Aiden Walker (Edson) about EDS-07.', severity: 'info', payload: {} })
    pushEvent({ type: 'plan_changed', sim_day: base, unit_id: 'EDS-07', title: 'Plan changed', detail: `EDS-07 moved to ${formatSimDate(32)}.`, severity: 'info', payload: {} })
    return json({ ok: true })
  }),
  http.post('/api/admin/tune', () => json({ threshold: 0.4, horizon_days: 14 })),

  // Technician phone page
  http.post('/api/field/:fieldPageId/answer', ({ params }) => {
    const t = TECHNICIANS.find((x) => x.field_page_id === params.fieldPageId) ?? TECHNICIANS[0]
    return json({
      signed_url: 'wss://mock.invalid/not-a-real-signed-url', language: t.language,
      dynamic_variables: { technician_id: String(t.id), technician_name: t.name, unit_id: 'EDS-07', station_name: 'Edson', rul_low: '14', rul_high: '35',
        reason: 'High-pressure compressor outlet temperature has risen for 6 days', proposed_day: 'Thursday', call_request_id: '41', sim_today: formatSimDate(MOCK_SIM_DAY) },
    })
  }),
  http.post('/api/field/:fieldPageId/decline', () => json({ ok: true })),
  http.post('/api/field/:fieldPageId/feedback', () => json({ ok: true })),
  http.post('/api/field/:fieldPageId/conversation', () => json({ ok: true })),
]
