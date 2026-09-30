import { Link, useLocation } from "react-router-dom";
import AuthLayout from "../../components/layout/AuthLayout";
import Button from "../../components/ui/Button";
import FullPageLoader from "../../components/feedback/FullPageLoader";
import { useAuth } from "../../auth/AuthContext";
import { authRedirectFor } from "../../lib/supabase";
import ResendVerification from "./ResendVerification";

const backToLogin = <Link to="/login">Back to log in</Link>;

export default function Verify() {
  const redirect = authRedirectFor("/verify");
  const { status } = useAuth();
  const location = useLocation();
  const knownEmail = location.state?.email ?? "";
  const signupEmail = location.state?.justSignedUp ? knownEmail : null;

  const arrivedFromLink = Boolean(redirect?.hasSession);
  const linkFailed = Boolean(redirect?.errorCode) || (arrivedFromLink && status === "unauthenticated");

  if (linkFailed) {
    return (
      <AuthLayout
        title="This link has expired"
        description="Verification links can only be used once and expire after a while. Enter your email and we'll send you a new one."
        footer={backToLogin}
      >
        <ResendVerification askForEmail />
      </AuthLayout>
    );
  }

  if (status === "loading") return <FullPageLoader label={arrivedFromLink ? "Confirming your email…" : "Loading…"} />;

  if (status === "authenticated") {
    return (
      <AuthLayout
        title={arrivedFromLink ? "Email verified" : "Your email is verified"}
        description="Your account is ready. You can start building your lecture library."
      >
        <div className="auth-form__actions">
          <Button as={Link} to="/dashboard">
            Continue to Dashboard
          </Button>
        </div>
      </AuthLayout>
    );
  }

  if (signupEmail) {
    return (
      <AuthLayout
        title="Check your inbox"
        description={`We sent a verification link to ${signupEmail}. Open it to activate your account.`}
        footer={backToLogin}
      >
        <ResendVerification initialEmail={signupEmail} />
        <p className="auth-note">Can&apos;t find it? Check your spam folder.</p>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Verify your email"
      description="Enter the email you signed up with and we'll send you a new verification link."
      footer={backToLogin}
    >
      <ResendVerification askForEmail initialEmail={knownEmail} />
    </AuthLayout>
  );
}
