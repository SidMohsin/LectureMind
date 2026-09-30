import Button from "./Button";
import "./EmptyState.css";

export default function ErrorState({ title = "Something went wrong", error, onRetry }) {
  return (
    <div className="empty-state empty-state--error" role="alert">
      <h3 className="empty-state__title">{title}</h3>
      {error?.message && <p className="empty-state__description">{error.message}</p>}
      {onRetry && (
        <div className="empty-state__action">
          <Button variant="secondary" onClick={onRetry}>
            Try again
          </Button>
        </div>
      )}
    </div>
  );
}
