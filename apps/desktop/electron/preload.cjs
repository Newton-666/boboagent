// Bobo Desktop — Preload script (context bridge)
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('boboAPI', {
  // Send a JSON-RPC message to the Python backend
  send: (msg) => ipcRenderer.send('backend-send', msg),

  // Request any messages buffered before IPC listener was ready
  getPending: () => ipcRenderer.send('backend-get-pending'),

  // Listen for messages from the Python backend
  onMessage: (callback) => {
    const handler = (_event, msg) => callback(msg)
    ipcRenderer.on('backend-message', handler)
    return () => ipcRenderer.removeListener('backend-message', handler)
  },

  // Listen for backend status changes (exited, error)
  onStatus: (callback) => {
    const handler = (_event, data) => callback(data)
    ipcRenderer.on('backend-status', handler)
    return () => ipcRenderer.removeListener('backend-status', handler)
  },

  // Open native macOS folder picker
  selectFolder: () => ipcRenderer.invoke('select-folder'),

  // Save .env config (bypasses backend, writes directly)
  saveEnv: (data) => ipcRenderer.invoke('save-env', data),

  // TICKET-GUI-F3 (F3-3): 读取会话上下文归档（archives/{sid}.jsonl）
  readArchive: (sid) => ipcRenderer.invoke('read-archive', sid),

  // TICKET-DESK-V4: 小组件开关/状态（只读投影的开关与状态查询）
  widgetToggle: () => ipcRenderer.invoke('widget-toggle'),
  widgetStatus: () => ipcRenderer.invoke('widget-status'),

  // TICKET-DESK-V4: 只读广播（主窗现有数据 → 小窗镜像；不改主窗任何行为）
  widgetCtxStats: (data) => ipcRenderer.send('widget-ctx-stats', data),
  widgetUserMsg: (text) => ipcRenderer.send('widget-user-msg', text),

  // TICKET-DESK-V4: 审批联动落地 —— 小窗点击 → 主窗跳到对应会话（现成 loadSession 入口）
  onWidgetFocusSession: (callback) => {
    const handler = (_event, sid) => callback(sid)
    ipcRenderer.on('widget-focus-session', handler)
    return () => ipcRenderer.removeListener('widget-focus-session', handler)
  },
})
