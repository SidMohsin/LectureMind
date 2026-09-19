import { useApp } from '../context/AppContext'

const NAV_ITEMS = [
  { key: 'dashboard', label: 'Dashboard', icon: 'D' },
  { key: 'library', label: 'My Lectures', icon: 'L' },
  { key: 'upload', label: 'Upload', icon: 'U' },
  { key: 'settings', label: 'Settings', icon: 'S' },
]

export default function Sidebar({ open, onNavigate }) {
  const { view, navigate } = useApp()

  function handleClick(key) {
    navigate(key)
    if (onNavigate) onNavigate()
  }

  return (
    <aside className={`app-sidebar ${open ? 'app-sidebar-open' : ''}`}>
      <div className="app-sidebar-brand">
        <span className="brand-mark" aria-hidden="true">LM</span>
        <span className="brand-name">LectureMind</span>
      </div>
      <nav className="app-nav" aria-label="Main navigation">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.key}
            className={`app-nav-item ${view === item.key ? 'app-nav-item-active' : ''}`}
            onClick={() => handleClick(item.key)}
            aria-current={view === item.key ? 'page' : undefined}
          >
            <span className="app-nav-icon" aria-hidden="true">{item.icon}</span>
            <span>{item.label}</span>
          </button>
        ))}
      </nav>
      <div className="app-sidebar-footer">
        <p>Lecture Intelligence System</p>
        <p className="app-sidebar-tagline">Whisper · RAG · LLM</p>
      </div>
    </aside>
  )
}
