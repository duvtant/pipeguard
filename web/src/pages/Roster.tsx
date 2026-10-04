import { motion } from 'motion/react'
import { Card, CardHeader } from '@/components/ui/Card'
import { Avatar } from '@/components/ui/Avatar'
import { Skeleton } from '@/components/ui/Skeleton'
import { useTechnicians } from '@/lib/queries'
import { pageItem } from '@/design/motion'
import { cx } from '@/components/ui/Card'

const STATION_NAME: Record<string, string> = { EDS: 'Edson', HIN: 'Hinton', WHT: 'Whitecourt', GPR: 'Grande Prairie', DRH: 'Drumheller' }

export default function Roster() {
  const { data, isError } = useTechnicians()
  const online = data?.filter((t) => t.online).length ?? 0
  return (
    <div>
      <h1 className="m-0 mb-1 text-[28px] [font-weight:var(--w-body)] leading-9 tracking-[-0.01em] text-ink">Roster</h1>
      <p className="m-0 mb-5 text-sm text-muted">{data ? `${online} of ${data.length} technicians are on shift right now. The agent calls the on-shift technician for the unit's station, then the backup.` : ' '}</p>
      <motion.div {...pageItem(0)}>
        <Card pad={false}>
          <div className="px-6 pt-5"><CardHeader title="Technicians" /></div>
          {isError ? <p role="alert" className="m-0 px-6 pb-5 text-sm text-risk">Could not load the roster.</p> : !data ? <div className="space-y-2 px-6 pb-5">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-10" />)}</div> : (
            <table className="w-full text-left text-sm">
              <caption className="sr-only">Technicians, their stations, shifts, languages and whether they are on shift</caption>
              <thead className="text-[13px] text-muted"><tr className="border-b border-line"><th className="px-6 py-2 [font-weight:var(--w-body)]">Technician</th><th className="py-2 [font-weight:var(--w-body)]">Station</th><th className="py-2 [font-weight:var(--w-body)]">Shift</th><th className="py-2 [font-weight:var(--w-body)]">Language</th><th className="px-6 py-2 [font-weight:var(--w-body)]">Status</th></tr></thead>
              <tbody>
                {[...data].sort((a, b) => a.station_code.localeCompare(b.station_code) || Number(a.is_backup) - Number(b.is_backup)).map((t, i) => (
                  <tr key={t.id} className="border-b border-line last:border-b-0">
                    <td className="px-6 py-2.5"><span className="flex items-center gap-3"><Avatar letter={t.name[0]} tone={i} size={36} src={`/people/tech-${t.id}.jpg`} /><span><span className="text-ink">{t.name}</span>{t.is_backup && <span className="ml-2 rounded-full bg-pill px-2 py-0.5 text-[13px] text-muted">Backup</span>}</span></span></td>
                    <td className="text-text">{STATION_NAME[t.station_code] ?? t.station_code}</td>
                    <td className="text-text">{t.shift === 'day' ? 'Day' : 'Night'}</td>
                    <td><span className="rounded-full bg-accent-soft px-2.5 py-0.5 text-[13px] text-accent-ink [font-weight:var(--w-strong)]">{t.language === 'fr' ? 'French' : 'English'}</span></td>
                    <td className="px-6"><span className={cx('inline-flex items-center gap-1.5', t.online ? 'text-ok' : 'text-muted')}><span aria-hidden className={cx('size-2 rounded-full', t.online ? 'bg-ok-fill' : 'bg-sens-fill')} />{t.online ? 'On shift' : 'Off shift'}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </motion.div>
    </div>
  )
}
