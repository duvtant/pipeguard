// ONE shared EventSource for the whole app (never one per component).
// TODO (David): de-duplicate by event_id, reconnect with Last-Event-ID, polling fallback
// on /api/events?after_id= if SSE cannot connect. See guide section 3.2.
export {}
