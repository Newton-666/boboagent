// Bobo Desktop — TICKET-DESK-V4: 小组件 preload（context bridge）
// 只读投影桥：小窗只能收事件/收统计/发"唤起主窗"请求，无任何后端写通道。
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('widgetAPI', {
  // 后端 JSON-RPC 事件流（主进程只读转发；小窗只监听不响应）
  onEvent: (callback) => {
    const handler = (_event, msg) => callback(msg)
    ipcRenderer.on('backend-message', handler)
    return () => ipcRenderer.removeListener('backend-message', handler)
  },

  // 主窗上下文药丸统计广播（只读投影）
  onCtxStats: (callback) => {
    const handler = (_event, data) => callback(data)
    ipcRenderer.on('widget-ctx-stats', handler)
    return () => ipcRenderer.removeListener('widget-ctx-stats', handler)
  },

  // 主窗用户指令广播（只读投影）
  onUserMsg: (callback) => {
    const handler = (_event, text) => callback(text)
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
})
