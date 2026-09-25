import { createContext, useContext, useState, useCallback, useEffect } from 'react'
import { getStoredToken, setStoredToken, clearStoredToken } from '../services/api'
import { getProfile } from '../services/authApi'

const AuthContext = createContext(null)

const USER_KEY = 'lecturemind-user'

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      const saved = localStorage.getItem(USER_KEY)
      return saved ? JSON.parse(saved) : null
    } catch {
      return null
    }
  })
  const [loading, setLoading] = useState(true)

  // On mount, validate the stored token
  useEffect(() => {
    const token = getStoredToken()
    if (!token) {
      setLoading(false)
      return
    }

    getProfile(token)
      .then((data) => {
        setUser(data.user)
        localStorage.setItem(USER_KEY, JSON.stringify(data.user))
      })
      .catch(() => {
        // Token invalid/expired
        clearStoredToken()
        localStorage.removeItem(USER_KEY)
        setUser(null)
      })
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback((token, userData) => {
    setStoredToken(token)
    setUser(userData)
    localStorage.setItem(USER_KEY, JSON.stringify(userData))
  }, [])

  const logout = useCallback(() => {
    clearStoredToken()
    localStorage.removeItem(USER_KEY)
    setUser(null)
  }, [])

  const updateUser = useCallback((userData) => {
    setUser(userData)
    localStorage.setItem(USER_KEY, JSON.stringify(userData))
  }, [])

  const value = {
    user,
    loading,
    isAuthenticated: !!user,
    login,
    logout,
    updateUser,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}
