import { useState, useEffect, useRef } from 'react'
import { useNavigate, useLocation, Link } from 'react-router-dom'
import { verifyOTP, resendOTP, getProfile } from '../services/authApi'
import { useAuth } from '../context/AuthContext'

export default function VerifyPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { login } = useAuth()

  const { userId, verificationMethod, email, phone } = location.state || {}

  const [otp, setOtp] = useState('')
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [loading, setLoading] = useState(false)
  const [resending, setResending] = useState(false)
  const [cooldown, setCooldown] = useState(0)

  const inputRef = useRef(null)
  const timerRef = useRef(null)

  useEffect(() => {
    if (!userId) {
      navigate('/signup', { replace: true })
    }
  }, [userId, navigate])

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  useEffect(() => {
    if (cooldown > 0) {
      timerRef.current = setTimeout(() => setCooldown((c) => c - 1), 1000)
      return () => clearTimeout(timerRef.current)
    }
  }, [cooldown])

  async function handleSubmit(e) {
    e.preventDefault()
    if (!otp.trim() || loading) return

    setLoading(true)
    setError(null)
    setSuccess(null)

    try {
      const res = await verifyOTP({ user_id: userId, otp: otp.trim() })
      if (res.access_token) {
        // Auto-login after verification
        const profileData = await getProfile(res.access_token)
        login(res.access_token, profileData.user)
        navigate('/', { replace: true })
      } else {
        setSuccess('Account verified! You can now sign in.')
        setTimeout(() => navigate('/login', { replace: true }), 2000)
      }
    } catch (err) {
      setError(err.message || 'Verification failed.')
    } finally {
      setLoading(false)
    }
  }

  async function handleResend() {
    if (resending || cooldown > 0) return
    setResending(true)
    setError(null)
    setSuccess(null)

    try {
      await resendOTP({ user_id: userId, method: verificationMethod || 'email' })
      setSuccess('A new code has been sent.')
      setCooldown(60)
    } catch (err) {
      setError(err.message || 'Failed to resend code.')
    } finally {
      setResending(false)
    }
  }

  const destination = verificationMethod === 'phone' ? phone : email

  if (!userId) return null

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-header">
          <h1 className="auth-brand">LectureMind</h1>
          <p className="auth-subtitle">Verify your account</p>
        </div>

        <p className="auth-description">
          We sent a verification code to <strong>{destination || 'your ' + (verificationMethod || 'email')}</strong>.
          Enter it below to activate your account.
        </p>

        <form className="auth-form" onSubmit={handleSubmit}>
          {error && <div className="auth-error">{error}</div>}
          {success && <div className="auth-success">{success}</div>}

          <div className="auth-field">
            <label htmlFor="otp">Verification code</label>
            <input
              ref={inputRef}
              id="otp"
              type="text"
              inputMode="numeric"
              placeholder="Enter 6-digit code"
              value={otp}
              onChange={(e) => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))}
              maxLength={6}
              autoComplete="one-time-code"
              className="auth-otp-input"
              required
            />
          </div>

          <button
            type="submit"
            className="btn-primary auth-submit"
            disabled={loading || otp.length < 4}
          >
            {loading ? 'Verifying…' : 'Verify'}
          </button>
        </form>

        <div className="auth-resend">
          <span>Didn't receive a code?</span>
          <button
            className="auth-link-button"
            onClick={handleResend}
            disabled={resending || cooldown > 0}
          >
            {cooldown > 0 ? `Resend in ${cooldown}s` : resending ? 'Sending…' : 'Resend code'}
          </button>
        </div>

        <p className="auth-footer">
          <Link to="/login">Back to sign in</Link>
        </p>
      </div>
    </div>
  )
}
