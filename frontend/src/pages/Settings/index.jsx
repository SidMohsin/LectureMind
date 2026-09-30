import { useState } from "react";
import PageContainer from "../../components/layout/PageContainer";
import PageHeader from "../../components/layout/PageHeader";
import Card from "../../components/ui/Card";
import Input from "../../components/ui/Input";
import Button from "../../components/ui/Button";
import Alert from "../../components/ui/Alert";
import Modal from "../../components/ui/Modal";
import { useAuth } from "../../auth/AuthContext";
import { updatePassword } from "../../services/auth";
import { MIN_PASSWORD_LENGTH, validateNewPassword } from "../../auth/validation";
import "./Settings.css";

export default function Settings() {
  const { user } = useAuth();

  return (
    <PageContainer className="settings">
      <PageHeader title="Settings" description="Manage your account and sign-in security." />

      <section className="settings-section" aria-labelledby="account-heading">
        <h2 id="account-heading" className="settings-section__title">
          Account
        </h2>
        <Card>
          <dl className="settings-account">
            <dt className="mono">Email</dt>
            <dd>{user?.email}</dd>
          </dl>
        </Card>
      </section>

      <section className="settings-section" aria-labelledby="password-heading">
        <h2 id="password-heading" className="settings-section__title">
          Password
        </h2>
        <Card>
          <ChangePasswordForm />
        </Card>
      </section>

      <section className="settings-section" aria-labelledby="sessions-heading">
        <h2 id="sessions-heading" className="settings-section__title">
          Sessions
        </h2>
        <Card>
          <SignOutEverywhere />
        </Card>
      </section>
    </PageContainer>
  );
}

function ChangePasswordForm() {
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    const errors = validateNewPassword(password, confirmPassword);
    setFieldErrors(errors);
    setError(null);
    setSaved(false);
    if (Object.keys(errors).length > 0) return;

    setSaving(true);
    try {
      await updatePassword(password);
      setSaved(true);
      setPassword("");
      setConfirmPassword("");
    } catch (failure) {
      setError(failure);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="settings-form">
      {saved && <Alert tone="success">Your password has been updated.</Alert>}
      {error && <Alert tone="error">{error.message}</Alert>}
      <Input
        id="new-password"
        type="password"
        label="New password"
        autoComplete="new-password"
        hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        error={fieldErrors.password}
        disabled={saving}
      />
      <Input
        id="confirm-new-password"
        type="password"
        label="Confirm new password"
        autoComplete="new-password"
        value={confirmPassword}
        onChange={(event) => setConfirmPassword(event.target.value)}
        error={fieldErrors.confirmPassword}
        disabled={saving}
      />
      <Button type="submit" disabled={saving} aria-busy={saving}>
        {saving ? "Updating…" : "Update Password"}
      </Button>
    </form>
  );
}

function SignOutEverywhere() {
  const { signOut } = useAuth();
  const [confirming, setConfirming] = useState(false);
  const [working, setWorking] = useState(false);

  return (
    <div className="settings-row">
      <div>
        <p className="settings-row__title">Sign out of all devices</p>
        <p className="settings-row__description">
          Ends your LectureMind sessions everywhere, including this browser.
        </p>
      </div>
      <Button variant="secondary" onClick={() => setConfirming(true)}>
        Sign Out Everywhere
      </Button>
      {confirming && (
        <Modal
          title="Sign out of all devices?"
          description="You'll need to log in again on every device, including this one."
          onClose={() => setConfirming(false)}
          busy={working}
          actions={
            <>
              <Button variant="secondary" onClick={() => setConfirming(false)} disabled={working}>
                Cancel
              </Button>
              <Button
                variant="destructive"
                disabled={working}
                aria-busy={working}
                onClick={async () => {
                  setWorking(true);
                  await signOut({ scope: "global" });
                }}
              >
                {working ? "Signing out…" : "Sign Out Everywhere"}
              </Button>
            </>
          }
        />
      )}
    </div>
  );
}
