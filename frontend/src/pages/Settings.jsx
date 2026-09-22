import { useState, useEffect } from 'react'
import { getConfig } from '../services/api'
import { SkeletonBlock } from '../components/Skeleton'

const ROWS = [
  { key: 'llm_provider', label: 'LLM Provider' },
  { key: 'llm_model', label: 'LLM Model' },
  { key: 'embedding_model', label: 'Embedding Model' },
  { key: 'whisper_model_size', label: 'Whisper Model' },
  { key: 'whisper_device', label: 'Whisper Device' },
  { key: 'top_k', label: 'Top-K Retrieval' },
  { key: 'chunk_size_words', label: 'Chunk Size (words)' },
  { key: 'chunk_overlap_words', label: 'Chunk Overlap (words)' },
]

export default function Settings() {
  const [config, setConfig] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getConfig()
      .then((c) => { if (!cancelled) setConfig(c) })
      .catch((e) => { if (!cancelled) setError(e.message || 'Failed to load configuration.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  return (
    <div className="page-settings">
      <div className="page-header-row">
        <h1>Settings</h1>
      </div>
      <p className="page-subtitle">
        These values reflect the backend's current environment configuration
        (<code>backend/.env</code>). To change them, edit that file and restart the backend.
      </p>

      <div className="card">
        {loading && <SkeletonBlock label="Loading configuration…" />}
        {!loading && error && <p className="error-banner">{error}</p>}
        {!loading && !error && config && (
          <table className="settings-table">
            <tbody>
              {ROWS.map((row) => (
                <tr key={row.key}>
                  <td className="settings-label">{row.label}</td>
                  <td className="settings-value">{String(config[row.key])}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
