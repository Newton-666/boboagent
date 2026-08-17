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

  // 票 DESK-P1：Choose a folder（别名，复用 select-folder IPC——main.cjs 已
  // 实现 dialog.showOpenDialog properties:['openDirectory']）
  chooseFolder: () => ipcRenderer.invoke('select-folder'),

  // Save .env config (bypasses backend, writes directly)
  saveEnv: (data) => ipcRenderer.invoke('save-env', data),

  // TICKET-GUI-F3 (F3-3): 读取会话上下文归档（archives/{sid}.jsonl）
  readArchive: (sid) => ipcRenderer.invoke('read-archive', sid),

  // TICKET-DESK-V4: 小组件开关/状态（只读投影的开关与状态查询）
  widgetToggle: () => ipcRenderer.invoke('widget-toggle'),
  widgetStatus: () => ipcRenderer.invoke('widget-status'),

  // TICKET-DESK-V4: 只读广播（主窗现有数据 → 小窗镜像；不改主窗任何行为）
  // V4B: 广播带会话 sid（小窗按钉选过滤，A 的事件/药丸不泄漏到钉 B 的小窗）
  widgetCtxStats: (data, sid) => ipcRenderer.send('widget-ctx-stats', data, sid),
  widgetUserMsg: (text, sid) => ipcRenderer.send('widget-user-msg', text, sid),

  // TICKET-DESK-V4: 审批联动落地 —— 小窗点击 → 主窗跳到对应会话（现成 loadSession 入口）
  onWidgetFocusSession: (callback) => {
    const handler = (_event, sid) => callback(sid)
    ipcRenderer.on('widget-focus-session', handler)
    return () => ipcRenderer.removeListener('widget-focus-session', handler)
  },

  // ── TICKET-DESK-V4B 会话钉选：主窗侧 4 桥 ──────────────────────────
  // 行内"投影到小组件"按钮 → 主进程 → 小窗（钉选/回落）
  widgetPinSession: (sid) => ipcRenderer.send('widget-pin-session', String(sid || '')),
  // 小窗钉选变化（点击轮换/回落）→ 主窗同步行内按钮态
  onWidgetPinChanged: (callback) => {
    const handler = (_event, sid) => callback(sid)
    ipcRenderer.on('widget-pin-changed', handler)
    return () => ipcRenderer.removeListener('widget-pin-changed', handler)
  },
  // 主窗当前会话广播 → 小窗（跟随模式基准；带 title 供会话指示）
  widgetCurrentSession: (sid, title) => ipcRenderer.send('widget-current-session', String(sid || ''), String(title || '')),
  // 主窗会话列表广播 → 小窗（会话名映射 + 删除回落兜底）
  widgetSessions: (list) => ipcRenderer.send('widget-sessions', Array.isArray(list) ? list : []),
})
