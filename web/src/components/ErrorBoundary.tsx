import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Card } from '@/components/ui/Card'
import { Chip } from '@/components/ui/Chip'
import Octagon from '~icons/ph/warning-octagon-fill'

/** Keeps a crash on one page from blanking the whole app: the shell and navigation stay, and the page offers a retry. */
export class ErrorBoundary extends Component<{ children: ReactNode; resetKey?: string }, { error: Error | null }> {
  state = { error: null as Error | null }
  static getDerivedStateFromError(error: Error) { return { error } }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error('Page crashed:', error, info.componentStack) }
  componentDidUpdate(prev: { resetKey?: string }) { if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null }) } // navigating away clears it
  render() {
    if (!this.state.error) return this.props.children
    return (
      <Card className="max-w-[520px]">
        <div className="flex items-start gap-3">
          <span className="grid size-8 flex-none place-items-center rounded-full bg-risk-tint text-risk"><Octagon width={16} height={16} aria-hidden /></span>
          <div role="alert">
            <h2 className="m-0 text-[15px] [font-weight:var(--w-strong)] text-ink">This page hit a problem</h2>
            <p className="m-0 mt-1 text-sm text-muted">The rest of PipeGuard is fine. Try again, or open another page from the menu.</p>
            <div className="mt-3 flex gap-2"><Chip primary onClick={() => this.setState({ error: null })}>Try again</Chip><Chip onClick={() => location.reload()}>Reload</Chip></div>
          </div>
        </div>
      </Card>
    )
  }
}
