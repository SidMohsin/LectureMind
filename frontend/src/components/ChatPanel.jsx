import { useState, useRef, useEffect } from 'react'
import { askQuestion, getChatHistory, clearChatHistory, deleteChatHistoryItem } from '../services/api'
import { useApp } from '../context/AppContext'
import { formatTimeRange } from '../services/format'

const SUGGESTED_QUESTIONS = [
  'Summarize this lecture.',
  'What are the main concepts covered?',
  'What examples were discussed?',
  'What are the key points for revision?',
]

export default function ChatPanel({ lectureId, lectureReady, onSeek }) {
  const { triggerRefresh } = useApp()
  const [messages, setMessages] = useState([])
  const [historyLoaded, setHistoryLoaded] = useState(false)

  useEffect(() => {
    let cancelled = false
    async function loadHistory() {
      try {
        const data = await getChatHistory(lectureId)
        if (cancelled) return
        const history = []
        for (const item of data.items || []) {
          history.push({ role: 'user', text: item.question, logId: item.id })
          history.push({
            role: 'assistant',
            text: item.answer,
            sources: item.sources || [],
            latency: item.latency_ms,
            grounded: true,
          })
        }
        setMessages(history)
      } catch (err) {
        console.error('Failed to load chat history:', err)
      } finally {
        if (!cancelled) setHistoryLoaded(true)
      }
    }
    if (lectureId) loadHistory()
    return () => { cancelled = true }
  }, [lectureId])

  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState(null)
  const [llmUnavailable, setLlmUnavailable] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, sending])

  async function sendQuestion(question) {
    if (!question.trim() || sending) return
    setInput('')
    setError(null)
    setLlmUnavailable(false)
    setMessages((prev) => [...prev, { role: 'user', text: question }])
    setSending(true)
    try {
      const res = await askQuestion(lectureId, question)
      setMessages((prev) => [...prev, {
        role: 'assistant',
        text: res.answer,
        sources: res.sources,
        grounded: res.grounded,
        latency: res.latency_ms,
      }])
      triggerRefresh()
    } catch (e) {
      if (e.status === 503) setLlmUnavailable(true)
      else setError(e.message || 'Failed to get an answer.')
    } finally {
      setSending(false)
    }
  }

  async function handleClear() {
    try {
      await clearChatHistory(lectureId)
      setMessages([])
      setError(null)
      setLlmUnavailable(false)
      triggerRefresh()
    } catch (err) {
      setError('Failed to clear conversation.')
    }
  }

  async function handleDeleteQuestion(logId) {
    try {
      await deleteChatHistoryItem(lectureId, logId)
      setMessages((prev) => {
        const index = prev.findIndex((message) => message.role === 'user' && message.logId === logId)
        return index === -1 ? prev : prev.filter((_, messageIndex) => messageIndex !== index && messageIndex !== index + 1)
      })
      triggerRefresh()
    } catch (err) {
      setError(err.message || 'Failed to delete question.')
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendQuestion(input)
    }
  }

  return (
    <div className="chat-area">
      <div className="chat-header-row">
        <div>
          <h3>Ask about this lecture</h3>
          <p className="chat-subline">Answers are grounded in the transcript.</p>
        </div>
        {messages.length > 0 && (
          <button className="btn-ghost btn-small" onClick={handleClear}>Clear</button>
        )}
      </div>

      {!lectureReady && (
        <p className="hint">The assistant will be available once processing completes.</p>
      )}

      {lectureReady && messages.length === 0 && historyLoaded && (
        <div className="chat-suggestions">
          <span className="chat-suggestions-label">Try asking</span>
          <div className="chat-suggestions-list">
            {SUGGESTED_QUESTIONS.map((q, i) => (
              <button key={i} className="suggestion-chip" onClick={() => sendQuestion(q)}>{q}</button>
            ))}
          </div>
        </div>
      )}

      <div className="chat-window">
        {messages.map((m, idx) => (
          <div key={idx} className={`chat-message chat-${m.role}`}>
            <div className="chat-bubble">
              <span className="chat-role-label">{m.role === 'user' ? 'You' : 'LectureMind'}</span>
              {m.role === 'user' && m.logId && (
                <button className="chat-delete-question" onClick={() => handleDeleteQuestion(m.logId)} aria-label="Delete question">
                  Delete
                </button>
              )}
              <div className={`chat-text`}>{m.text}</div>

              {m.role === 'assistant' && m.grounded === false && (
                <p className="chat-ungrounded">Not found in the lecture content.</p>
              )}

              {m.role === 'assistant' && m.sources?.length > 0 && (
                <div className="chat-sources">
                  <span className="sources-label">Sources</span>
                  <div className="chat-sources-list">
                    {m.sources.map((s, i) => (
                      <button
                        key={i}
                        className="source-chip"
                        title={s.text}
                        onClick={() => onSeek && onSeek(s.start)}
                      >
                        <span className="source-chip-time">{formatTimeRange(s.start, s.end)}</span>
                        {typeof s.score === 'number' && (
                          <span className="source-chip-score">{Math.round(s.score * 100)}%</span>
                        )}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {m.role === 'assistant' && m.latency != null && (
                <span className="latency-label">{Math.round(m.latency)} ms</span>
              )}
            </div>
          </div>
        ))}

        {sending && (
          <div className="chat-message chat-assistant">
            <div className="chat-bubble">
              <span className="chat-role-label">LectureMind</span>
              <div className="chat-loading-bubble">
                <div className="typing-dots">
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                </div>
                <span className="chat-loading-label">Finding relevant sections…</span>
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {llmUnavailable && (
        <div className="error-banner" style={{ marginBottom: 12 }}>
          The configured LLM is unavailable. Check its API key, selected model, and backend logs, then restart the backend.
        </div>
      )}
      {error && <div className="error-banner" style={{ marginBottom: 12 }}>{error}</div>}

      <div className="chat-input-area">
        <textarea
          rows={2}
          placeholder={lectureReady ? 'Ask a question… (Enter to send, Shift+Enter for new line)' : 'Waiting for processing…'}
          value={input}
          disabled={!lectureReady || sending}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button
          className="btn-primary"
          disabled={!lectureReady || sending || !input.trim()}
          onClick={() => sendQuestion(input)}
        >
          {sending ? 'Thinking…' : 'Send'}
        </button>
      </div>
    </div>
  )
}
