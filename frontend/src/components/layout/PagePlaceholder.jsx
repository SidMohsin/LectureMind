import PageContainer from "./PageContainer";
import Badge from "../ui/Badge";
import "./PagePlaceholder.css";

/**
 * Consistent placeholder for routes whose full product behaviour is planned
 * for a later roadmap phase. Keeps route boundaries and visual language in
 * place now without faking functionality that does not exist yet.
 */
export default function PagePlaceholder({ title, description, phase, children }) {
  return (
    <PageContainer>
      <div className="page-placeholder">
        <Badge tone="info">{phase}</Badge>
        <h1 className="page-placeholder__title">{title}</h1>
        <p className="page-placeholder__description">{description}</p>
        {children}
      </div>
    </PageContainer>
  );
}
