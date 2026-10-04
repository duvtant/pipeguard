import { describe, expect, it } from 'vitest'
import { guardrailLabel, reportCardSummary, toolCallsByTurn } from './toolCalls'
import type { TranscriptTurn } from './types'

const turn = (o: Partial<TranscriptTurn> = {}): TranscriptTurn => ({ role: 'agent', message: 'm', time_in_call_secs: 0, ...o })

describe('toolCallsByTurn (ElevenLabs transcript shape)', () => {
  it('joins a tool call to its result by request_id, even when the result is in a later turn', () => {
    const t = [turn({ tool_calls: [{ request_id: 'r1', tool_name: 'submit_availability', params_as_json: '{"unit_id":"EDS-07","earliest_day_text":"Friday"}', tool_has_been_called: true }] }),
      turn({ tool_results: [{ request_id: 'r1', tool_name: 'submit_availability', result_value: '{"ok":true,"say":"Done."}', is_error: false, tool_latency_secs: 0.4 }] })]
    const [first, second] = toolCallsByTurn(t)
    expect(first).toEqual([{ name: 'submit_availability', args: [['unit_id', 'EDS-07'], ['earliest_day_text', 'Friday']], status: 'worked', say: 'Done.', seconds: 0.4 }])
    expect(second).toEqual([])
  })
  it('marks a tool as failed on an error or on ok:false, and pending when there is no result yet', () => {
    const call = (id: string) => ({ request_id: id, tool_name: 'feedback', params_as_json: '{}', tool_has_been_called: true })
    const t = [turn({ tool_calls: [call('a'), call('b'), call('c')] }), turn({ tool_results: [
      { request_id: 'a', tool_name: 'feedback', result_value: '{"ok":false,"say":"Sorry"}', is_error: false },
      { request_id: 'b', tool_name: 'feedback', result_value: 'boom', is_error: true }] })]
    expect(toolCallsByTurn(t)[0].map((x) => x.status)).toEqual(['failed', 'failed', 'pending'])
  })
  it('never throws on odd data: bad JSON, missing fields, a call that was not actually made', () => {
    const t = [turn({ tool_calls: [{ request_id: 'x', tool_name: 'n', params_as_json: 'not json', tool_has_been_called: true }, { request_id: 'y', tool_name: 'skipped', params_as_json: '{}', tool_has_been_called: false }] }), turn()]
    const out = toolCallsByTurn(t)
    expect(out[0]).toHaveLength(1); expect(out[0][0].args).toEqual([]); expect(out[1]).toEqual([])
  })
})

describe('guardrails and the report card', () => {
  it('uses plain words for known guardrails and a readable fallback for new ones', () => {
    expect(guardrailLabel({ guardrail_type: 'prompt_injection' })).toBe('Manipulation guardrail')
    expect(guardrailLabel({ guardrail_type: 'hate_threatening' })).toBe('hate threatening guardrail')
    expect(guardrailLabel({ guardrail_type: 'custom', guardrail_name: 'No financial advice' })).toBe('No financial advice')
  })
  it('counts passed, failed and unknown separately (unknown is not a failure)', () => {
    expect(reportCardSummary([{ criteria_id: 'a', result: 'success', rationale: '' }, { criteria_id: 'b', result: 'failure', rationale: '' }, { criteria_id: 'c', result: 'unknown', rationale: '' }])).toEqual({ passed: 1, failed: 1, unknown: 1, total: 3 })
  })
})
