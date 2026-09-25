import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { signup } from '../services/authApi'

export default function SignupPage() {
  const navigate = useNavigate()

  const [form, setForm] = useState({
    name: '',
    email: '',
    phone: '',
    password: '',
    password_confirmation: '',
    verification_method: 'email',
  })
  const [errors, setErrors] = useState({})
  const [serverError, setServerError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)

  function updateField(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }))
    setErrors((prev) => ({ ...prev, [field]: null }))
  }

  function validate() {
    const errs = {}
    if (!form.name.trim()) errs.name = 'Name is required.'
    if (!form.email.trim()) errs.email = 'Email is required.'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) errs.email = 'Invalid email format.'
    if (!form.phone.trim()) errs.phone = 'Phone number is required.'
    else if (!/^\+?[1-9]\d{6,14}$/.test(form.phone.replace(/[\s-]/g, ''))) errs.phone = 'Invalid phone number. Use international format.'

    if (!form.password) errs.password = 'Password is required.'
    else {
      if (form.password.length < 8) errs.password = 'At least 8 characters required.'
      else if (!/[A-Z]/.test(form.password)) errs.password = 'Must contain an uppercase letter.'
      else if (!/[a-z]/.test(form.password)) errs.password = 'Must contain a lowercase letter.'
      else if (!/\d/.test(form.password)) errs.password = 'Must contain a digit.'
      else if (!/[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/.test(form.password)) errs.password = 'Must contain a special character.'
    }

    if (!form.password_confirmation) errs.password_confirmation = 'Please confirm your password.'
    else if (form.password !== form.password_confirmation) errs.password_confirmation = 'Passwords do not match.'

    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!validate()) return

    setLoading(true)
    setServerError(null)

    try {
      const res = await signup({
        ...form,
        phone: form.phone.replace(/[\s-]/g, ''),
      })
      navigate('/verify', {
        state: {
          userId: res.user_id,
          verificationMethod: res.verification_method,
          email: form.email,
          phone: form.phone,
        },
      })
    } catch (err) {
      setServerError(err.message || 'Signup failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card auth-card-wide">
        <div className="auth-header">
          <h1 className="auth-brand">LectureMind</h1>
          <p className="auth-subtitle">Create your account</p>
        </div>

        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          {serverError && <div className="auth-error">{serverError}</div>}

          <div className="auth-field">
            <label htmlFor="name">Full name</label>
            <input
              id="name"
              type="text"
              placeholder="Your name"
              value={form.name}
              onChange={(e) => updateField('name', e.target.value)}
              autoFocus
              required
            />
            {errors.name && <span className="auth-field-error">{errors.name}</span>}
          </div>

          <div className="auth-field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              placeholder="you@example.com"
              value={form.email}
              onChange={(e) => updateField('email', e.target.value)}
              autoComplete="email"
              required
            />
            {errors.email && <span className="auth-field-error">{errors.email}</span>}
          </div>

          <div className="auth-field">
            <label htmlFor="phone">Phone number</label>
            <input
              id="phone"
              type="tel"
              placeholder="+919876543210"
              value={form.phone}
              onChange={(e) => updateField('phone', e.target.value)}
              autoComplete="tel"
              required
            />
            {errors.phone && <span className="auth-field-error">{errors.phone}</span>}
          </div>

          <div className="auth-field">
            <label htmlFor="password">Password</label>
            <div className="auth-password-wrapper">
              <input
                id="password"
                type={showPassword ? 'text' : 'password'}
                placeholder="Min. 8 characters"
                value={form.password}
                onChange={(e) => updateField('password', e.target.value)}
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
            {errors.password && <span className="auth-field-error">{errors.password}</span>}
            <span className="auth-field-hint">Use 8+ characters with uppercase, lowercase, number, and special character.</span>
          </div>

          <div className="auth-field">
            <label htmlFor="confirm-password">Confirm password</label>
            <input
              id="confirm-password"
              type={showPassword ? 'text' : 'password'}
              placeholder="Re-enter password"
              value={form.password_confirmation}
              onChange={(e) => updateField('password_confirmation', e.target.value)}
              autoComplete="new-password"
              required
            />
            {errors.password_confirmation && (
              <span className="auth-field-error">{errors.password_confirmation}</span>
            )}
          </div>

          <div className="auth-field">
            <label>Verify via</label>
            <div className="auth-radio-group">
              <label className="auth-radio">
                <input
                  type="radio"
                  name="verification_method"
                  value="email"
                  checked={form.verification_method === 'email'}
                  onChange={(e) => updateField('verification_method', e.target.value)}
                />
                <span>Email</span>
              </label>
              <label className="auth-radio">
                <input
                  type="radio"
                  name="verification_method"
                  value="phone"
                  checked={form.verification_method === 'phone'}
                  onChange={(e) => updateField('verification_method', e.target.value)}
                />
                <span>Phone</span>
              </label>
            </div>
          </div>

          <button
            type="submit"
            className="btn-primary auth-submit"
            disabled={loading}
          >
            {loading ? 'Creating account…' : 'Create account'}
          </button>
        </form>

        <p className="auth-footer">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  )
}
