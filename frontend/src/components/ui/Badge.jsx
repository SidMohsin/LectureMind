import "./Badge.css";

const TONE_CLASS = {
  neutral: "badge badge--neutral",
  success: "badge badge--success",
  warning: "badge badge--warning",
  error: "badge badge--error",
  info: "badge badge--info",
};

export default function Badge({ tone = "neutral", children, className = "" }) {
  return <span className={`${TONE_CLASS[tone] || TONE_CLASS.neutral} ${className}`.trim()}>{children}</span>;
}
