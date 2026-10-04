import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import PhoneCall from '~icons/ph/phone-call'
import Flask from '~icons/ph/flask'
import Play from '~icons/ph/play-fill'
import Pause from '~icons/ph/pause-fill'
import Lock from '~icons/ph/lock-simple'
import ArrowLeft from '~icons/ph/arrow-left'
import { Card, CardHeader } from '@/components/ui/Card'
import { ActionButton } from '@/components/ui/ActionButton'
import { HoldToConfirm } from '@/components/ui/HoldToConfirm'
import { Segmented } from '@/components/ui/Segmented'
import { Chip } from '@/components/ui/Chip'
import { useToast } from '@/components/ui/Toast'
import { adminApi, useFaults, useFleet, useTechnicians, getAdminToken, setAdminToken } from '@/lib/queries'
import { api } from '@/lib/api'
import { SENSOR_LABELS } from '@/lib/sensors'
import { formatSimDate } from '@/lib/simCalendar'
import type { Fault, FaultType } from '@/lib/types'

// Test mode: the demo operator's console (kill a sensor, simulate a call, reset). Not in the manager's menu, and it needs the
// admin token, which is typed here and kept in sessionStorage only. It is never in the bundle (no VITE_ variable).
const FIELD: Record<FaultType, string> = { dead: 'sensor offline', stuck: 'sensor stuck', spike: 'sensor spiking', out_of_range: 'sensor out of range' }
const SELECT = 'h-9 min-w-0 rounded-[10px] border border-line bg-canvas px-3 text-sm text-ink outline-none focus-visible:border-accent'

function TokenGate({ onUnlock }: { onUnlock: () => void }) {
  const [token, setToken] = useState('')
  const [error, setError] = useState('')
  async function unlock() {
    setError(''); setAdminToken(token.trim())
    try { await adminApi('/testmode/faults'); onUnlock() }
    catch { setAdminToken(''); setError('That token was not accepted. Check it and try again.'); throw new Error('rejected') }
  }
  return (
    <Card className="max-w-[460px]">
      <div className="mb-1 flex items-center gap-2 text-[15px] text-ink"><Lock width={16} height={16} aria-hidden /><h2 className="m-0 text-[15px] [font-weight:var(--w-body)]">Admin token</h2></div>
      <p className="m-0 mb-3 text-sm text-muted">Test mode can reset the demo and break sensors, so it needs the admin token. It is kept in this tab only.</p>
      <form onSubmit={(e) => { e.preventDefault(); void unlock().catch(() => {}) }} className="flex flex-wrap items-center gap-2">
        <label className="sr-only" htmlFor="tok">Admin token</label>
        <input id="tok" type="password" autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)} placeholder="Paste the admin token" className={`${SELECT} flex-1`} />
        <ActionButton variant="primary" disabled={!token.trim()} onAction={unlock} successLabel="Unlocked" errorLabel="Rejected">Unlock</ActionButton>
      </form>
      {error && <p role="alert" className="m-0 mt-2 text-sm text-risk">{error}</p>}
    </Card>
  )
}

function Console({ onLock }: { onLock: () => void }) {
  const qc = useQueryClient()
  const toast = useToast()
  const { data: fleet } = useFleet()
  const { data: techs } = useTechnicians()
  const faults = useFaults(true)
  const units = fleet?.units ?? []
  const [unit, setUnit] = useState('HIN-05')
  const [sensor, setSensor] = useState('s3')
  const running = fleet?.clock.status === 'running'
  const active = (faults.data ?? []).filter((f) => f.end_day === null)
  const fallback = useMemo(() => units.filter((u) => u.data_source === 'fallback').length, [units])
  const refresh = () => { qc.invalidateQueries({ queryKey: ['fleet'] }); qc.invalidateQueries({ queryKey: ['faults'] }) }
  const rejected = (e: unknown) => { if (String(e).includes('401')) { setAdminToken(''); onLock() } }

  const addFault = useMutation({
    mutationFn: (type: FaultType) => adminApi<Fault>('/testmode/faults', { method: 'POST', body: JSON.stringify({ unit_id: unit, sensor, type }) }),
    onSuccess: (f) => { refresh(); toast.show({ title: `${f.unit_id}: ${FIELD[f.type]}`, detail: 'The unit turns grey with a wrench and no crew is called.', tone: 'info' }) },
    onError: rejected,
  })
  const endFault = useMutation({ mutationFn: (id: number) => adminApi(`/testmode/faults/${id}`, { method: 'DELETE' }), onSuccess: refresh, onError: rejected })
  const clock = useMutation({ mutationFn: (b: { action: 'play' | 'pause' | 'speed' | 'advance'; speed_seconds_per_day?: number; days?: number }) => api('/clock', { method: 'POST', body: JSON.stringify(b) }), onSuccess: refresh })

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card><CardHeader title="Replay clock" />
        <p className="m-0 mb-3 text-sm text-muted">{fleet ? `${running ? 'Running' : 'Paused'} · ${formatSimDate(fleet.sim_day)} (day ${fleet.sim_day})` : 'Loading…'}</p>
        <div className="flex flex-wrap items-center gap-2">
          <ActionButton variant="primary" icon={running ? <Pause width={16} height={16} /> : <Play width={16} height={16} />} onAction={() => clock.mutateAsync({ action: running ? 'pause' : 'play' })} successLabel={running ? 'Paused' : 'Playing'}>{running ? 'Pause' : 'Play'}</ActionButton>
          <ActionButton onAction={() => clock.mutateAsync({ action: 'advance', days: 1 })} successLabel="Advanced">Advance one day</ActionButton>
          <Segmented label="Replay speed" value={String(fleet?.clock.speed_seconds_per_day ?? 1)} onChange={(v) => clock.mutate({ action: 'speed', speed_seconds_per_day: Number(v) })}
            options={[{ value: '2', label: 'Slow', icon: <span className="text-[13px]">1×</span> }, { value: '1', label: 'Normal', icon: <span className="text-[13px]">2×</span> }, { value: '0.25', label: 'Fast', icon: <span className="text-[13px]">8×</span> }]} />
        </div>
      </Card>

      <Card><CardHeader title="Break a sensor" />
        <p className="m-0 mb-3 text-sm text-muted">&ldquo;PipeGuard knows a broken sensor isn&rsquo;t a broken turbine.&rdquo; The unit turns grey with a wrench within a tick or two, confidence goes low, and nobody is called.</p>
        <div className="flex flex-wrap items-center gap-2">
          <label className="sr-only" htmlFor="u">Unit</label>
          <select id="u" className={SELECT} value={unit} onChange={(e) => setUnit(e.target.value)}>{units.map((u) => <option key={u.unit_id} value={u.unit_id}>{u.unit_id}</option>)}{units.length === 0 && <option>{unit}</option>}</select>
          <label className="sr-only" htmlFor="s">Sensor</label>
          <select id="s" className={`${SELECT} max-w-[240px]`} value={sensor} onChange={(e) => setSensor(e.target.value)}>{Object.entries(SENSOR_LABELS).map(([id, l]) => <option key={id} value={id}>{l}</option>)}</select>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <ActionButton variant="primary" onAction={() => addFault.mutateAsync('dead')} successLabel="Sensor killed">Kill sensor</ActionButton>
          <ActionButton onAction={() => addFault.mutateAsync('spike')} successLabel="Sensor corrupted">Corrupt sensor</ActionButton>
        </div>
      </Card>

      <Card className="lg:col-span-2"><CardHeader title="Active faults" />
        {faults.isError ? <p role="alert" className="m-0 text-sm text-risk">Could not load the faults.</p> : active.length === 0 ? <p className="m-0 text-sm text-muted">No sensor faults right now.</p> : (
          <ul className="m-0 list-none p-0">
            {active.map((f) => (
              <li key={f.id} className="flex items-center gap-3 border-t border-line py-2 first:border-t-0">
                <span className="tnum text-sm [font-weight:var(--w-strong)] text-ink">{f.unit_id}</span><span className="text-sm text-muted">{SENSOR_LABELS[f.sensor] ?? f.sensor} · {FIELD[f.type]} · since day {f.start_day}{f.source === 'planted' ? ' · planted in the scenario' : ''}</span>
                <span className="ml-auto"><ActionButton onAction={() => endFault.mutateAsync(f.id)} successLabel="Ended">End fault</ActionButton></span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card><CardHeader title="Calls and tuning" />
        <p className="m-0 mb-3 text-sm text-muted">Simulate call replays the recorded real call, so the demo works without a phone. Tune now re-runs the self-tuning.</p>
        <div className="flex flex-wrap gap-2">
          <ActionButton variant="primary" icon={<PhoneCall width={16} height={16} />} onAction={() => adminApi('/admin/simulate-call', { method: 'POST' }).then(refresh).catch((e) => { rejected(e); throw e })} successLabel="Call replayed" pendingLabel="Calling">Simulate call</ActionButton>
          <ActionButton icon={<Flask width={16} height={16} />} onAction={() => adminApi<{ threshold: number; horizon_days: number }>('/admin/tune', { method: 'POST' }).then((r) => { toast.show({ title: 'Tuned', detail: `Alert threshold ${r.threshold.toFixed(2)}, plan ${r.horizon_days} days ahead.`, tone: 'calm' }) }).catch((e) => { rejected(e); throw e })} successLabel="Tuned" pendingLabel="Tuning">Tune now</ActionButton>
        </div>
        <h3 className="m-0 mb-1 mt-5 text-sm [font-weight:var(--w-strong)] text-ink">Technician phone pages</h3>
        <ul className="m-0 list-none p-0 text-sm">{(techs ?? []).filter((t) => !t.is_backup).map((t) => <li key={t.id} className="py-0.5"><a className="text-accent-ink" href={`/field/${t.field_page_id}`} target="_blank" rel="noreferrer">{t.name}</a><span className="text-muted"> · {t.language === 'fr' ? 'French' : 'English'}</span></li>)}</ul>
      </Card>

      <Card><CardHeader title="Reset" />
        <p className="m-0 mb-3 text-sm text-muted">Puts the whole demo back to day 0: the clock, the fleet, the plan and the log. It cannot be undone, so you have to hold the button.</p>
        <HoldToConfirm confirmLabel="Demo reset" onConfirm={() => { adminApi('/admin/reset', { method: 'POST' }).then(() => { qc.invalidateQueries(); toast.show({ title: 'Demo reset', detail: 'Everything is back at day 0.', tone: 'calm' }) }).catch(rejected) }}>Hold to reset demo</HoldToConfirm>
        <p className="m-0 mt-4 text-[13px] text-muted">{fallback > 0 ? `${fallback} ${fallback === 1 ? 'unit is' : 'units are'} using precomputed predictions because the live model is not answering.` : 'All units are using live predictions.'}</p>
      </Card>
    </div>
  )
}

export default function TestMode() {
  const [unlocked, setUnlocked] = useState(() => getAdminToken() !== '')
  return (
    <div className="min-h-[100dvh] bg-canvas">
      <header className="flex h-[61px] items-center gap-3 border-b border-line px-6">
        <img src="/logo-mark.svg" width={28} height={28} alt="" /><span className="[font-weight:var(--w-strong)] text-ink">PipeGuard</span><span className="rounded-full bg-warn-tint px-2.5 py-0.5 text-[13px] text-warn [font-weight:var(--w-strong)]">Test mode</span>
        <Link to="/" className="ml-auto inline-flex min-h-9 items-center gap-1.5 text-sm text-accent-ink"><ArrowLeft width={14} height={14} aria-hidden />Back to the dashboard</Link>
        {unlocked && <Chip onClick={() => { setAdminToken(''); setUnlocked(false) }}>Lock</Chip>}
      </header>
      <main className="mx-auto max-w-[1080px] px-6 py-8">
        <h1 className="m-0 mb-1 text-[28px] [font-weight:var(--w-body)] leading-9 tracking-[-0.01em] text-ink">Test mode</h1>
        <p className="m-0 mb-5 text-sm text-muted">For the person running the demo. Everything here is safe to use live.</p>
        {unlocked ? <Console onLock={() => setUnlocked(false)} /> : <TokenGate onUnlock={() => setUnlocked(true)} />}
      </main>
    </div>
  )
}
