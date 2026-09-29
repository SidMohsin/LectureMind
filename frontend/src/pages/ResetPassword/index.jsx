import AuthLayout from "../../components/layout/AuthLayout";
import Input from "../../components/ui/Input";
import Button from "../../components/ui/Button";

export default function ResetPassword() {
  return (
    <AuthLayout
      title="Set a new password"
      description="This screen will complete the Supabase Auth password reset flow in Phase 2."
    >
      <form onSubmit={(event) => event.preventDefault()}>
        <Input id="password" label="New password" type="password" placeholder="••••••••" autoComplete="new-password" />
        <Input id="confirm" label="Confirm password" type="password" placeholder="••••••••" autoComplete="new-password" />
        <Button type="submit" variant="primary" disabled style={{ width: "100%" }}>
          Reset Password
        </Button>
      </form>
    </AuthLayout>
  );
}
