import { Link } from "react-router-dom";
import PageContainer from "../../components/layout/PageContainer";
import Button from "../../components/ui/Button";

export default function NotFound() {
  return (
    <PageContainer>
      <div style={{ textAlign: "center", padding: "80px 0" }}>
        <h1 style={{ fontSize: "var(--fs-display)", marginBottom: "12px" }}>Page not found</h1>
        <p style={{ color: "var(--color-text-secondary)", marginBottom: "24px" }}>
          The page you're looking for doesn't exist or has moved.
        </p>
        <Button as={Link} to="/" variant="primary">
          Back to home
        </Button>
      </div>
    </PageContainer>
  );
}
