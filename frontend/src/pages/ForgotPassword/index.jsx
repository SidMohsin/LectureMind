import { useState } from "react";
import { Link } from "react-router-dom";
import AuthLayout from "../../components/layout/AuthLayout";
import Input from "../../components/ui/Input";
import Button from "../../components/ui/Button";
import Alert from "../../components/ui/Alert";
import { requestPasswordReset } from "../../services/auth";
import { validateEmail } from "../../auth/validation";

const backToLogin = <Link to="/login">Back to log in</Link>;

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [emailError, setEmailError] = useState(null);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [sentTo, setSentTo] = useState(null);

  async function handleSubmit(event) {
    event.preventDefault();
    const validationError = validateEmail(email);
    setEmailError(validationError);
    setError(null);
    if (validationError) return;

    setSubmitting(true);
    try {
      await requestPasswordReset(email);
      setSentTo(email.trim());
    } catch (failure) {
      setError(failure);
    } finally {
      setSubmitting(false);
    }
  }

  if (sentTo) {
    return (
      <AuthLayout
        title="Check your email"
        description={`If an account exists for ${sentTo}, we've sent a link to reset your password. The link can only be used once.`}
        footer={backToLogin}
      >
        <div className="auth-form__actions">
          <Button variant="secondary" onClick={() => setSentTo(null)}>
            Use a different email
          </Button>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Reset your password"
      description="Enter the email you use for LectureMind and we'll send you a reset link."
      footer={backToLogin}
    >
      {error && <Alert tone="error">{error.message}</Alert>}
      <form onSubmit={handleSubmit} noValidate>
        <Input
          id="email"
          label="Email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          error={emailError}
          disabled={submitting}
        />
        <Button type="submit" className="auth-form__submit" disabled={submitting} aria-busy={submitting}>
          {submitting ? "Sending…" : "Send Reset Link"}
        </Button>
      </form>
    </AuthLayout>
  );
}
