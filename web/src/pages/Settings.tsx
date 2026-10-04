import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'motion/react'
import { Card, CardHeader } from '@/components/ui/Card'
import { Slider } from '@/components/ui/Slider'
import { Toggle } from '@/components/ui/Toggle'
import { ActionButton } from '@/components/ui/ActionButton'
import { Chip } from '@/components/ui/Chip'
import { Skeleton } from '@/components/ui/Skeleton'
import { useToast } from '@/components/ui/Toast'
import { useSettings } from '@/lib/queries'
import { api } from '@/lib/api'
import { signOut } from '@/lib/auth'
import { useProjector } from '@/hooks/useProjector'
import { dollars } from '@/lib/format'
import { pageItem } from '@/design/motion'
import type { Settings as SettingsT } from '@/lib/types'

export default function Settings() {
  const { data: saved, isError } = useSettings()
  const [draft, setDraft] = useState<SettingsT | null>(null)
  const qc = useQueryClient()
  const toast = useToast()
  const navigate = useNavigate()
  const [projector, toggleProjector] = useProjector()
  useEffect(() => { if (saved && !draft) setDraft(saved) }, [saved, draft])
  const save = useMutation({
    mutationFn: (s: SettingsT) => api<SettingsT>('/settings', { method: 'PUT', body: JSON.stringify(s) }),
    onSuccess: (s) => { qc.setQueryData(['settings'], s); qc.invalidateQueries({ queryKey: ['plan'] }); toast.show({ title: 'Settings saved', detail: 'The plan will be recomputed with the new crew size.', tone: 'calm' }) },
  })
  const dirty = !!draft && !!saved && JSON.stringify(draft) !== JSON.stringify(saved)
  const set = <K extends keyof SettingsT>(k: K, v: SettingsT[K]) => setDraft((d) => (d ? { ...d, [k]: v } : d))

  return (
    <div>
      <h1 className="m-0 mb-1 text-[28px] [font-weight:var(--w-body)] leading-9 tracking-[-0.01em] text-ink">Settings</h1>
      <p className="m-0 mb-5 text-sm text-muted">These drive the planner and the agent&rsquo;s calls. Changes apply when you save.</p>
      {isError ? <p role="alert" className="text-sm text-risk">Could not load the settings.</p> : (
        <div className="grid gap-6 xl:grid-cols-2">
          <motion.div {...pageItem(0)}>
            <Card className="h-full"><CardHeader title="Crews and costs" />
              {!draft ? <Skeleton className="h-[220px]" /> : (<>
                <Slider className="mt-3" label="Crews per station" value={draft.crews_per_station} min={0} max={5} step={1} onValueChange={(v) => set('crews_per_station', v)} detents={[0, 1, 2, 3, 4, 5]} format={(v) => `${v} ${v === 1 ? 'crew' : 'crews'}`} />
                <Slider className="mt-3" label="Cost of a breakdown" value={draft.cost_breakdown} min={50_000} max={500_000} step={10_000} onValueChange={(v) => set('cost_breakdown', v)} detents={[{ value: 200_000, label: 'default' }]} format={dollars} />
                <Slider className="mt-3" label="Cost of a planned service" value={draft.cost_service} min={5_000} max={60_000} step={1_000} onValueChange={(v) => set('cost_service', v)} detents={[{ value: 20_000, label: 'default' }]} format={dollars} />
                <p className="m-0 mt-3 text-[13px] text-muted">Costs are illustrative. They decide when a service is worth doing.</p></>)}
            </Card>
          </motion.div>
          <motion.div {...pageItem(1)}>
            <Card className="h-full"><CardHeader title="Call rules" />
              {!draft ? <Skeleton className="h-[220px]" /> : (<>
                <Slider className="mt-3" label="How long a phone rings" value={draft.ring_timeout_secs} min={10} max={60} step={5} onValueChange={(v) => set('ring_timeout_secs', v)} detents={[{ value: 30, label: 'default' }]} format={(v) => `${v} seconds`} />
                <div className="mt-3"><Toggle label="Call the backup technician if nobody answers" hint="Then alert a manager if the backup misses it too." checked={draft.call_backup_when_missed} onChange={(v) => set('call_backup_when_missed', v)} /></div>
                <Toggle label="Ask a manager when no crew slot is free" hint="Otherwise the unit stays unscheduled and quietly waits." checked={draft.require_manager_for_conflicts} onChange={(v) => set('require_manager_for_conflicts', v)} /></>)}
            </Card>
          </motion.div>
          <motion.div {...pageItem(2)}>
            <Card><CardHeader title="Display" />
              <Toggle label="Projector mode" hint="Larger, higher-contrast interface for the judging room. Press P anywhere." checked={projector} onChange={toggleProjector} />
            </Card>
          </motion.div>
          <motion.div {...pageItem(3)}>
            <Card><CardHeader title="Account" /><p className="m-0 mb-3 text-sm text-muted">Signed in as the Maintenance Manager (demonstration only; there is no real password).</p>
              <Chip onClick={() => { signOut(); navigate('/signin') }}>Sign out</Chip></Card>
          </motion.div>
        </div>
      )}
      <div className="sticky bottom-0 mt-6 flex items-center gap-3 border-t border-line bg-canvas py-3">
        <ActionButton variant="primary" disabled={!dirty} onAction={() => save.mutateAsync(draft as SettingsT)} successLabel="Saved">Save changes</ActionButton>
        <Chip disabled={!dirty} onClick={() => setDraft(saved ?? null)}>Discard changes</Chip>
        {dirty && <span className="text-[13px] text-muted" role="status">You have unsaved changes.</span>}
      </div>
    </div>
  )
}
