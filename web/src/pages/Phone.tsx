import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { AnimatePresence, motion } from 'motion/react'
import { ConversationProvider, useConversationControls, useConversationInput, useConversationMode, useConversationStatus } from '@elevenlabs/react'
import PhoneCallI from '~icons/ph/phone-call'
import PhoneX from '~icons/ph/phone-x'
import Octagon from '~icons/ph/warning-octagon-fill'
import Check from '~icons/ph/check-circle-fill'
import MicOff from '~icons/ph/microphone-slash'
import Mic from '~icons/ph/microphone'
import { StatusPill } from '@/components/ui/status'
import { useTechnicians } from '@/lib/queries'
import { useFieldRing } from '@/lib/field'
import { startRinging, stopRinging, unlockAudio } from '@/lib/ringtone'
import { api } from '@/lib/api'
import { dur, ease, spring } from '@/design/motion'
import type { AnswerResponse, Language, RingEvent, TranscriptTurn, Verdict } from '@/lib/types'

// Technician phone page (DESIGN.md 5, 9.4; docs/delegation/03 section 4). One screen at a time.
//   gate -> idle -> ringing -> connecting -> in call -> after call -> thanks, with missed and problem screens off to the side.
// `?state=` (dev and mock builds only) jumps straight to a screen for design review, with a simulated call.
type Phase = 'gate' | 'idle' | 'ringing' | 'connecting' | 'incall' | 'after' | 'thanks' | 'missed' | 'problem'
const LANG: Record<Language, string> = { en: 'English', fr: 'French' }
const VERDICTS: { value: Verdict; label: string; hint: string }[] = [
  { value: 'confirmed_wear', label: 'Wear confirmed', hint: 'It was worn, as predicted' },
  { value: 'looks_fine', label: 'Looks fine', hint: 'Nothing wrong found' },
  { value: 'part_replaced', label: 'Part replaced', hint: 'I replaced a part' },
]
const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

export default function Phone() {
  return <ConversationProvider><PhoneApp /></ConversationProvider>
}

function PhoneApp() {
  const { fieldPageId = '' } = useParams()
  const [params] = useSearchParams()
  const preview = (import.meta.env.DEV || import.meta.env.VITE_MOCK === '1') ? (params.get('state') as Phase | null) : null
  const { data: techs } = useTechnicians()
  const tech = techs?.find((t) => t.field_page_id === fieldPageId)

  const [phase, setPhase] = useState<Phase>(preview ?? 'gate')
  const [mic, setMic] = useState<'unknown' | 'denied'>('unknown')
  const [problem, setProblem] = useState('')
  const [answering, setAnswering] = useState(false)
  const [muted, setMutedLocal] = useState(false)
  const [secs, setSecs] = useState(0)
  const [left, setLeft] = useState(0)
  const [lines, setLines] = useState<TranscriptTurn[]>([])
  const [verdict, setVerdict] = useState<Verdict | null>(null)
  const [verdictError, setVerdictError] = useState(false)
  const [language, setLanguage] = useState<Language>('en')
  const [previewRing, setPreviewRing] = useState<RingEvent | null>(null)
  const [simulated, setSimulated] = useState(!!preview)
  const [simSpeaking, setSimSpeaking] = useState(false)

  const { startSession, endSession, getId } = useConversationControls()
  const { status } = useConversationStatus()
  const { isSpeaking } = useConversationMode()
  const { setMuted } = useConversationInput()
  const { ring: liveRing, connected, finish, setBusy } = useFieldRing(fieldPageId, phase !== 'gate' && !preview)
  const ring = preview ? previewRing : liveRing
  const callRequest = useRef<number>(0)
  const endedByUser = useRef(false)
  const wakeLock = useRef<{ release: () => Promise<void> } | null>(null)
  const simScript = useRef<TranscriptTurn[]>([])

  // Design-review preview: a fake ring and a scripted transcript, loaded only on demand so mock data never ships to production.
  useEffect(() => {
    if (!preview) return
    void import('@/mocks/fixtures/ring').then((m) => { setPreviewRing(m.makeRing(fieldPageId, 30)); simScript.current = m.MOCK_TRANSCRIPT; setLines(m.MOCK_TRANSCRIPT.slice(0, 2)) })
  }, [preview, fieldPageId])

  // A ring arrives while we are waiting: ring the phone.
  useEffect(() => {
    if (ring && phase === 'idle') { setLanguage(ring.language); setPhase('ringing'); if (!preview) startRinging() }
  }, [ring, phase, preview])

  // Countdown. Reaching zero means the ring expired: the server already alerted the manager and tried the backup.
  useEffect(() => {
    if (phase !== 'ringing' || !ring) return
    const tick = () => {
      const s = Math.ceil((Date.parse(ring.expires_at) - Date.now()) / 1000)
      setLeft(s)
      if (s <= 0) { stopRinging(); if (!preview) finish(ring.call_request_id); setPhase('missed') }
    }
    tick(); const t = setInterval(tick, 500)
    return () => clearInterval(t)
  }, [phase, ring, finish, preview])
  useEffect(() => () => stopRinging(), [])

  // In call: elapsed timer, and a simulated conversation for the design preview and mock builds.
  useEffect(() => {
    if (phase !== 'incall') return
    setSecs(0)
    const t = setInterval(() => setSecs((s) => s + 1), 1000)
    return () => clearInterval(t)
  }, [phase])
  useEffect(() => {
    if (phase !== 'incall' || !simulated) return
    let i = Math.min(2, simScript.current.length)
    const t = setInterval(() => {
      if (i >= simScript.current.length) return
      const turn = simScript.current[i++]; setLines((l) => [...l, turn].slice(-4)); setSimSpeaking(turn.role === 'agent')
    }, 2200)
    return () => clearInterval(t)
  }, [phase, simulated])

  const releaseWake = useCallback(() => { void wakeLock.current?.release().catch(() => {}); wakeLock.current = null }, [])
  useEffect(() => () => releaseWake(), [releaseWake])

  async function goOnShift() {
    await unlockAudio() // a tap is required before a page may make sound; this is that tap
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true }) // ask now, so a permission prompt never interrupts a call
      stream.getTracks().forEach((t) => t.stop())
      setMic('unknown'); setPhase('idle')
    } catch { setMic('denied') }
  }

  // True once the voice session has connected. After that, a library error must not throw away a call that went fine (see onError below).
  const connectedOnce = useRef(false)
  const post = (path: string, body: unknown) => api(`/field/${fieldPageId}/${path}`, { method: 'POST', body: JSON.stringify(body) }).catch(() => undefined)
  const toProblem = (msg: string) => { stopRinging(); releaseWake(); setBusy(false); setProblem(msg); setPhase('problem') }

  async function answer() {
    if (!ring || answering) return // a double tap must not start two calls
    setAnswering(true); stopRinging(); callRequest.current = ring.call_request_id
    if (preview) { setSimulated(true); setBusy(true); setPhase('incall'); setAnswering(false); return }
    try {
      setBusy(true)
      const res = await api<AnswerResponse>(`/field/${fieldPageId}/answer`, { method: 'POST', body: JSON.stringify({ call_request_id: ring.call_request_id }) })
      finish(ring.call_request_id); setLanguage(res.language); setLines([]); endedByUser.current = false; setPhase('connecting')
      if (res.signed_url.startsWith('wss://mock.invalid')) { // the mock backend hands out a fake URL: play a scripted call instead
        const m = await import('@/mocks/fixtures/ring'); simScript.current = m.MOCK_TRANSCRIPT; setSimulated(true); setPhase('incall'); return
      }
      setSimulated(false); connectedOnce.current = false
      startSession({
        signedUrl: res.signed_url, dynamicVariables: res.dynamic_variables, overrides: { agent: { language: res.language } },
        onConnect: () => {
          connectedOnce.current = true; setPhase('incall'); void post('conversation', { call_request_id: callRequest.current, conversation_id: getId() })
          void (navigator as unknown as { wakeLock?: { request: (t: 'screen') => Promise<{ release: () => Promise<void> }> } }).wakeLock?.request('screen').then((l) => { wakeLock.current = l }).catch(() => {})
        },
        onDisconnect: (d?: { reason?: string }) => {
          releaseWake(); setBusy(false); void post('conversation', { call_request_id: callRequest.current, conversation_id: getId(), ended: true })
          if (d?.reason === 'error' && !endedByUser.current) toProblem('The call dropped. Your answers are not lost: tell us what you found below.')
          else setPhase('after')
        },
        // Found on a real phone call (Oct 4): after the agent ended the call, the library failed while closing the connection, called onDisconnect
        // (-> the thanks screen) and then onError, which flipped the page to "Something went wrong" although the call was perfect. Once a call has
        // connected, an error is only logged; onDisconnect decides what the person sees. Before it connects, it is a real failure.
        onError: (message?: string) => { if (connectedOnce.current) { console.warn('voice session error after connect (ignored):', message); return } toProblem('We could not connect the call. Tell us what you found below, and your manager will follow up.') },
        onMessage: (m: { source?: string; role?: string; message?: string }) => { if (m.message) setLines((l) => [...l, { role: (m.role ?? m.source) === 'user' ? ('user' as const) : ('agent' as const), message: m.message ?? '', time_in_call_secs: 0 }].slice(-4)) },
      })
    } catch (e) {
      setBusy(false)
      toProblem(/\b(409|410)\b/.test(String(e)) ? 'That call has already ended or was taken by someone else.' : 'We could not start the call. Tell us what you found below, and your manager will follow up.')
    } finally { setAnswering(false) }
  }

  function decline() { stopRinging(); if (ring && !preview) { finish(ring.call_request_id); void post('decline', { call_request_id: ring.call_request_id }) } setPhase('idle') }
  function endCall() { endedByUser.current = true; if (simulated) { setBusy(false); setPhase('after') } else endSession() }
  async function sendVerdict(v: Verdict) {
    setVerdict(v); setVerdictError(false)
    try { if (!preview) await api(`/field/${fieldPageId}/feedback`, { method: 'POST', body: JSON.stringify({ call_request_id: callRequest.current, verdict: v }) }); setTimeout(() => setPhase('thanks'), 450) }
    catch { setVerdict(null); setVerdictError(true) }
  }
  function backToWaiting() { setVerdict(null); setLines([]); setBusy(false); setPhase('idle') }

  const speaking = simulated ? simSpeaking : isSpeaking
  const header = ring?.station_name ?? (tech ? { EDS: 'Edson', HIN: 'Hinton', WHT: 'Whitecourt', GPR: 'Grande Prairie', DRH: 'Drumheller' }[tech.station_code] : '') ?? ''

  return (
    <div className="mx-auto flex min-h-[100dvh] max-w-[430px] flex-col bg-canvas px-[22px] pb-[max(24px,env(safe-area-inset-bottom))] pt-[max(20px,env(safe-area-inset-top))]">
      <header className="flex items-center justify-center gap-2 text-sm text-muted"><img src="/logo-mark.svg" width={22} height={22} alt="" />PipeGuard{header ? ` · ${header}` : ''}</header>
      <AnimatePresence mode="wait" initial={false}>
        <motion.main key={phase} className="flex flex-1 flex-col" initial={{ opacity: 0, y: phase === 'ringing' ? 40 : 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4, transition: { duration: dur.fast, ease: ease.exit } }}
          transition={phase === 'ringing' ? spring.panel : { duration: dur.base, ease: ease.out }}>

          {phase === 'gate' && (
            <div className="flex flex-1 flex-col items-center justify-center text-center">
              <img src="/brand/empty-waiting-for-call.webp" width={220} height={165} alt="" className="mix-blend-multiply" />
              <h1 className="m-0 mt-2 text-[28px] leading-9 text-ink [font-weight:var(--w-strong)]">{tech ? `Hi ${tech.name.split(' ')[0]}` : 'Ready for calls?'}</h1>
              <p className="m-0 mt-2 max-w-[320px] text-[15px] text-muted">Tap below to go on shift. This turns the ringtone on and asks for your microphone now, so nothing interrupts a call later.</p>
              <button type="button" onClick={goOnShift} className="mt-6 min-h-14 w-full max-w-[320px] rounded-full bg-accent px-6 text-[17px] text-white transition-transform duration-[90ms] active:scale-[0.98] [font-weight:var(--w-strong)]">I&rsquo;m on shift</button>
              {mic === 'denied' && (
                <div role="alert" className="mt-4 flex max-w-[320px] items-start gap-2.5 rounded-2xl bg-[image:var(--g-attn)] px-4 py-3 text-left text-sm text-ink">
                  <MicOff width={18} height={18} className="mt-0.5 flex-none text-risk" aria-hidden />
                  <span><b className="block [font-weight:var(--w-strong)]">The microphone is blocked</b>PipeGuard needs it to talk to you. Allow the microphone for this site (tap the lock or settings icon next to the web address, or Settings, then Safari or Chrome, then Microphone), then tap again.</span>
                </div>
              )}
            </div>
          )}

          {phase === 'idle' && (
            <div className="flex flex-1 flex-col items-center justify-center text-center">
              <img src="/brand/empty-waiting-for-call.webp" width={240} height={180} alt="" className="mix-blend-multiply" />
              <h1 className="m-0 mt-2 text-[28px] font-[480] leading-9 text-ink [font-weight:var(--w-strong)]">No calls right now</h1>
              <p className="m-0 mt-2 max-w-[300px] text-[15px] text-muted">Keep this page open. If a unit needs attention, your phone will ring here.</p>
              <p className="m-0 mt-5 flex items-center gap-2 text-sm text-ok"><Check width={16} height={16} aria-hidden />{tech ? `On shift: ${tech.name}` : 'On shift'}</p>
              {tech && <p className="m-0 mt-1 text-[13px] text-muted">{tech.shift === 'day' ? 'Day shift' : 'Night shift'} · Calls in {LANG[tech.language]}</p>}
              {!preview && !connected && <p role="status" className="m-0 mt-3 text-[13px] text-muted">Reconnecting. Your phone will still ring when it is back.</p>}
            </div>
          )}

          {phase === 'ringing' && ring && (
            <>
              <section className="px-1.5 pt-12 text-center" aria-live="polite">
                <p className="m-0 text-sm text-muted">Incoming call · {LANG[ring.language]}</p>
                <h1 className="m-0 my-1.5 text-[30px] leading-9 text-ink [font-weight:var(--w-strong)]">Unit {ring.unit_id} needs attention</h1>
                <div className="mt-2 flex justify-center"><StatusPill status="at_risk" label={`At risk · ${Math.round(ring.rul_low)} to ${Math.round(ring.rul_high)} days`} /></div>
                <p className="tnum m-0 mt-2.5 text-sm text-muted">Ringing · answer within {Math.max(0, left)} s</p>
              </section>
              <div className="mt-[22px] rounded-2xl p-3.5 text-[15px] shadow-card"><div className="mb-1 text-sm text-ink [font-weight:var(--w-strong)]">Why</div>{ring.reason}</div>
              <div className="mt-4 flex items-center gap-3.5 rounded-2xl bg-[image:var(--g-attn)] px-[22px] py-3.5 text-ink">
                <span className="grid size-9 flex-none place-items-center rounded-full bg-white/80 text-risk"><Octagon width={18} height={18} aria-hidden /></span>
                <b className="[font-weight:var(--w-strong)]">Can your crew service it soon?</b>
              </div>
              <div className="mt-auto flex justify-between px-[30px] pt-8">
                <CallButton label="Decline" tone="decline" onClick={decline} disabled={answering} />
                <CallButton label="Answer" tone="answer" ring onClick={answer} disabled={answering} />
              </div>
            </>
          )}

          {phase === 'connecting' && (
            <div className="flex flex-1 flex-col items-center justify-center text-center" role="status">
              <h1 className="m-0 text-[28px] leading-9 text-ink [font-weight:var(--w-strong)]">Connecting…</h1>
              <p className="m-0 mt-2 text-[15px] text-muted">Putting you through to PipeGuard.</p>
            </div>
          )}

          {phase === 'incall' && (
            <>
              <section className="px-1.5 pt-10 text-center">
                <p className="m-0 text-sm text-muted">{simulated || status === 'connected' ? 'In call with PipeGuard' : 'Connecting…'} · {LANG[language]}</p>
                <h1 className="tnum m-0 my-1 text-[34px] leading-10 text-ink [font-weight:var(--w-strong)]">{mmss(secs)}</h1>
                <div className={`pg-bars mt-2 inline-flex h-7 items-center gap-1 ${speaking ? '' : 'idle'}`} role="status" aria-label={speaking ? 'PipeGuard is speaking' : 'Listening'}>
                  {[0, 1, 2].map((i) => <span key={i} className="pg-bar h-6 w-1.5 rounded-full bg-accent" />)}
                </div>
                <p className="m-0 mt-1 text-sm text-muted">{speaking ? 'PipeGuard is speaking' : muted ? 'Your microphone is muted' : 'Listening'}</p>
              </section>
              <ol className="m-0 mt-5 flex list-none flex-col gap-2.5 p-0" aria-label="Live transcript">
                {lines.slice(-3).map((m, i) => <li key={`${i}-${m.message.slice(0, 12)}`} className={`max-w-[88%] rounded-2xl px-3.5 py-2.5 text-[15px] ${m.role === 'agent' ? 'self-start bg-pill text-ink' : 'self-end bg-accent-soft text-accent-ink'}`}>{m.message}</li>)}
              </ol>
              <div className="mt-auto flex items-end justify-center gap-10 pt-8">
                <button type="button" aria-pressed={muted} onClick={() => { const v = !muted; setMutedLocal(v); if (!simulated) setMuted(v) }} aria-label={muted ? 'Unmute microphone' : 'Mute microphone'}
                  className={`grid size-14 place-items-center rounded-full transition-colors ${muted ? 'bg-ink text-white' : 'bg-pill text-ink'}`}>{muted ? <MicOff width={24} height={24} aria-hidden /> : <Mic width={24} height={24} aria-hidden />}</button>
                <CallButton label="End call" tone="decline" onClick={endCall} />
              </div>
            </>
          )}

          {(phase === 'after' || phase === 'problem') && (
            <>
              <section className="px-1.5 pt-12 text-center" role={phase === 'problem' ? 'alert' : undefined}>
                <h1 className="m-0 text-[28px] leading-9 text-ink [font-weight:var(--w-strong)]">{phase === 'problem' ? 'Something went wrong' : 'Thanks. Plan updated.'}</h1>
                <p className="m-0 mt-2 text-[15px] text-muted">{phase === 'problem' ? problem : 'One tap helps PipeGuard learn. You can skip this.'}</p>
              </section>
              <h2 className="m-0 mb-2.5 mt-7 text-base text-ink [font-weight:var(--w-strong)]">What did you find{ring?.unit_id ? ` on ${ring.unit_id}` : ''}?</h2>
              <div className="flex flex-col gap-2.5">
                {VERDICTS.map((v, i) => (
                  <motion.button key={v.value} type="button" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: dur.base, ease: ease.out, delay: i * 0.04 }}
                    onClick={() => sendVerdict(v.value)} aria-pressed={verdict === v.value}
                    className={`flex min-h-16 items-center gap-3 rounded-2xl px-[18px] text-left shadow-card transition-[transform,background-color] duration-150 active:scale-[0.98] ${verdict === v.value ? 'bg-accent-soft' : 'bg-canvas'}`}>
                    <span className="flex-1"><b className="block text-ink [font-weight:var(--w-strong)]">{v.label}</b><span className="text-sm text-muted">{v.hint}</span></span>
                    {verdict === v.value && <Check width={24} height={24} className="text-ok" aria-hidden />}
                  </motion.button>
                ))}
              </div>
              {verdictError && <p role="alert" className="m-0 mt-3 text-sm text-risk">That did not send. Check your connection and tap again.</p>}
              <button type="button" onClick={() => (phase === 'problem' ? backToWaiting() : setPhase('thanks'))} className="mx-auto mt-auto min-h-12 px-6 pt-6 text-[15px] text-accent-ink [font-weight:var(--w-strong)]">{phase === 'problem' ? 'Back to waiting' : 'Skip'}</button>
            </>
          )}

          {phase === 'missed' && (
            <div className="flex flex-1 flex-col items-center justify-center text-center" role="status">
              <span className="grid size-14 place-items-center rounded-full bg-warn-tint text-warn"><PhoneX width={28} height={28} aria-hidden /></span>
              <h1 className="m-0 mt-4 text-[28px] leading-9 text-ink [font-weight:var(--w-strong)]">Call missed</h1>
              <p className="m-0 mt-2 max-w-[300px] text-[15px] text-muted">Nobody picked up in time. Your manager has been told and the backup technician is being called.</p>
              <button type="button" onClick={backToWaiting} className="mt-6 min-h-12 rounded-full bg-pill px-6 text-ink [font-weight:var(--w-strong)]">Back to waiting</button>
            </div>
          )}

          {phase === 'thanks' && (
            <div className="flex flex-1 flex-col items-center justify-center text-center">
              <img src="/brand/empty-all-clear.webp" width={240} height={180} alt="" className="mix-blend-multiply" />
              <h1 className="m-0 mt-2 text-[28px] leading-9 text-ink [font-weight:var(--w-strong)]">All done</h1>
              <p className="m-0 mt-2 max-w-[300px] text-[15px] text-muted">Thank you. We will call again if anything changes.</p>
              <button type="button" onClick={backToWaiting} className="mt-6 min-h-12 rounded-full bg-pill px-6 text-ink [font-weight:var(--w-strong)]">Back to waiting</button>
            </div>
          )}
        </motion.main>
      </AnimatePresence>
    </div>
  )
}

/** 78px round call button with a label. The Answer button gets two expanding rings while the phone rings. */
function CallButton({ label, tone, ring, onClick, disabled }: { label: string; tone: 'answer' | 'decline'; ring?: boolean; onClick: () => void; disabled?: boolean }) {
  const Icon = tone === 'answer' ? PhoneCallI : PhoneX
  const bg = tone === 'answer' ? 'bg-ok-fill' : 'bg-risk-fill'
  return (
    <div className="flex flex-col items-center">
      <div className="relative grid size-[78px] place-items-center">
        {ring && !disabled && <><span aria-hidden className={`pg-ring absolute inset-0 rounded-full ${bg}`} /><span aria-hidden className={`pg-ring d2 absolute inset-0 rounded-full ${bg}`} /></>}
        <button type="button" onClick={onClick} disabled={disabled} aria-label={label} className={`relative grid size-[78px] place-items-center rounded-full text-white transition-transform duration-[90ms] active:scale-[0.94] disabled:opacity-60 ${bg}`}><Icon width={34} height={34} aria-hidden /></button>
      </div>
      <span className="mt-2 text-ink [font-weight:var(--w-strong)]">{label}</span>
    </div>
  )
}
