// Bobo Desktop — Electron main process
// Spawns Python backend, bridges JSON-RPC between renderer and backend.

const { app, BrowserWindow, ipcMain } = require('electron')
const { spawn } = require('child_process')
const path = require('path')
const fs = require('fs')

let mainWindow = null
let backendProcess = null
let backendBuffer = ''
let backendRestartCount = 0
const MAX_BACKEND_RESTARTS = 3
let pendingMessages = []  // Buffer for messages received before window's IPC listener is ready

// ── Python backend management ──────────────────────────────────────────

function resolvePython() {
  // Try configured python, then common paths
  const configured = process.env.BOBO_PYTHON
  if (configured && fs.existsSync(configured)) return configured

  for (const cmd of ['python3', 'python']) {
    try {
      const result = require('child_process').execSync(`${cmd} --version`, { timeout: 3000 })
      if (result) return cmd
    } catch {}
  }
  return 'python3'
}

function startBackend() {
  const python = resolvePython()
  const isPackaged = app.isPackaged
  let projectRoot
  if (isPackaged) {
    // Packaged .dmg: Python backend is bundled in Resources
    projectRoot = path.join(process.resourcesPath, 'bobo-backend')
  } else {
    // Dev: 3 levels up from electron/ to project root
    projectRoot = path.resolve(__dirname, '..', '..', '..')
  }

  const env = {
    ...process.env,
    BOBO_BACKEND: '1',
    PYTHONPATH: projectRoot,
    BOBO_CWD: process.cwd(),
  }

  console.log(`[bobo-desktop] Starting backend: ${python} -m bobo_tui_gateway.entry`)
  console.log(`[bobo-desktop] Project root: ${projectRoot}`)

  backendProcess = spawn(python, ['-m', 'bobo_tui_gateway.entry'], {
    cwd: projectRoot,
    env,
    stdio: ['pipe', 'pipe', 'pipe'],
  })

  backendProcess.on('error', (err) => {
    console.error(`[bobo-desktop] Backend spawn error: ${err.message}`)
    if (mainWindow) {
      mainWindow.webContents.send('backend-status', { status: 'error', message: err.message })
    }
  })

  backendProcess.on('exit', (code) => {
    console.log(`[bobo-desktop] Backend exited with code ${code}`)
    backendProcess = null
    if (mainWindow) {
      mainWindow.webContents.send('backend-status', { status: 'exited', code })
    }
    // Auto-restart with backoff (up to MAX_BACKEND_RESTARTS times)
    if (code !== 0 && backendRestartCount < MAX_BACKEND_RESTARTS) {
      backendRestartCount++
      const delay = backendRestartCount * 1000
      console.log(`[bobo-desktop] Restarting backend in ${delay}ms (attempt ${backendRestartCount}/${MAX_BACKEND_RESTARTS})`)
      setTimeout(() => startBackend(), delay)
    } else if (code !== 0) {
      console.error(`[bobo-desktop] Backend crashed ${MAX_BACKEND_RESTARTS} times, giving up`)
    }
  })

  backendProcess.stderr.on('data', (data) => {
    const text = data.toString()
    if (mainWindow) {
      mainWindow.webContents.send('backend-log', { stream: 'stderr', text })
    }
    process.stderr.write(`[backend] ${text}`)
  })

  // Parse JSON-RPC lines from stdout
  backendProcess.stdout.on('data', (data) => {
    backendBuffer += data.toString()
    const lines = backendBuffer.split('\n')
    backendBuffer = lines.pop() // keep incomplete line in buffer

    for (const line of lines) {
      if (!line.trim()) continue
      try {
        const msg = JSON.parse(line)
        if (mainWindow) {
          mainWindow.webContents.send('backend-message', msg)
        } else {
          pendingMessages.push(msg)
        }
      } catch {
        process.stderr.write(`[bobo-desktop] Unparseable backend output: ${line.slice(0, 100)}\n`)
      }
    }
  })
}

function sendToBackend(msg) {
  if (!backendProcess || !backendProcess.stdin) {
    console.warn('[bobo-desktop] Backend not running, cannot send message')
    return false
  }
  backendProcess.stdin.write(JSON.stringify(msg) + '\n')
  return true
}

function stopBackend() {
  if (backendProcess) {
    backendProcess.stdin.end()
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
  mainWindow = new BrowserWindow({
    width: 900,
    height: 680,
    minWidth: 500,
    minHeight: 400,
    title: 'Bobo',
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

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

// ── IPC handlers ───────────────────────────────────────────────────────

ipcMain.on('backend-send', (_event, msg) => {
  sendToBackend(msg)
})

ipcMain.handle('backend-send-sync', async (_event, msg) => {
  return sendToBackend(msg)
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
  startBackend()
  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  stopBackend()
  app.quit()
})

app.on('before-quit', () => {
  stopBackend()
})
