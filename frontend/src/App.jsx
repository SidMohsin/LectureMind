import { AppProvider, useApp } from './context/AppContext'
import Topbar from './components/Topbar'
import Dashboard from './pages/Dashboard'
import Library from './pages/Library'
import UploadPage from './pages/UploadPage'
import Settings from './pages/Settings'
import LectureWorkspace from './pages/LectureWorkspace'

function Shell() {
  const { view, selectedLectureId } = useApp()

  return (
    <div className="app-shell">
      <div className="app-shell-content">
        <Topbar />

        <main className="app-main">
          {view === 'dashboard' && <Dashboard />}
          {view === 'library' && <Library />}
          {view === 'upload' && <UploadPage />}
          {view === 'settings' && <Settings />}
          {view === 'lecture' && selectedLectureId && (
            <LectureWorkspace lectureId={selectedLectureId} />
          )}
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