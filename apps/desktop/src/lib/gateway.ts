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

  connect() {
    this.unsubMessage = window.boboAPI.onMessage((msg) => {
      // msg is a JSON-RPC response or event from the Python backend
      if (msg && typeof msg === 'object' && 'method' in msg) {
        // Event (notification)
        const event = msg as { method: string; params: Record<string, unknown> }
        const handler = this.handlers.get(event.method)
        if (handler) handler(event.params || {})
      }
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
  }

  on(event: string, handler: EventHandler) {
    this.handlers.set(event, handler)
  }

  // Send a JSON-RPC request and get a response
  async call(method: string, params: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
    const id = `req-${++this.reqId}`
    const msg = { jsonrpc: '2.0', id, method, params }

    return new Promise((resolve) => {
      const timeout = setTimeout(() => {
        resolve({ error: { code: -32000, message: 'Request timeout' } })
      }, 30000)

      const unsub = window.boboAPI.onMessage((response) => {
        if (response && typeof response === 'object' && 'id' in response) {
          const resp = response as { id: string; result?: Record<string, unknown>; error?: { message: string } }
          if (resp.id === id || resp.id === null) {
            clearTimeout(timeout)
            unsub()
            resolve(resp.result || { error: resp.error?.message })
          }
        }
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
    window.boboAPI.send({
      jsonrpc: '2.0',
      id: `prompt-${++this.reqId}`,
      method: 'prompt.submit',
      params: { session_id: sessionId, text },
    })
  }
}

export const gateway = new GatewayClient()
