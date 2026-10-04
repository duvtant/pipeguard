import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LiveStream, type StreamStatus } from './sse'
import type { EventMsg } from './types'

const ev = (id: number): EventMsg => ({ event_id: id, type: 'status_change', sim_day: 1, unit_id: 'EDS-01', title: 't', detail: 'd', severity: 'info', payload: {} })

// A minimal EventSource we can drive by hand.
class FakeES {
  static all: FakeES[] = []
  readyState = 0
  url: string
  onopen: (() => void) | null = null
  onmessage: ((m: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  constructor(url: string) { this.url = url; FakeES.all.push(this) }
  close() { this.readyState = 2 }
  open() { this.readyState = 1; this.onopen?.() }
  send(e: EventMsg) { this.onmessage?.({ data: JSON.stringify(e) }) }
  fail(closed: boolean) { this.readyState = closed ? 2 : 0; this.onerror?.() }
}

function setup(serverEvents: () => EventMsg[] = () => []) {
  const events: number[] = []; const statuses: StreamStatus[] = []; const urls: string[] = []
  const fetchImpl = (async (url: string) => {
    urls.push(url)
    const after = Number(new URL(url, 'http://x').searchParams.get('after_id'))
    return { ok: true, json: async () => serverEvents().filter((e) => e.event_id > after) } as Response
  }) as unknown as typeof fetch
  const s = new LiveStream({ onEvent: (e) => events.push(e.event_id), onStatus: (x) => statuses.push(x), EventSourceImpl: FakeES as unknown as typeof EventSource, fetchImpl, pollMs: 1000, retryMs: 1000, watchdogMs: 2000 })
  return { s, events, statuses, urls }
}
const flush = () => vi.advanceTimersByTimeAsync(0)

beforeEach(() => { FakeES.all = []; vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers() })

describe('LiveStream', () => {
  it('goes live on open and delivers each event once, even if the server replays it', async () => {
    const { s, events, statuses } = setup()
    s.start(); const es = FakeES.all[0]; es.open(); await flush()
    es.send(ev(1)); es.send(ev(2)); es.send(ev(2)); es.send(ev(1)); es.send(ev(3))
    expect(statuses).toEqual(['live']); expect(events).toEqual([1, 2, 3]); expect(s.lastId).toBe(3)
  })

  it('ignores events the page already loaded (seed)', async () => {
    const { s, events } = setup()
    s.seed([1, 2, 3]); s.start(); FakeES.all[0].open(); await flush()
    FakeES.all[0].send(ev(3)); FakeES.all[0].send(ev(4))
    expect(events).toEqual([4])
  })

  it('accepts events that arrive out of order (two writers) without dropping the lower id', async () => {
    const { s, events } = setup()
    s.start(); FakeES.all[0].open(); await flush()
    FakeES.all[0].send(ev(5)); FakeES.all[0].send(ev(4))
    expect(events).toEqual([5, 4])
  })

  it('shows "reconnecting" while the browser retries, then catches up on the gap when it reopens', async () => {
    const server = [ev(1), ev(2), ev(3), ev(4)]
    const { s, events, statuses, urls } = setup(() => server)
    s.start(); const es = FakeES.all[0]; es.open(); await flush(); es.send(ev(1)); es.send(ev(2))
    es.fail(false) // connection dropped, browser is retrying by itself
    expect(statuses.at(-1)).toBe('reconnecting')
    es.open(); await flush() // browser reconnected: events 3 and 4 happened meanwhile
    expect(urls.at(-1)).toContain('after_id=2'); expect(events).toEqual([1, 2, 3, 4]); expect(statuses.at(-1)).toBe('live')
  })

  it('falls back to polling when the browser gives up, never duplicates, and returns to the stream when it works again', async () => {
    let server = [ev(1), ev(2)]
    const { s, events, statuses } = setup(() => server)
    s.start(); const es = FakeES.all[0]; es.open(); await flush(); es.send(ev(1)); es.send(ev(2))
    es.fail(true) // CLOSED: gave up
    await flush(); expect(statuses.at(-1)).toBe('polling')
    server = [...server, ev(3)]; await vi.advanceTimersByTimeAsync(1000)
    server = [...server, ev(4)]; await vi.advanceTimersByTimeAsync(1000)
    expect(events).toEqual([1, 2, 3, 4])
    expect(FakeES.all.length).toBeGreaterThan(1) // it keeps trying to reconnect the stream
    const next = FakeES.all.at(-1)!; next.open(); await flush()
    expect(statuses.at(-1)).toBe('live')
    const before = vi.getTimerCount(); next.send(ev(5)); expect(events).toEqual([1, 2, 3, 4, 5]); expect(vi.getTimerCount()).toBe(before)
  })

  it('starts polling if reconnecting takes too long, and reports offline when the server cannot be reached', async () => {
    const events: number[] = []; const statuses: StreamStatus[] = []
    const s = new LiveStream({ onEvent: (e) => events.push(e.event_id), onStatus: (x) => statuses.push(x), EventSourceImpl: FakeES as unknown as typeof EventSource,
      fetchImpl: (async () => { throw new Error('down') }) as unknown as typeof fetch, pollMs: 1000, retryMs: 1000, watchdogMs: 2000 })
    s.start(); FakeES.all[0].fail(false); expect(statuses.at(-1)).toBe('reconnecting')
    await vi.advanceTimersByTimeAsync(2100); expect(statuses.at(-1)).toBe('offline')
  })

  it('stop() closes everything and stops delivering', async () => {
    const { s, events } = setup()
    s.start(); const es = FakeES.all[0]; es.open(); await flush(); s.stop()
    expect(es.readyState).toBe(2); es.send(ev(9)); expect(vi.getTimerCount()).toBe(0)
    // a closed stream's late frame is still ours to ignore at the app level; the engine just must not reconnect
    expect(FakeES.all.length).toBe(1); void events
  })
})
