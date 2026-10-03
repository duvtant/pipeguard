import { sse } from 'msw/sse'
import { LIVE_EVENTS } from './fixtures/events'
import { TECHNICIANS } from './fixtures/technicians'
import { pushEvent } from './handlers'

// Server-Sent Event streams. Browser only: MSW cannot intercept EventSource in Node,
// so these are exercised with `pnpm dev:mock`, not in the vitest suite.
export const sseHandlers = [
  // Live event stream: replays LIVE_EVENTS then repeats, with ever-increasing ids.
  sse('/api/stream', ({ client, request }) => {
    let i = 0
    const timer = setInterval(() => {
      const ev = pushEvent(LIVE_EVENTS[i++ % LIVE_EVENTS.length])
      client.send({ id: String(ev.event_id), data: ev })
    }, 4000)
    request.signal.addEventListener('abort', () => clearInterval(timer))
  }),
  // Ring a phone: a ring event 3 s after the technician's page connects.
  sse('/api/field/:fieldPageId/stream', ({ client, params, request }) => {
    const t = TECHNICIANS.find((x) => x.field_page_id === params.fieldPageId) ?? TECHNICIANS[0]
    const timer = setTimeout(() => {
      client.send({ data: { type: 'ring', call_request_id: 41, unit_id: 'EDS-07', station_name: 'Edson', technician_id: t.id, technician_name: t.name,
        language: t.language, rul_low: 14, rul_high: 35, reason: 'High-pressure compressor outlet temperature has risen for 6 days',
        expires_at: new Date(Date.now() + 30000).toISOString() } })
    }, 3000)
    request.signal.addEventListener('abort', () => clearTimeout(timer))
  }),
]
