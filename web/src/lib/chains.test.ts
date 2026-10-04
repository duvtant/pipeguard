import { describe, expect, it } from 'vitest'
import { buildChains, matchesFilter } from './chains'
import { EVENTS } from '@/mocks/fixtures/events'
import type { EventMsg } from './types'

const e = (event_id: number, type: EventMsg['type'], unit_id: string | null, title = 't', severity: EventMsg['severity'] = 'info'): EventMsg =>
  ({ event_id, type, sim_day: 1, unit_id, title, detail: 'd', severity, payload: {} })

describe('buildChains', () => {
  it('puts one alert story in one chain, oldest event first, and sorts chains newest first', () => {
    const chains = buildChains(EVENTS)
    const eds07 = chains.find((c) => c.unit_id === 'EDS-07')!
    expect(eds07.events.map((x) => x.type)).toEqual(['status_change', 'call_requested', 'call_answered', 'constraint_added', 'plan_changed', 'call_summary'])
    expect(eds07.outcome).toBe('replanned')
    expect(chains.map((c) => c.lastId)).toEqual([...chains.map((c) => c.lastId)].sort((a, b) => b - a))
  })
  it('keeps a missed call and an unresolved alert visible, never dropped', () => {
    const chains = buildChains(EVENTS)
    expect(chains.find((c) => c.unit_id === 'DRH-09')!.outcome).toBe('missed')
    expect(chains.find((c) => c.unit_id === 'EDS-14')!.outcome).toBe('needs_decision')
    expect(chains.find((c) => c.unit_id === 'GPR-15')!.outcome).toBe('failed')
  })
  it('keeps system events (threshold changes) as their own chains', () => {
    const sys = buildChains(EVENTS).filter((c) => c.unit_id === null)
    expect(sys).toHaveLength(1); expect(sys[0].outcome).toBe('system')
  })
  it('starts a NEW chain for a unit only after its previous story finished', () => {
    const open = buildChains([e(1, 'status_change', 'A'), e(2, 'status_change', 'A')])
    expect(open).toHaveLength(1)
    const done = buildChains([e(1, 'status_change', 'A'), e(2, 'plan_changed', 'A'), e(3, 'status_change', 'A'), e(4, 'call_requested', 'A')])
    expect(done).toHaveLength(2); expect(done[0].events.map((x) => x.event_id)).toEqual([3, 4])
  })
  it('does not care about arrival order (two writers can commit out of order)', () => {
    const a = buildChains([e(3, 'call_answered', 'A'), e(1, 'status_change', 'A'), e(2, 'call_requested', 'A')])
    expect(a).toHaveLength(1); expect(a[0].events.map((x) => x.event_id)).toEqual([1, 2, 3])
  })
  it('marks a chain as approved once a manager approves the plan change, and a later alert starts a new chain', () => {
    const c = buildChains([e(1, 'status_change', 'A'), e(2, 'plan_changed', 'A'), e(3, 'plan_approved', 'A')])
    expect(c).toHaveLength(1); expect(c[0].outcome).toBe('approved')
    expect(buildChains([...c[0].events, e(4, 'status_change', 'A')])).toHaveLength(2)
  })
  it('filters by calls, plan changes and alerts', () => {
    const [c] = buildChains([e(1, 'status_change', 'A'), e(2, 'call_requested', 'A'), e(3, 'plan_changed', 'A')])
    expect(matchesFilter(c, 'calls')).toBe(true); expect(matchesFilter(c, 'plan')).toBe(true); expect(matchesFilter(c, 'alerts')).toBe(false)
    expect(matchesFilter(buildChains([e(9, 'sensor_issue', 'B', 'Sensor issue', 'warning')])[0], 'alerts')).toBe(true)
  })
  it('marks a chain as decided once a manager resolves a needs-a-decision alert', () => {
    const c = buildChains([e(1, 'manager_alert', 'A'), e(2, 'manager_decision', 'A')])
    expect(c).toHaveLength(1); expect(c[0].outcome).toBe('decided')
  })
})
