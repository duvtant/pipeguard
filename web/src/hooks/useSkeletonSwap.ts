// Adapted from interior.dev (MIT, (c) 2026 ozzy): https://github.com/ddoemonn/interior
// Only the timing hook is kept (see docs/design/COMPONENTS.md section 3, item 5).
import { useEffect, useRef, useState } from 'react'

/** Decides when to show a skeleton so loading never flickers:
 *  a fast load (under `delay`) shows no skeleton at all, and once a skeleton is shown it stays at least `minVisible`. */
export function useSkeletonSwap({ ready, delay = 120, minVisible = 380 }: { ready: boolean; delay?: number; minVisible?: number }) {
  const [visible, setVisible] = useState(false)
  const shownAt = useRef(0)
  useEffect(() => {
    if (!ready) {
      if (visible) return
      const t = setTimeout(() => { shownAt.current = performance.now(); setVisible(true) }, delay)
      return () => clearTimeout(t)
    }
    if (!visible) return
    const rest = Math.max(0, minVisible - (performance.now() - shownAt.current))
    const t = setTimeout(() => setVisible(false), rest)
    return () => clearTimeout(t)
  }, [ready, visible, delay, minVisible])
  return { showSkeleton: visible, busy: !ready }
}
