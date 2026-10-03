import { setupWorker } from 'msw/browser'
import { handlers } from './handlers'
import { sseHandlers } from './sse-handlers'

export const worker = setupWorker(...handlers, ...sseHandlers)
