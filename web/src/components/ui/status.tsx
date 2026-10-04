import type { ComponentType, SVGProps } from 'react'
import Check from '~icons/ph/check-circle-fill'
import Warn from '~icons/ph/warning-fill'
import Octagon from '~icons/ph/warning-octagon-fill'
import Wrench from '~icons/ph/wrench-fill'
import XCircle from '~icons/ph/x-circle-fill'
import type { DisplayStatus } from '@/lib/types'

// One place that maps a status to its label, icon and colours (DESIGN.md section 4).
// Every status has its own icon AND label, so colour is never the only signal.
type Icon = ComponentType<SVGProps<SVGSVGElement>>
export interface StatusMeta {
  label: string
  Icon: Icon
  text: string      // text/icon colour class
  tint: string      // tint background class
  fill: string      // icon fill colour class (tile icons)
}

export const STATUS: Record<DisplayStatus | 'failed', StatusMeta> = {
  healthy: { label: 'Healthy', Icon: Check, text: 'text-ok', tint: 'bg-ok-tint', fill: 'text-ok-fill' },
  watch: { label: 'Watch', Icon: Warn, text: 'text-warn', tint: 'bg-warn-tint', fill: 'text-warn-fill' },
  at_risk: { label: 'At risk', Icon: Octagon, text: 'text-risk', tint: 'bg-risk-tint', fill: 'text-risk-fill' },
  sensor_issue: { label: 'Sensor issue', Icon: Wrench, text: 'text-sens', tint: 'bg-sens-tint', fill: 'text-sens-fill' },
  failed: { label: 'Failed', Icon: XCircle, text: 'text-fail', tint: 'bg-fail-tint', fill: 'text-fail' },
}

export const STATUS_ORDER: (DisplayStatus | 'failed')[] = ['healthy', 'watch', 'at_risk', 'sensor_issue', 'failed']

export function StatusPill({ status, label }: { status: DisplayStatus | 'failed'; label?: string }) {
  const m = STATUS[status]
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full py-[3px] pl-2 pr-2.5 text-[13px] font-semibold ${m.tint} ${m.text}`}>
      <m.Icon width={15} height={15} aria-hidden />
      {label ?? m.label}
    </span>
  )
}
