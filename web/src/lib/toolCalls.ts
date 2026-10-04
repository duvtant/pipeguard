import type { ElevenToolCall, ElevenToolResult, EvaluationResult, TranscriptTurn, TriggeredGuardrail } from './types'

// Turns ElevenLabs' raw transcript records into what the Decision log shows. Everything is optional and tolerant: an old call without
// tool data, a tool result that is not JSON, or a guardrail type we have not seen must never break the page.
export interface ShownToolCall { name: string; args: [string, string][]; status: 'worked' | 'failed' | 'pending'; say?: string; seconds?: number }

const safeJson = (s: string | undefined): unknown => { try { return s ? JSON.parse(s) : undefined } catch { return undefined } }

/** Our tools answer `{"ok": true|false, "say": "..."}`. A tool counts as worked when ElevenLabs reports no error and the tool did not say ok:false. */
export function toolCallsByTurn(transcript: TranscriptTurn[]): ShownToolCall[][] {
  const results = new Map<string, ElevenToolResult>()
  for (const t of transcript) for (const r of t.tool_results ?? []) results.set(r.request_id, r)
  return transcript.map((turn) => (turn.tool_calls ?? []).filter((c: ElevenToolCall) => c.tool_has_been_called !== false).map((c) => {
    const params = safeJson(c.params_as_json)
    const args = params && typeof params === 'object' ? Object.entries(params as Record<string, unknown>).map(([k, v]): [string, string] => [k, String(v)]) : []
    const res = results.get(c.request_id)
    const body = safeJson(res?.result_value) as { ok?: boolean; say?: string } | undefined
    const status: ShownToolCall['status'] = !res ? 'pending' : res.is_error || body?.ok === false ? 'failed' : 'worked'
    return { name: c.tool_name, args, status, say: typeof body?.say === 'string' ? body.say : undefined, seconds: res?.tool_latency_secs }
  }))
}

const GUARDRAIL_WORDS: Record<string, string> = { prompt_injection: 'Manipulation guardrail', focus: 'Focus guardrail', custom: 'Custom guardrail' }
export const guardrailLabel = (g: TriggeredGuardrail) => g.guardrail_name || GUARDRAIL_WORDS[g.guardrail_type] || `${g.guardrail_type.replaceAll('_', ' ')} guardrail`

// Names for the report-card rules we configured on the agent (infra/elevenlabs: platform_settings.evaluation.criteria).
export const CRITERIA_NAMES: Record<string, string> = {
  asked_earliest_day: 'Asked for the earliest day', confirmed_before_booking: 'Confirmed before booking',
  stayed_on_task_and_facts: 'Stayed on task, no invented facts', honest_about_being_automated: 'Honest about being automated',
}
export const criteriaName = (id: string) => CRITERIA_NAMES[id] ?? id.replaceAll('_', ' ')

export function reportCardSummary(r: EvaluationResult[]) {
  const passed = r.filter((x) => x.result === 'success').length, failed = r.filter((x) => x.result === 'failure').length
  return { passed, failed, unknown: r.length - passed - failed, total: r.length }
}
