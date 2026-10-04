import { Link } from 'react-router-dom'

export default function Placeholder({ title }: { title: string }) {
  return (
    <div>
      <h1 className="m-0 mb-2 text-[28px] [font-weight:var(--w-body)] leading-9 tracking-[-0.01em] text-ink">{title}</h1>
      <p className="m-0 text-muted">That page does not exist. <Link to="/" className="text-accent-ink underline">Back to the fleet</Link></p>
    </div>
  )
}
