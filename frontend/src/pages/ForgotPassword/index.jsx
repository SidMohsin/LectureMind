import { Link } from "react-router-dom";
import AuthLayout from "../../components/layout/AuthLayout";
import Input from "../../components/ui/Input";
import Button from "../../components/ui/Button";

export default function ForgotPassword() {
  return (
    <AuthLayout
      title="Reset your password"
      description="Password reset is implemented in Phase 2 alongside Supabase Auth."
    >
      <form onSubmit={(event) => event.preventDefault()}>
        <Input id="email" label="Email" type="email" placeholder="you@university.edu" autoComplete="email" />
        <Button type="submit" variant="primary" disabled style={{ width: "100%" }}>
          Send Reset Link
        </Button>
      </form>
      <p style={{ marginTop: "16px", fontSize: "0.8rem", color: "var(--color-text-tertiary)" }}>
        <Link to="/login">Back to login</Link>
      </p>
    </AuthLayout>
  );
}
