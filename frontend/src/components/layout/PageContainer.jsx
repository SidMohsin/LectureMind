import "./PageContainer.css";

export default function PageContainer({ children, className = "" }) {
  return <div className={`page-container ${className}`.trim()}>{children}</div>;
}
