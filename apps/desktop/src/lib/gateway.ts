// Bobo Desktop — Gateway client (talks to Python backend via Electron IPC)
// Same JSON-RPC protocol as the terminal TUI.

declare global {
  interface Window {
    boboAPI: {
      send: (msg: Record<string, unknown>) => void
      onMessage: (callback: (msg: Record<string, unknown>) => void) => () => void
      onStatus: (callback: (data: { status: string; message?: string; code?: number }) => void) => () => void
      onLog: (callback: (data: { stream: string; text: string }) => void) => () => void
    }
  }
}

type EventHandler = (data: Record<string, unknown>) => void

class GatewayClient {
  private reqId = 0
  private handlers = new Map<string, EventHandler>()
  private unsubMessage: (() => void) | null = null
  private unsubStatus: (() => void) | null = null
  private pendingResponses = new Map<string, (value: Record<string, unknown>) => void>()

  private browserMode = false

  get isBrowserMode() { return this.browserMode }

  connect() {
    if (!window.boboAPI) {
      this.browserMode = true
      console.log('[gateway] Browser mode — no backend connection')
      return
    }
    this.unsubMessage = window.boboAPI.onMessage((msg) => {
      if (!msg || typeof msg !== 'object') return

      // 1) Events: {method: "event", params: {type: "...", payload: ...}}
      //    Must be checked FIRST — events may also carry an id field in some protocols
      const params = msg.params as { type?: string; payload?: Record<string, unknown> } | undefined
      if (msg.method === 'event' && params?.type) {
        const handler = this.handlers.get(params.type)
        if (handler) handler(params.payload || params)
        return
      }

      // 2) Response with id → resolve pending call()
      if ('id' in msg && msg.id) {
        const resolve = this.pendingResponses.get(msg.id as string)
        if (resolve) {
          this.pendingResponses.delete(msg.id as string)
          const resp = msg as { result?: Record<string, unknown>; error?: { message: string } }
          resolve(resp.result || { error: resp.error?.message || 'unknown error' })
          return
        }
        // Unknown id — could be a prompt.submit response we didn't await
        // Silently ignore (sendPrompt doesn't store a pending promise)
        return
      }

      // 3) Unrecognized message — log for debugging
      console.warn('[gateway] Unhandled message:', JSON.stringify(msg).slice(0, 200))
    })

    this.unsubStatus = window.boboAPI.onStatus((data) => {
      if (data.status === 'exited') {
        const handler = this.handlers.get('backend.exited')
        if (handler) handler(data)
      }
    })
  }

  disconnect() {
    this.unsubMessage?.()
    this.unsubStatus?.()
    // Reject all pending
    for (const resolve of this.pendingResponses.values()) {
      resolve({ error: { code: -32000, message: 'Gateway disconnected' } })
    }
    this.pendingResponses.clear()
  }

  on(event: string, handler: EventHandler) {
    this.handlers.set(event, handler)
  }

  // Send a JSON-RPC request and get a response
  async call(method: string, params: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
    if (this.browserMode || !window.boboAPI) return {}
    const id = `req-${++this.reqId}`
    const msg = { jsonrpc: '2.0', id, method, params }

    return new Promise((resolve) => {
      const timeout = setTimeout(() => {
        this.pendingResponses.delete(id)
        resolve({ error: { code: -32000, message: 'Request timeout' } })
      }, 120000) // 120s timeout to match TUI

      this.pendingResponses.set(id, (result) => {
        clearTimeout(timeout)
        resolve(result)
      })

      window.boboAPI.send(msg)
    })
  }

  // Subscribe to a session and start receiving events
  subscribe(sessionId: string) {
    this.call('session.activate', { session_id: sessionId })
  }

  // Send a prompt to the backend
  sendPrompt(sessionId: string, text: string) {
    if (this.browserMode || !window.boboAPI) return
    window.boboAPI.send({
      jsonrpc: '2.0',
      id: `prompt-${++this.reqId}`,
      method: 'prompt.submit',
      params: { session_id: sessionId, text },
    })
  }
}

export const gateway = new GatewayClient()
