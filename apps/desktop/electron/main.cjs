// Bobo Desktop — Electron main process
// Spawns Python backend, bridges JSON-RPC between renderer and backend.

const { app, BrowserWindow, ipcMain, dialog } = require('electron')
const { spawn } = require('child_process')
const path = require('path')
const fs = require('fs')
const os = require('os')
// TICKET-DESK-V4: 小组件开关状态 + 窗口尺寸持久化（纯 Node 模块）
const { readWidgetEnabled, writeWidgetEnabled, readWidgetSize, writeWidgetSize } = require('./widget-config.cjs')
// TICKET-GW-SOCK: 桌面端 ⇄ gateway 的 unix socket 桥（固定名 bobo-gw-main.sock）
const { resolveGwSockPath, probeSocket, cleanupStaleSocket, createGatewayClient, buildBackendEnv } = require('./gateway-socket.cjs')

const GW_SOCK_PATH = resolveGwSockPath()

let mainWindow = null
let widgetWindow = null   // TICKET-DESK-V4: 只读投影小组件小窗（独立生命周期，不波及主窗/后端）
let backendProcess = null
let gwClient = null       // TICKET-GW-SOCK: unix socket 客户端（替代 stdio 管道桥接）
let backendRestartCount = 0
const MAX_BACKEND_RESTARTS = 3
// 票 SAFETY-1：用户/系统主动停后端标志（退出应用 Cmd+Q / 改配置重启）。
// true 时后端 exit 不触发自动重启——否则 Cmd+Q 幽灵复活、save-env 双重启动。
let backendStopRequested = false
let pendingMessages = []  // Buffer for messages received before window's IPC listener is ready
let frontendLogFd = null   // TICKET-D1d ⑧: renderer log (O-7 黑匣子对齐)

// TICKET-D1d ⑧: data/logs 目录解析 —— dev 用仓库 data/logs（与 TUI dev 一致），
// packaged 用 ~/.bobo/data/logs（与 TUI 生产一致）。
function getLogDir() {
  if (app.isPackaged) {
    return path.join(os.homedir(), '.bobo', 'data', 'logs')
  }
  return path.join(path.resolve(__dirname, '..', '..', '..'), 'data', 'logs')
}

// TICKET-D1d ⑦-A: 数据目录解析（save-env 写盘路径跟随）—— dev 用仓库 data/（与
// setup.submit/BOBO_DATA_DIR 一致，消除双 .env 分叉），packaged 用 ~/.bobo。
function getDataDir() {
  if (app.isPackaged) {
    return path.join(os.homedir(), '.bobo')
  }
  return path.join(path.resolve(__dirname, '..', '..', '..'), 'data')
}

function initFrontendLog() {
  try {
    const logDir = getLogDir()
    if (!fs.existsSync(logDir)) fs.mkdirSync(logDir, { recursive: true })
    const pid = process.pid
    const logPath = path.join(logDir, `frontend_${pid}.log`)
    frontendLogFd = fs.openSync(logPath, 'a')
    const header = `=== desktop frontend log started at ${new Date().toISOString()} (pid=${pid}) ===\n`
    fs.writeSync(frontendLogFd, header)
    console.log(`[bobo-desktop] Frontend log: ${logPath}`)
  } catch (e) {
    console.warn(`[bobo-desktop] Frontend log init failed: ${e.message}`)
  }
}

function frontendLog(line) {
  if (!frontendLogFd) return
  try {
    fs.writeSync(frontendLogFd, `[${new Date().toISOString()}] ${line}\n`)
  } catch (_) {}
}

// ── Python backend management ──────────────────────────────────────────

function resolvePython() {
  // Try configured python, then project venv, then common paths.
  // 优先项目 .venv：它有 pyobjc（computer_use/AX 树依赖 ApplicationServices），
  // 系统 python3 没有 pyobjc → computer_use 加载失败（报 'No module named ApplicationServices'）。
  const configured = process.env.BOBO_PYTHON
  if (configured && fs.existsSync(configured)) return configured

  // 项目 .venv（Apple Silicon / Intel 通用，pyobjc 在 site-packages）
  for (const rel of ['.venv/bin/python', 'venv/bin/python']) {
    const p = path.join(__dirname, '..', '..', '..', rel)
    if (fs.existsSync(p)) return p
  }

  // Homebrew paths (Apple Silicon / Intel)
  for (const p of ['/opt/homebrew/bin/python3', '/usr/local/bin/python3', '/usr/bin/python3', 'python3', 'python']) {
    try {
      const result = require('child_process').execSync(`${p} --version`, { timeout: 3000 })
      if (result) return p
    } catch {}
  }
  return 'python3'
}

async function startBackend() {
  const python = resolvePython()
  const isPackaged = app.isPackaged
  let projectRoot
  // 票 SAFETY-1：新一轮启动清除主动停止标志（下次 exit 按异常终止处理）
  backendStopRequested = false

  // Install backend to ~/.bobo/ if packaged
  if (isPackaged) {
    installBoboBackend()
    projectRoot = path.join(os.homedir(), '.bobo')
  } else {
    // Dev: 3 levels up from electron/ to project root
    projectRoot = path.resolve(__dirname, '..', '..', '..')
  }

  // TICKET-GW-SOCK：spawn 前先探测——若已有活跃后端（旧桌面端残留 / 用户手动
  // 起过 gateway）直接复用其 socket，不重复 spawn，杜绝双 gateway 抢同一 sock
  // （EADDRINUSE 根治法：复用而非再起）。
  const reused = await probeSocket(GW_SOCK_PATH, 1000)
  if (reused) {
    console.log(`[bobo-desktop] 探测到活跃后端 ${GW_SOCK_PATH}，复用（不重新 spawn）`)
    backendProcess = null
    ensureGatewayClient()
    gwClient.connect()
    return
  }

  // 无活跃后端：清理陈旧 sock 文件（残留文件会导致新后端 bind 报地址占用）后 spawn
  cleanupStaleSocket(GW_SOCK_PATH)

  // TICKET-GW-SOCK 版 D1b E1 防护：显式注入 BOBO_GW_SOCKET 固定路径 + 空闲超时 0
  // （后端生命周期由桌面端管，窗口崩/关不杀后端，重开重连恢复会话）；
  // BOBO_SESSION_DIR 仍删除，防继承 TUI 专用会话路径。
  const env = buildBackendEnv({ projectRoot, isPackaged })

  console.log(`[bobo-desktop] Starting backend: ${python} -m bobo_tui_gateway.entry (socket=${GW_SOCK_PATH})`)
  console.log(`[bobo-desktop] Project root: ${projectRoot}`)

  backendProcess = spawn(python, ['-m', 'bobo_tui_gateway.entry'], {
    cwd: projectRoot,
    env,
    // TICKET-GW-SOCK：socket 模式下 JSON-RPC 不再走 stdin/stdout——stdin 不用，
    // stdout 仅转发日志（无 JSON-RPC 行解析）。
    stdio: ['ignore', 'pipe', 'pipe'],
  })

  backendProcess.on('error', (err) => {
    console.error(`[bobo-desktop] Backend spawn error: ${err.message}`)
    if (mainWindow) {
      mainWindow.webContents.send('backend-status', { status: 'error', message: `后端启动失败: ${err.message}` })
    }
  })

  backendProcess.on('exit', (code) => {
    console.log(`[bobo-desktop] Backend exited with code ${code} (stopRequested=${backendStopRequested})`)
    backendProcess = null
    // 票 SAFETY-1：退出码 0 也提示（可能是被外部 SIGTERM 后优雅退出——18:53
    // 事故实证：bobo 误杀后端，退出码 0，旧逻辑不重启 → owner 桌面端永久断连）
    const exitMsg = { status: 'exited', code, message: code !== 0 ? `后端进程异常退出 (代码: ${code})` : '后端进程已退出（自动重启中）' }
    if (mainWindow) {
      mainWindow.webContents.send('backend-status', exitMsg)
    }
    // TICKET-DESK-V4: 小窗同步连接状态（只读投影，不响应）
    if (widgetWindow) {
      widgetWindow.webContents.send('backend-status', exitMsg)
    }
    // 票 SAFETY-1：用户主动停止（Cmd+Q 退出应用 / 改配置重启）不自动重启——
    // 否则幽灵复活；其余情况无论退出码 0 与否都走自动重启（保留 backoff 与上限）
    if (backendStopRequested) return
    // Auto-restart with backoff (up to MAX_BACKEND_RESTARTS times)
    if (backendRestartCount < MAX_BACKEND_RESTARTS) {
      backendRestartCount++
      const delay = backendRestartCount * 1000
      console.log(`[bobo-desktop] Restarting backend in ${delay}ms (attempt ${backendRestartCount}/${MAX_BACKEND_RESTARTS})`)
      setTimeout(() => startBackend(), delay)
    } else {
      console.error(`[bobo-desktop] Backend exited ${MAX_BACKEND_RESTARTS} times, retrying in 60s`)
      setTimeout(() => {
        backendRestartCount = 0
        startBackend()
      }, 60000)
    }
  })

  backendProcess.stderr.on('data', (data) => {
    const text = data.toString()
    if (mainWindow) {
      mainWindow.webContents.send('backend-log', { stream: 'stderr', text })
    }
    process.stderr.write(`[backend] ${text}`)
  })

  // TICKET-GW-SOCK：socket 模式下 stdout 只有日志（JSON-RPC 走 unix socket），
  // 转发到 renderer 的 backend-log（与 stderr 同款），不再做 JSON-RPC 行解析。
  backendProcess.stdout.on('data', (data) => {
    const text = data.toString()
    if (mainWindow) {
      mainWindow.webContents.send('backend-log', { stream: 'stdout', text })
    }
    process.stdout.write(`[backend] ${text}`)
  })

  // TICKET-GW-SOCK：spawn 后连 socket（后端 bind 需要时间，client 自动重连兜底）
  ensureGatewayClient()
  gwClient.connect()
}

/** TICKET-GW-SOCK：建立/复用 gateway socket 客户端。renderer 的 IPC 接口
 * （backend-send / backend-message / backend-status）完全不变——桥接层从
 * stdio 管道换成 unix socket，对窗口与小组件透明。 */
function ensureGatewayClient() {
  if (gwClient) return
  gwClient = createGatewayClient({
    sockPath: GW_SOCK_PATH,
    onMessage: (msg) => {
      if (mainWindow) {
        mainWindow.webContents.send('backend-message', msg)
      } else {
        pendingMessages.push(msg)
      }
      // TICKET-DESK-V4: 只读投影 —— 同一条现成事件流镜像给小组件（只监听不响应）
      if (widgetWindow) {
        widgetWindow.webContents.send('backend-message', msg)
      }
    },
    onStatus: (status) => {
      if (mainWindow) {
        mainWindow.webContents.send('backend-status', { status: 'socket', detail: status })
      }
    },
    onLog: (line) => console.log(`[bobo-desktop] ${line}`),
  })
}

function sendToBackend(msg) {
  if (!gwClient || !gwClient.send(msg)) {
    console.warn('[bobo-desktop] Backend not connected, cannot send message')
    return false
  }
  return true
}

function stopBackend() {
  // 票 SAFETY-1：主动停止（退出应用 / 改配置重启）→ exit 不触发自动重启
  backendStopRequested = true
  // TICKET-GW-SOCK：先关 socket 客户端（停止重连），再杀后端进程。
  // 复用外部后端时 backendProcess 为 null——天然杀不到外部进程（它归用户/旧桌面端管）。
  if (gwClient) {
    gwClient.close()
    gwClient = null
  }
  if (backendProcess) {
    // stdio 已切 socket 模式（stdin='ignore'），防御性判空
    if (backendProcess.stdin) backendProcess.stdin.end()
    setTimeout(() => {
      if (backendProcess) {
        backendProcess.kill()
        backendProcess = null
      }
    }, 2000)
  }
}

// ── Window management ──────────────────────────────────────────────────

function createWindow() {
  // Reset backend restart counter for fresh start
  backendRestartCount = 0

  mainWindow = new BrowserWindow({
    width: 900,
    height: 680,
    minWidth: 500,
    minHeight: 400,
    title: 'Bobo',
    icon: path.join(__dirname, '..', 'build', 'icon.icns'),
    titleBarStyle: 'hiddenInset',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  // In dev mode, load from Vite dev server
  const isDev = process.env.BOBO_DESKTOP_DEV === '1'
  if (isDev) {
    mainWindow.loadURL('http://localhost:5173')
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))
  }

  // TICKET-D1d ⑧: renderer log (O-7 黑匣子对齐) — console / crash / preload 错误落盘
  initFrontendLog()
  mainWindow.webContents.on('console-message', (...args) => {
    // Electron 32+ 新签名: (event, {level, message, lineNumber, sourceId})
    // 旧签名: (event, level, message, line, sourceId) — 兼容处理
    let level, message, line, sourceId
    if (args.length >= 5 && typeof args[1] === 'number') {
      ;[ , level, message, line, sourceId] = args
    } else {
      const d = args[1] || {}
      level = d.level; message = d.message; line = d.lineNumber; sourceId = d.sourceId
    }
    const levelName = ['log', 'info', 'warning', 'error'][level] || String(level)
    frontendLog(`[renderer:${levelName}] ${message} (${sourceId || ''}:${line})`)
  })
  mainWindow.webContents.on('render-process-gone', (_e, details) => {
    frontendLog(`[renderer-gone] reason=${details.reason} exitCode=${details.exitCode}`)
  })
  mainWindow.webContents.on('preload-error', (_e, preloadPath, error) => {
    frontendLog(`[preload-error] ${preloadPath}: ${error.message}`)
  })

  mainWindow.on('closed', () => {
    mainWindow = null
    // TICKET-DESK-V4: 主窗关闭即销毁小窗（零残留），保证 window-all-closed 触发退出；
    // 反之小窗关闭不波及主窗/后端（独立生命周期）。
    destroyWidgetWindow()
  })
}

// ── TICKET-DESK-V4: 只读投影小组件小窗 ─────────────────────────────────
// 第一铁律：只读投影，零干涉。小窗独立 BrowserWindow，独立开关/生命周期；
// 关闭=当场销毁（不是隐藏）；崩溃/关闭不波及主窗与后端。
function createWidgetWindow() {
  if (widgetWindow) return widgetWindow
  // TICKET-DESK-V4 追加②：尺寸持久化恢复（重启回上次大小；无配置回默认 280×160）
  const size = readWidgetSize(getDataDir())
  widgetWindow = new BrowserWindow({
    width: size.width,
    height: size.height,
    frame: false,
    transparent: true,
    // TICKET-DESK-V4 追加②：可拖拽 resize（拖边/角拉大）；最小尺寸限制，拖到最小即停
    resizable: true,
    minWidth: 240,
    minHeight: 150,
    maximizable: false,
    minimizable: false,
    fullscreenable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    hasShadow: false,
    title: 'Bobo 执行实况',
    webPreferences: {
      preload: path.join(__dirname, 'widget-preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })
  widgetWindow.setAlwaysOnTop(true, 'floating')
  widgetWindow.loadFile(path.join(__dirname, 'widget.html'))
  widgetWindow.on('closed', () => {
    widgetWindow = null
  })
  // TICKET-DESK-V4 追加②：resize 时持久化尺寸（与开关状态同文件，重启恢复）
  widgetWindow.on('resize', () => {
    try {
      const [w, h] = widgetWindow.getSize()
      writeWidgetSize(getDataDir(), { width: w, height: h })
    } catch (_) {}
  })
  // 小窗自身崩溃/异常不影响主窗与后端（不弹错误框）
  widgetWindow.webContents.on('render-process-gone', () => {
    try { widgetWindow && widgetWindow.destroy() } catch (_) {}
  })
  return widgetWindow
}

function destroyWidgetWindow() {
  if (widgetWindow) {
    const w = widgetWindow
    widgetWindow = null
    try { w.destroy() } catch (_) {}
  }
}

function toggleWidget() {
  if (widgetWindow) {
    destroyWidgetWindow()
  } else {
    createWidgetWindow()
  }
  writeWidgetEnabled(getDataDir(), !!widgetWindow)
  return { enabled: !!widgetWindow }
}

function widgetStatus() {
  return { enabled: !!widgetWindow }
}

function ensureWidgetByConfig() {
  // 重启桌面端按持久化状态自动恢复；默认关（配置不存在时 readWidgetEnabled 返回 false）
  if (readWidgetEnabled(getDataDir())) {
    createWidgetWindow()
  }
}

// ── IPC handlers ───────────────────────────────────────────────────────

ipcMain.on('backend-send', (_event, msg) => {
  sendToBackend(msg)
})

ipcMain.handle('backend-send-sync', async (_event, msg) => {
  return sendToBackend(msg)
})

// ── TICKET-DESK-V4: 小组件 IPC（开关/状态/审批联动/只读广播）──
ipcMain.handle('widget-toggle', () => {
  return toggleWidget()
})

ipcMain.handle('widget-status', () => {
  return widgetStatus()
})

// 小窗点击审批 → 唤起主窗并跳到对应会话（只调主窗现成的聚焦/切会话入口，不自建通道）
ipcMain.on('widget-approval-focus', (_event, sid) => {
  if (!mainWindow) return
  if (mainWindow.isMinimized()) mainWindow.restore()
  mainWindow.show()
  mainWindow.focus()
  if (sid) mainWindow.webContents.send('widget-focus-session', String(sid))
})

// 主窗只读广播 → 小窗（上下文药丸 / 用户指令；V4B 起带会话 sid，小窗按钉选过滤）
ipcMain.on('widget-ctx-stats', (_event, data, sid) => {
  if (widgetWindow) widgetWindow.webContents.send('widget-ctx-stats', data, sid)
})
ipcMain.on('widget-user-msg', (_event, text, sid) => {
  if (widgetWindow) widgetWindow.webContents.send('widget-user-msg', String(text), sid)
})

// ── TICKET-DESK-V4B 会话钉选：主窗 ⇄ 小窗 4 通道 ─────────────────────
// 主窗行内"投影到小组件" → 小窗钉选（sid 空串 = 回落跟随主窗）
ipcMain.on('widget-pin-session', (_event, sid) => {
  if (widgetWindow) widgetWindow.webContents.send('widget-pin-session', String(sid || ''))
})
// 小窗钉选变化（点击轮换/回落）→ 主窗同步行内按钮态（三向一致）
ipcMain.on('widget-pin-changed', (_event, sid) => {
  if (mainWindow) mainWindow.webContents.send('widget-pin-changed', String(sid || ''))
})
// 主窗当前会话广播 → 小窗（跟随模式基准 + 会话指示名）
ipcMain.on('widget-current-session', (_event, sid, title) => {
  if (widgetWindow) widgetWindow.webContents.send('widget-current-session', String(sid || ''), String(title || ''))
})
// 主窗会话列表广播 → 小窗（会话名映射 + 删除回落兜底）
ipcMain.on('widget-sessions', (_event, list) => {
  if (widgetWindow) widgetWindow.webContents.send('widget-sessions', Array.isArray(list) ? list : [])
})

// ── First-run config ──
// DEPRECATED (TICKET-D1d ⑦-B): setup 屏幕已改调 setup.submit（后端权威写盘 + B3 热生效）。
// 本 handler 保留不删，仅作 base_url 等无 RPC 通道的字段的兜底写入通道。
ipcMain.handle('save-env', async (_event, data) => {
  // TICKET-D1d ⑦-A: envDir 跟随数据目录（dev=仓库 data/，packaged=~/.bobo），与
  // setup.submit 的 BOBO_DATA_DIR/.env 一致，消除 dev 双 .env 分叉。
  const envDir = getDataDir()
  if (!fs.existsSync(envDir)) fs.mkdirSync(envDir, { recursive: true })
  const envPath = path.join(envDir, '.env')
  let lines = []
  if (fs.existsSync(envPath)) {
    lines = fs.readFileSync(envPath, 'utf8').split('\n').filter(l => {
      const t = l.trim(); if (!t || t.startsWith('#')) return true
      return !data[t.split('=')[0].trim()]
    })
  }
  for (const [k, v] of Object.entries(data)) {
    if (v) lines.push(`${k}=${v}`)
  }
  fs.writeFileSync(envPath, lines.join('\n') + '\n', 'utf8')
  console.log('[bobo-desktop] Saved .env')
  stopBackend()
  setTimeout(() => startBackend(), 500)
  return { ok: true }
})

// ── Backend install ──
function installBoboBackend() {
  const srcDir = path.join(process.resourcesPath, 'bobo-backend')
  const destDir = path.join(os.homedir(), '.bobo')
  const binDir = path.join(destDir, 'bin')

  // If src doesn't exist, we're in dev or unbundled — skip
  if (!fs.existsSync(srcDir)) return false

  // Ensure dest exists
  if (!fs.existsSync(destDir)) fs.mkdirSync(destDir, { recursive: true })

  let copied = 0
  // Copy directories
  for (const dir of ['core', 'tools', 'bobo_tui_gateway']) {
    const s = path.join(srcDir, dir)
    const d = path.join(destDir, dir)
    if (fs.existsSync(s)) _copyDir(s, d)
    copied++
  }
  // Copy files (skip .env)
  for (const f of ['config.py', 'pyproject.toml']) {
    const s = path.join(srcDir, f)
    const d = path.join(destDir, f)
    if (fs.existsSync(s)) fs.copyFileSync(s, d)
    copied++
  }
  // Create bobo CLI script
  if (!fs.existsSync(binDir)) fs.mkdirSync(binDir, { recursive: true })
  const cliPath = path.join(binDir, 'bobo')
  if (!fs.existsSync(cliPath)) {
    fs.writeFileSync(cliPath, `#!/bin/bash\ncd "${destDir}" && python3 -m bobo_tui_gateway.entry "$@"\n`, 'utf8')
    fs.chmodSync(cliPath, 0o755)
  }
  console.log(`[bobo-desktop] Installed backend to ${destDir} (${copied} items)`)

  // Auto-install Python deps
  const python = resolvePython()
  if (python) {
    try {
      require('child_process').execSync(
        `${python} -m pip install --user --break-system-packages python-dotenv httpx Pillow pyyaml -q`,
        { timeout: 60000, stdio: 'pipe' }
      )
      console.log('[bobo-desktop] Python deps installed')
    } catch (e) {
      console.log(`[bobo-desktop] pip install warning: ${e.message}`)
    }
  }

  return true
}

function _copyDir(src, dest) {
  if (!fs.existsSync(dest)) fs.mkdirSync(dest, { recursive: true })
  for (const entry of fs.readdirSync(src)) {
    const s = path.join(src, entry)
    const d = path.join(dest, entry)
    const stat = fs.statSync(s)
    if (stat.isDirectory()) {
      _copyDir(s, d)
    } else {
      // Never overwrite .env
      if (entry === '.env' && fs.existsSync(d)) continue
      fs.copyFileSync(s, d)
    }
  }
}

ipcMain.handle('select-folder', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory'],
  })
  if (result.canceled || result.filePaths.length === 0) return null
  return result.filePaths[0]
})

// TICKET-GUI-F3 (F3-3): 读会话上下文归档（archives/{sid}.jsonl）供展示层全文恢复。
// 归档目录解析与 core/context.py._get_archive_dir 一致：BOBO_DATA_DIR 环境变量优先，
// 否则默认 ~/.bobo_v2。只读不改写；sid 白名单 + 路径前缀双校验防穿越。
ipcMain.handle('read-archive', async (_event, sid) => {
  if (typeof sid !== 'string' || !/^[\w.-]+$/.test(sid) || sid.includes('..')) {
    return { ok: false, error: 'invalid sid' }
  }
  const base = process.env.BOBO_DATA_DIR || path.join(os.homedir(), '.bobo_v2')
  const archiveDir = path.resolve(base, 'archives')
  const target = path.resolve(archiveDir, `${sid}.jsonl`)
  if (!target.startsWith(archiveDir + path.sep)) {
    return { ok: false, error: 'invalid path' }
  }
  try {
    if (!fs.existsSync(target)) return { ok: true, records: [] }
    const lines = fs.readFileSync(target, 'utf8').split('\n').filter(Boolean)
    const records = lines
      .map((l) => { try { return JSON.parse(l) } catch { return null } })
      .filter(Boolean)
    return { ok: true, records }
  } catch (e) {
    return { ok: false, error: String((e && e.message) || e) }
  }
})

// Renderer requests any buffered backend messages that arrived before IPC was ready
ipcMain.on('backend-get-pending', (event) => {
  if (pendingMessages.length > 0) {
    for (const msg of pendingMessages) {
      event.sender.send('backend-message', msg)
    }
    pendingMessages = []
  }
})

// ── App lifecycle ──────────────────────────────────────────────────────

app.whenReady().then(() => {
  app.setName('Bobo')
  // Set dock icon (overrides Electron default in dev mode)
  try {
    const nativeImage = require('electron').nativeImage
    const iconPath = path.join(__dirname, '..', 'build', 'icon.icns')
    if (require('fs').existsSync(iconPath)) {
      app.dock.setIcon(nativeImage.createFromPath(iconPath))
    }
  } catch (_) {}
  startBackend()
  createWindow()
  // TICKET-DESK-V4: 重启按持久化开关自动恢复小组件（默认关）
  ensureWidgetByConfig()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
    // macOS Dock 激活恢复主窗后，同步恢复小组件（配置开启时）
    ensureWidgetByConfig()
  })
})

app.on('window-all-closed', () => {
  stopBackend()
  app.quit()
})

app.on('before-quit', () => {
  stopBackend()
})
