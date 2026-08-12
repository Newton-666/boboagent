// Browser-mode gateway — connects to Python backend via WebSocket in dev mode.
// In production (Electron), the IPC-based gateway.ts is used instead.

type EventHandler = (data: Record<string, unknown>) => void

class BrowserGateway {
  private ws: WebSocket | null = null
  private handlers = new Map<string, EventHandler>()
  private reqId = 0
  private pending = new Map<string, (value: Record<string, unknown>) => void>()

  async connect(port = 9876) {
    return new Promise<void>((resolve) => {
      this.ws = new WebSocket(`ws://localhost:${port}`)
      this.ws.onopen = () => {
        console.log('[browser-gateway] Connected to backend')
        resolve()
      }
      this.ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)
          // Events: {method: "event", params: {type, payload}}
          // Responses: {id, result, error}
          const isEvent = msg.method === 'event'
          if (isEvent) {
            const eventType = msg.params?.type
            const handler = this.handlers.get(eventType)
            if (handler) {
              handler(msg.params?.payload || msg.params || {})
            }
            return
          }
          if (msg.id) {
            const resolve = this.pending.get(msg.id)
            if (resolve) {
              this.pending.delete(msg.id)
              resolve(msg.result || msg.error || {})
            }
          }
        } catch (e) {
          console.error('[browser-gateway] Message parse error:', e, event.data?.slice(0, 200))
        }
      }
      this.ws.onerror = () => {
        console.warn('[browser-gateway] WebSocket connection failed. For dev mode, run: python3 -m bobo_tui_gateway.entry')
      }
      this.ws.onclose = () => {
        console.log('[browser-gateway] Disconnected')
      }
      // Timeout
      setTimeout(() => resolve(), 2000)
    })
  }

  on(event: string, handler: EventHandler) {
    this.handlers.set(event, handler)
  }

  async call(method: string, params: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return { error: { code: -32000, message: 'WebSocket not connected' } }
    const id = `req-${++this.reqId}`
    return new Promise((resolve) => {
      this.pending.set(id, resolve)
      this.ws!.send(JSON.stringify({ jsonrpc: '2.0', id, method, params }))
      setTimeout(() => {
        this.pending.delete(id)
        resolve({ error: { code: -32000, message: 'Request timeout' } })
      }, 120000) // 120s timeout to match TUI
    })
  }

  send(msg: Record<string, unknown>) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg))
    }
  }

  subscribe(sessionId: string) {
    this.call('session.resume', { session_id: sessionId })
  }

  sendPrompt(sessionId: string, text: string) {
    this.send({
      jsonrpc: '2.0',
      id: `prompt-${++this.reqId}`,
      method: 'prompt.submit',
      params: { session_id: sessionId, text },
    })
  }

  disconnect() {
    this.ws?.close()
  }
}

export const browserGateway = new BrowserGateway()
