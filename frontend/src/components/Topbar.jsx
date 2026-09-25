import { useEffect, useRef, useState } from 'react'
import { useApp } from '../context/AppContext'
import { useAuth } from '../context/AuthContext'

export default function Topbar() {
  const { view, theme, toggleTheme, navigate } = useApp()
  const { user, logout } = useAuth()

  const [query, setQuery] = useState('')
  const [profileOpen, setProfileOpen] = useState(false)
  const profileRef = useRef(null)

  const initial = user?.name ? user.name.charAt(0).toUpperCase() : '?'

  useEffect(() => {
    function handleOutside(e) {
      if (profileRef.current && !profileRef.current.contains(e.target)) {
        setProfileOpen(false)
      }
    }
    function handleEsc(e) {
      if (e.key === 'Escape') setProfileOpen(false)
    }
    document.addEventListener('mousedown', handleOutside)
    document.addEventListener('keydown', handleEsc)
    return () => {
      document.removeEventListener('mousedown', handleOutside)
      document.removeEventListener('keydown', handleEsc)
    }
  }, [])

  function handleSearchKeyDown(e) {
    if (e.key === 'Enter' && query.trim()) {
      navigate('library')
      window.dispatchEvent(new CustomEvent('lecturemind:search', { detail: query.trim() }))
    }
  }

  function handleLogout() {
    setProfileOpen(false)
    logout()
  }

  return (
    <header className="app-topbar">
      <button className="topbar-brand" onClick={() => navigate('dashboard')}>
        <span className="brand-mark" aria-hidden="true">L</span>
        <span>LectureMind</span>
      </button>

      <nav className="topbar-nav" aria-label="Main navigation">
        <button
          className={`topbar-nav-item ${view === 'dashboard' ? 'topbar-nav-item-active' : ''}`}
          onClick={() => navigate('dashboard')}
        >
          Home
        </button>
        <button
          className={`topbar-nav-item ${view === 'library' || view === 'lecture' ? 'topbar-nav-item-active' : ''}`}
          onClick={() => navigate('library')}
        >
          Library
        </button>
      </nav>

      <div className="topbar-spacer" />

      <div className="topbar-search">
        <span className="topbar-search-icon">⌕</span>
        <input
          type="search"
          placeholder="Search lectures…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleSearchKeyDown}
          aria-label="Search lectures"
        />
      </div>

      <div className="topbar-actions">
        <button className="topbar-add" onClick={() => navigate('upload')}>
          <span>+</span> Add lecture
        </button>
        <button
          className="theme-toggle"
          onClick={toggleTheme}
          aria-label={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
          title={theme === 'light' ? 'Dark mode' : 'Light mode'}
        >
          {theme === 'light' ? '☾' : '☀'}
        </button>

        <div className="profile-menu" ref={profileRef}>
          <button
            className={`topbar-avatar ${profileOpen ? 'topbar-avatar-active' : ''}`}
            onClick={() => setProfileOpen((o) => !o)}
            aria-label="Account menu"
            aria-expanded={profileOpen}
          >
            {initial}
          </button>

          {profileOpen && (
            <div className="profile-popover">
              <div className="profile-header">
                <div className="profile-large-avatar">{initial}</div>
                <div className="profile-user-info">
                  <strong>{user?.name || 'User'}</strong>
                  <span>{user?.email || ''}</span>
                </div>
              </div>

              <div className="profile-divider" />

              <button
                className="profile-menu-item"
                onClick={() => { setProfileOpen(false); navigate('settings') }}
              >
                <span>Settings</span>
                <span className="profile-menu-arrow">→</span>
              </button>

              <div className="profile-divider" />

              <button className="profile-menu-item profile-menu-danger" onClick={handleLogout}>
                <span>Sign out</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
