import { useState } from "react";
import "./Input.css";

export default function Input({ label, id, error, hint, className = "", type = "text", ...rest }) {
  const [revealed, setRevealed] = useState(false);
  const describedBy = [error && `${id}-error`, hint && `${id}-hint`].filter(Boolean).join(" ") || undefined;
  const isPassword = type === "password";

  const control = (
    <input
      id={id}
      type={isPassword && revealed ? "text" : type}
      className={`input-field__control ${isPassword ? "input-field__control--with-toggle" : ""} ${
        error ? "input-field__control--error" : ""
      } ${className}`.trim()}
      aria-invalid={error ? true : undefined}
      aria-describedby={describedBy}
      {...rest}
    />
  );

  return (
    <div className="input-field">
      {label && (
        <label htmlFor={id} className="input-field__label">
          {label}
        </label>
      )}
      {isPassword ? (
        <div className="input-field__wrap">
          {control}
          <button
            type="button"
            className="input-field__toggle"
            onClick={() => setRevealed((value) => !value)}
            aria-label={revealed ? "Hide password" : "Show password"}
            aria-pressed={revealed}
            aria-controls={id}
            disabled={rest.disabled}
          >
            {revealed ? <EyeOffIcon /> : <EyeIcon />}
          </button>
        </div>
      ) : (
        control
      )}
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

function EyeIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function EyeOffIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M17.94 17.94A10.1 10.1 0 0 1 12 19c-6.5 0-10-7-10-7a18.4 18.4 0 0 1 5.06-5.94" />
      <path d="M9.9 4.24A9.1 9.1 0 0 1 12 4c6.5 0 10 7 10 7a18.5 18.5 0 0 1-2.16 3.19" />
      <path d="M14.12 14.12a3 3 0 1 1-4.24-4.24" />
      <path d="M2 2l20 20" />
    </svg>
  );
}
