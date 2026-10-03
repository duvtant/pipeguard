import { useState } from 'react'
import { ConversationProvider, useConversationControls, useConversationMode, useConversationStatus } from '@elevenlabs/react'

// DEV-ONLY smoke test (plan task P1.11): talk to the agent directly with a hand-minted signed URL, before the
// backend exists. Not part of the product, not styled on purpose (design is Phase 2). Route: /dev/voice
// Mint a URL:  ./scripts/signed-url      (valid 15 minutes)
const DEFAULT_VARS = {
  technician_id: '1', technician_name: 'Aiden', unit_id: 'EDS-07', station_name: 'Edson', rul_low: '14', rul_high: '35',
  reason: 'High-pressure compressor outlet temperature has risen for 6 days', proposed_day: 'Thursday',
  call_request_id: '0', sim_today: 'Tuesday, November 3',
}

function Session() {
  const { startSession, endSession, getId } = useConversationControls()
  const { status } = useConversationStatus()
  const { isSpeaking } = useConversationMode()
  const [signedUrl, setSignedUrl] = useState('')
  const [vars, setVars] = useState(JSON.stringify(DEFAULT_VARS, null, 2))
  const [lang, setLang] = useState<'en' | 'fr'>('en')
  const [log, setLog] = useState<string[]>([])
  const add = (s: string) => setLog((l) => [...l, s])

  async function start() {
    try {
      await navigator.mediaDevices.getUserMedia({ audio: true }) // ask for the mic up front, not mid-call
      startSession({
        signedUrl: signedUrl.trim(),
        dynamicVariables: JSON.parse(vars),
        overrides: { agent: { language: lang } },
        onConnect: () => add(`connected (conversation ${getId()})`),
        onDisconnect: () => add('disconnected'),
        onError: (m: unknown) => add(`error: ${String(m)}`),
        onMessage: (m: { source?: string; role?: string; message?: string }) => add(`${m.role ?? m.source}: ${m.message ?? ''}`),
      })
    } catch (e) {
      add(`could not start: ${String(e)}`)
    }
  }

  return (
    <div style={{ maxWidth: 720, margin: '24px auto', fontFamily: 'sans-serif' }}>
      <h1>Voice smoke test (dev only)</h1>
      <p>Status: <b>{status}</b> {isSpeaking ? '· agent speaking' : ''}</p>
      <input style={{ width: '100%' }} placeholder="wss://api.elevenlabs.io/... (from ./scripts/signed-url)" value={signedUrl} onChange={(e) => setSignedUrl(e.target.value)} />
      <p><label>Language <select value={lang} onChange={(e) => setLang(e.target.value as 'en' | 'fr')}><option value="en">en</option><option value="fr">fr</option></select></label></p>
      <textarea style={{ width: '100%', height: 220, fontFamily: 'monospace' }} value={vars} onChange={(e) => setVars(e.target.value)} />
      <p>
        <button onClick={start} disabled={!signedUrl || status === 'connected' || status === 'connecting'}>Start call</button>{' '}
        <button onClick={() => endSession()} disabled={status !== 'connected'}>End call</button>
      </p>
      <p>Wear headphones (the agent will hear itself otherwise). Say "Thursday", then "not before Friday". Tool calls will fail until the backend exists, which is expected.</p>
      <pre style={{ background: '#f4f4f4', padding: 8, minHeight: 120, whiteSpace: 'pre-wrap' }}>{log.join('\n')}</pre>
    </div>
  )
}

export default function VoiceSmoke() {
  return (
    <ConversationProvider>
      <Session />
    </ConversationProvider>
  )
}
