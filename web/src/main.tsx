import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { MotionConfig } from 'motion/react'
import './index.css'
import { LiveProvider } from './lib/live'
import { ToastProvider } from './components/ui/Toast'
import App from './App.tsx'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 1000, refetchOnWindowFocus: false } },
})

// `pnpm dev:mock` (VITE_MOCK=1) serves the in-browser mock API (src/mocks) so every screen can be
// built before the real backend exists. Without it, /api is proxied to the real FastAPI service.
async function enableMocks() {
  if (import.meta.env.VITE_MOCK !== '1') return
  const { worker } = await import('./mocks/browser')
  ;(window as unknown as { __pgQc: QueryClient }).__pgQc = queryClient // lets the browser tests read the cache (mock builds only)
  await worker.start({ onUnhandledFrame: 'bypass' })
}

enableMocks().then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          {/* Honour the OS reduced-motion setting everywhere (DESIGN.md 9.5) */}
          <MotionConfig reducedMotion="user"><ToastProvider><LiveProvider><App /></LiveProvider></ToastProvider></MotionConfig>
        </BrowserRouter>
      </QueryClientProvider>
    </StrictMode>,
  )
})
