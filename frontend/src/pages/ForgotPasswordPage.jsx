import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { forgotPassword } from '../services/authApi'

export default function ForgotPasswordPage() {
  const navigate = useNavigate()

  const [identifier, setIdentifier] = useState('')
  const [method, setMethod] = useState('email')
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!identifier.trim()) return

    setLoading(true)
    setError(null)

    try {
      const res = await forgotPassword({
        identifier: identifier.trim(),
        method,
      })
      navigate('/reset-password', {
        state: {
          userId: res.user_id,
          method,
          identifier: identifier.trim(),
        },
      })
    } catch (err) {
      setError(err.message || 'Failed to process request.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-header">
          <h1 className="auth-brand">LectureMind</h1>
          <p className="auth-subtitle">Reset your password</p>
        </div>

        <p className="auth-description">
          Enter your email or phone number and we'll send you a verification code
          to reset your password.
        </p>

        <form className="auth-form" onSubmit={handleSubmit}>
          {error && <div className="auth-error">{error}</div>}

          <div className="auth-field">
            <label htmlFor="identifier">Email or phone</label>
            <input
              id="identifier"
              type="text"
              placeholder="you@example.com"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              autoFocus
              required
            />
          </div>

          <div className="auth-field">
            <label>Send code via</label>
            <div className="auth-radio-group">
              <label className="auth-radio">
                <input
                  type="radio"
                  name="method"
                  value="email"
                  checked={method === 'email'}
                  onChange={(e) => setMethod(e.target.value)}
                />
                <span>Email</span>
              </label>
              <label className="auth-radio">
                <input
                  type="radio"
                  name="method"
                  value="phone"
                  checked={method === 'phone'}
                  onChange={(e) => setMethod(e.target.value)}
                />
                <span>Phone</span>
              </label>
            </div>
          </div>

          <button
            type="submit"
            className="btn-primary auth-submit"
            disabled={loading || !identifier.trim()}
          >
            {loading ? 'Sending…' : 'Send verification code'}
          </button>
        </form>

        <p className="auth-footer">
          Remember your password? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  )
}
