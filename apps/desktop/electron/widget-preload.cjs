// Bobo Desktop — TICKET-DESK-V4: 小组件 preload（context bridge）
// TICKET-DESK-V4B: 会话钉选 —— 增 4 桥（钉选指令/钉选变化上报/当前会话广播/会话列表广播），
// 全部只读监听或仅发"唤起主窗/上报钉选"两个 send，无任何后端写通道。
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('widgetAPI', {
  // 后端 JSON-RPC 事件流（主进程只读转发；小窗只监听不响应）
  onEvent: (callback) => {
    const handler = (_event, msg) => callback(msg)
    ipcRenderer.on('backend-message', handler)
    return () => ipcRenderer.removeListener('backend-message', handler)
  },

  // 主窗上下文药丸统计广播（只读投影；V4B 起带会话 sid）
  onCtxStats: (callback) => {
    const handler = (_event, data, sid) => callback(data, sid)
    ipcRenderer.on('widget-ctx-stats', handler)
    return () => ipcRenderer.removeListener('widget-ctx-stats', handler)
  },

  // 主窗用户指令广播（只读投影；V4B 起带会话 sid）
  onUserMsg: (callback) => {
    const handler = (_event, text, sid) => callback(text, sid)
    ipcRenderer.on('widget-user-msg', handler)
    return () => ipcRenderer.removeListener('widget-user-msg', handler)
  },

  // 后端状态（exited/error）
  onStatus: (callback) => {
    const handler = (_event, data) => callback(data)
    ipcRenderer.on('backend-status', handler)
    return () => ipcRenderer.removeListener('backend-status', handler)
  },

  // 审批待审时点击小窗 → 唤起主窗并跳到对应会话（只调主窗现成入口，不自建通道）
  approvalFocus: (sid) => ipcRenderer.send('widget-approval-focus', String(sid || '')),

  // ── TICKET-DESK-V4B 会话钉选：4 桥 ──────────────────────────────────
  // 主窗行内"投影到小组件"按钮 → 钉选指令（sid 空串 = 回落跟随主窗）
  onPinSession: (callback) => {
    const handler = (_event, sid) => callback(String(sid || ''))
    ipcRenderer.on('widget-pin-session', handler)
    return () => ipcRenderer.removeListener('widget-pin-session', handler)
  },
  // 小窗点击会话名轮换/回落 → 上报主窗（主窗同步行内按钮态，三向一致）
  pinChanged: (sid) => ipcRenderer.send('widget-pin-changed', String(sid || '')),
  // 主窗当前会话广播（跟随模式对照基准；带 title 供会话指示显示）
  onCurrentSession: (callback) => {
    const handler = (_event, sid, title) => callback(String(sid || ''), String(title || ''))
    ipcRenderer.on('widget-current-session', handler)
    return () => ipcRenderer.removeListener('widget-current-session', handler)
  },
  // 主窗会话列表广播（会话名映射 + 删除回落兜底：钉住 sid 不在列表 → 回落跟随）
  onSessions: (callback) => {
    const handler = (_event, list) => callback(list || [])
    ipcRenderer.on('widget-sessions', handler)
    return () => ipcRenderer.removeListener('widget-sessions', handler)
  },
})
