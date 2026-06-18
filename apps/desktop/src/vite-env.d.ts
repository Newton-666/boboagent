/// <reference types="vite/client" />

interface Window {
  boboAPI: {
    send: (msg: Record<string, unknown>) => void
    onMessage: (callback: (msg: Record<string, unknown>) => void) => () => void
    onStatus: (callback: (data: { status: string; message?: string; code?: number }) => void) => () => void
    onLog: (callback: (data: { stream: string; text: string }) => void) => () => void
  }
}
