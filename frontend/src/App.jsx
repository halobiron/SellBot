import { useState, useRef, useEffect } from 'react'
import { sendChat, sendChatStream, resetChat } from './api'
import Message from './components/Message'
import QuickSuggestions from './components/QuickSuggestions'

const SID = (() => {
  let s = sessionStorage.getItem('emx_sid')
  if (!s) {
    s = 'demo-' + Math.random().toString(36).slice(2)
    sessionStorage.setItem('emx_sid', s)
  }
  return s
})()

export default function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState(null)
  const [theme, setTheme] = useState(() => localStorage.getItem('emx_theme') || 'light')
  
  const chatRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('emx_theme', theme)
  }, [theme])

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'light' ? 'dark' : 'light'))
  }

  const scrollToBottom = () => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight
    }
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, status])

  function replaceLast(msg) {
    setMessages((m) => [...m.slice(0, -1), msg])
  }

  async function send(text) {
    if (!text || busy) return
    const userMsg = {
      id: 'msg-' + Date.now(),
      role: 'user',
      text,
    }
    setMessages((m) => [...m, userMsg])
    setInput('')
    setBusy(true)
    setStatus('Đang xử lý yêu cầu…')

    let streamed = false
    const botMsgId = 'msg-' + (Date.now() + 1)
    
    try {
      const res = await sendChatStream(SID, text, {
        onStatus: (st) => setStatus(st),
        onDelta: (chunk) => {
          if (!streamed) {
            streamed = true
            setStatus(null)
            setMessages((m) => [
              ...m,
              {
                id: botMsgId,
                role: 'bot',
                text: chunk,
              },
            ])
          } else {
            setMessages((m) => {
              const last = m[m.length - 1]
              return [...m.slice(0, -1), { ...last, text: last.text + chunk }]
            })
          }
        },
      })

      const finalMsg = {
        id: botMsgId,
        role: 'bot',
        text: res.reply,
        recommendation: res.recommendation,
      }

      if (streamed) replaceLast(finalMsg)
      else setMessages((m) => [...m, finalMsg])
    } catch (e) {
      if (e.phase === 'connect') {
        try {
          const res = await sendChat(SID, text)
          setMessages((m) => [
            ...m,
            {
              id: botMsgId,
              role: 'bot',
              text: res.reply,
              recommendation: res.recommendation,
            },
          ])
        } catch {
          setMessages((m) => [
            ...m,
            {
              id: botMsgId,
              role: 'bot',
              text: 'Hệ thống đang bận. Vui lòng thử lại sau ít phút.',
            },
          ])
        }
      } else {
        const errMsg = {
          id: botMsgId,
          role: 'bot',
          text: 'Kết nối bị gián đoạn. Vui lòng gửi lại câu hỏi.',
        }
        if (streamed) replaceLast(errMsg)
        else setMessages((m) => [...m, errMsg])
      }
    } finally {
      setBusy(false)
      setStatus(null)
      if (inputRef.current) inputRef.current.focus()
    }
  }

  function submit(e) {
    e.preventDefault()
    send(input.trim())
  }

  async function onReset() {
    if (busy) return
    try {
      await resetChat(SID)
    } catch {
      /* ignore */
    }
    setMessages([])
    if (inputRef.current) inputRef.current.focus()
  }

  return (
    <div className="app-layout">
      <div className="app-container">
        {/* Minimal Clean Header */}
        <header className="app-header">
          <div className="brand-group">
            <div className="brand-avatar">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
              </svg>
            </div>
            <div>
              <h1 className="brand-name">Điện Máy Xanh AI</h1>
              <span className="brand-status"><span className="status-dot" />Sẵn sàng tư vấn</span>
            </div>
          </div>

          <div className="header-actions">
            <button
              className="icon-btn"
              onClick={toggleTheme}
              title={theme === 'light' ? 'Chế độ tối' : 'Chế độ sáng'}
            >
              {theme === 'light' ? (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z" />
                </svg>
              ) : (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z" />
                </svg>
              )}
            </button>

            <button
              className="btn-new-chat"
              onClick={onReset}
              disabled={busy}
              title="Làm mới cuộc trò chuyện"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
              </svg>
              <span>Làm mới</span>
            </button>
          </div>
        </header>

        {/* Chat Feed */}
        <main className="chat-viewport" ref={chatRef}>
          <div className="messages-list">
            {messages.map((m, i) => (
              <Message
                key={m.id || i}
                msg={m}
                isLast={i === messages.length - 1}
                onSuggest={send}
                disabled={busy}
              />
            ))}

            {messages.length === 0 && (
              <QuickSuggestions onPick={send} disabled={busy} />
            )}

            {/* Live Typing Status */}
            {busy && status !== null && (
              <div className="msg-row bot-row typing-row">
                <div className="typing-bubble">
                  <span className="typing-text">{status}</span>
                  <div className="typing-dots">
                    <span />
                    <span />
                    <span />
                  </div>
                </div>
              </div>
            )}
          </div>
        </main>

        {/* Minimal Composer */}
        <footer className="composer-wrapper">
          <form className="composer-form" onSubmit={submit}>
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Nhập nhu cầu tư vấn (VD: Tủ lạnh 4 người dưới 15 triệu, máy giặt sấy...)"
              aria-label="Nội dung câu hỏi"
              autoFocus
            />
            <button
              type="submit"
              className="send-btn"
              disabled={busy || input.trim().length === 0}
              aria-label="Gửi"
            >
              {busy ? (
                <svg className="spinner-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path strokeLinecap="round" d="M12 3a9 9 0 1 0 9 9" />
                </svg>
              ) : (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.125A59.769 59.769 0 0121.485 12 59.768 59.768 0 013.27 20.875L5.999 12Zm0 0h7.5" />
                </svg>
              )}
            </button>
          </form>
        </footer>
      </div>
    </div>
  )
}

