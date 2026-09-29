import { Link } from "react-router-dom";
import AuthLayout from "../../components/layout/AuthLayout";
import Input from "../../components/ui/Input";
import Button from "../../components/ui/Button";

export default function Login() {
  return (
    <AuthLayout
      title="Log in to LectureMind"
      description="Authentication is implemented in Phase 2. This screen establishes the route and visual foundation."
    >
      <form
        onSubmit={(event) => event.preventDefault()}
        aria-describedby="login-phase-note"
      >
        <Input id="email" label="Email" type="email" placeholder="you@university.edu" autoComplete="email" />
        <Input id="password" label="Password" type="password" placeholder="••••••••" autoComplete="current-password" />
        <Button type="submit" variant="primary" disabled style={{ width: "100%" }}>
          Log In
        </Button>
      </form>
      <p id="login-phase-note" style={{ marginTop: "16px", fontSize: "0.8rem", color: "var(--color-text-tertiary)" }}>
        Supabase-backed authentication is not active yet.{" "}
        <Link to="/signup">Create an account</Link> · <Link to="/forgot-password">Forgot password</Link>
      </p>
    </AuthLayout>
  );
}
