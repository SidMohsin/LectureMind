import { useState, useEffect } from 'react'
import { AppProvider, useApp } from './context/AppContext'
import Sidebar from './components/Sidebar'
import Topbar from './components/Topbar'
import Dashboard from './pages/Dashboard'
import Library from './pages/Library'
import UploadPage from './pages/UploadPage'
import Settings from './pages/Settings'
import LectureWorkspace from './pages/LectureWorkspace'

function Shell() {
  const { view, selectedLectureId } = useApp()
  const [sidebarOpen, setSidebarOpen] = useState(false)

  // Close the mobile sidebar automatically whenever the view changes.
  useEffect(() => { setSidebarOpen(false) }, [view])

  return (
    <div className="app-shell">
      <Sidebar open={sidebarOpen} onNavigate={() => setSidebarOpen(false)} />
      {sidebarOpen && <div className="sidebar-scrim" onClick={() => setSidebarOpen(false)} />}

      <div className="app-shell-content">
        <Topbar onToggleSidebar={() => setSidebarOpen((v) => !v)} />
        <main className="app-main">
          {view === 'dashboard' && <Dashboard />}
          {view === 'library' && <Library />}
          {view === 'upload' && <UploadPage />}
          {view === 'settings' && <Settings />}
          {view === 'lecture' && selectedLectureId && <LectureWorkspace lectureId={selectedLectureId} />}
        </main>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <AppProvider>
      <Shell />
    </AppProvider>
  )
}
