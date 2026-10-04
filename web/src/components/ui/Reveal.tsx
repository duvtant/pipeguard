import type { ReactNode } from 'react'
import { useSkeletonSwap } from '@/hooks/useSkeletonSwap'

/** Skeleton and content share one grid cell, so the height is the taller of the two (nothing clips or jumps).
 *  Cross-fade is opacity only, 200 ms: no blur, no scale (DESIGN.md 9.5). */
export function Reveal({ ready, skeleton, children, label = 'Loading' }: { ready: boolean; skeleton: ReactNode; children: ReactNode; label?: string }) {
  const { showSkeleton, busy } = useSkeletonSwap({ ready })
  const showContent = ready && !showSkeleton
  return (
    <div className="grid" aria-busy={busy}>
      <div className="col-start-1 row-start-1 transition-opacity duration-200 ease-[var(--ease-out)]" style={{ opacity: showContent ? 1 : 0 }} aria-hidden={!showContent}>
        {ready ? children : null}
      </div>
      <div className="pointer-events-none col-start-1 row-start-1 transition-opacity duration-200 ease-[var(--ease-out)]" style={{ opacity: showContent ? 0 : 1 }} aria-hidden={showContent} role="status" aria-label={label}>
        {showContent ? null : skeleton}
      </div>
    </div>
  )
}
