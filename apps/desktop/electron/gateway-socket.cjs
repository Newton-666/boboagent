// gateway-socket.cjs — desktop ⇄ bobo gateway unix socket bridge (TICKET-GW-SOCK)
//
// 桌面端主进程与后端 gateway 的通道从 stdio 管道切换为 unix socket 常驻：
//   - 固定名 bobo-gw-main.sock（VS Code 扩展 discover 正则 ^bobo-gw-.*\.sock$
//     天然扫到，扩展零改动）
//   - 前端断开/崩溃：后端进程不死（entry.py socket 模式语义），重连恢复会话
//   - spawn 前探测：已有活跃后端则复用（不重复 spawn，杜绝双 gateway 抢 sock）
// 纯 Node 模块，无 electron 依赖——可单测。
const net = require('net')
const fs = require('fs')
const os = require('os')
const path = require('path')

const GW_SOCK_NAME = 'bobo-gw-main.sock'

/** 固定 socket 路径：os.tmpdir()/bobo-gw-main.sock */
function resolveGwSockPath() {
  return path.join(os.tmpdir(), GW_SOCK_NAME)
}

/**
 * 探测 socket 是否已有活跃后端在 listen。
 * 能连上 = 有活跃后端（复用场景，不 spawn）；连不上/超时 = 无（可安全清理 + spawn）。
 */
function probeSocket(sockPath, timeoutMs = 1000) {
  return new Promise((resolve) => {
    let settled = false
    const s = net.connect(sockPath)
    const done = (ok) => {
      if (settled) return
      settled = true
      try { s.destroy() } catch (_) {}
      resolve(ok)
    }
    s.setTimeout(timeoutMs)
    s.once('connect', () => done(true))
    s.once('timeout', () => done(false))
    s.once('error', () => done(false))
  })
}

/** 清理陈旧 sock 文件（无活跃进程时删除；有活跃进程时由调用方先探测复用，不走这里） */
function cleanupStaleSocket(sockPath) {
  try { fs.unlinkSync(sockPath) } catch (_) {}
}

/**
 * 构造后端 spawn 环境变量（TICKET-GW-SOCK 版 D1b E1 防护）：
 *   - BOBO_GW_SOCKET：显式注入固定路径（不信任环境泄漏值，原逻辑是删除防 socket 模式，
 *     本票桌面端主动要 socket 模式 → 改为显式覆盖）
 *   - BOBO_GW_IDLE_TIMEOUT：0 = 后端生命周期由桌面端管理（窗口崩/关不杀后端，
 *     重开窗口重连恢复会话；杜绝 60s 空闲自退导致 VS Code 扩展断连）
 *   - BOBO_SESSION_DIR：仍删除（防止继承 TUI 专用会话路径）
 */
function buildBackendEnv({ projectRoot, isPackaged = false, baseEnv = process.env }) {
  const env = {
    ...baseEnv,
    BOBO_BACKEND: '1',
    PYTHONPATH: projectRoot,
    BOBO_CWD: baseEnv.BOBO_CWD || process.cwd(),
  }
  if (isPackaged) {
    env.BOBO_DATA_DIR = baseEnv.BOBO_DATA_DIR || path.join(os.homedir(), '.bobo')
  }
  env.BOBO_GW_SOCKET = resolveGwSockPath()
  env.BOBO_GW_IDLE_TIMEOUT = '0'
  delete env.BOBO_SESSION_DIR
  return env
}

/**
 * JSON-RPC 行协议 unix socket 客户端（带自动重连 + 指数退避）。
 *
 * events:
 *   onMessage(msg)  完整 JSON-RPC 消息（gateway.ready / event / response）
 *   onStatus(status) {state:'connected'|'connecting'|'disconnected', attempt?, reason?}
 *   onLog(line)     诊断日志
 */
function createGatewayClient({ sockPath, onMessage, onStatus, onLog = () => {} }) {
  let sock = null
  let buffer = ''
  let closed = false
  let retryCount = 0
  let retryTimer = null

  const log = (m) => onLog(`[gw-socket] ${m}`)

  function teardownSocket() {
    if (sock) {
      sock.removeAllListeners()
      try { sock.destroy() } catch (_) {}
      sock = null
    }
    buffer = ''
  }

  function scheduleReconnect(reason) {
    if (closed) return
    retryCount++
    const delay = Math.min(1000 * Math.pow(2, Math.min(retryCount - 1, 3)), 8000)
    log(`断开（${reason}），${delay}ms 后重连（第 ${retryCount} 次）`)
    if (onStatus) onStatus({ state: 'disconnected', attempt: retryCount, reason })
    clearTimeout(retryTimer)
    retryTimer = setTimeout(connect, delay)
  }

  function connect() {
    if (closed) return
    log(`connecting ${sockPath}`)
    if (onStatus) onStatus({ state: 'connecting', attempt: retryCount + 1 })
    const s = net.connect(sockPath)
    sock = s

    s.on('connect', () => {
      if (closed || s !== sock) return
      retryCount = 0
      log('connected')
      if (onStatus) onStatus({ state: 'connected' })
    })

    s.on('data', (chunk) => {
      if (s !== sock) return
      buffer += chunk.toString('utf8')
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        const t = line.trim()
        if (!t) continue
        try {
          onMessage(JSON.parse(t))
        } catch (e) {
          log(`unparseable line: ${t.slice(0, 120)}`)
        }
      }
    })

    s.on('close', () => {
      if (s !== sock) return
      teardownSocket()
      scheduleReconnect('close')
    })

    s.on('error', (err) => {
      if (s !== sock) return
      log(`socket error: ${err.code || err.message}`)
      if (err.code === 'ECONNREFUSED') {
        // 后端还没 bind 或已退出：等 close 后重连（close 事件随后必然触发）
        teardownSocket()
        scheduleReconnect(err.code)
      }
    })
  }

  function send(msg) {
    if (!sock || sock.destroyed) {
      log('send 失败：未连接')
      return false
    }
    try {
      sock.write(JSON.stringify(msg) + '\n')
      return true
    } catch (e) {
      log(`send 异常: ${e.message}`)
      return false
    }
  }

  function close() {
    closed = true
    clearTimeout(retryTimer)
    teardownSocket()
  }

  return {
    connect,
    send,
    close,
    get connected() {
      return !!sock && !sock.destroyed
    },
  }
}

module.exports = {
  GW_SOCK_NAME,
  resolveGwSockPath,
  probeSocket,
  cleanupStaleSocket,
  buildBackendEnv,
  createGatewayClient,
}
