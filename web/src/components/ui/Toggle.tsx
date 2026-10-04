import { cx } from './Card'

/** On/off switch: a real button with role="switch", so it works with keyboard and screen readers. Label text sits beside it. */
export function Toggle({ checked, onChange, label, hint, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; hint?: string; disabled?: boolean }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} disabled={disabled} onClick={() => onChange(!checked)}
      className="flex w-full items-center gap-4 rounded-[12px] px-1 py-2 text-left disabled:opacity-50">
      <span className="min-w-0 flex-1"><span className="block text-[15px] text-ink">{label}</span>{hint && <span className="block text-[13px] text-muted">{hint}</span>}</span>
      <span aria-hidden className={cx('relative h-6 w-10 flex-none rounded-full transition-colors duration-150', checked ? 'bg-accent' : 'bg-line')}>
        <span className={cx('absolute top-0.5 size-5 rounded-full bg-white shadow-[0_1px_3px_rgba(8,9,17,0.3)] transition-transform duration-150 ease-[var(--ease-out)]', checked ? 'translate-x-[18px]' : 'translate-x-0.5')} />
      </span>
      <span className="sr-only">{checked ? 'On' : 'Off'}</span>
    </button>
  )
}
