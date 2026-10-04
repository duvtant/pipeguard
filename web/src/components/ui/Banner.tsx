import { AnimatePresence, motion } from 'motion/react'
import { useLive } from '@/lib/live'
import { Strip } from './Strip'
import Cloud from '~icons/ph/cloud-slash'
import Wifi from '~icons/ph/wifi-high'
import { dur, ease } from '@/design/motion'

/** System notice across the top of the content (DESIGN.md 5.10): the live connection dropped, is being retried, or came back.
 *  The last known data stays on screen underneath. */
export function Banner() {
  const { banner, status } = useLive()
  const copy = banner === 'down'
    ? { tone: 'insight' as const, title: 'Reconnecting to live data', subtitle: status === 'polling' ? 'Showing the last known data, refreshing every few seconds.' : 'Showing the last known data. Updates resume on their own.', icon: <Wifi width={16} height={16} aria-hidden /> }
    : banner === 'offline'
      ? { tone: 'attention' as const, title: 'Cannot reach the server', subtitle: 'Showing the last known data. We keep trying.', icon: <Cloud width={16} height={16} aria-hidden /> }
      : banner === 'recovered' ? { tone: 'calm' as const, title: 'Back online', subtitle: 'Live updates have resumed.', icon: undefined } : null
  return (
    <div role="status" aria-live="polite">
      <AnimatePresence initial={false}>
        {copy && (
          <motion.div key={banner} initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8, transition: { duration: dur.fast, ease: ease.exit } }} transition={{ duration: dur.base, ease: ease.out }}>
            <Strip tone={copy.tone} title={copy.title} subtitle={copy.subtitle} icon={copy.icon} className="border-b border-line" />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
