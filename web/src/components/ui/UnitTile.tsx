import { memo } from 'react'
import type { FleetUnit } from '@/lib/types'
import Wrench from '~icons/ph/wrench-fill'
import { STATUS } from './status'
import { cx } from './Card'

const tileKey = (u: FleetUnit) => (u.failed ? 'failed' : u.display_status)

/** One turbine in the Fleet grid (DESIGN.md 5.5). Labels are short so nothing wraps.
 *  At risk + sensor issue: stays red and gets a small white wrench badge. */
function UnitTileBase({ unit, onSelect, changed }: { unit: FleetUnit; onSelect?: (u: FleetUnit) => void; changed?: boolean }) {
  const key = tileKey(unit)
  const m = STATUS[key]
  const badge = unit.sensor_issue && unit.display_status === 'at_risk'
  const days = unit.failed ? 'Failed' : `${unit.rul.likely} d`
  const Tag = onSelect ? 'button' : 'div'
  return (
    <Tag
      {...(onSelect ? { type: 'button' as const, onClick: () => onSelect(unit) } : { role: 'img' as const })}
      aria-label={`${unit.unit_id}, ${m.label}${unit.failed ? '' : `, about ${unit.rul.likely} days left`}${badge ? ', sensor issue' : ''}`}
      className={cx(
        'relative flex min-h-[54px] flex-col gap-1 rounded-tile px-2 pb-2 pt-2 text-left transition-[transform,box-shadow] duration-150 ease-[var(--ease-out)] hover:-translate-y-px',
        key === 'healthy' ? 'bg-canvas shadow-tile hover:shadow-card' : m.tint, changed && 'pg-flash',
      )}
    >
      <span className="tnum text-[13px] [font-weight:var(--w-strong)] tracking-[-0.01em] text-ink">{unit.unit_id}</span>
      <span className="tnum text-[13px] text-muted">{days}</span>
      <m.Icon width={16} height={16} aria-hidden className={cx('absolute bottom-1.5 right-2', key === 'healthy' ? m.fill : m.text)} />
      {badge && (
        <span className="absolute right-2 top-[7px] grid size-[18px] place-items-center rounded-full bg-white text-sens shadow-tile">
          <Wrench width={12} height={12} aria-hidden />
        </span>
      )}
    </Tag>
  )
}

// 100 tiles: re-render one only if something it shows changed.
export const UnitTile = memo(UnitTileBase, (a, b) =>
  a.unit.unit_id === b.unit.unit_id && a.unit.display_status === b.unit.display_status && a.unit.failed === b.unit.failed &&
  a.unit.rul.likely === b.unit.rul.likely && a.unit.sensor_issue === b.unit.sensor_issue && a.changed === b.changed && a.onSelect === b.onSelect)
