import "./Logo.css";

/**
 * LectureMind mark: transcript lines with a timestamp marker - a lecture you can
 * jump into. The same drawing is used for public/favicon.svg.
 */
export function LogoMark({ size = 28 }) {
  return (
    <svg className="logo-mark" width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <rect width="32" height="32" rx="8" fill="var(--color-accent, #1e2f7a)" />
      <rect x="8" y="9" width="11" height="2.6" rx="1.3" fill="#fff" />
      <rect x="8" y="14.7" width="16" height="2.6" rx="1.3" fill="#fff" opacity="0.85" />
      <rect x="8" y="20.4" width="8" height="2.6" rx="1.3" fill="#fff" opacity="0.7" />
      <circle cx="22.6" cy="10.3" r="3.1" fill="#7aa2ff" />
    </svg>
  );
}

export default function Logo({ size = 28, className = "" }) {
  return (
    <span className={`logo ${className}`.trim()}>
      <LogoMark size={size} />
      <span className="logo__text">LectureMind</span>
    </span>
  );
}
