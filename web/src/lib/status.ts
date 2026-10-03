import type { DisplayStatus, RiskStatus } from './types'

// Contract decision D1: a unit with a sensor issue shows grey + wrench, UNLESS it is already at risk,
// in which case it stays red with a wrench badge so a real risk is never hidden behind a sensor fault.
// The server computes display_status; this mirrors the rule for mocks and tests.
export function displayStatus(risk: RiskStatus, sensorIssue: boolean): DisplayStatus {
  return sensorIssue && risk !== 'at_risk' ? 'sensor_issue' : risk
}
