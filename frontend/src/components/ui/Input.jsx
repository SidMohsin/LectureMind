import "./Input.css";

export default function Input({ label, id, error, hint, className = "", ...rest }) {
  const describedBy = [error && `${id}-error`, hint && `${id}-hint`].filter(Boolean).join(" ") || undefined;

  return (
    <div className="input-field">
      {label && (
        <label htmlFor={id} className="input-field__label">
          {label}
        </label>
      )}
      <input
        id={id}
        className={`input-field__control ${error ? "input-field__control--error" : ""} ${className}`.trim()}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        {...rest}
      />
      {hint && !error && (
        <span id={`${id}-hint`} className="input-field__hint">
          {hint}
        </span>
      )}
      {error && (
        <span id={`${id}-error`} className="input-field__error">
          {error}
        </span>
      )}
    </div>
  );
}
