// Adapted from interior.dev (MIT, (c) 2026 ozzy): https://github.com/ddoemonn/interior (loading-button.tsx)
import { useCallback, useEffect, useRef, useState } from 'react'

export type AsyncActionStatus = 'idle' | 'pending' | 'success' | 'error'

/** Runs an async action once at a time and walks idle -> pending -> success or error -> idle. A second click while pending is ignored. */
export function useAsyncAction({ action, resetAfter = 1400, onError }: { action: () => unknown; resetAfter?: number; onError?: (error: unknown) => void }) {
  const [status, setStatus] = useState<AsyncActionStatus>('idle')
  const phase = useRef<AsyncActionStatus>('idle')
  const runId = useRef(0)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const alive = useRef(true)
  const act = useRef(action)
  const fail = useRef(onError)
  useEffect(() => { act.current = action; fail.current = onError })
  const clear = useCallback(() => { if (timer.current) { clearTimeout(timer.current); timer.current = null } }, [])

  const run = useCallback(() => {
    if (phase.current === 'pending') return
    clear()
    const id = ++runId.current
    phase.current = 'pending'
    setStatus('pending')
    const settle = (next: 'success' | 'error') => {
      if (!alive.current || id !== runId.current) return
      clear()
      phase.current = next
      setStatus(next)
      timer.current = setTimeout(() => {
        if (!alive.current || id !== runId.current) return
        phase.current = 'idle'
        setStatus('idle')
      }, resetAfter)
    }
    Promise.resolve().then(() => act.current()).then(() => settle('success'), (error: unknown) => { fail.current?.(error); settle('error') })
  }, [clear, resetAfter])

  useEffect(() => { alive.current = true; return () => { alive.current = false; clear() } }, [clear])
  return { status, run, pending: status === 'pending' }
}
