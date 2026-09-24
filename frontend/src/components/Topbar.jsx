import { useEffect, useRef, useState } from 'react'
import { useApp } from '../context/AppContext'

export default function Topbar() {
  const {
    view,
    theme,
    toggleTheme,
    navigate,
  } = useApp()

  const [query, setQuery] = useState('')
  const [profileOpen, setProfileOpen] = useState(false)

  const profileRef = useRef(null)

  // Temporary current user.
  // Authentication can provide this later.
  const user = {
    name: 'Mohsin',
    role: 'M.Tech Data Science',
  }

  const initial = user.name.charAt(0).toUpperCase()

  useEffect(() => {
    function handleOutsideClick(event) {
      if (
        profileRef.current &&
        !profileRef.current.contains(event.target)
      ) {
        setProfileOpen(false)
      }
    }

    function handleEscape(event) {
      if (event.key === 'Escape') {
        setProfileOpen(false)
      }
    }

    document.addEventListener('mousedown', handleOutsideClick)
    document.addEventListener('keydown', handleEscape)

    return () => {
      document.removeEventListener('mousedown', handleOutsideClick)
      document.removeEventListener('keydown', handleEscape)
    }
  }, [])

  function handleSearchKeyDown(e) {
    if (e.key === 'Enter' && query.trim()) {
      navigate('library')

      window.dispatchEvent(
        new CustomEvent('lecturemind:search', {
          detail: query.trim(),
        })
      )
    }
  }

  return (
    <header className="app-topbar">

      <button
        className="topbar-brand"
        onClick={() => navigate('dashboard')}
      >
        LectureMind
      </button>

      <nav className="topbar-nav" aria-label="Main navigation">

        <button
          className={`topbar-nav-item ${
            view === 'dashboard'
              ? 'topbar-nav-item-active'
              : ''
          }`}
          onClick={() => navigate('dashboard')}
        >
          Overview
        </button>

        <button
          className={`topbar-nav-item ${
            view === 'library' || view === 'lecture'
              ? 'topbar-nav-item-active'
              : ''
          }`}
          onClick={() => navigate('library')}
        >
          Lectures
        </button>

      </nav>

      <div className="topbar-spacer" />

      {/* One search only */}
      <div className="topbar-search">
        <span className="topbar-search-icon">⌕</span>

        <input
          type="search"
          placeholder="Search lectures"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleSearchKeyDown}
          aria-label="Search lectures"
        />

        {/* {query && (
          <button
            className="topbar-search-clear"
            onClick={() => setQuery('')}
            aria-label="Clear search"
          >
            
          </button>
        )} */}
      </div>

      <div className="topbar-actions">

        <button
          className="theme-toggle"
          onClick={toggleTheme}
          aria-label={
            theme === 'light'
              ? 'Switch to dark mode'
              : 'Switch to light mode'
          }
        >
          {theme === 'light' ? '☾' : '☀'}
        </button>

        <div className="profile-menu" ref={profileRef}>

          <button
            className={`topbar-avatar ${
              profileOpen ? 'topbar-avatar-active' : ''
            }`}
            onClick={() => setProfileOpen((open) => !open)}
            aria-label="Open account menu"
            aria-expanded={profileOpen}
          >
            {initial}
          </button>

          {profileOpen && (
            <div className="profile-popover">

              <div className="profile-header">
                <div className="profile-large-avatar">
                  {initial}
                </div>

                <div className="profile-user-info">
                  <strong>{user.name}</strong>
                  <span>{user.role}</span>
                </div>
              </div>

              <div className="profile-divider" />

              <button
                className="profile-menu-item"
                onClick={() => {
                  setProfileOpen(false)
                  navigate('settings')
                }}
              >
                <span>Account settings</span>
                <span className="profile-menu-arrow">→</span>
              </button>

              <div className="profile-divider" />

              <button
                className="profile-menu-item"
                onClick={() => setProfileOpen(false)}
              >
                <span>Add another account</span>
              </button>

              <button
                className="profile-menu-item profile-menu-danger"
                onClick={() => setProfileOpen(false)}
              >
                <span>Log out</span>
              </button>

            </div>
          )}

        </div>

      </div>
    </header>
  )
}