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
})
