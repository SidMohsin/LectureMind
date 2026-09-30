import { useState } from "react";
import { Link } from "react-router-dom";
import AuthLayout from "../../components/layout/AuthLayout";
import Input from "../../components/ui/Input";
import Button from "../../components/ui/Button";
import Alert from "../../components/ui/Alert";
import FullPageLoader from "../../components/feedback/FullPageLoader";
import { useAuth } from "../../auth/AuthContext";
import { authRedirectFor } from "../../lib/supabase";
import { updatePassword } from "../../services/auth";
import { MIN_PASSWORD_LENGTH, validateNewPassword } from "../../auth/validation";

export default function ResetPassword() {
  const redirect = authRedirectFor("/reset-password");
  const { status } = useAuth();

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  // The form is only offered to someone who arrived through a recovery link,
  // not to anyone who happens to be signed in.
  const isRecoveryLink = Boolean(redirect?.hasSession) && redirect.type === "recovery";

  if (!isRecoveryLink || (status === "unauthenticated" && !done)) {
    return (
      <AuthLayout
        title={redirect?.errorCode || isRecoveryLink ? "This reset link has expired" : "Open your reset link"}
        description={
          redirect?.errorCode || isRecoveryLink
            ? "Password reset links can only be used once and expire after a while. Request a new one to continue."
            : "To set a new password, open the reset link we emailed you. You can request a new link below."
        }
        footer={<Link to="/login">Back to log in</Link>}
      >
        <div className="auth-form__actions">
          <Button as={Link} to="/forgot-password">
            Request a New Link
          </Button>
        </div>
      </AuthLayout>
    );
  }

  if (status === "loading") return <FullPageLoader label="Checking your reset link…" />;

  if (done) {
    return (
      <AuthLayout title="Password updated" description="Your new password is set and you're signed in.">
        <div className="auth-form__actions">
          <Button as={Link} to="/dashboard">
            Continue to Dashboard
          </Button>
        </div>
      </AuthLayout>
    );
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const errors = validateNewPassword(password, confirmPassword);
    setFieldErrors(errors);
    setError(null);
    if (Object.keys(errors).length > 0) return;

    setSubmitting(true);
    try {
      await updatePassword(password);
      setDone(true);
    } catch (failure) {
      setError(failure);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout title="Set a new password" description="Choose a new password for your LectureMind account.">
      {error && <Alert tone="error">{error.message}</Alert>}
      <form onSubmit={handleSubmit} noValidate>
        <Input
          id="password"
          label="New password"
          type="password"
          autoComplete="new-password"
          hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          error={fieldErrors.password}
          disabled={submitting}
        />
        <Input
          id="confirmPassword"
          label="Confirm new password"
          type="password"
          autoComplete="new-password"
          value={confirmPassword}
          onChange={(event) => setConfirmPassword(event.target.value)}
          error={fieldErrors.confirmPassword}
          disabled={submitting}
        />
        <Button type="submit" className="auth-form__submit" disabled={submitting} aria-busy={submitting}>
          {submitting ? "Updating…" : "Update Password"}
        </Button>
      </form>
    </AuthLayout>
  );
}
