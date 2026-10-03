import type { PolicyResult, SimulateRequest, SimulateResponse } from '@/lib/types'

// A plausible, deterministic stand-in for POST /api/simulate. It is NOT the real model:
// numbers only need to move sensibly with the sliders (more crews -> fewer breakdowns).
export function simulate(req: SimulateRequest): SimulateResponse {
  const { crews_per_station: crews, cost_breakdown: cb, cost_service: cs } = req
  const c = Math.max(0, crews)
  const pgBreakdowns = c === 0 ? 40 : Math.max(2, Math.round(4 + 16 / c))
  const pgServices = c === 0 ? 0 : Math.min(130, 90 + c * 8)
  const pgWasted = Math.round(pgServices * 0.08)
  const defBreakdowns = pgBreakdowns + 4
  const defServices = Math.max(0, pgServices - 6)
  const policies: PolicyResult[] = [
    { policy: 'run_to_failure', breakdowns: 100, planned_services: 0, wasted_services: 0, crew_days: 0, total_cost: 100 * cb },
    { policy: 'fixed_schedule', breakdowns: 31, planned_services: 160, wasted_services: 84, crew_days: 160, total_cost: 31 * cb + 160 * cs },
    { policy: 'pipeguard', breakdowns: pgBreakdowns, planned_services: pgServices, wasted_services: pgWasted, crew_days: pgServices, total_cost: pgBreakdowns * cb + pgServices * cs },
  ]
  const tunedCost = policies[2].total_cost
  const defaultCost = defBreakdowns * cb + defServices * cs
  const caught = 100 - pgBreakdowns
  return {
    policies,
    default: { threshold: req.threshold ?? 0.5, horizon_days: req.horizon_days ?? 14, total_cost: defaultCost },
    tuned: { threshold: 0.4, horizon_days: req.horizon_days ?? 14, total_cost: tunedCost },
    headline: { detected: caught + 3, actioned: caught, total: 100, lead_days: 14,
      text: `PipeGuard would have caught ${caught} of 100 failures at least 14 days early.` },
    computed_ms: 120,
  }
}
