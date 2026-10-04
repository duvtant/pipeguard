// Hand-written from docs/delegation/00_TEAM_CONTRACT.md section 4.3 so the dashboard can be built
// before the backend exists. Once Ebube's API is up, run `pnpm gen:api` and replace these with the
// generated types (src/lib/api-types.ts). Shapes marked "NOT IN CONTRACT YET" were inferred from
// docs/techstack.md and must be confirmed with Ebube.

export type RiskStatus = 'healthy' | 'watch' | 'at_risk'
export type DisplayStatus = RiskStatus | 'sensor_issue'
export type Confidence = 'normal' | 'low'
export type Language = 'en' | 'fr'
export type FaultType = 'dead' | 'stuck' | 'spike' | 'out_of_range'
export type Verdict = 'confirmed_wear' | 'looks_fine' | 'part_replaced'
export type PlanState = 'planned' | 'done' | 'blocked' | 'needs_manager_decision'
export type CallState = 'ringing' | 'answered' | 'missed' | 'escalated' | 'done'
export type Policy = 'run_to_failure' | 'fixed_schedule' | 'pipeguard'
export type Severity = 'info' | 'warning' | 'critical'
export type EventType =
  | 'status_change' | 'sensor_issue' | 'call_requested' | 'call_answered' | 'constraint_added'
  | 'plan_changed' | 'plan_approved' | 'call_summary' | 'feedback_received' | 'threshold_adjusted' | 'failure'
  | 'manager_alert' | 'manager_decision'

export interface Rul { low: number; likely: number; high: number }

export interface FleetUnit {
  unit_id: string
  station_code: string
  station: string
  risk_status: RiskStatus
  sensor_issue: boolean
  display_status: DisplayStatus
  rul: Rul
  p_fail: number
  confidence: Confidence
  reason: string
  top_sensors: string[]
  next_service_day: number | null
  needs_manager_decision: boolean
  failed: boolean
  data_source: 'live' | 'fallback'
  model_version: string
}

export interface ClockState {
  status: 'running' | 'paused'
  speed_seconds_per_day: number
  sim_day: number
}

export interface FleetResponse { sim_day: number; clock: ClockState; units: FleetUnit[] }

export interface HistoryPoint { sim_day: number; rul_low: number; rul_likely: number; rul_high: number; p_fail: number }
export interface SensorSeries { sensor: string; label: string; points: { sim_day: number; value: number }[] }
export interface QualityFlag {
  id: number; unit_id: string; sim_day: number; sensor: string
  flag_type: 'sensor_offline' | 'sensor_stuck' | 'sensor_spike' | 'sensor_out_of_range'
  resolved_day: number | null
}

// What the agent DID during a call, in ElevenLabs' own transcript shape (docs: GET /v1/convai/conversations/{id}). The backend must store
// the transcript unmodified so these survive (NOT IN CONTRACT YET: see docs/delegation/MESSAGE_TO_EBUBE.md).
export interface ElevenToolCall { request_id: string; tool_name: string; params_as_json: string; tool_has_been_called?: boolean }
export interface ElevenToolResult { request_id: string; tool_name: string; result_value: string; is_error: boolean; tool_latency_secs?: number }
export interface TriggeredGuardrail { guardrail_type: string; guardrail_name?: string | null }
// The call's report card (analysis.evaluation_criteria_results_list). `unknown` is not a failure.
export interface EvaluationResult { criteria_id: string; result: 'success' | 'failure' | 'unknown'; rationale: string }
// NOT IN CONTRACT YET: the policy gate's reasoning, attached to an event's payload so the log can say WHY a call was (or was not) made.
export interface PolicyCheck { rule: string; passed: boolean; detail: string }
export interface TranscriptTurn { role: 'agent' | 'user'; message: string; time_in_call_secs: number; tool_calls?: ElevenToolCall[]; tool_results?: ElevenToolResult[]; triggered_guardrails?: TriggeredGuardrail[] }
// NOT IN CONTRACT YET (techstack section 10, `calls` table)
export interface CallRecord {
  id: number; call_request_id: number; unit_id: string; technician_id: number; technician_name: string
  conversation_id: string; language: Language; transcript: TranscriptTurn[]
  summary: string; summary_en: string; duration_secs: number
  received_via: 'webhook' | 'pull' | 'webhook_fallback' | 'simulated'
  data_collection: { available_day?: string; verdict?: string; unit_mentioned?: string }
  evaluation?: EvaluationResult[]
}

export interface UnitDetail extends FleetUnit {
  history: HistoryPoint[]
  sensors: SensorSeries[]
  events: EventMsg[]
  calls: CallRecord[]
  quality_flags: QualityFlag[]
}

export interface PlanItem {
  id: number; unit_id: string; station_code: string; planned_day: number; planned_date: string
  technician_id: number; technician_name: string; expected_saving: number; reason: string; state: PlanState
  // NOT IN CONTRACT YET: manager approval. When the API omits this field the whole approval UI stays hidden (nothing fake is shown).
  // `proposed` = the agent or planner scheduled it, a manager has not approved it. `approved` = released as a work order.
  approval?: 'proposed' | 'approved'
  // NOT IN CONTRACT YET: how a manager resolved a `needs_manager_decision` item. `overtime` = scheduled with an extra crew; `deferred` = risk accepted for now.
  decision?: 'overtime' | 'deferred'
}

export type DecisionChoice = 'overtime' | 'defer'

export interface EventMsg {
  event_id: number; type: EventType; sim_day: number; unit_id: string | null
  title: string; detail: string; severity: Severity; payload: Record<string, unknown>
}

export interface SimulateRequest {
  crews_per_station: number; cost_breakdown: number; cost_service: number
  threshold: number | null; horizon_days: number | null
}
export interface PolicyResult {
  policy: Policy; breakdowns: number; planned_services: number; wasted_services: number
  crew_days: number; total_cost: number
}
export interface TuneSetting { threshold: number; horizon_days: number; total_cost: number }
export interface SimulateResponse {
  policies: PolicyResult[]
  default: TuneSetting
  tuned: TuneSetting
  headline: { detected: number; actioned: number; total: number; lead_days: number; text: string }
  computed_ms: number
  // NOT IN CONTRACT YET: cumulative cost per policy per simulated day, for the Impact comparison chart.
  // Ask Olise/Ebube to include it in the simulate response (see docs/delegation/00 section 8 open items).
  series?: CostPoint[]
}
// NOT IN CONTRACT YET
export interface CostPoint { sim_day: number; run_to_failure: number; fixed_schedule: number; pipeguard: number }
// NOT IN CONTRACT YET: how many units needed attention each day, for the Fleet KPI chart (GET /api/fleet/trend).
export interface TrendPoint { sim_day: number; needing_attention: number }
// NOT IN CONTRACT YET: model metrics from ml/artifacts/metadata.json (GET /api/model). Mock values are placeholders.
// NOT IN CONTRACT YET: how often technicians confirmed a warning (GET /api/feedback/stats). `confirmed` counts confirmed_wear + part_replaced; `looks_fine` is a false alarm. Mock values are placeholders.
export interface FeedbackStats { total: number; confirmed: number }
export interface ModelMetrics { rmse: number; baseline_rmse: number; model_version: string }

// NOT IN CONTRACT YET (techstack section 11.1 /api/technicians)
export interface Technician {
  id: number; name: string; station_code: string; shift: 'day' | 'night'; language: Language
  is_backup: boolean; online: boolean; field_page_id: string
}

export interface RingEvent {
  type: 'ring'; call_request_id: number; unit_id: string; station_name: string
  technician_id: number; technician_name: string; language: Language
  rul_low: number; rul_high: number; reason: string; expires_at: string
}

export interface AnswerResponse {
  signed_url: string
  language: Language
  dynamic_variables: Record<string, string> // all values are strings
}

// NOT IN CONTRACT YET: Settings page (GET and PUT /api/settings). Ask Ebube for the real shape.
export interface Settings {
  crews_per_station: number; cost_breakdown: number; cost_service: number
  ring_timeout_secs: number; call_backup_when_missed: boolean; require_manager_for_conflicts: boolean
}

export interface Fault { id: number; unit_id: string; sensor: string; type: FaultType; start_day: number; end_day: number | null; source: 'planted' | 'toggle' }
