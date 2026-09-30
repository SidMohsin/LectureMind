import "./Select.css";

export default function Select({ label, id, options, className = "", hideLabel = false, ...rest }) {
  return (
    <div className={`select-field ${className}`.trim()}>
      {label && (
        <label htmlFor={id} className={hideLabel ? "visually-hidden" : "select-field__label"}>
          {label}
        </label>
      )}
      <select id={id} className="select-field__control" {...rest}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}
