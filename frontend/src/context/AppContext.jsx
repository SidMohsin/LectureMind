import { createContext, useContext, useState, useCallback, useEffect } from 'react'

// Lightweight app-level context: current view/navigation state + theme.
// No router library is used (kept dependency-free, matching the project's
// "avoid unnecessary complexity" philosophy) — navigation is just state.

const AppContext = createContext(null)

const THEME_STORAGE_KEY = 'lecturemind-theme'

export function AppProvider({ children }) {
  const [view, setView] = useState('dashboard') // dashboard | library | lecture | settings | upload
  const [selectedLectureId, setSelectedLectureId] = useState(null)
  const [refreshToken, setRefreshToken] = useState(0)

  const [theme, setTheme] = useState(() => {
    if (typeof window === 'undefined') return 'light'
    return localStorage.getItem(THEME_STORAGE_KEY) || 'light'
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem(THEME_STORAGE_KEY, theme)
  }, [theme])

  const toggleTheme = useCallback(() => {
    setTheme((t) => (t === 'light' ? 'dark' : 'light'))
  }, [])

  const navigate = useCallback((nextView, lectureId = null) => {
    setView(nextView)
    if (lectureId !== null) setSelectedLectureId(lectureId)
  }, [])

  // Bump this to signal that lists (lectures, stats) should be refetched,
  // e.g. after an upload completes, processing finishes, or a lecture is deleted.
  const triggerRefresh = useCallback(() => setRefreshToken((t) => t + 1), [])

  const value = {
    view, navigate,
    selectedLectureId, setSelectedLectureId,
    theme, toggleTheme,
    refreshToken, triggerRefresh,
  }

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

export function useApp() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be used within an AppProvider')
  return ctx
}
