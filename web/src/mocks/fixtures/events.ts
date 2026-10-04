import type { CallRecord, EventMsg, PolicyCheck } from '@/lib/types'

const e = (event_id: number, type: EventMsg['type'], sim_day: number, unit_id: string | null, title: string, detail: string,
  severity: EventMsg['severity'] = 'info', payload: Record<string, unknown> = {}): EventMsg =>
  ({ event_id, type, sim_day, unit_id, title, detail, severity, payload })

// The policy gate's reasoning for a call (techstack 7.8). The agent only calls when EVERY check passes; the log shows them.
export const CALL_CHECKS: PolicyCheck[] = [
  { rule: 'Red for 3 readings in a row', passed: true, detail: 'Confirmed over 3 consecutive readings, not a one-day blip.' },
  { rule: 'In the top priority band', passed: true, detail: 'At risk, with one of the highest expected savings.' },
  { rule: 'Not a sensor problem', passed: true, detail: 'No sensor fault on this unit. Faulty sensors never trigger a crew call.' },
  { rule: 'No repeat call within 3 days', passed: true, detail: 'This unit has not been called about in the last 3 simulated days.' },
  { rule: 'Technician under the daily limit', passed: true, detail: '1 of 3 calls used today.' },
]

// The decision-log chains: sensor drift -> prediction -> call -> answer -> plan change -> summary -> feedback.
export const EVENTS: EventMsg[] = [
  e(1, 'status_change', 24, 'GPR-15', 'Unit failed', 'GPR-15 failed on day 24 before a service slot was available.', 'critical'),
  e(2, 'sensor_issue', 26, 'HIN-12', 'Sensor issue', 'Low-pressure turbine outlet temperature has stopped changing. Instrument check requested. No crew call.', 'warning'),
  e(3, 'status_change', 27, 'EDS-07', 'At risk', 'EDS-07 is at risk: about 14 to 35 days left. High-pressure compressor outlet temperature rising for 6 days.', 'warning'),
  e(4, 'call_requested', 27, 'EDS-07', 'Calling technician', 'Calling Aiden Walker (Edson, day shift) about EDS-07.', 'info', { checks: CALL_CHECKS }),
  e(5, 'call_answered', 27, 'EDS-07', 'Call answered', 'Aiden Walker answered and is discussing EDS-07.'),
  e(6, 'constraint_added', 27, 'EDS-07', 'Availability recorded', 'Technician cannot service EDS-07 before Friday (day 32).'),
  e(7, 'plan_changed', 27, 'EDS-07', 'Plan changed', 'EDS-07 moved to Fri (day 32). EDS-02 takes the Thursday slot.'),
  e(8, 'call_summary', 27, 'EDS-07', 'Call summary', 'Technician can service EDS-07 from Friday. Plan updated.'),
  e(9, 'status_change', 28, 'WHT-03', 'At risk, sensor issue', 'WHT-03 is at risk and a sensor is faulty. It stays red so the risk is not hidden. Instrument check requested.', 'warning'),
  e(10, 'manager_alert', 28, 'EDS-14', 'Needs a manager decision', 'EDS-14 is at risk and no crew slot is free in the next 7 days.', 'critical', { checks: [...CALL_CHECKS.slice(0, 3), { rule: 'A crew slot is free this week', passed: false, detail: 'No crew is free in the next 7 days, so there is nothing to ask a technician to do. A manager decides.' }] }),
  e(11, 'call_requested', 28, 'GPR-02', 'Calling technician', 'Calling Marc Tremblay (Grande Prairie, day shift, French) about GPR-02.', 'info', { checks: CALL_CHECKS }),
  e(12, 'call_answered', 28, 'GPR-02', 'Call answered', 'Marc Tremblay answered (French).'),
  e(13, 'plan_changed', 28, 'GPR-02', 'Plan changed', 'GPR-02 scheduled for day 33.'),
  e(14, 'call_summary', 28, 'GPR-02', 'Call summary', 'Technician can service GPR-02 from Friday and expects wear on the outlet seal.'),
  e(15, 'call_requested', 28, 'DRH-09', 'Calling technician', 'Calling Lena Fischer (Drumheller) about DRH-09.'),
  e(16, 'manager_alert', 28, 'DRH-09', 'Call missed, escalated', 'Nobody answered. The backup technician also did not answer. Manager alerted.', 'warning'),
  e(17, 'feedback_received', 29, 'EDS-02', 'Feedback received', 'Technician confirmed wear on EDS-02. The warning was correct.'),
  e(18, 'threshold_adjusted', 29, null, 'Threshold adjusted', 'Feedback received, threshold adjusted from 0.50 to 0.55.'),
]

// Extra events the mock stream replays to make the dashboard feel live.
export const LIVE_EVENTS: Omit<EventMsg, 'event_id'>[] = [
  { type: 'status_change', sim_day: 30, unit_id: 'DRH-04', title: 'Watch', detail: 'DRH-04 moved to watch: about 40 to 70 days left.', severity: 'info', payload: {} },
  { type: 'status_change', sim_day: 31, unit_id: 'HIN-08', title: 'At risk', detail: 'HIN-08 is at risk: about 10 to 28 days left.', severity: 'warning', payload: {} },
  { type: 'plan_changed', sim_day: 31, unit_id: 'HIN-08', title: 'Plan changed', detail: 'HIN-08 scheduled for day 34.', severity: 'info', payload: {} },
]

export const CALLS: CallRecord[] = [
  {
    id: 1, call_request_id: 41, unit_id: 'EDS-07', technician_id: 1, technician_name: 'Aiden Walker',
    conversation_id: 'conv_mock_0001', language: 'en', duration_secs: 38, received_via: 'webhook',
    evaluation: [
      { criteria_id: 'asked_earliest_day', result: 'success', rationale: 'The agent asked for the earliest day and used the answer given.' },
      { criteria_id: 'confirmed_before_booking', result: 'success', rationale: 'The day was clear ("Not before Friday") and the agent confirmed it before ending.' },
      { criteria_id: 'stayed_on_task_and_facts', result: 'success', rationale: 'Only EDS-07 and the 14 to 35 day range were discussed.' },
      { criteria_id: 'honest_about_being_automated', result: 'success', rationale: 'The technician never asked whether it was a person.' },
    ],
    summary: 'The agent told the technician EDS-07 has 14 to 35 days left. The technician can service it from Friday.',
    summary_en: 'The agent told the technician EDS-07 has 14 to 35 days left. The technician can service it from Friday.',
    data_collection: { available_day: 'not before Friday', unit_mentioned: 'EDS-07' },
    transcript: [
      { role: 'agent', message: 'Hi Aiden, this is PipeGuard for Prairie Gas. Unit EDS-07 at Edson needs attention. Do you have a minute?', time_in_call_secs: 0 },
      { role: 'user', message: 'Yeah, go ahead.', time_in_call_secs: 6 },
      { role: 'agent', message: 'It has about 14 to 35 days left. High-pressure compressor outlet temperature has been rising for six days. What is the earliest day your crew can service it?', time_in_call_secs: 8 },
      { role: 'user', message: 'Not before Friday.', time_in_call_secs: 19 },
      { role: 'agent', message: 'Got it. EDS-07 moves to Friday, and EDS-02 takes Thursday\'s slot. Does that work?', time_in_call_secs: 23,
        tool_calls: [{ request_id: 'req_mock_1', tool_name: 'submit_availability', params_as_json: JSON.stringify({ unit_id: 'EDS-07', technician_id: '1', earliest_day_text: 'Not before Friday' }), tool_has_been_called: true }],
        tool_results: [{ request_id: 'req_mock_1', tool_name: 'submit_availability', result_value: JSON.stringify({ ok: true, say: "Got it. EDS-07 moves to Friday, and EDS-02 takes Thursday's slot. Does that work?" }), is_error: false, tool_latency_secs: 0.6 }] },
      { role: 'user', message: 'That works.', time_in_call_secs: 31 },
      { role: 'agent', message: 'Thanks, Aiden. Talk soon.', time_in_call_secs: 33 },
    ],
  },
  {
    id: 2, call_request_id: 44, unit_id: 'GPR-02', technician_id: 3, technician_name: 'Marc Tremblay',
    conversation_id: 'conv_mock_0002', language: 'fr', duration_secs: 41, received_via: 'webhook',
    evaluation: [
      { criteria_id: 'asked_earliest_day', result: 'success', rationale: "L'agent a demandé le premier jour possible." },
      { criteria_id: 'confirmed_before_booking', result: 'success', rationale: 'Le jour (vendredi) était clair et a été confirmé.' },
      { criteria_id: 'stayed_on_task_and_facts', result: 'success', rationale: 'Seule GPR-02 et sa plage de 12 à 38 jours ont été mentionnées.' },
      { criteria_id: 'honest_about_being_automated', result: 'success', rationale: "Le technicien n'a pas demandé s'il parlait à une personne." },
    ],
    summary: "L'agent a informé le technicien que GPR-02 a de 12 à 38 jours restants. Le technicien peut intervenir à partir de vendredi.",
    summary_en: 'The agent told the technician GPR-02 has 12 to 38 days left. The technician can service it from Friday and expects wear on the outlet seal.',
    data_collection: { available_day: 'pas avant vendredi', unit_mentioned: 'GPR-02' },
    transcript: [
      { role: 'agent', message: "Bonjour Marc, ici PipeGuard pour Prairie Gas. L'unité GPR-02 à Grande Prairie demande de l'attention. Avez-vous une minute ?", time_in_call_secs: 0 },
      { role: 'user', message: 'Oui.', time_in_call_secs: 7 },
      { role: 'agent', message: "Il lui reste environ 12 à 38 jours. La pression statique de sortie du compresseur baisse depuis sept jours. Quel est le premier jour où votre équipe peut intervenir ?", time_in_call_secs: 9 },
      { role: 'user', message: 'Pas avant vendredi.', time_in_call_secs: 22 },
      { role: 'agent', message: "Compris. GPR-02 passe à vendredi. Cela vous convient ?", time_in_call_secs: 26,
        tool_calls: [{ request_id: 'req_mock_2', tool_name: 'submit_availability', params_as_json: JSON.stringify({ unit_id: 'GPR-02', technician_id: '3', earliest_day_text: 'Pas avant vendredi' }), tool_has_been_called: true }],
        tool_results: [{ request_id: 'req_mock_2', tool_name: 'submit_availability', result_value: JSON.stringify({ ok: true, say: 'Compris. GPR-02 passe à vendredi. Cela vous convient ?' }), is_error: false, tool_latency_secs: 0.7 }] },
      { role: 'user', message: 'Oui, ça va.', time_in_call_secs: 34 },
      { role: 'agent', message: 'Merci, Marc. À bientôt.', time_in_call_secs: 37 },
    ],
  },
]
