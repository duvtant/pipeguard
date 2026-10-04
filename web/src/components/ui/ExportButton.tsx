import Download from '~icons/ph/download-simple'
import { ActionButton } from './ActionButton'
import { useToast } from './Toast'
import { downloadCsv, type CsvFile } from '@/lib/exportCsv'

/** "Export CSV" chip: same look and feedback as the Work orders download. `build` runs on click, so it always exports what is on screen now. */
export function ExportButton({ build, label = 'Export CSV', disabled }: { build: () => CsvFile | null; label?: string; disabled?: boolean }) {
  const toast = useToast()
  return (
    <ActionButton icon={<Download width={16} height={16} />} successLabel="Saved" disabled={disabled}
      onAction={() => {
        const file = build()
        if (!file) throw new Error('nothing to export')
        downloadCsv(file)
        toast.show({ title: 'Export saved', detail: `${file.filename} · ${file.rows.length} ${file.rows.length === 1 ? 'row' : 'rows'}`, tone: 'calm' })
      }}>{label}</ActionButton>
  )
}
