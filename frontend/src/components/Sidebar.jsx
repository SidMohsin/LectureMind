import { useApp } from '../context/AppContext'
import { useAuth } from '../context/AuthContext'

const NAV_ITEMS = [
  { key: 'dashboard', label: 'Overview' },
  { key: 'library', label: 'All lectures' },
  { key: 'upload', label: 'Add lecture' },
  { key: 'settings', label: 'Settings' },
]

export default function Sidebar({ open, onNavigate }) {
  const { view, navigate } = useApp()
  const { user } = useAuth()

  function handleClick(key) {
    navigate(key)
    if (onNavigate) onNavigate()
  }

  return (
    <aside className={`app-sidebar ${open ? 'app-sidebar-open' : ''}`}>

      <div className="app-sidebar-brand">
        <span className="brand-name">LectureMind</span>
      </div>

      <nav className="app-nav" aria-label="Main navigation">

        <div className="app-nav-section">
          <span className="app-nav-section-label">Library</span>

          {NAV_ITEMS.slice(0, 3).map((item) => (
            <button
              key={item.key}
              className={`app-nav-item ${
                view === item.key ? 'app-nav-item-active' : ''
              }`}
              onClick={() => handleClick(item.key)}
              aria-current={view === item.key ? 'page' : undefined}
            >
              <span>{item.label}</span>
            </button>
          ))}
        </div>

        <div className="app-nav-section app-nav-section-workspace">
          <span className="app-nav-section-label">Workspace</span>

          <button
            className={`app-nav-item ${
              view === 'settings' ? 'app-nav-item-active' : ''
            }`}
            onClick={() => handleClick('settings')}
            aria-current={view === 'settings' ? 'page' : undefined}
          >
            <span>Settings</span>
          </button>
        </div>

      </nav>

      <div className="app-sidebar-footer">
        <div className="sidebar-user">
          <div className="sidebar-user-avatar">
            {user?.name ? user.name.charAt(0).toUpperCase() : '?'}
          </div>

          <div className="sidebar-user-info">
            <span className="sidebar-user-name">{user?.name || 'User'}</span>
            <span className="sidebar-user-role">{user?.email || ''}</span>
          </div>
        </div>
      </div>

    </aside>
  )
}