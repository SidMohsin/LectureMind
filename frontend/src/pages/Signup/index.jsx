import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import AuthLayout from "../../components/layout/AuthLayout";
import Input from "../../components/ui/Input";
import Button from "../../components/ui/Button";
import Alert from "../../components/ui/Alert";
import { signUp } from "../../services/auth";
import { MIN_PASSWORD_LENGTH, validateEmail, validateNewPassword } from "../../auth/validation";

export default function Signup() {
  const navigate = useNavigate();

  const [form, setForm] = useState({ fullName: "", email: "", password: "", confirmPassword: "" });
  const [fieldErrors, setFieldErrors] = useState({});
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const update = (field) => (event) => setForm((current) => ({ ...current, [field]: event.target.value }));

  async function handleSubmit(event) {
    event.preventDefault();
    const errors = validateNewPassword(form.password, form.confirmPassword);
    if (!form.fullName.trim()) errors.fullName = "Enter your name.";
    const emailError = validateEmail(form.email);
    if (emailError) errors.email = emailError;
    setFieldErrors(errors);
    setError(null);
    if (Object.keys(errors).length > 0) return;

    setSubmitting(true);
    try {
      const { needsVerification } = await signUp(form);
      if (needsVerification) {
        navigate("/verify", { replace: true, state: { email: form.email.trim(), justSignedUp: true } });
      }
      // Without verification a session exists and the route guard redirects.
    } catch (failure) {
      setError(failure);
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout
      title="Create your account"
      description="Turn your lectures into searchable, structured knowledge."
      footer={
        <>
          Already have an account? <Link to="/login">Log in</Link>
        </>
      }
    >
      {error && (
        <Alert tone="error">
          {error.message}
          {error.code === "user_already_exists" && (
            <>
              {" "}
              <Link to="/login">Go to login</Link>
            </>
          )}
        </Alert>
      )}

      <form onSubmit={handleSubmit} noValidate>
        <Input
          id="fullName"
          label="Full name"
          type="text"
          autoComplete="name"
          maxLength={120}
          value={form.fullName}
          onChange={update("fullName")}
          error={fieldErrors.fullName}
          disabled={submitting}
        />
        <Input
          id="email"
          label="Email"
          type="email"
          autoComplete="email"
          value={form.email}
          onChange={update("email")}
          error={fieldErrors.email}
          disabled={submitting}
        />
        <Input
          id="password"
          label="Password"
          type="password"
          autoComplete="new-password"
          hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}
          value={form.password}
          onChange={update("password")}
          error={fieldErrors.password}
          disabled={submitting}
        />
        <Input
          id="confirmPassword"
          label="Confirm password"
          type="password"
          autoComplete="new-password"
          value={form.confirmPassword}
          onChange={update("confirmPassword")}
          error={fieldErrors.confirmPassword}
          disabled={submitting}
        />
        <Button type="submit" className="auth-form__submit" disabled={submitting} aria-busy={submitting}>
          {submitting ? "Creating account…" : "Create Account"}
        </Button>
      </form>
    </AuthLayout>
  );
}
