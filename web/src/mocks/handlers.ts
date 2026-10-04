import { http, HttpResponse, delay, type JsonBodyType } from 'msw'
import type { ClockState, EventMsg, Fault, FleetUnit, Settings, SimulateRequest } from '@/lib/types'
import { displayStatus } from '@/lib/status'
import { formatSimDate, isoSimDate } from '@/lib/simCalendar'
import { makeFleet, MOCK_SIM_DAY } from './fixtures/fleet'
import { makeDetail } from './fixtures/detail'
import { makePlan, type Approvals, type Decisions } from './fixtures/plan'
import { CALL_CHECKS, CALLS, EVENTS, LIVE_EVENTS } from './fixtures/events'
import { TECHNICIANS } from './fixtures/technicians'
import { simulate } from './fixtures/simulate'
import { makeTrend } from './fixtures/trend'

// REST handlers only. The SSE streams live in sse-handlers.ts (browser only).
// In-memory mock backend. Mutating endpoints (Test mode faults, clock, reset) change this state so
// the dashboard reacts the way it will against the real API. Resets on page reload.
type Db = { units: FleetUnit[]; events: EventMsg[]; faults: Fault[]; clock: ClockState; nextEventId: number; nextFaultId: number; settings: Settings; demoCalled: boolean; approvals: Approvals; decisions: Decisions }
// The demo starts BEFORE the technician call: EDS-07 is at risk and planned for Thursday (day 30), and its call story is not
// in the log yet. "Simulate call" plays that story live and moves the plan block to Friday (day 32), like the real recorded call.
const DEMO_UNIT = 'EDS-07'
const DEMO_STORY = new Set(['call_requested', 'call_answered', 'constraint_added', 'plan_changed', 'call_summary'])
const fresh = (): Db => ({
  units: makeFleet().map((u) => (u.unit_id === DEMO_UNIT ? { ...u, next_service_day: 30 } : u)),
  events: structuredClone(EVENTS).filter((e) => !(e.unit_id === DEMO_UNIT && DEMO_STORY.has(e.type))), faults: [], demoCalled: false, approvals: {}, decisions: {},
  clock: { status: 'paused', speed_seconds_per_day: 1, sim_day: MOCK_SIM_DAY },
  nextEventId: EVENTS.length + 1, nextFaultId: 1,
  settings: { crews_per_station: 2, cost_breakdown: 200000, cost_service: 20000, ring_timeout_secs: 30, call_backup_when_missed: true, require_manager_for_conflicts: true },
})
// The real API needs X-Admin-Token on admin and test-mode calls. The mock accepts any non-empty token.
const needsToken = (request: Request) => (request.headers.get('x-admin-token') ?? '') === '' ? HttpResponse.json({ detail: 'invalid admin token' }, { status: 401 }) : null
let db = fresh()

// Subscribers are the open SSE connections (browser only). Events are produced here, not per connection, so an
// outage does not stop the world: events keep happening and a reconnecting client catches up (like the real API).
const subscribers = new Set<(ev: EventMsg) => void>()
export const onEvent = (fn: (ev: EventMsg) => void) => { subscribers.add(fn); return () => { subscribers.delete(fn) } }
export const eventsSince = (id: number) => db.events.filter((e) => e.event_id > id)
export const pushEvent = (e: Omit<EventMsg, 'event_id'>) => { const ev = { ...e, event_id: db.nextEventId++ }; db.events.push(ev); subscribers.forEach((fn) => fn(ev)); return ev }

// Browser-only live feed: every few seconds a scripted event happens and, for status changes, the unit really changes,
// so tiles, the KPI and the Stations list move on their own while you watch.
const LIVE_STATUS: Record<string, FleetUnit['risk_status']> = { Watch: 'watch', 'At risk': 'at_risk' }
let feedStarted = false
export function startLiveFeed(everyMs = 4000) {
  if (feedStarted) return
  feedStarted = true
  let i = 0
  setInterval(() => {
    const e = LIVE_EVENTS[i++ % LIVE_EVENTS.length]
    const u = db.units.find((x) => x.unit_id === e.unit_id)
    const next = LIVE_STATUS[e.title]
    if (u && e.type === 'status_change' && next) {
      u.risk_status = next; u.display_status = displayStatus(next, u.sensor_issue)
      // a unit that turns watch or red really is closer to failure, so its numbers move with its colour (keeps the saving sensible)
      u.p_fail = Math.max(u.p_fail, next === 'at_risk' ? 0.55 : 0.25)
      u.rul = next === 'at_risk' ? { low: 10, likely: 24, high: 40 } : { low: 28, likely: 52, high: 90 }
    }
    pushEvent(e)
  }, everyMs)
}
// Test hook (window.__pgMock in the browser): make the stream endpoint fail, to prove the dashboard recovers.
const plan = () => makePlan(db.units, db.settings.crews_per_station, db.approvals, db.decisions)
export const streamControl = { down: false }
const json = <T extends JsonBodyType>(body: T, init?: ResponseInit) => HttpResponse.json(body, init)

export const handlers = [
  http.get('/api/health', () => json({ status: 'ok', service: 'mock' })),
  http.get('/api/fleet', () => json({ sim_day: db.clock.sim_day, clock: db.clock, units: db.units })),
  // NOT IN CONTRACT YET (see lib/types.ts TrendPoint, ModelMetrics)
  http.get('/api/fleet/trend', () => json(makeTrend(db.clock.sim_day, db.units.filter((u) => u.display_status === 'at_risk' || u.failed).length))),
  // NOT IN CONTRACT YET (see docs/delegation/MESSAGE_TO_EBUBE.md item 7). Placeholder numbers, not real results.
  http.get('/api/feedback/stats', () => json({ total: 12, confirmed: 10 })),
  http.get('/api/model', () => json({ rmse: 14.8, baseline_rmse: 27.5, model_version: 'v1' })),
  http.get('/api/units/:id', ({ params }) => {
    const u = db.units.find((x) => x.unit_id === params.id)
    return u ? json(makeDetail(u, db.events, db.demoCalled ? CALLS : CALLS.filter((c) => c.unit_id !== DEMO_UNIT))) : json({ detail: 'unknown unit' }, { status: 404 })
  }),
  http.get('/api/plan', () => json(plan())),
  // NOT IN CONTRACT YET: manager approval of plan changes (see docs/delegation/MESSAGE_TO_EBUBE.md)
  http.post('/api/plan/:id/approve', ({ params }) => {
    const item = plan().find((p) => String(p.id) === params.id)
    if (!item) return json({ detail: 'unknown plan item' }, { status: 404 })
    if (item.approval !== 'approved') {
      db.approvals[item.unit_id] = { day: item.planned_day, status: 'approved' }
      pushEvent({ type: 'plan_approved', sim_day: db.clock.sim_day, unit_id: item.unit_id, title: 'Plan approved', detail: `A manager approved ${item.unit_id} for ${formatSimDate(item.planned_day)}. It is now a work order.`, severity: 'info', payload: {} })
    }
    return json({ ...item, approval: 'approved' })
  }),
  // NOT IN CONTRACT YET: a manager resolves a unit that no crew could take (see docs/delegation/MESSAGE_TO_EBUBE.md).
  // Body `{choice: 'overtime' | 'defer'}`. Idempotent: choosing the same thing twice changes nothing and writes one event.
  http.post('/api/plan/:id/decide', async ({ params, request }) => {
    const item = plan().find((p) => String(p.id) === params.id)
    if (!item) return json({ detail: 'unknown plan item' }, { status: 404 })
    const choice = ((await request.json().catch(() => ({}))) as { choice?: string }).choice
    if (choice !== 'overtime' && choice !== 'defer') return json({ detail: 'choice must be overtime or defer' }, { status: 422 })
    if (item.state !== 'needs_manager_decision' && !item.decision) return json({ detail: 'this item does not need a decision' }, { status: 409 })
    const next = choice === 'defer' ? 'deferred' : 'overtime'
    if (item.decision !== next) {
      const day = db.clock.sim_day + 1
      db.decisions[item.unit_id] = { choice: next, day }
      const u = db.units.find((x) => x.unit_id === item.unit_id)
      if (u) { u.needs_manager_decision = false; if (next === 'overtime') u.next_service_day = day }
      pushEvent({ type: 'manager_decision', sim_day: db.clock.sim_day, unit_id: item.unit_id, severity: 'info', payload: { choice: next },
        title: next === 'overtime' ? 'Overtime crew approved' : 'Risk accepted for now',
        detail: next === 'overtime' ? `A manager approved an overtime crew for ${item.unit_id} on ${formatSimDate(day)}. It is now a work order.` : `A manager accepted the risk on ${item.unit_id} for now. No crew is booked.` })
    }
    return json(plan().find((p) => p.unit_id === item.unit_id))
  }),
  http.post('/api/plan/approve-all', () => {
    const waiting = plan().filter((p) => p.approval === 'proposed' && p.state !== 'needs_manager_decision')
    for (const it of waiting) {
      db.approvals[it.unit_id] = { day: it.planned_day, status: 'approved' }
      pushEvent({ type: 'plan_approved', sim_day: db.clock.sim_day, unit_id: it.unit_id, title: 'Plan approved', detail: `A manager approved ${it.unit_id} for ${formatSimDate(it.planned_day)}. It is now a work order.`, severity: 'info', payload: {} })
    }
    return json({ approved: waiting.length })
  }),
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
    const rows = plan().filter((p) => p.approval !== 'proposed').map((p) => [isoSimDate(p.planned_day), p.station_code, p.unit_id, p.technician_name, p.expected_saving, `"${p.reason}"`].join(','))
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
    const denied = needsToken(request); if (denied) return denied
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
  http.delete('/api/testmode/faults/:id', ({ params, request }) => {
    const denied = needsToken(request); if (denied) return denied
    const f = db.faults.find((x) => String(x.id) === params.id)
    if (!f) return json({ detail: 'unknown fault' }, { status: 404 })
    f.end_day = db.clock.sim_day
    const u = db.units.find((x) => x.unit_id === f.unit_id)!
    if (!db.faults.some((x) => x.unit_id === f.unit_id && x.end_day === null)) { u.sensor_issue = false; u.confidence = 'normal'; u.display_status = displayStatus(u.risk_status, false) }
    return json(f)
  }),
  http.get('/api/testmode/faults', ({ request }) => needsToken(request) ?? json(db.faults)),
  http.get('/api/settings', () => json(db.settings)),
  http.put('/api/settings', async ({ request }) => { db.settings = { ...db.settings, ...((await request.json()) as Partial<Settings>) }; return json(db.settings) }),
  http.post('/api/admin/reset', ({ request }) => { const denied = needsToken(request); if (denied) return denied; db = fresh(); return json({ ok: true }) }),
  http.post('/api/admin/simulate-call', ({ request }) => {
    const denied = needsToken(request); if (denied) return denied
    const base = db.clock.sim_day
    db.demoCalled = true
    // The real call takes about 40 s; the mock plays the same story in 6 s.
    const step = (ms: number, e: Omit<EventMsg, 'event_id'>, effect?: () => void) => setTimeout(() => { effect?.(); pushEvent(e) }, ms)
    const ev = (type: EventMsg['type'], title: string, detail: string): Omit<EventMsg, 'event_id'> => ({ type, sim_day: base, unit_id: DEMO_UNIT, title, detail, severity: 'info', payload: {} })
    step(0, { ...ev('call_requested', 'Calling technician', 'Calling Aiden Walker (Edson, day shift) about EDS-07.'), payload: { checks: CALL_CHECKS } })
    step(1500, ev('call_answered', 'Call answered', 'Aiden Walker answered and is discussing EDS-07.'))
    step(3000, ev('constraint_added', 'Availability recorded', `Technician cannot service EDS-07 before Friday (${formatSimDate(32)}).`))
    step(4500, ev('plan_changed', 'Plan changed', `EDS-07 moved to ${formatSimDate(32)}. Waiting for the manager to approve it.`), () => { const u = db.units.find((x) => x.unit_id === DEMO_UNIT); if (u) u.next_service_day = 32; db.approvals[DEMO_UNIT] = { day: 32, status: 'proposed' } })
    step(6000, ev('call_summary', 'Call summary', 'Technician can service EDS-07 from Friday. Plan updated.'))
    return json({ ok: true })
  }),
  http.post('/api/admin/tune', ({ request }) => needsToken(request) ?? json({ threshold: 0.4, horizon_days: 14 })),

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
