import { useCallback, useEffect, useRef, useState } from 'react'
import type { RingEvent } from './types'

/** The technician page's own event stream: `GET /api/field/{id}/stream`. The server replays an active ring when the page connects
 *  late, so opening the page after the phone started ringing still shows the ring with its remaining time. The browser reconnects
 *  by itself after a network drop, and the page shows its current state, never a stale ring. */
export function useFieldRing(fieldPageId: string, enabled: boolean) {
  const [ring, setRing] = useState<RingEvent | null>(null)
  const [connected, setConnected] = useState(false)
  const handled = useRef(new Set<number>()) // rings already answered, declined or missed: a replay must not ring again
  const busy = useRef(false)                // while a call is in progress, a second ring is ignored (the server guards too)

  useEffect(() => {
    if (!enabled || !fieldPageId) return
    const es = new EventSource(`/api/field/${fieldPageId}/stream`)
    es.onopen = () => setConnected(true)
    es.onerror = () => setConnected(false)
    // The server may send the ring as an unnamed frame or as a named `event: ring` frame (Ebube's mock API names it). Listen for both.
    const onFrame = (m: MessageEvent) => {
      try {
        const e = JSON.parse(m.data) as RingEvent
        if (e.type !== 'ring' || handled.current.has(e.call_request_id) || busy.current) return
        if (Date.parse(e.expires_at) <= Date.now()) return // an old ring that already expired
        setRing((cur) => (cur && cur.call_request_id === e.call_request_id ? cur : e))
      } catch { /* ignore a malformed frame */ }
    }
    es.onmessage = onFrame
    es.addEventListener('ring', onFrame as EventListener)
    return () => es.close()
  }, [fieldPageId, enabled])

  /** Mark a ring as dealt with (answered, declined or expired). `inCall` blocks new rings until the call ends. */
  const finish = useCallback((callRequestId: number) => { handled.current.add(callRequestId); setRing(null) }, [])
  const setBusy = useCallback((b: boolean) => { busy.current = b }, [])
  return { ring, connected, finish, setBusy }
}
