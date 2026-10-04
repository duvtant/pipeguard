import { describe, expect, it, vi } from 'vitest'
import { newestPerUnit } from './queries'
import type { PlanItem } from './types'

// The query functions must hand the screens whole days even when the real engine sends decimals.
describe('real API decimals', () => {
  it('rounds remaining life in the fleet and in a unit detail', async () => {
    const fleet = { sim_day: 1, clock: { status: 'paused', speed_seconds_per_day: 1, sim_day: 1 }, units: [{ unit_id: 'DRH-01', rul: { low: 88.32, likely: 99.138705157, high: 109.6 } }] }
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(fleet), { status: 200, headers: { 'Content-Type': 'application/json' } })))
    const { renderHook, waitFor } = await import('@testing-library/react')
    const { QueryClient, QueryClientProvider } = await import('@tanstack/react-query')
    const { createElement } = await import('react')
    const { useFleet } = await import('./queries')
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => useFleet(), { wrapper: ({ children }) => createElement(QueryClientProvider, { client: qc }, children) })
    await waitFor(() => expect(result.current.data).toBeDefined())
    expect(result.current.data!.units[0].rul).toEqual({ low: 88, likely: 99, high: 110 })
    vi.unstubAllGlobals()
  })
})

describe('duplicate plan rows from the backend', () => {
  const row = (id: number, unit_id: string, planned_day: number) => ({ id, unit_id, planned_day }) as PlanItem
  it('keeps only the newest row per unit and leaves single rows alone', () => {
    const out = newestPerUnit([row(1, 'HIN-02', 29), row(2, 'HIN-02', 30), row(3, 'EDS-01', 31), row(4, 'HIN-02', 32)])
    expect(out.map((p) => [p.unit_id, p.id])).toEqual([['EDS-01', 3], ['HIN-02', 4]])
    expect(newestPerUnit([row(1, 'A', 1), row(2, 'B', 1)])).toHaveLength(2)
  })
})
