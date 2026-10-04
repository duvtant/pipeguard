import { sse } from 'msw/sse'
import { TECHNICIANS } from './fixtures/technicians'
import { eventsSince, onEvent, startLiveFeed, streamControl } from './handlers'

type SseClient = { send: (m: { id?: string; data: unknown }) => void; close: () => void; error: () => void }
const open = new Set<SseClient>()

/** Test hooks, exposed as window.__pgMock in mock builds: drop the live stream, and later bring it back. */
export const mockControls = {
  dropStream() { streamControl.down = true; open.forEach((c) => c.error()); open.clear() },
  restoreStream() { streamControl.down = false },
}

// Server-Sent Event streams. Browser only: MSW cannot intercept EventSource in Node,
// so these are exercised with `pnpm dev:mock`, not in the vitest suite.
export const sseHandlers = [
  // Live event stream. Like the real API: honours Last-Event-ID by replaying from (last id - 20), so a client must de-duplicate.
  sse('/api/stream', ({ client, request }) => {
    if (streamControl.down) { client.error(); return }
    startLiveFeed()
    const last = Number(request.headers.get('last-event-id') ?? 0)
    if (last) for (const ev of eventsSince(Math.max(0, last - 20))) client.send({ id: String(ev.event_id), data: ev })
    const off = onEvent((ev) => client.send({ id: String(ev.event_id), data: ev }))
    open.add(client)
    request.signal.addEventListener('abort', () => { off(); open.delete(client) })
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
