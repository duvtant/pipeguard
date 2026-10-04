import type { RingEvent } from '@/lib/types'
import { CALLS } from './events'
import { TECHNICIANS } from './technicians'

// A ring for the demo unit, expiring `seconds` from now. Phase 3 replaces this with the field SSE stream.
export function makeRing(fieldPageId: string, seconds = 30): RingEvent {
  const t = TECHNICIANS.find((x) => x.field_page_id === fieldPageId) ?? TECHNICIANS[0]
  return {
    type: 'ring', call_request_id: 41, unit_id: 'EDS-07', station_name: 'Edson',
    technician_id: t.id, technician_name: t.name, language: t.language, rul_low: 14, rul_high: 35,
    reason: 'High-pressure compressor outlet temperature has risen for 6 days.',
    expires_at: new Date(Date.now() + seconds * 1000).toISOString(),
  }
}
export const MOCK_TRANSCRIPT = CALLS[0].transcript
