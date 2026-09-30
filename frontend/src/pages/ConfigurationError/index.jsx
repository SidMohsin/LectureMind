import PageContainer from "../../components/layout/PageContainer";

export default function ConfigurationError() {
  return (
    <PageContainer>
      <div style={{ maxWidth: 560, padding: "80px 0" }}>
        <h1 style={{ fontSize: "var(--fs-page-heading)", marginBottom: 12 }}>LectureMind isn&apos;t configured</h1>
        <p style={{ color: "var(--color-text-secondary)" }}>
          Set <code className="mono">VITE_SUPABASE_URL</code> and <code className="mono">VITE_SUPABASE_ANON_KEY</code>{" "}
          in <code className="mono">frontend/.env</code>, then restart the dev server. See the README for details.
        </p>
      </div>
    </PageContainer>
  );
}
