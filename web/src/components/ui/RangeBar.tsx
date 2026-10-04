import { cx } from './Card'

/** Remaining life as a range: a track from 0 to the longest plausible life, a bar from the low to the high estimate, and a
 *  marker at the likely value. Low confidence draws the bar dashed, so uncertainty is visible without a colour. */
export function RangeBar({ low, likely, high, max = 125, lowConfidence, className }: { low: number; likely: number; high: number; max?: number; lowConfidence?: boolean; className?: string }) {
  const pct = (v: number) => `${Math.min(100, Math.max(0, (v / max) * 100))}%`
  return (
    <div className={cx('w-full', className)} role="img" aria-label={`Remaining life: between ${low} and ${high} days, most likely ${likely}${lowConfidence ? ', low confidence' : ''}`}>
      <div className="relative h-2.5 rounded-full bg-pill">
        <div className={cx('absolute inset-y-0 rounded-full', lowConfidence ? 'border border-dashed border-accent bg-accent-soft' : 'bg-accent-fill')} style={{ left: pct(low), width: `calc(${pct(high)} - ${pct(low)})` }} />
        <div className="absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-[3px] border-accent bg-white" style={{ left: pct(likely) }} />
      </div>
      <div className="tnum mt-1 flex justify-between text-[13px] text-muted"><span>0 days</span><span>{max} days</span></div>
    </div>
  )
}
