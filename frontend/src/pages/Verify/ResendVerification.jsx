import { useEffect, useState } from "react";
import Input from "../../components/ui/Input";
import Button from "../../components/ui/Button";
import Alert from "../../components/ui/Alert";
import { resendVerification } from "../../services/auth";
import { validateEmail } from "../../auth/validation";

const COOLDOWN_SECONDS = 60;

export default function ResendVerification({ initialEmail = "", askForEmail = false }) {
  const [email, setEmail] = useState(initialEmail);
  const [emailError, setEmailError] = useState(null);
  const [sending, setSending] = useState(false);
  const [sentTo, setSentTo] = useState(null);
  const [error, setError] = useState(null);
  const [cooldown, setCooldown] = useState(0);

  useEffect(() => {
    if (cooldown <= 0) return undefined;
    const timer = setTimeout(() => setCooldown((seconds) => seconds - 1), 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  async function handleSubmit(event) {
    event.preventDefault();
    const validationError = validateEmail(email);
    setEmailError(validationError);
    setError(null);
    if (validationError) return;

    setSending(true);
    try {
      await resendVerification(email);
      setSentTo(email.trim());
      setCooldown(COOLDOWN_SECONDS);
    } catch (failure) {
      setError(failure);
    } finally {
      setSending(false);
    }
  }

  const label = sending
    ? "Sending…"
    : cooldown > 0
      ? `Resend available in ${cooldown}s`
      : sentTo
        ? "Resend verification email"
        : "Send verification email";

  return (
    <form onSubmit={handleSubmit} noValidate>
      {sentTo && !error && <Alert tone="success">We sent a new verification link to {sentTo}.</Alert>}
      {error && <Alert tone="error">{error.message}</Alert>}
      {askForEmail && (
        <Input
          id="verify-email"
          label="Email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          error={emailError}
          disabled={sending}
        />
      )}
      <Button
        type="submit"
        variant={askForEmail ? "primary" : "secondary"}
        className="auth-form__submit"
        disabled={sending || cooldown > 0}
        aria-busy={sending}
      >
        {label}
      </Button>
    </form>
  );
}
