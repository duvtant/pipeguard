import type { TrendPoint } from '@/lib/types'
import { MOCK_SIM_DAY } from './fleet'

// Placeholder series ending at the mock fleet's real count of at-risk units. Not model output.
export function makeTrend(now: number, last: number): TrendPoint[] {
  const out: TrendPoint[] = []
  for (let d = 30; d >= 0; d--) {
    const t = 1 - d / 30
    out.push({ sim_day: now - d, needing_attention: Math.max(0, Math.round(last * (0.35 + 0.65 * t * t) + (d % 7 === 3 ? 1 : 0))) })
  }
  out[out.length - 1].needing_attention = last
  return out
}
export const MOCK_TREND_DAY = MOCK_SIM_DAY
