import type { EventMsg } from './types'

// ONE shared event stream for the whole app (never one per component). Plain TypeScript, no React, so it can be tested.
//   - de-duplicates by event_id (the server replays a few old events on reconnect, and two writers can commit out of order)
//   - the browser's EventSource reconnects by itself and sends Last-Event-ID; if it gives up we retry, and after any gap
//     we catch up through GET /api/events?after_id= so nothing is missed
//   - if the stream cannot connect, falls back to polling /api/events?after_id= every few seconds
export type StreamStatus = 'connecting' | 'live' | 'reconnecting' | 'polling' | 'offline'

export interface LiveStreamOptions {
  onEvent: (e: EventMsg) => void
  onStatus: (s: StreamStatus) => void
  url?: string
  eventsUrl?: string
  pollMs?: number
  retryMs?: number
  /** How long a connection may stay in "reconnecting" before polling takes over. */
  watchdogMs?: number
  EventSourceImpl?: typeof EventSource
  fetchImpl?: typeof fetch
}

export class LiveStream {
  private es: EventSource | null = null
  private seen = new Set<number>()
  private maxId = 0
  private status: StreamStatus = 'connecting'
  private hadGap = false
  private poll: ReturnType<typeof setInterval> | null = null
  private retry: ReturnType<typeof setTimeout> | null = null
  private watchdog: ReturnType<typeof setTimeout> | null = null
  private stopped = true
  private o: Required<Omit<LiveStreamOptions, 'onEvent' | 'onStatus'>> & Pick<LiveStreamOptions, 'onEvent' | 'onStatus'>

  constructor(opts: LiveStreamOptions) {
    this.o = {
      url: '/api/stream', eventsUrl: '/api/events', pollMs: 3000, retryMs: 3000, watchdogMs: 5000,
      EventSourceImpl: typeof EventSource === 'undefined' ? (undefined as never) : EventSource,
      fetchImpl: (...a) => fetch(...a), ...opts,
    }
  }

  get lastId() { return this.maxId }

  /** Tell the stream about events the app already has (the first page load), so they are never delivered twice. */
  seed(ids: number[]) { for (const id of ids) { this.seen.add(id); this.maxId = Math.max(this.maxId, id) } }

  start() { this.stopped = false; this.connect() }

  stop() {
    this.stopped = true
    this.es?.close(); this.es = null
    this.stopPolling()
    if (this.retry) clearTimeout(this.retry)
    if (this.watchdog) clearTimeout(this.watchdog)
    this.retry = this.watchdog = null
  }

  private set(s: StreamStatus) { if (s !== this.status) { this.status = s; this.o.onStatus(s) } }

  private deliver(ev: EventMsg) {
    if (this.seen.has(ev.event_id)) return
    this.seen.add(ev.event_id)
    this.maxId = Math.max(this.maxId, ev.event_id)
    this.o.onEvent(ev)
  }

  private connect() {
    if (this.stopped) return
    const es = new this.o.EventSourceImpl(this.o.url)
    this.es = es
    es.onopen = async () => {
      if (this.watchdog) { clearTimeout(this.watchdog); this.watchdog = null }
      this.stopPolling()
      if (this.hadGap) await this.catchUp() // fill the gap before declaring ourselves live again
      this.hadGap = false
      this.set('live')
    }
    es.onmessage = (m) => { try { this.deliver(JSON.parse(m.data) as EventMsg) } catch { /* ignore a malformed frame */ } }
    es.onerror = () => {
      this.hadGap = true
      if (es.readyState === 2 /* CLOSED: the browser gave up */) {
        es.close(); if (this.es === es) this.es = null
        this.startPolling()
        this.retry = setTimeout(() => this.connect(), this.o.retryMs)
        return
      }
      // CONNECTING: the browser is retrying by itself. If it takes too long, start polling in the meantime.
      this.set('reconnecting')
      if (!this.watchdog) this.watchdog = setTimeout(() => { this.watchdog = null; if (this.status !== 'live') this.startPolling() }, this.o.watchdogMs)
    }
  }

  private async fetchAfter(): Promise<boolean> {
    try {
      const res = await this.o.fetchImpl(`${this.o.eventsUrl}?after_id=${this.maxId}`)
      if (!res.ok) return false
      for (const ev of (await res.json()) as EventMsg[]) this.deliver(ev)
      return true
    } catch { return false }
  }

  private async catchUp() { await this.fetchAfter() }

  private startPolling() {
    if (this.stopped || this.poll) { if (!this.stopped) this.set('polling'); return }
    this.set('polling')
    const tick = async () => { const ok = await this.fetchAfter(); if (!this.stopped && this.poll) this.set(ok ? 'polling' : 'offline') }
    void tick()
    this.poll = setInterval(tick, this.o.pollMs)
  }

  private stopPolling() { if (this.poll) { clearInterval(this.poll); this.poll = null } }
}
