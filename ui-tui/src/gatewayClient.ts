import { type ChildProcess, spawn } from 'node:child_process'
import { EventEmitter } from 'node:events'
import { existsSync, unlinkSync } from 'node:fs'
import { type Socket, createConnection } from 'node:net'
import { tmpdir } from 'node:os'
import { delimiter, join, resolve } from 'node:path'
import { createInterface } from 'node:readline'

import type { GatewayEvent } from './gatewayTypes.js'
import { CircularBuffer } from './lib/circularBuffer.js'
import { recordParentLifecycle } from './lib/parentLog.js'

const MAX_GATEWAY_LOG_LINES = 200
const MAX_LOG_LINE_BYTES = 4096
const MAX_BUFFERED_EVENTS = 2000
const MAX_LOG_PREVIEW = 240
const STARTUP_TIMEOUT_MS = Math.max(5000, parseInt(process.env.BOBO_TUI_STARTUP_TIMEOUT_MS ?? '15000', 10) || 15000)
const REQUEST_TIMEOUT_MS = Math.max(30000, parseInt(process.env.BOBO_TUI_RPC_TIMEOUT_MS ?? '120000', 10) || 120000)
const WS_CONNECTING = 0
const WS_OPEN = 1
const WS_CLOSING = 2
const WS_CLOSED = 3

const truncateLine = (line: string) =>
  line.length > MAX_LOG_LINE_BYTES ? `${line.slice(0, MAX_LOG_LINE_BYTES)}… [truncated ${line.length} bytes]` : line

const describeChild = (proc: ChildProcess | null) => {
  if (!proc) {
    return 'pid=none'
  }

  return `pid=${proc.pid ?? 'unknown'} killed=${proc.killed} exitCode=${proc.exitCode ?? 'null'} signal=${proc.signalCode ?? 'null'}`
}

const resolveGatewayAttachUrl = () => {
  const raw = process.env.BOBO_TUI_GATEWAY_URL?.trim()

  return raw ? raw : null
}

const resolveSidecarUrl = () => {
  const raw = process.env.BOBO_TUI_SIDECAR_URL?.trim()

  return raw ? raw : null
}

const resolvePython = (root: string) => {
  const configured = process.env.BOBO_PYTHON?.trim() || process.env.PYTHON?.trim()

  if (configured) {
    return configured
  }

  const venv = process.env.VIRTUAL_ENV?.trim()

  const hit = [
    venv && resolve(venv, 'bin/python'),
    venv && resolve(venv, 'Scripts/python.exe'),
    resolve(root, '.venv/bin/python'),
    resolve(root, '.venv/bin/python3'),
    resolve(root, 'venv/bin/python'),
    resolve(root, 'venv/bin/python3')
  ].find(p => p && existsSync(p))

  return hit || (process.platform === 'win32' ? 'python' : 'python3')
}

const asGatewayEvent = (value: unknown): GatewayEvent | null =>
  value && typeof value === 'object' && !Array.isArray(value) && typeof (value as { type?: unknown }).type === 'string'
    ? (value as GatewayEvent)
    : null

const _wireDecoder = new TextDecoder()

const asWireText = (raw: unknown): string | null => {
  if (typeof raw === 'string') {
    return raw
  }

  if (raw instanceof ArrayBuffer || ArrayBuffer.isView(raw)) {
    return _wireDecoder.decode(raw as ArrayBufferLike)
  }

  return null
}

const _USERINFO_FALLBACK_RE = /^([a-z][a-z0-9+.-]*:\/\/)[^/?#@]*@/i

const redactUrl = (raw: string): string => {
  if (!raw) {
    return raw
  }

  try {
    const url = new URL(raw)
    const userInfo = url.username || url.password ? '***@' : ''
    const query = url.search ? '?***' : ''

    return `${url.protocol}//${userInfo}${url.host}${url.pathname}${query}`
  } catch {
    const noUserInfo = raw.replace(_USERINFO_FALLBACK_RE, '$1***@')
    const queryIdx = noUserInfo.indexOf('?')

    return queryIdx >= 0 ? `${noUserInfo.slice(0, queryIdx)}?***` : noUserInfo
  }
}

interface Pending {
  id: string
  method: string
  reject: (e: Error) => void
  resolve: (v: unknown) => void
  timeout: ReturnType<typeof setTimeout>
}

export class GatewayClient extends EventEmitter {
  private proc: ChildProcess | null = null
  private ws: WebSocket | null = null
  private wsConnectPromise: Promise<void> | null = null
  // TICKET-018：unix socket 传输。python bind/listen，node 只做连接方——
  // 管道 fd 被原生层误关（2026-07-31 连环死亡案）从此只是"客户端断开"，
  // 自动重连即可，gateway 进程不死、会话不丢。
  private sock: Socket | null = null
  private sockRl: ReturnType<typeof createInterface> | null = null
  private sockPath: string | null = null
  private socketDisabled = process.env.BOBO_DISABLE_SOCKET_TRANSPORT === '1'
  private sidecarWs: WebSocket | null = null
  private attachUrl: null | string = null
  private sidecarUrl: null | string = null
  private reqId = 0
  private logs = new CircularBuffer<string>(MAX_GATEWAY_LOG_LINES)
  private pending = new Map<string, Pending>()
  private bufferedEvents = new CircularBuffer<GatewayEvent>(MAX_BUFFERED_EVENTS)
  private pendingExit: number | null | undefined
  private ready = false
  private readyTimer: ReturnType<typeof setTimeout> | null = null
  private subscribed = false
  private stdoutRl: ReturnType<typeof createInterface> | null = null
  private stderrRl: ReturnType<typeof createInterface> | null = null

  constructor() {
    super()
    this.setMaxListeners(0)
  }

  private publish(ev: GatewayEvent) {
    if (ev.type === 'gateway.ready') {
      this.ready = true

      if (this.readyTimer) {
        clearTimeout(this.readyTimer)
        this.readyTimer = null
      }
    }

    if (this.subscribed) {
      return void this.emit('event', ev)
    }

    this.bufferedEvents.push(ev)
  }

  private clearReadyTimer() {
    if (this.readyTimer) {
      clearTimeout(this.readyTimer)
      this.readyTimer = null
    }
  }

  private closeSidecarSocket() {
    try {
      this.sidecarWs?.close()
    } catch {
    } finally {
      this.sidecarWs = null
    }
  }

  private closeGatewaySocket() {
    const ws = this.ws
    this.ws = null
    this.wsConnectPromise = null

    try {
      ws?.close()
    } catch {
    }
  }

  private resetStartupState() {
    this.rejectPending(new Error('gateway restarting'))
    this.ready = false
    this.bufferedEvents.clear()
    this.pendingExit = undefined
    this.stdoutRl?.close()
    this.stderrRl?.close()
    this.stdoutRl = null
    this.stderrRl = null
    this.clearReadyTimer()
    // socket 传输（TICKET-018）清理：先摘引用和监听器再 destroy，
    // 防止 close 事件触发重连逻辑（此处是主动替换，不是断线）
    const sock = this.sock
    this.sock = null
    this.sockRl?.close()
    this.sockRl = null
    sock?.removeAllListeners()
    sock?.destroy()
    this.sockPath = null
  }

  private startReadyTimer(python: string, cwd: string) {
    this.readyTimer = setTimeout(() => {
      if (this.ready) {
        return
      }

      const stderrTail = this.getLogTail(20)

      this.lifecycle(`[startup] timed out waiting for gateway.ready (python=${python}, cwd=${cwd})`)
      this.publish({
        type: 'gateway.start_timeout',
        payload: { cwd, python, stderr_tail: stderrTail }
      })
    }, STARTUP_TIMEOUT_MS)
  }

  private handleTransportExit(code: null | number, reason?: string) {
    this.clearReadyTimer()
    this.closeSidecarSocket()
    this.lifecycle(`[lifecycle] transport exit code=${code ?? 'null'} reason=${reason ?? 'none'}`)
    this.rejectPending(new Error(reason || `gateway exited${code === null ? '' : ` (${code})`}`))

    if (this.subscribed) {
      this.emit('exit', code)
    } else {
      this.pendingExit = code
    }
  }

  private connectSidecarMirror() {
    this.closeSidecarSocket()

    if (!this.sidecarUrl) {
      return
    }

    if (typeof WebSocket === 'undefined') {
      this.pushLog(`[sidecar] WebSocket unavailable; skipping mirror to ${redactUrl(this.sidecarUrl)}`)
      return
    }

    try {
      const ws = new WebSocket(this.sidecarUrl)

      this.sidecarWs = ws
      ws.addEventListener('close', () => {
        if (this.sidecarWs === ws) {
          this.sidecarWs = null
        }
      })
      ws.addEventListener('error', () => {
        this.pushLog('[sidecar] mirror connection error')
      })
    } catch (err) {
      this.pushLog(`[sidecar] failed to connect ${redactUrl(this.sidecarUrl)} (constructor error)`)
      this.sidecarWs = null
    }
  }

  private mirrorEventToSidecar(rawFrame: string) {
    const ws = this.sidecarWs

    if (!ws || ws.readyState !== WS_OPEN) {
      return
    }

    try {
      ws.send(rawFrame)
    } catch {
    }
  }

  private handleWebSocketFrame(raw: unknown) {
    const text = asWireText(raw)

    if (!text) {
      return
    }

    try {
      const frame = JSON.parse(text) as Record<string, unknown>

      if (frame.method === 'event') {
        this.mirrorEventToSidecar(text)
      }

      this.dispatch(frame)
    } catch {
      const preview = text.trim().slice(0, MAX_LOG_PREVIEW) || '(empty frame)'

      this.pushLog(`[protocol] malformed websocket frame: ${preview}`)
      this.publish({ type: 'gateway.protocol_error', payload: { preview } })
    }
  }

  private startSpawnedGateway(root: string) {
    const python = resolvePython(root)
    const cwd = process.env.BOBO_CWD || root
    const env = { ...process.env }
    const pyPath = env.PYTHONPATH?.trim()

    env.PYTHONPATH = pyPath ? `${root}${delimiter}${pyPath}` : root
    // TICKET-018：socket 模式——让 python 自己 bind/listen，node 仅作连接方
    const sockPath = this.socketDisabled ? null : join(tmpdir(), `bobo-gw-${process.pid}-${Date.now()}.sock`)
    if (sockPath) {
      env.BOBO_GW_SOCKET = sockPath
    }
    // TICKET-028：显式授权单实例守卫——只有 TUI 正规军 spawn 的 gateway
    // 才执行残留清理；测试/基准/其他 agent 的子进程不触发，防误杀
    env.BOBO_GW_GUARD = '1'
    this.startReadyTimer(python, cwd)
    this.proc = spawn(python, ['-m', 'bobo_tui_gateway.entry'], { cwd, env, stdio: ['pipe', 'pipe', 'pipe'] })
    this.lifecycle(`[lifecycle] spawned gateway child ${describeChild(this.proc)} python=${python} cwd=${cwd}${sockPath ? ' [socket 模式]' : ' [stdio 模式]'}`)

    if (sockPath) {
      this.connectSocketWithRetry(this.proc, sockPath, 0)
    }

    // 法医探针（2026-07-31 连环静默死亡案）：gateway 多次死于 stdin EOF，
    // 但父进程活着、没 kill、没 replace。给三根管道装带调用栈的监听器，
    // 谁掐断管道，栈里就有谁的名字。
    const pipeOwner = this.proc
    pipeOwner.stdin?.on('error', err => {
      if (this.proc !== pipeOwner) return
      this.lifecycle(`[forensics] gateway stdin ERROR: ${err.message}\n${err.stack ?? ''}`)
    })
    pipeOwner.stdin?.on('close', () => {
      if (this.proc !== pipeOwner) return
      this.lifecycle(`[forensics] gateway stdin CLOSED trace:\n${new Error('stdin-close-trace').stack ?? ''}`)
    })
    pipeOwner.stdout?.on('error', err => {
      if (this.proc !== pipeOwner) return
      this.lifecycle(`[forensics] gateway stdout ERROR: ${err.message}`)
    })

    this.stdoutRl = createInterface({ input: this.proc.stdout! })
    this.stdoutRl.on('line', raw => {
      try {
        this.dispatch(JSON.parse(raw))
      } catch {
        const preview = raw.trim().slice(0, MAX_LOG_PREVIEW) || '(empty line)'

        this.pushLog(`[protocol] malformed stdout: ${preview}`)
        this.publish({ type: 'gateway.protocol_error', payload: { preview } })
      }
    })

    this.stderrRl = createInterface({ input: this.proc.stderr! })
    this.stderrRl.on('line', raw => {
      const line = truncateLine(raw.trim())

      if (!line) {
        return
      }

      this.pushLog(line)
      this.publish({ type: 'gateway.stderr', payload: { line } })
    })

    const ownedProc = this.proc
    this.proc.on('error', err => {
      if (this.proc !== ownedProc) {
        this.pushLog(`[lifecycle] stale child error ignored ${describeChild(ownedProc)} message=${err.message}`)
        return
      }

      const line = `[spawn] ${err.message}`

      this.lifecycle(`[lifecycle] child error ${describeChild(ownedProc)} message=${err.message}`)
      this.pushLog(line)
      this.publish({ type: 'gateway.stderr', payload: { line } })
      this.proc = null
      this.handleTransportExit(1, `gateway error: ${err.message}`)
    })
    this.proc.on('exit', (code, signal) => {
      if (this.proc !== ownedProc) {
        this.pushLog(
          `[lifecycle] stale child exit ignored ${describeChild(ownedProc)} code=${code ?? 'null'} signal=${signal ?? 'null'}`
        )
        return
      }

      this.lifecycle(`[lifecycle] child exit ${describeChild(ownedProc)} code=${code ?? 'null'} signal=${signal ?? 'null'}`)
      this.handleTransportExit(code)
    })
  }

  private startAttachedGateway(attachUrl: string) {
    const safeAttachUrl = redactUrl(attachUrl)
    this.startReadyTimer('websocket', safeAttachUrl)

    if (typeof WebSocket === 'undefined') {
      const line = `[startup] WebSocket API unavailable; cannot attach to ${safeAttachUrl}`

      this.pushLog(line)
      this.publish({ type: 'gateway.stderr', payload: { line } })
      this.handleTransportExit(1, 'gateway websocket unavailable')
      return
    }

    try {
      const ws = new WebSocket(attachUrl)
      let settled = false

      this.ws = ws

      const connectPromise = new Promise<void>((resolve, reject) => {
        ws.addEventListener('open', () => {
          if (!settled) {
            settled = true
            resolve()
          }
          this.connectSidecarMirror()
        }, { once: true })

        ws.addEventListener('error', () => {
          if (!settled) {
            this.pushLog('[startup] gateway websocket connect error')
            settled = true
            reject(new Error('gateway websocket connection failed'))
          }
        }, { once: true })

        ws.addEventListener('close', ev => {
          if (!settled) {
            settled = true
            reject(new Error(`gateway websocket closed (${ev.code}) during connect`))
          }
        }, { once: true })
      })

      connectPromise.catch(() => {})
      this.wsConnectPromise = connectPromise

      ws.addEventListener('message', ev => this.handleWebSocketFrame(ev.data))
      ws.addEventListener('close', ev => {
        if (this.ws !== ws) {
          this.pushLog(`[lifecycle] stale websocket close ignored code=${ev.code}`)
          return
        }

        this.pushLog(`[lifecycle] websocket close code=${ev.code}`)
        this.ws = null
        this.wsConnectPromise = null
        this.handleTransportExit(ev.code, `gateway websocket closed${ev.code ? ` (${ev.code})` : ''}`)
      })
      ws.addEventListener('error', () => {
        const line = '[gateway] websocket transport error'

        this.pushLog(line)
        this.publish({ type: 'gateway.stderr', payload: { line } })
      })
    } catch (err) {
      this.pushLog(`[startup] failed to connect websocket gateway ${safeAttachUrl} (constructor error)`)
      this.handleTransportExit(1, 'gateway websocket startup failed')
    }
  }

  start() {
    const root = process.env.BOBO_PYTHON_SRC_ROOT ?? resolve(import.meta.dirname, '../../')
    const attachUrl = resolveGatewayAttachUrl()
    const sidecarUrl = resolveSidecarUrl()

    this.attachUrl = attachUrl
    this.sidecarUrl = sidecarUrl
    this.resetStartupState()

    if (this.proc && !this.proc.killed && this.proc.exitCode === null) {
      this.lifecycle(`[lifecycle] start() replacing live child pid=${this.proc.pid ?? 'unknown'}`)
      this.lifecycle(`[lifecycle] replacing live gateway child ${describeChild(this.proc)}`)
      this.proc.kill()
    }

    this.proc = null
    this.closeGatewaySocket()
    this.closeSidecarSocket()

    if (attachUrl) {
      this.startAttachedGateway(attachUrl)
      return
    }

    this.startSpawnedGateway(root)
  }

  private dispatch(msg: Record<string, unknown>) {
    const id = msg.id as string | undefined
    const p = id ? this.pending.get(id) : undefined

    if (p) {
      this.settle(p, msg.error ? this.toError(msg.error) : null, msg.result)
      return
    }

    if (msg.method === 'event') {
      const ev = asGatewayEvent(msg.params)

      if (ev) {
        this.publish(ev)
      }
    }
  }

  private toError(raw: unknown): Error {
    const err = raw as { message?: unknown } | null | undefined

    return new Error(typeof err?.message === 'string' ? err.message : 'request failed')
  }

  private settle(p: Pending, err: Error | null, result: unknown) {
    clearTimeout(p.timeout)
    this.pending.delete(p.id)

    if (err) {
      p.reject(err)
    } else {
      p.resolve(result)
    }
  }

  private pushLog(line: string) {
    this.logs.push(truncateLine(line))
  }

  private lifecycle(line: string) {
    this.pushLog(line)
    recordParentLifecycle(line)
  }

  private rejectPending(err: Error) {
    for (const p of this.pending.values()) {
      clearTimeout(p.timeout)
      p.reject(err)
    }

    this.pending.clear()
  }

  private onTimeout = (id: string) => {
    const p = this.pending.get(id)

    if (p) {
      this.pending.delete(id)
      p.reject(new Error(`timeout: ${p.method}`))
    }
  }

  drain() {
    this.subscribed = true

    for (const ev of this.bufferedEvents.drain()) {
      this.emit('event', ev)
    }

    if (this.pendingExit !== undefined) {
      const code = this.pendingExit

      this.pendingExit = undefined
      this.emit('exit', code)
    }
  }

  getLogTail(limit = 20): string {
    return this.logs.tail(Math.max(1, limit)).join('\n')
  }

  private async ensureAttachedWebSocket(method: string): Promise<WebSocket> {
    if (!this.attachUrl) {
      throw new Error('gateway not running')
    }

    if (!this.ws || this.ws.readyState === WS_CLOSED || this.ws.readyState === WS_CLOSING) {
      this.start()
    }

    if (this.ws?.readyState === WS_CONNECTING) {
      try {
        await this.wsConnectPromise
      } catch (err) {
        throw err instanceof Error ? err : new Error(String(err))
      }
    }

    if (!this.ws || this.ws.readyState !== WS_OPEN) {
      throw new Error(`gateway not connected: ${method}`)
    }

    return this.ws
  }

  // ── TICKET-018 socket 传输 ──────────────────────────────────────────

  private wireSocket(ownedProc: ChildProcess, sockPath: string, sock: Socket) {
    this.sock = sock
    this.sockPath = sockPath
    this.lifecycle(`[socket] 已连接 ${sockPath}（gateway 自持监听，前端断开不再致命）`)
    const rl = createInterface({ input: sock })
    this.sockRl = rl
    rl.on('line', raw => {
      try {
        this.dispatch(JSON.parse(raw))
      } catch {
        const preview = raw.trim().slice(0, MAX_LOG_PREVIEW) || '(empty line)'
        this.pushLog(`[protocol] malformed socket frame: ${preview}`)
        this.publish({ type: 'gateway.protocol_error', payload: { preview } })
      }
    })
    sock.on('close', () => this.handleSocketClose(ownedProc, sockPath, sock))
    sock.on('error', err => {
      if (this.proc === ownedProc) {
        this.lifecycle(`[socket] error: ${err.message}`)
      }
    })
  }

  private connectSocketWithRetry(ownedProc: ChildProcess, sockPath: string, attempt: number) {
    const timer = setTimeout(() => {
      if (this.proc !== ownedProc || this.sock) {
        return
      }
      if (ownedProc.killed || ownedProc.exitCode !== null) {
        return
      }
      if (!existsSync(sockPath)) {
        if (attempt < 50) {
          this.connectSocketWithRetry(ownedProc, sockPath, attempt + 1)
        } else {
          this.lifecycle('[socket] 等待 socket 文件超时 → kill 后以 stdio 模式重启 child')
          this.socketDisabled = true
          ownedProc.kill()
        }
        return
      }
      const sock = createConnection(sockPath)
      let opened = false
      sock.on('connect', () => {
        opened = true
        if (this.proc !== ownedProc || this.sock) {
          sock.destroy()
          return
        }
        this.wireSocket(ownedProc, sockPath, sock)
      })
      sock.on('error', () => {
        if (!opened) {
          sock.destroy()
          if (attempt < 50) {
            this.connectSocketWithRetry(ownedProc, sockPath, attempt + 1)
          }
        }
      })
    }, attempt === 0 ? 0 : 100)
    timer.unref?.()
  }

  private handleSocketClose(ownedProc: ChildProcess, sockPath: string, sock: Socket) {
    if (this.sock === sock) {
      this.sock = null
    }
    if (this.proc !== ownedProc) {
      return
    }
    if (ownedProc.killed || ownedProc.exitCode !== null) {
      return // child 已死，走既有 transport exit 流程
    }
    // child 活着但 socket 断了——正是 fd 凶杀案现场。重连，不判死。
    this.lifecycle('[socket] 连接断开但 gateway 存活 → 自动重连（不再判 gateway 死亡）')
    this.reconnectSocket(ownedProc, sockPath, 0)
  }

  private reconnectSocket(ownedProc: ChildProcess, sockPath: string, attempt: number) {
    if (attempt >= 20) {
      this.lifecycle('[socket] 重连 20 次失败 → kill child，走既有 recovery 流程')
      ownedProc.kill()
      return
    }
    const timer = setTimeout(() => {
      if (this.proc !== ownedProc || this.sock || ownedProc.killed || ownedProc.exitCode !== null) {
        return
      }
      const sock = createConnection(sockPath)
      let opened = false
      sock.on('connect', () => {
        opened = true
        if (this.proc !== ownedProc || this.sock) {
          sock.destroy()
          return
        }
        this.lifecycle('[socket] 重连成功 ✓ gateway 会话无损')
        this.wireSocket(ownedProc, sockPath, sock)
      })
      sock.on('error', () => {
        if (!opened) {
          sock.destroy()
          this.reconnectSocket(ownedProc, sockPath, attempt + 1)
        }
      })
    }, 300)
    timer.unref?.()
  }

  private requestOverSocket<T = unknown>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    const id = `r${++this.reqId}`

    return new Promise<T>((resolve, reject) => {
      const timeout = setTimeout(this.onTimeout, REQUEST_TIMEOUT_MS, id)

      timeout.unref?.()

      this.pending.set(id, {
        id,
        method,
        reject,
        resolve: v => resolve(v as T),
        timeout
      })

      try {
        this.sock!.write(JSON.stringify({ id, jsonrpc: '2.0', method, params }) + '\n')
      } catch (e) {
        const pending = this.pending.get(id)

        if (pending) {
          clearTimeout(pending.timeout)
          this.pending.delete(id)
        }

        reject(e)
      }
    })
  }

  private requestOverWebSocket<T = unknown>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    return this.ensureAttachedWebSocket(method).then(
      ws =>
        new Promise<T>((resolve, reject) => {
          const id = `r${++this.reqId}`
          const timeout = setTimeout(this.onTimeout, REQUEST_TIMEOUT_MS, id)

          timeout.unref?.()
          this.pending.set(id, {
            id,
            method,
            reject,
            resolve: v => resolve(v as T),
            timeout
          })

          try {
            ws.send(JSON.stringify({ id, jsonrpc: '2.0', method, params }))
          } catch (e) {
            const pending = this.pending.get(id)

            if (pending) {
              clearTimeout(pending.timeout)
              this.pending.delete(id)
            }

            reject(e instanceof Error ? e : new Error(String(e)))
          }
        })
    )
  }

  request<T = unknown>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    const attachUrl = resolveGatewayAttachUrl()

    if (attachUrl) {
      if (this.attachUrl !== attachUrl) {
        this.rejectPending(new Error('gateway attach url changed'))
        this.start()
      }

      return this.requestOverWebSocket<T>(method, params)
    }

    // TICKET-018：socket 已连接时优先走 socket（gateway 自持，断线可重连）
    if (this.sock && !this.sock.destroyed) {
      return this.requestOverSocket<T>(method, params)
    }

    if (!this.proc?.stdin || this.proc.killed || this.proc.exitCode !== null) {
      this.start()
    }

    if (!this.proc?.stdin) {
      return Promise.reject(new Error('gateway not running'))
    }

    const id = `r${++this.reqId}`

    return new Promise<T>((resolve, reject) => {
      const timeout = setTimeout(this.onTimeout, REQUEST_TIMEOUT_MS, id)

      timeout.unref?.()

      this.pending.set(id, {
        id,
        method,
        reject,
        resolve: v => resolve(v as T),
        timeout
      })

      try {
        this.proc!.stdin!.write(JSON.stringify({ id, jsonrpc: '2.0', method, params }) + '\n')
      } catch (e) {
        const pending = this.pending.get(id)

        if (pending) {
          clearTimeout(pending.timeout)
          this.pending.delete(id)
        }

        reject(e instanceof Error ? e : new Error(String(e)))
      }
    })
  }

  kill(reason = 'requested') {
    const proc = this.proc
    const killed = proc?.kill()

    this.lifecycle(`[lifecycle] GatewayClient.kill reason=${reason} ${describeChild(proc)} killResult=${killed ?? 'none'}`)
    this.closeGatewaySocket()
    this.closeSidecarSocket()
    this.clearReadyTimer()
    this.rejectPending(new Error('gateway closed'))
    // socket 传输清理（TICKET-018）：断开连接并删掉 socket 文件
    const sock = this.sock
    this.sock = null
    this.sockRl?.close()
    this.sockRl = null
    sock?.removeAllListeners()
    sock?.destroy()
    if (this.sockPath) {
      try { unlinkSync(this.sockPath) } catch { /* 已被 python 侧清理或不存在 */ }
      this.sockPath = null
    }
  }
}
