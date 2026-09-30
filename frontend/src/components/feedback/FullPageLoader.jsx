import "./FullPageLoader.css";

export default function FullPageLoader({ label = "Loading…" }) {
  return (
    <div className="full-page-loader" role="status" aria-live="polite">
      <span className="full-page-loader__spinner" aria-hidden="true" />
      <span className="full-page-loader__label">{label}</span>
    </div>
  );
}
