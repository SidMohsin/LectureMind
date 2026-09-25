import { useState, useEffect, useRef } from 'react'
import { useNavigate, useLocation, Link } from 'react-router-dom'
import { verifyResetOTP, resetPassword, resendOTP } from '../services/authApi'

export default function ResetPasswordPage() {
  const navigate = useNavigate()
  const location = useLocation()

  const { userId, method, identifier } = location.state || {}

  const [step, setStep] = useState('otp') // 'otp' | 'reset'
  const [otp, setOtp] = useState('')
  const [resetToken, setResetToken] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [loading, setLoading] = useState(false)
  const [resending, setResending] = useState(false)
  const [cooldown, setCooldown] = useState(0)

  const inputRef = useRef(null)

  useEffect(() => {
    if (!userId) {
      navigate('/forgot-password', { replace: true })
    }
  }, [userId, navigate])

  useEffect(() => {
    inputRef.current?.focus()
  }, [step])

  useEffect(() => {
    if (cooldown > 0) {
      const t = setTimeout(() => setCooldown((c) => c - 1), 1000)
      return () => clearTimeout(t)
    }
  }, [cooldown])

  async function handleVerifyOTP(e) {
    e.preventDefault()
    if (!otp.trim() || loading) return

    setLoading(true)
    setError(null)

    try {
      const res = await verifyResetOTP({ user_id: userId, otp: otp.trim() })
      setResetToken(res.reset_token)
      setStep('reset')
      setSuccess('Code verified. Set your new password below.')
    } catch (err) {
      setError(err.message || 'Verification failed.')
    } finally {
      setLoading(false)
    }
  }

  async function handleResetPassword(e) {
    e.preventDefault()

    if (newPassword.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }
    if (newPassword !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }

    setLoading(true)
    setError(null)

    try {
      await resetPassword({
        user_id: userId,
        reset_token: resetToken,
        new_password: newPassword,
        new_password_confirmation: confirmPassword,
      })
      setSuccess('Password reset successfully! Redirecting to login…')
      setTimeout(() => navigate('/login', { replace: true }), 2500)
    } catch (err) {
      setError(err.message || 'Failed to reset password.')
    } finally {
      setLoading(false)
    }
  }

  async function handleResend() {
    if (resending || cooldown > 0) return
    setResending(true)
    setError(null)

    try {
      await resendOTP({ user_id: userId, method: method || 'email' })
      setSuccess('A new code has been sent.')
      setCooldown(60)
    } catch (err) {
      setError(err.message || 'Failed to resend code.')
    } finally {
      setResending(false)
    }
  }

  if (!userId) return null

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-header">
          <h1 className="auth-brand">LectureMind</h1>
          <p className="auth-subtitle">
            {step === 'otp' ? 'Enter verification code' : 'Create new password'}
          </p>
        </div>

        {step === 'otp' && (
          <>
            <p className="auth-description">
              Enter the verification code sent to <strong>{identifier || 'your ' + (method || 'email')}</strong>.
            </p>

            <form className="auth-form" onSubmit={handleVerifyOTP}>
              {error && <div className="auth-error">{error}</div>}
              {success && <div className="auth-success">{success}</div>}

              <div className="auth-field">
                <label htmlFor="reset-otp">Verification code</label>
                <input
                  ref={inputRef}
                  id="reset-otp"
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
                {loading ? 'Verifying…' : 'Verify code'}
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
          </>
        )}

        {step === 'reset' && (
          <form className="auth-form" onSubmit={handleResetPassword}>
            {error && <div className="auth-error">{error}</div>}
            {success && <div className="auth-success">{success}</div>}

            <div className="auth-field">
              <label htmlFor="new-password">New password</label>
              <div className="auth-password-wrapper">
                <input
                  ref={inputRef}
                  id="new-password"
                  type={showPassword ? 'text' : 'password'}
                  placeholder="Min. 8 characters"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  autoComplete="new-password"
                  required
                />
                <button
                  type="button"
                  className="auth-password-toggle"
                  onClick={() => setShowPassword(!showPassword)}
                  tabIndex={-1}
                >
                  {showPassword ? 'Hide' : 'Show'}
                </button>
              </div>
              <span className="auth-field-hint">
                Use 8+ characters with uppercase, lowercase, number, and special character.
              </span>
            </div>

            <div className="auth-field">
              <label htmlFor="confirm-new-password">Confirm new password</label>
              <input
                id="confirm-new-password"
                type={showPassword ? 'text' : 'password'}
                placeholder="Re-enter password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
                required
              />
            </div>

            <button
              type="submit"
              className="btn-primary auth-submit"
              disabled={loading || !newPassword || !confirmPassword}
            >
              {loading ? 'Resetting…' : 'Reset password'}
            </button>
          </form>
        )}

        <p className="auth-footer">
          <Link to="/login">Back to sign in</Link>
        </p>
      </div>
    </div>
  )
}
