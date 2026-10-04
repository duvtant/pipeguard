import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Link, type LinkProps } from 'react-router-dom'
import { cx } from './Card'

/** Pill-shaped quick action. `primary` is the single solid accent action on a page. */
const chipClass = (primary?: boolean, quiet?: boolean, className?: string) => cx(
  'inline-flex min-h-8 items-center gap-1.5 rounded-full px-3.5 text-sm transition-[background-color,transform] duration-150 ease-[var(--ease-out)] active:scale-[0.98] disabled:opacity-60',
  primary ? 'bg-accent [font-weight:var(--w-strong)] text-white hover:bg-accent-ink' : quiet ? 'bg-transparent text-ink hover:bg-pill' : 'bg-pill text-ink hover:bg-line',
  className,
)
const Ic = ({ icon }: { icon?: ReactNode }) => (icon ? <span className="grid place-items-center" aria-hidden>{icon}</span> : null)

export function Chip({ icon, primary, quiet, className, children, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { icon?: ReactNode; primary?: boolean; quiet?: boolean }) {
  return <button type="button" {...rest} className={chipClass(primary, quiet, className)}><Ic icon={icon} />{children}</button>
}

export function ChipLink({ icon, primary, quiet, className, children, ...rest }: LinkProps & { icon?: ReactNode; primary?: boolean; quiet?: boolean }) {
  return <Link {...rest} className={chipClass(primary, quiet, className)}><Ic icon={icon} />{children}</Link>
}
