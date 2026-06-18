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
  toolResult?: string
  toolDuration?: number
  toolError?: string
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
  const [debugInfo, setDebugInfo] = useState('Starting...')
  const [showSetup, setShowSetup] = useState(false)
  const [setupProvider, setSetupProvider] = useState('deepseek')
  const [setupKey, setSetupKey] = useState('')
  const [setupError, setSetupError] = useState('')
  const chatEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  // Track streaming text buffer to avoid React re-render thrashing
  const streamingBufRef = useRef('')
  const streamingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  // Flush streaming buffer to messages state (throttled)
  const flushStreaming = useCallback(() => {
    if (streamingTimerRef.current) {
      clearTimeout(streamingTimerRef.current)
      streamingTimerRef.current = null
    }
    const buf = streamingBufRef.current
    if (!buf) return
    streamingBufRef.current = ''
    setMessages((prev) => {
      const last = prev[prev.length - 1]
      if (last && last.role === 'assistant' && last.id === 'streaming') {
        return [...prev.slice(0, -1), { ...last, text: last.text + buf }]
      }
      return [...prev, { id: 'streaming', role: 'assistant', text: buf }]
    })
  }, [])

  useEffect(() => {
    setDebugInfo('Connecting...')
    if (isBrowserDev) gw.connect(9876)
    else gw.connect()

    gw.on('gateway.ready', async () => {
      setDebugInfo('Connected ✓')
      setConnected(true)
      // Check if provider is configured
      const statusResult = await gw.call('setup.status', {})
      const needsSetup = statusResult && typeof statusResult === 'object' && (statusResult as Record<string, unknown>).provider_configured === false
      if (needsSetup) {
        setShowSetup(true)
        setDebugInfo('Setup required')
        return
      }
      const result = await gw.call('session.create', { title: 'New Chat' })
      if (result && typeof result === 'object' && !('error' in result) && 'session_id' in result) {
        const r = result as Record<string, unknown>
        const sid = r.session_id as string
        setSessionId(sid)
        setSessions(prev => [...prev, { id: sid, title: 'New Chat' }])
        gw.subscribe(sid)
      } else if (result && typeof result === 'object' && 'error' in result) {
        const err = result as { error: { message?: string } }
        setDebugInfo(`Error: ${err.error?.message || 'session.create failed'}`)
      }
    })

    gw.on('thinking.delta', (data) => {
      const text = (data as Record<string, string>).text || ''
      if (text) {
        setDebugInfo(`Thinking: ${text.slice(0, 60)}...`)
      }
    })

    gw.on('message.delta', (data) => {
      const text = (data as Record<string, string>).text || ''
      if (!text) return
      streamingBufRef.current += text
      // Throttle React updates to ~50ms intervals
      if (!streamingTimerRef.current) {
        streamingTimerRef.current = setTimeout(flushStreaming, 50)
      }
    })

    gw.on('message.start', () => {
      setStreaming(true)
      setDebugInfo('Receiving...')
      streamingBufRef.current = ''
    })

    gw.on('message.complete', (data) => {
      setStreaming(false)
      // Flush any remaining buffered text
      flushStreaming()
      const d = data as Record<string, string>
      const finalText = d.final_text || ''
      if (finalText) {
        setMessages((prev) => {
          if (prev[prev.length - 1]?.id === 'streaming') {
            return [...prev.slice(0, -1), { id: `msg-${Date.now()}`, role: 'assistant', text: finalText }]
          }
          return prev
        })
      }
      setDebugInfo('Ready')
    })

    gw.on('tool.start', (data) => {
      const d = data as Record<string, unknown>
      const name = (d.name || d.tool_id) as string
      const args = d.arguments as Record<string, unknown> | undefined
      const argsText = args ? JSON.stringify(args).slice(0, 200) : ''
      setMessages((prev) => [...prev, {
        id: `tool-${Date.now()}`,
        role: 'tool',
        text: argsText,
        toolName: name,
      }])
      setDebugInfo(`Tool: ${name}`)
    })

    gw.on('tool.complete', (data) => {
      const d = data as Record<string, unknown>
      const name = d.name as string
      const resultText = (d.result_text as string) || ''
      const error = d.error as string
      const duration = d.duration as number
      // Update the last tool message with result
      setMessages((prev) => {
        // Find the last tool message with matching name
        for (let i = prev.length - 1; i >= 0; i--) {
          if (prev[i].role === 'tool' && prev[i].toolName === name) {
            const updated = [...prev]
            updated[i] = {
              ...updated[i],
              toolResult: resultText.slice(0, 300),
              toolDuration: duration,
              toolError: error,
            }
            return updated
          }
        }
        return prev
      })
      setDebugInfo(`Tool ${name} ${error ? 'failed' : 'done'}`)
    })

    gw.on('status.update', (data) => {
      const d = data as Record<string, string>
      if (d.text && d.text !== '工具执行完成' && d.text !== '正在思考...') {
        setMessages((prev) => [...prev, { id: `status-${Date.now()}`, role: 'system', text: d.text }])
      }
    })

    gw.on('backend.exited', () => {
      setConnected(false)
      setStreaming(false)
      setMessages((prev) => [...prev, { id: `err-${Date.now()}`, role: 'system', text: 'Backend disconnected.' }])
      setDebugInfo('Disconnected')
    })

    return () => {
      if (streamingTimerRef.current) clearTimeout(streamingTimerRef.current)
      try { gw.disconnect() } catch {}
    }
  }, [flushStreaming])

  const handleSend = useCallback(() => {
    if (!input.trim() || !sessionId || !connected) return
    const userText = input.trim()
    setInput('')
    setMessages((prev) => [...prev, { id: `user-${Date.now()}`, role: 'user', text: userText }])
    gw.sendPrompt(sessionId, userText)
  }, [input, sessionId, connected])

  const handleSetup = async () => {
    if (!setupKey.trim()) return
    setSetupError('')
    setDebugInfo('Configuring...')
    const result = await gw.call('setup.submit', { provider: setupProvider, api_key: setupKey.trim() })
    if (result && typeof result === 'object' && (result as Record<string, unknown>).ok === false) {
      const errMsg = (result as Record<string, unknown>).error as string || 'Configuration failed'
      setSetupError(errMsg)
      setDebugInfo('Setup failed')
      return
    }
    setShowSetup(false)
    setDebugInfo('Setup complete, creating session...')
    // Create session after setup
    const createResult = await gw.call('session.create', { title: 'New Chat' })
    if (createResult && typeof createResult === 'object' && !('error' in createResult) && 'session_id' in createResult) {
      const cr = createResult as Record<string, unknown>
      const sid = cr.session_id as string
      setSessionId(sid)
      setSessions(prev => [...prev, { id: sid, title: 'New Chat' }])
      gw.subscribe(sid)
      setDebugInfo('Ready')
    }
  }

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }, [handleSend])

  const switchSession = useCallback(async (sid: string) => {
    if (sid === sessionId) return
    setDebugInfo('Switching session...')
    setSessionId(sid)
    setMessages([])
    // Load history via session.resume
    const result = await gw.call('session.resume', { session_id: sid })
    if (result && typeof result === 'object' && !('error' in result)) {
      const r = result as { messages?: Array<{ role: string; text: string }> }
      if (r.messages && r.messages.length > 0) {
        setMessages(r.messages.map((m, i) => ({
          id: `hist-${i}`,
          role: m.role as Message['role'],
          text: m.text,
        })))
      }
    }
    gw.subscribe(sid)
    setDebugInfo('Ready')
  }, [sessionId])

  const newChat = async () => {
    const result = await gw.call('session.create', { title: 'New Chat' })
    if (result && typeof result === 'object' && !('error' in result) && 'session_id' in result) {
      const r = result as Record<string, unknown>
      const sid = r.session_id as string
      setSessionId(sid)
      setMessages([])
      setSessions(prev => [...prev, { id: sid, title: 'New Chat' }])
      gw.subscribe(sid)
      setDebugInfo('Ready')
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
              onClick={() => switchSession(s.id)}>
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
        {showSetup ? (
          <div className="welcome">
            <h1>Bobo</h1>
            <p className="welcome-sub">配置 API Key</p>
            <div className="setup-form">
              <select className="setup-select" value={setupProvider} onChange={(e) => setSetupProvider(e.target.value)}>
                <option value="deepseek">DeepSeek</option>
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic</option>
                <option value="google">Google</option>
              </select>
              <input className="setup-input" type="password" placeholder="Paste your API key here..."
                value={setupKey} onChange={(e) => setSetupKey(e.target.value)} />
              {setupError && <p className="setup-error">{setupError}</p>}
              <button className="setup-btn" onClick={handleSetup} disabled={!setupKey.trim()}>
                Submit
              </button>
            </div>
            <p className="hint">Need a key? <a href="https://platform.deepseek.com/api-keys" target="_blank">Get DeepSeek key</a></p>
          </div>
        ) : messages.length === 0 ? (
          <div className="welcome">
            <h1>Bobo</h1>
            <p className="welcome-sub">你的个人 AI 助手</p>
            <p className="debug-line">[{debugInfo}]</p>
          </div>
        ) : (
          <div className="chat">
            {messages.map((msg) => (
              <div key={msg.id} className={`msg-row ${msg.role === 'user' ? 'user-row' : ''}`}>
                {msg.role === 'tool' && (
                  <div className="tool-badge">
                    🔧 {msg.toolName || 'Tool'}
                    {msg.toolDuration !== undefined && ` (${msg.toolDuration.toFixed(1)}s)`}
                    {msg.toolError && <span className="tool-error"> ⚠ {msg.toolError}</span>}
                    {msg.toolResult && <div className="tool-result">{msg.toolResult}</div>}
                  </div>
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
