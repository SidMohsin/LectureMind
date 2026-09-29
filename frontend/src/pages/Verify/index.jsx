import AuthLayout from "../../components/layout/AuthLayout";

export default function Verify() {
  return (
    <AuthLayout
      title="Verify your email"
      description="Email verification will be delivered through Supabase Auth in Phase 2. This route is reserved for that flow."
    />
  );
}
