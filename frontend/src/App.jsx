import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import { AppProvider, useApp } from './context/AppContext'
import Topbar from './components/Topbar'
import Dashboard from './pages/Dashboard'
import Library from './pages/Library'
import UploadPage from './pages/UploadPage'
import Settings from './pages/Settings'
import LectureWorkspace from './pages/LectureWorkspace'
import LoginPage from './pages/LoginPage'
import SignupPage from './pages/SignupPage'
import VerifyPage from './pages/VerifyPage'
import ForgotPasswordPage from './pages/ForgotPasswordPage'
import ResetPasswordPage from './pages/ResetPasswordPage'

function ProtectedRoute({ children }) {
  const { isAuthenticated, loading } = useAuth()

  if (loading) {
    return (
      <div className="auth-loading">
        <div className="auth-loading-spinner" />
        <p>Loading…</p>
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return children
}

function GuestRoute({ children }) {
  const { isAuthenticated, loading } = useAuth()

  if (loading) {
    return (
      <div className="auth-loading">
        <div className="auth-loading-spinner" />
        <p>Loading…</p>
      </div>
    )
  }

  if (isAuthenticated) {
    return <Navigate to="/" replace />
  }

  return children
}

function AppShell() {
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
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          {/* Auth routes (guest-only) */}
          <Route path="/login" element={<GuestRoute><LoginPage /></GuestRoute>} />
          <Route path="/signup" element={<GuestRoute><SignupPage /></GuestRoute>} />
          <Route path="/verify" element={<GuestRoute><VerifyPage /></GuestRoute>} />
          <Route path="/forgot-password" element={<GuestRoute><ForgotPasswordPage /></GuestRoute>} />
          <Route path="/reset-password" element={<GuestRoute><ResetPasswordPage /></GuestRoute>} />

          {/* Protected app routes */}
          <Route
            path="/*"
            element={
              <ProtectedRoute>
                <AppProvider>
                  <AppShell />
                </AppProvider>
              </ProtectedRoute>
            }
          />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}