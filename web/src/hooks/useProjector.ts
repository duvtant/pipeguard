import { useCallback, useEffect, useState } from 'react'

// Projector mode (DESIGN.md 3.4): stronger edges and darker secondary text for the judging room.
// Stored per browser; press P anywhere (outside a text field) to toggle.
const KEY = 'pg-projector'
const read = () => { try { return localStorage.getItem(KEY) === '1' } catch { return false } }

export function useProjector() {
  const [on, setOn] = useState(read)
  useEffect(() => {
    document.documentElement.dataset.projector = String(on)
    try { localStorage.setItem(KEY, on ? '1' : '0') } catch { /* private window: fine */ }
  }, [on])
  const toggle = useCallback(() => setOn((v) => !v), [])
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      if (e.metaKey || e.ctrlKey || e.altKey || (t && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)) || t?.isContentEditable) return
      if (e.key === 'p' || e.key === 'P') toggle()
    }
    addEventListener('keydown', h)
    return () => removeEventListener('keydown', h)
  }, [toggle])
  return [on, toggle] as const
}
