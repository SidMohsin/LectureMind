import "./Input.css";

export default function Input({ label, id, error, className = "", ...rest }) {
  return (
    <div className="input-field">
      {label && (
        <label htmlFor={id} className="input-field__label">
          {label}
        </label>
      )}
      <input id={id} className={`input-field__control ${error ? "input-field__control--error" : ""} ${className}`.trim()} {...rest} />
      {error && <span className="input-field__error">{error}</span>}
    </div>
  );
}
