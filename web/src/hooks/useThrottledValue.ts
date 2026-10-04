import { useEffect, useRef, useState } from 'react'

/** Follows `value`, but changes at most once per `ms`. The first change is immediate; later ones wait their turn.
 *  Keeps live numbers from flashing on every SSE tick (DESIGN.md 9.2: at most once per 2 s). */
export function useThrottledValue<T>(value: T, ms: number): T {
  const [shown, setShown] = useState(value)
  const shownRef = useRef(value)
  const last = useRef(-Infinity) // the mount itself is not a change, so the first real change is immediate
  useEffect(() => {
    if (Object.is(value, shownRef.current)) return
    const wait = Math.max(0, last.current + ms - performance.now())
    const t = setTimeout(() => { last.current = performance.now(); shownRef.current = value; setShown(value) }, wait)
    return () => clearTimeout(t)
  }, [value, ms])
  return shown
}
