import { useState, useEffect, useRef, useCallback } from 'react'
import { gateway } from '../lib/gateway'
import { browserGateway } from '../lib/gateway-browser'

const gw = window.boboAPI ? gateway : browserGateway
const isBrowserDev = !window.boboAPI

interface Message {
  id: string
  role: 'user' | 'assistant' | 'system' | 'tool'
  text: string
  toolName?: string
}

interface ChatSession {
  id: string
  title: string
}

function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [connected, setConnected] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const chatEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  useEffect(() => {
    if (isBrowserDev) gw.connect(9876)
    else gw.connect()

    gw.on('gateway.ready', async () => {
      setConnected(true)
      const result = await gw.call('session.create', { title: 'New Chat' })
      if (result && typeof result === 'object' && 'session_id' in result) {
        const sid = (result as Record<string, unknown>).session_id as string
        setSessionId(sid)
        setSessions(prev => [...prev, { id: sid, title: 'New Chat' }])
        gw.subscribe(sid)
      }
    })

    gw.on('message.delta', (data) => {
      const text = (data as Record<string, string>).text || ''
      setMessages((prev) => {
        const last = prev[prev.length - 1]
        if (last && last.role === 'assistant' && last.id === 'streaming') {
          return [...prev.slice(0, -1), { ...last, text: last.text + text }]
        }
        return [...prev, { id: 'streaming', role: 'assistant', text }]
      })
    })

    gw.on('message.start', () => setStreaming(true))

    gw.on('message.complete', (data) => {
      setStreaming(false)
      const finalText = (data as Record<string, string>).final_text || ''
      if (finalText) {
        setMessages((prev) => {
          if (prev[prev.length - 1]?.id === 'streaming') {
            return [...prev.slice(0, -1), { id: `msg-${Date.now()}`, role: 'assistant', text: finalText }]
          }
          return prev
        })
      }
    })

    gw.on('tool.start', (data) => {
      const d = data as Record<string, unknown>
      setMessages((prev) => [...prev, { id: `tool-${Date.now()}`, role: 'tool', text: '', toolName: (d.name || d.tool_id) as string }])
    })

    gw.on('status.update', (data) => {
      const d = data as Record<string, string>
      if (d.text && d.text !== '工具执行完成' && d.text !== '正在思考...') {
        setMessages((prev) => [...prev, { id: `status-${Date.now()}`, role: 'system', text: d.text }])
      }
    })

    gw.on('backend.exited', () => {
      setConnected(false)
      setMessages((prev) => [...prev, { id: `err-${Date.now()}`, role: 'system', text: 'Backend disconnected.' }])
    })

    return () => { try { gw.disconnect() } catch {} }
  }, [])

  const handleSend = useCallback(() => {
    if (!input.trim() || !sessionId || !connected) return
    const userText = input.trim()
    setInput('')
    setMessages((prev) => [...prev, { id: `user-${Date.now()}`, role: 'user', text: userText }])
    gw.sendPrompt(sessionId, userText)
  }, [input, sessionId, connected])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }, [handleSend])

  const newChat = async () => {
    const result = await gw.call('session.create', { title: 'New Chat' })
    if (result && typeof result === 'object' && 'session_id' in result) {
      const sid = (result as Record<string, unknown>).session_id as string
      setSessionId(sid)
      setMessages([])
      setSessions(prev => [...prev, { id: sid, title: 'New Chat' }])
      gw.subscribe(sid)
    }
  }

  return (
    <div className="app">
      {/* Sidebar */}
      <aside className={`sidebar ${sidebarOpen ? 'open' : 'closed'}`}>
        <div className="sidebar-header">
          <button className="new-chat-btn" onClick={newChat}>+ 新对话</button>
        </div>
        <div className="sidebar-list">
          {sessions.map(s => (
            <div key={s.id} className={`sidebar-item ${s.id === sessionId ? 'active' : ''}`}
              onClick={() => { setSessionId(s.id); setMessages([]); gw.subscribe(s.id) }}>
              {s.title}
            </div>
          ))}
        </div>
        <div className="sidebar-footer">
          {isBrowserDev && <span className="dev-badge">Dev</span>}
          <span className={`dot ${connected ? 'green' : 'red'}`} />
          {connected ? 'Connected' : 'Offline'}
        </div>
      </aside>

      {/* Toggle sidebar */}
      <button className="sidebar-toggle" onClick={() => setSidebarOpen(!sidebarOpen)}>
        {sidebarOpen ? '◁' : '▷'}
      </button>

      {/* Main */}
      <div className="main">
        {messages.length === 0 ? (
          <div className="welcome">
            <h1>Bobo</h1>
            <p className="welcome-sub">你的个人 AI 助手</p>
          </div>
        ) : (
          <div className="chat">
            {messages.map((msg) => (
              <div key={msg.id} className={`msg-row ${msg.role === 'user' ? 'user-row' : ''}`}>
                {msg.role === 'tool' && (
                  <div className="tool-badge">🔧 {msg.toolName || 'Tool'}</div>
                )}
                {msg.role === 'system' && (
                  <div className="system-msg">{msg.text}</div>
                )}
                {(msg.role === 'user' || msg.role === 'assistant') && (
                  <div className={`bubble ${msg.role}`}>
                    <div className="bubble-role">{msg.role === 'user' ? 'You' : 'Bobo'}</div>
                    <div className="bubble-text">{msg.text || (streaming && msg.id === 'streaming' ? '...' : '')}</div>
                  </div>
                )}
              </div>
            ))}
            <div ref={chatEndRef} />
          </div>
        )}

        {/* Input */}
        <div className="input-box">
          <textarea
            ref={textareaRef}
            className="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={connected ? '给 Bobo 发送消息...' : 'Connecting...'}
            disabled={!connected || streaming}
            rows={1}
          />
          <button className="send-btn" onClick={handleSend} disabled={!connected || !input.trim()}>
            ↑
          </button>
        </div>
      </div>
    </div>
  )
}

export default App
