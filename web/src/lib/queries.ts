import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api } from './api'
import { useFallbackInterval } from './live'
import type { Fault, Settings, Technician, EventMsg, FeedbackStats, FleetResponse, ModelMetrics, PlanItem, SimulateRequest, SimulateResponse, TrendPoint, UnitDetail } from './types'

// Data hooks. Phase 3 (P3.1) patches the fleet cache from one shared event stream; until then this polls.
export const useFleet = () => useQuery({ queryKey: ['fleet'], queryFn: () => api<FleetResponse>('/fleet'), refetchInterval: useFallbackInterval() })
export const useTrend = () => useQuery({ queryKey: ['fleet', 'trend'], queryFn: () => api<TrendPoint[]>('/fleet/trend') })
// retry: false so a backend that has not built this endpoint hides the card at once instead of after three tries.
export const useFeedbackStats = () => useQuery({ queryKey: ['feedback-stats'], queryFn: () => api<FeedbackStats>('/feedback/stats'), retry: false })
export const useModel = () => useQuery({ queryKey: ['model'], queryFn: () => api<ModelMetrics>('/model') })

/** What-if simulation. The previous result stays on screen (dimmed) while a new one loads. */
export const useSimulate = (req: SimulateRequest) =>
  useQuery({
    queryKey: ['simulate', req],
    queryFn: ({ signal }) => api<SimulateResponse>('/simulate', { method: 'POST', body: JSON.stringify(req), signal }),
    placeholderData: keepPreviousData,
  })

export const usePlan = () => useQuery({ queryKey: ['plan'], queryFn: () => api<PlanItem[]>('/plan'), refetchInterval: useFallbackInterval() })
export const useEvents = () => useQuery({ queryKey: ['events'], queryFn: () => api<EventMsg[]>('/events'), refetchInterval: useFallbackInterval(), staleTime: Infinity })

export const useUnit = (id: string | null) =>
  useQuery({ queryKey: ['unit', id], queryFn: () => api<UnitDetail>(`/units/${id}`), enabled: !!id, refetchInterval: useFallbackInterval() })

export const useTechnicians = () => useQuery({ queryKey: ['technicians'], queryFn: () => api<Technician[]>('/technicians') })
export const useSettings = () => useQuery({ queryKey: ['settings'], queryFn: () => api<Settings>('/settings'), staleTime: Infinity })

// Admin and test-mode calls carry the token the presenter typed into Test mode (kept in sessionStorage only, never in the bundle).
const TOKEN_KEY = 'pg-admin-token'
export const getAdminToken = () => { try { return sessionStorage.getItem(TOKEN_KEY) ?? '' } catch { return '' } }
export const setAdminToken = (t: string) => { try { if (t) sessionStorage.setItem(TOKEN_KEY, t); else sessionStorage.removeItem(TOKEN_KEY) } catch { /* private window */ } }
export const adminApi = <T,>(path: string, init: RequestInit = {}) => api<T>(path, { ...init, headers: { 'X-Admin-Token': getAdminToken(), ...(init.headers ?? {}) } })
export const useFaults = (enabled: boolean) => useQuery({ queryKey: ['faults'], queryFn: () => adminApi<Fault[]>('/testmode/faults'), enabled, refetchInterval: 4000 })
