import type { Confidence, FleetUnit, RiskStatus } from '@/lib/types'
import { displayStatus } from '@/lib/status'
import { SENSOR_LABELS } from '@/lib/sensors'

// Deterministic: same seed, same fleet, every run. 5 stations x 20 units = 100 turbines.
export const MOCK_SIM_DAY = 29 // a Tuesday in the simulated calendar, so "Friday" is day 32

export const STATIONS = [
  { code: 'EDS', name: 'Edson' },
  { code: 'HIN', name: 'Hinton' },
  { code: 'WHT', name: 'Whitecourt' },
  { code: 'GPR', name: 'Grande Prairie' },
  { code: 'DRH', name: 'Drumheller' },
] as const

function mulberry32(seed: number) {
  let a = seed
  return () => {
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const RISING = ['s2', 's3', 's4', 's11', 's13']
const FALLING = ['s7', 's12', 's20', 's21']
const reasonFor = (sensor: string, days: number) => {
  const dir = RISING.includes(sensor) ? 'rising' : 'falling'
  return `${SENSOR_LABELS[sensor]} ${dir} for ${days} days`
}

const unitId = (code: string, n: number) => `${code}-${String(n).padStart(2, '0')}`

function build(code: string, name: string, n: number, rand: () => number): FleetUnit {
  const r = rand()
  const risk: RiskStatus = r < 0.82 ? 'healthy' : r < 0.95 ? 'watch' : 'at_risk'
  const sensors = [...RISING, ...FALLING]
  const s1 = sensors[Math.floor(rand() * sensors.length)]
  const s2 = sensors[Math.floor(rand() * sensors.length)]
  const s3 = sensors[Math.floor(rand() * sensors.length)]
  const likely = risk === 'healthy' ? 80 + rand() * 45 : risk === 'watch' ? 32 + rand() * 38 : 8 + rand() * 22
  const p = risk === 'healthy' ? rand() * 0.08 : risk === 'watch' ? 0.1 + rand() * 0.35 : 0.5 + rand() * 0.4
  const low = Math.max(1, likely - (6 + rand() * 10))
  const high = Math.min(125, likely + (8 + rand() * 14))
  return {
    unit_id: unitId(code, n), station_code: code, station: name,
    risk_status: risk, sensor_issue: false, display_status: risk,
    rul: { low: Math.round(low), likely: Math.round(likely), high: Math.round(high) },
    p_fail: Math.round(p * 100) / 100, confidence: 'normal',
    reason: risk === 'healthy' ? 'No significant drift' : reasonFor(s1, 3 + Math.floor(rand() * 9)),
    top_sensors: [s1, s2, s3], next_service_day: null, needs_manager_decision: false,
    failed: false, data_source: 'live', model_version: 'v1',
  }
}

// Named edge cases the dashboard must handle (design and build against these).
type Override = Partial<FleetUnit> & { unit_id: string }
const OVERRIDES: Override[] = [
  // The demo unit: red, called, plan moved to Friday (sim_day 32) after the technician's answer.
  { unit_id: 'EDS-07', risk_status: 'at_risk', rul: { low: 14, likely: 22, high: 35 }, p_fail: 0.62,
    reason: reasonFor('s3', 6), top_sensors: ['s3', 's4', 's11'], next_service_day: 32 },
  // Grey + wrench: a stuck sensor on an otherwise healthy unit, low confidence.
  { unit_id: 'HIN-12', risk_status: 'healthy', sensor_issue: true, confidence: 'low' as Confidence,
    rul: { low: 60, likely: 98, high: 125 }, p_fail: 0.03, reason: 'No significant drift',
    top_sensors: ['s4', 's2', 's3'] },
  // Red WITH wrench (contract D1): a real risk is never hidden behind a sensor fault.
  { unit_id: 'WHT-03', risk_status: 'at_risk', sensor_issue: true, confidence: 'low' as Confidence,
    rul: { low: 9, likely: 21, high: 40 }, p_fail: 0.71, reason: reasonFor('s11', 8), top_sensors: ['s11', 's7', 's3'] },
  // Failed: counts as a breakdown, never hidden.
  { unit_id: 'GPR-15', risk_status: 'at_risk', failed: true, rul: { low: 0, likely: 0, high: 0 }, p_fail: 1,
    reason: 'Failed on day 24', top_sensors: ['s3', 's4', 's11'] },
  // At risk, but no crew slot: needs a manager decision (never fails silently).
  { unit_id: 'EDS-14', risk_status: 'at_risk', needs_manager_decision: true, rul: { low: 6, likely: 15, high: 26 },
    p_fail: 0.83, reason: reasonFor('s4', 10), top_sensors: ['s4', 's3', 's2'] },
  // Watch with low confidence (little history): wide range, honest label.
  { unit_id: 'DRH-09', risk_status: 'watch', confidence: 'low' as Confidence, rul: { low: 22, likely: 54, high: 110 },
    p_fail: 0.22, reason: reasonFor('s2', 4), top_sensors: ['s2', 's13', 's3'] },
  // French-speaking technician's unit: at risk, call in French.
  { unit_id: 'GPR-02', risk_status: 'at_risk', rul: { low: 12, likely: 24, high: 38 }, p_fail: 0.55,
    reason: reasonFor('s11', 7), top_sensors: ['s11', 's3', 's4'], next_service_day: 33 },
  // Engine fell back to precomputed predictions: shown honestly in the UI.
  { unit_id: 'DRH-17', data_source: 'fallback' },
]

export function makeFleet(): FleetUnit[] {
  const units: FleetUnit[] = []
  STATIONS.forEach((s, si) => {
    const rand = mulberry32(1000 + si)
    for (let n = 1; n <= 20; n++) units.push(build(s.code, s.name, n, rand))
  })
  for (const o of OVERRIDES) {
    const i = units.findIndex((u) => u.unit_id === o.unit_id)
    units[i] = { ...units[i], ...o }
  }
  return units.map((u) => ({ ...u, display_status: displayStatus(u.risk_status, u.sensor_issue) }))
}
