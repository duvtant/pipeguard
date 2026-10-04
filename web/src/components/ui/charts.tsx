import { useEffect, useId, useState } from 'react'
import { Area, AreaChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, type TooltipContentProps } from 'recharts'
import { useReducedMotion } from 'motion/react'

// Charts, Mercury style (DESIGN.md 6): no gridlines, no axis lines, muted x labels, a gradient area
// that bleeds to the card edges, and a dark tooltip with colour keys. Live updates never re-animate.
/** True for the first draw only, so the line draws in once and later data changes do not replay it. */
function useFirstDraw() {
  const reduced = useReducedMotion()
  const [first, setFirst] = useState(true)
  useEffect(() => { const t = setTimeout(() => setFirst(false), 900); return () => clearTimeout(t) }, [])
  return first && !reduced
}

export interface TipRow { label: string; color: string; value: string }

export function DarkTip({ title, rows }: { title: string; rows: TipRow[] }) {
  return (
    <div className="min-w-[170px] rounded-[10px] bg-tip px-3 py-2.5 text-[13px] leading-5 text-white shadow-tip">
      <div className="mb-1 text-[#B9BDD3]">{title}</div>
      {rows.map((r) => (
        <div key={r.label} className="flex justify-between gap-5">
          <span><i className="mr-2 inline-block h-3 w-[3px] rounded-sm align-[-2px]" style={{ background: r.color }} />{r.label}</span>
          <b className="tnum font-semibold">{r.value}</b>
        </div>
      ))}
    </div>
  )
}

/** Evenly spaced x labels under a full-bleed plot (the plot touches the card edges; the labels keep the card padding). */
function XLabels({ labels }: { labels: string[] }) {
  return <div className="flex justify-between px-6 pt-2 text-[13px] text-muted" aria-hidden>{labels.map((l, i) => <span key={i}>{l}</span>)}</div>
}
const pick = (xs: string[], n: number) => xs.filter((_, i) => i % Math.max(1, Math.floor((xs.length - 1) / (n - 1))) === 0).slice(0, n)

export function AreaTrend({ data, label, unit = '', height = 190, xTicks = 5, bare = false }: {
  data: { x: string; y: number }[]; label: string; unit?: string; height?: number | '100%'; xTicks?: number
  /** Small inline chart: no x labels. */
  bare?: boolean
}) {
  const id = useId().replace(/:/g, '')
  const drawing = useFirstDraw()
  return (
    <div className={height === '100%' ? 'flex h-full min-h-[200px] flex-col' : undefined}>
    <div role="img" aria-label={label} className="pg-chart min-h-0 flex-1" style={height === '100%' ? undefined : { height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 0, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor="#5367EB" stopOpacity={0.22} />
              <stop offset="1" stopColor="#5367EB" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <XAxis dataKey="x" hide />
          <YAxis hide domain={['dataMin - 1', 'dataMax + 1']} />
          <Tooltip cursor={false} isAnimationActive={false} content={(p: TooltipContentProps) => p.active && p.payload?.length ? <DarkTip title={String(p.label)} rows={[{ label, color: '#5367EB', value: `${p.payload[0].value}${unit}` }]} /> : null} />
          <Area type="monotone" dataKey="y" stroke="var(--color-accent-line)" fill={`url(#${id})`} isAnimationActive={drawing} animationDuration={800} animationEasing="ease-out" dot={false} activeDot={{ r: 6, fill: '#fff', stroke: '#5367EB', strokeWidth: 3 }} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
    {!bare && <XLabels labels={pick(data.map((d) => d.x), xTicks)} />}
    </div>
  )
}

export interface CompareSeries { key: string; label: string; color: string; dashed?: boolean; strong?: boolean }

/** Impact comparison: three policies, PipeGuard strongest, gradient under PipeGuard only. */
export function CompareChart({ data, series, label, height = 210, format }: {
  data: Record<string, number | string>[]; series: CompareSeries[]; label: string; height?: number; format: (n: number) => string
}) {
  const id = useId().replace(/:/g, '')
  const drawing = useFirstDraw()
  const strong = series.find((s) => s.strong)
  return (
    <div>
    <div role="img" aria-label={label} className="pg-chart" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 0, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor="#5367EB" stopOpacity={0.24} />
              <stop offset="1" stopColor="#5367EB" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} horizontal={false} />
          <XAxis dataKey="x" hide />
          <YAxis hide domain={[0, 'dataMax']} />
          <Tooltip cursor={{ stroke: 'var(--color-line)' }} isAnimationActive={false} content={(p: TooltipContentProps) => p.active && p.payload?.length ? (
            <DarkTip title={String(p.label)} rows={series.map((s) => ({ label: s.label, color: s.color, value: format(Number(p.payload!.find((x) => x.dataKey === s.key)?.value ?? 0)) }))} />
          ) : null} />
          {strong && <Area type="monotone" dataKey={strong.key} stroke="none" fill={`url(#${id})`} isAnimationActive={false} legendType="none" tooltipType="none" />}
          {series.map((s) => (
            <Line key={s.key} type="monotone" dataKey={s.key} stroke={s.color} strokeWidth={s.strong ? 3 : 2.5} strokeDasharray={s.dashed ? '6 6' : undefined} dot={false}
              isAnimationActive={drawing} animationDuration={800} activeDot={{ r: s.strong ? 6 : 4, fill: '#fff', stroke: s.color, strokeWidth: 3 }} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
    <XLabels labels={pick(data.map((d) => String(d.x)), 5)} />
    </div>
  )
}
