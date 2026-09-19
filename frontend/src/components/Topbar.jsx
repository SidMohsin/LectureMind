import { useState } from 'react'
import { useApp } from '../context/AppContext'

export default function Topbar({ onToggleSidebar, lectures }) {
  const { theme, toggleTheme, navigate } = useApp()
  const [query, setQuery] = useState('')

  function handleSearchKeyDown(e) {
    if (e.key === 'Enter' && query.trim()) {
      navigate('library')
      // Library page reads the initial query itself from this shared input
      // via a simple event so search feels instant without adding a router.
      window.dispatchEvent(new CustomEvent('lecturemind:search', { detail: query.trim() }))
    }
  }

  return (
    <header className="app-topbar">
      <button className="sidebar-toggle" onClick={onToggleSidebar} aria-label="Toggle navigation menu">
        <span />
        <span />
        <span />
      </button>

      <div className="topbar-search">
        <input
          type="search"
          placeholder="Search your lectures…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleSearchKeyDown}
          aria-label="Search lectures"
        />
      </div>

      <div className="topbar-actions">
        <button
          className="theme-toggle"
          onClick={toggleTheme}
          aria-label={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
          title={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
        >
          {theme === 'light' ? '🌙' : '☀️'}
        </button>
      </div>
    </header>
  )
}
