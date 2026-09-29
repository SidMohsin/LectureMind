import { Link } from "react-router-dom";
import AuthLayout from "../../components/layout/AuthLayout";
import Input from "../../components/ui/Input";
import Button from "../../components/ui/Button";

export default function Signup() {
  return (
    <AuthLayout
      title="Create your LectureMind account"
      description="Authentication is implemented in Phase 2. This screen establishes the route and visual foundation."
    >
      <form onSubmit={(event) => event.preventDefault()}>
        <Input id="name" label="Full name" type="text" placeholder="Alex Chen" autoComplete="name" />
        <Input id="email" label="Email" type="email" placeholder="you@university.edu" autoComplete="email" />
        <Input id="password" label="Password" type="password" placeholder="••••••••" autoComplete="new-password" />
        <Button type="submit" variant="primary" disabled style={{ width: "100%" }}>
          Sign Up
        </Button>
      </form>
      <p style={{ marginTop: "16px", fontSize: "0.8rem", color: "var(--color-text-tertiary)" }}>
        Already have an account? <Link to="/login">Log in</Link>
      </p>
    </AuthLayout>
  );
}
