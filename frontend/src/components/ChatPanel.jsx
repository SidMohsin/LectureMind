import { useState, useRef, useEffect } from 'react'
import { askQuestion } from '../services/api'
import { formatTimeRange } from '../services/format'

const SUGGESTED_QUESTIONS = [
  'Summarize this lecture.',
  'What are the main concepts?',
  'What examples were discussed?',
  'What are the important points for revision?',
]

export default function ChatPanel({ lectureId, lectureReady, onSeek }) {
  const [messages, setMessages] = useState([])
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
    } catch (e) {
      if (e.status === 503) {
        setLlmUnavailable(true)
      } else {
        setError(e.message || 'Failed to get an answer from LectureMind.')
      }
    } finally {
      setSending(false)
    }
  }

  function handleSend() {
    sendQuestion(input)
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  function handleClear() {
    setMessages([])
    setError(null)
    setLlmUnavailable(false)
  }

  return (
    <div className="card chat-card">
      <div className="chat-header">
        <div>
          <h3>Ask LectureMind</h3>
          <p className="hint">Ask questions about this lecture — answers are grounded in the transcript.</p>
        </div>
        {messages.length > 0 && (
          <button className="btn-secondary btn-small" onClick={handleClear}>Clear conversation</button>
        )}
      </div>

      {!lectureReady && (
        <p className="hint">The chatbot will be available once processing is completed.</p>
      )}

      {lectureReady && messages.length === 0 && (
        <div className="chat-suggestions">
          <span className="chat-suggestions-label">Try asking:</span>
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
              <strong className="chat-bubble-role">{m.role === 'user' ? 'You' : 'LectureMind'}</strong>
              <p>{m.text}</p>
              {m.role === 'assistant' && !m.grounded && (
                <span className="chat-ungrounded-note">Not found in this lecture's content.</span>
              )}
              {m.role === 'assistant' && m.sources && m.sources.length > 0 && (
                <div className="chat-sources">
                  <span className="sources-label">Sources from lecture</span>
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
                          <span className="source-chip-score">{Math.round(s.score * 100)}% match</span>
                        )}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {m.role === 'assistant' && (
                <span className="latency-label">{m.latency?.toFixed?.(0)} ms</span>
              )}
            </div>
          </div>
        ))}

        {sending && (
          <div className="chat-message chat-assistant">
            <div className="chat-bubble chat-bubble-loading">
              <span className="typing-dot" /><span className="typing-dot" /><span className="typing-dot" />
              <span className="chat-loading-label">Finding relevant lecture sections and generating an answer…</span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {llmUnavailable && (
        <div className="error-banner">
          Configure your selected LLM provider to enable AI answers. See <code>backend/.env</code> — set
          <code> LLM_PROVIDER</code> to <code>ollama</code>, <code>openai</code>, or <code>groq</code> and make sure
          it is reachable (e.g. <code>ollama serve</code>), then restart the backend.
        </div>
      )}
      {error && <div className="error-banner">{error}</div>}

      <div className="chat-input-row">
        <textarea
          rows={2}
          placeholder={lectureReady ? 'Ask a question about this lecture… (Enter to send, Shift+Enter for a new line)' : 'Waiting for processing to finish…'}
          value={input}
          disabled={!lectureReady || sending}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button
          className="btn-primary"
          disabled={!lectureReady || sending || !input.trim()}
          onClick={handleSend}
        >
          {sending ? 'Thinking…' : 'Send'}
        </button>
      </div>
    </div>
  )
}
