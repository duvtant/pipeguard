import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useQueryClient, type QueryClient } from '@tanstack/react-query'
import { LiveStream, type StreamStatus } from './sse'
import { useToast } from '@/components/ui/Toast'
import type { EventMsg, EventType } from './types'

export type BannerState = 'none' | 'down' | 'offline' | 'recovered'
interface Live { status: StreamStatus; banner: BannerState }
const LiveContext = createContext<Live>({ status: 'connecting', banner: 'none' })
export const useLive = () => useContext(LiveContext)

/** Polling interval for data queries: off while the live stream is healthy, a safety net otherwise. */
export const useFallbackInterval = (ms = 5000) => (useLive().status === 'live' ? false : ms)

// Which cached data an event can change. Events are patched into the cache directly; anything derived
// from other tables (fleet, plan, a unit's detail) is refreshed once, batched, instead of once per event.
const AFFECTS_FLEET = new Set<EventType>(['status_change', 'sensor_issue', 'failure', 'manager_alert', 'plan_changed', 'plan_approved', 'manager_decision', 'threshold_adjusted'])
const AFFECTS_PLAN = new Set<EventType>(['status_change', 'failure', 'manager_alert', 'plan_changed', 'plan_approved', 'manager_decision'])

function patchEvents(qc: QueryClient, ev: EventMsg) {
  qc.setQueryData<EventMsg[]>(['events'], (old) => {
    if (old?.some((e) => e.event_id === ev.event_id)) return old
    return [...(old ?? []), ev].sort((a, b) => a.event_id - b.event_id)
  })
}

export function LiveProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const toast = useToast()
  const showToast = useRef(toast.show)
  const [status, setStatus] = useState<StreamStatus>('connecting')
  const [banner, setBanner] = useState<BannerState>('none')
  const shown = useRef(false) // has the banner been shown for the current outage?

  useEffect(() => {
    const pending = { fleet: false, plan: false, units: new Set<string>() }
    let timer: ReturnType<typeof setTimeout> | null = null
    const flush = () => {
      timer = null
      if (pending.fleet) qc.invalidateQueries({ queryKey: ['fleet'], exact: true })
      if (pending.plan) qc.invalidateQueries({ queryKey: ['plan'] })
      for (const id of pending.units) qc.invalidateQueries({ queryKey: ['unit', id] })
      pending.fleet = pending.plan = false; pending.units.clear()
    }
    const stream = new LiveStream({
      onStatus: setStatus,
      onEvent: (ev) => {
        patchEvents(qc, ev)
        // The signature moment (DESIGN.md 9.3): a plan change is announced, and a manager decision is flagged.
        // The technician's phone page (/field/...) is not the manager's screen: a manager toast there covered the Answer and Decline buttons
        // (found on the deployed server). The events still update the caches; they just do not pop up.
        const quiet = window.location.pathname.startsWith('/field/')
        if (quiet) { /* no toast */ } else if (ev.type === 'plan_changed') showToast.current({ title: 'Plan changed', detail: ev.detail, tone: 'info' })
        else if (ev.type === 'plan_approved') showToast.current({ title: 'Plan approved', detail: ev.detail, tone: 'calm' })
        else if (ev.type === 'manager_decision') showToast.current({ title: ev.title, detail: ev.detail, tone: 'calm' })
        else if (ev.type === 'manager_alert' && ev.severity === 'critical') showToast.current({ title: ev.title, detail: ev.detail, tone: 'attention' })
        if (AFFECTS_FLEET.has(ev.type)) pending.fleet = true
        if (AFFECTS_PLAN.has(ev.type)) pending.plan = true
        if (ev.unit_id) pending.units.add(ev.unit_id)
        if (!timer) timer = setTimeout(flush, 250) // one refresh per burst
      },
    })
    // Events the page already loaded must not be delivered again.
    const seedFromCache = () => stream.seed((qc.getQueryData<EventMsg[]>(['events']) ?? []).map((e) => e.event_id))
    seedFromCache()
    const unsub = qc.getQueryCache().subscribe((e) => { if (e.type === 'updated' && e.query.queryKey[0] === 'events') seedFromCache() })
    stream.start()
    return () => { stream.stop(); unsub(); if (timer) clearTimeout(timer) }
  }, [qc])

  // Banner: wait 1.5 s before showing "reconnecting" (so a blip never flashes), then show "back online" briefly.
  useEffect(() => {
    if (status === 'live' || status === 'connecting') {
      if (!shown.current) return
      shown.current = false
      const t0 = setTimeout(() => setBanner('recovered'), 0)
      const t1 = setTimeout(() => setBanner('none'), 2800)
      return () => { clearTimeout(t0); clearTimeout(t1) }
    }
    if (status === 'offline') { shown.current = true; const t = setTimeout(() => setBanner('offline'), 0); return () => clearTimeout(t) }
    const t = setTimeout(() => { shown.current = true; setBanner((b) => (b === 'offline' ? b : 'down')) }, 1500)
    return () => clearTimeout(t)
  }, [status])

  const value = useMemo(() => ({ status, banner }), [status, banner])
  return <LiveContext.Provider value={value}>{children}</LiveContext.Provider>
}
