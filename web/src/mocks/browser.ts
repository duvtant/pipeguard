import { setupWorker } from 'msw/browser'
import { handlers } from './handlers'
import { mockControls, sseHandlers } from './sse-handlers'

export const worker = setupWorker(...handlers, ...sseHandlers)
;(window as unknown as { __pgMock: typeof mockControls }).__pgMock = mockControls
