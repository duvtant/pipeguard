import type { CallRecord, EventMsg, FleetUnit, HistoryPoint, QualityFlag, SensorSeries, UnitDetail } from '@/lib/types'
import { SENSOR_LABELS } from '@/lib/sensors'
import { MOCK_SIM_DAY } from './fleet'

// Deterministic per-unit detail (no randomness: derived from the unit's own numbers).
export function makeDetail(u: FleetUnit, events: EventMsg[], calls: CallRecord[]): UnitDetail {
  const days = Array.from({ length: 30 }, (_, i) => MOCK_SIM_DAY - 29 + i)
  const history: HistoryPoint[] = days.map((d, i) => {
    const t = i / 29 // 0 = a month ago, 1 = now
    const drift = (1 - t) * (u.risk_status === 'healthy' ? 4 : 18)
    return {
      sim_day: d,
      rul_low: Math.round(u.rul.low + drift), rul_likely: Math.round(u.rul.likely + drift * 1.2), rul_high: Math.round(u.rul.high + drift * 1.5),
      p_fail: Math.max(0, Math.round((u.p_fail * (0.35 + 0.65 * t)) * 100) / 100),
    }
  })
  const sensors: SensorSeries[] = u.top_sensors.slice(0, 3).map((s, k) => ({
    sensor: s, label: SENSOR_LABELS[s] ?? s,
    points: days.map((d, i) => ({ sim_day: d, value: Math.round((100 + k * 8 + i * (u.risk_status === 'healthy' ? 0.05 : 0.5) + Math.sin(i + k) * 0.6) * 100) / 100 })),
  }))
  const quality_flags: QualityFlag[] = u.sensor_issue
    ? [{ id: 1, unit_id: u.unit_id, sim_day: 26, sensor: u.top_sensors[0], flag_type: 'sensor_stuck', resolved_day: null }]
    : []
  return {
    ...u, history, sensors, quality_flags,
    events: events.filter((e) => e.unit_id === u.unit_id),
    calls: calls.filter((c) => c.unit_id === u.unit_id),
  }
}
