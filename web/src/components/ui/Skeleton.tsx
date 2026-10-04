import { cx } from './Card'

/** Loading placeholder shaped like the final content, in --pill. Never a spinner over a blank page. */
export const Skeleton = ({ className }: { className?: string }) => <div aria-hidden className={cx('rounded-xl bg-pill', className)} />
