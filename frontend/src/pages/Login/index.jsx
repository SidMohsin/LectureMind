import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import AuthLayout from "../../components/layout/AuthLayout";
import Input from "../../components/ui/Input";
import Button from "../../components/ui/Button";
import Alert from "../../components/ui/Alert";
import { signIn } from "../../services/auth";
import { validateEmail } from "../../auth/validation";

const NOTICES = {
  expired: "Your session has expired. Please log in again.",
  signed_out: "You've been logged out.",
};

export default function Login() {
  const location = useLocation();
  const notice = NOTICES[location.state?.reason];

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    const errors = {};
    const emailError = validateEmail(email);
    if (emailError) errors.email = emailError;
    if (!password) errors.password = "Enter your password.";
    setFieldErrors(errors);
    setError(null);
    if (Object.keys(errors).length > 0) return;

    setSubmitting(true);
    try {
      await signIn({ email, password });
      // The public-only route guard moves the user on once the session exists.
    } catch (failure) {
      setError(failure);
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout
      title="Log in to LectureMind"
      description="Pick up where you left off with your lectures."
      footer={
        <>
          New to LectureMind? <Link to="/signup">Create an account</Link>
        </>
      }
    >
      {notice && !error && <Alert tone="info">{notice}</Alert>}
      {error && (
        <Alert tone="error">
          {error.message}
          {error.code === "email_not_confirmed" && (
            <>
              {" "}
              <Link to="/verify" state={{ email: email.trim() }}>
                Resend verification email
              </Link>
            </>
          )}
        </Alert>
      )}

      <form onSubmit={handleSubmit} noValidate>
        <Input
          id="email"
          label="Email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          error={fieldErrors.email}
          disabled={submitting}
        />
        <Input
          id="password"
          label="Password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          error={fieldErrors.password}
          disabled={submitting}
        />
        <div className="auth-form__row">
          <Link to="/forgot-password">Forgot password?</Link>
        </div>
        <Button type="submit" className="auth-form__submit" disabled={submitting} aria-busy={submitting}>
          {submitting ? "Logging in…" : "Log In"}
        </Button>
      </form>
    </AuthLayout>
  );
}
