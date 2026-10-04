import { useEffect, useRef, useState } from 'react'
import type { FleetUnit } from '@/lib/types'

/** Ids of units whose status just changed, for the 1.2 s highlight (DESIGN.md 9.2). At most 6 at a time: a bigger burst
 *  (for example a reset) just changes colour without a pulse, so 100 tiles never animate at once. */
export function useChangedUnits(units: FleetUnit[] | undefined, holdMs = 1200, cap = 6) {
  const prev = useRef<Map<string, string> | null>(null)
  const [changed, setChanged] = useState<ReadonlySet<string>>(new Set())
  useEffect(() => {
    if (!units) return
    const now = new Map(units.map((u) => [u.unit_id, `${u.display_status}|${u.failed}`]))
    const before = prev.current
    prev.current = now
    if (!before) return // the first load is not a change
    const ids = units.filter((u) => before.has(u.unit_id) && before.get(u.unit_id) !== now.get(u.unit_id)).map((u) => u.unit_id)
    if (ids.length === 0 || ids.length > cap) return
    const t0 = setTimeout(() => setChanged(new Set(ids)), 0)
    const t1 = setTimeout(() => setChanged(new Set()), holdMs)
    return () => { clearTimeout(t0); clearTimeout(t1) }
  }, [units, holdMs, cap])
  return changed
}
