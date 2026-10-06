import "./Skeleton.css";

/**
 * Placeholder block shown while content loads, shaped like the content it
 * replaces, so the page doesn't jump when data arrives. Purely decorative:
 * the surrounding region announces loading (aria-busy / role="status").
 */
export default function Skeleton({ width = "100%", height = 14, radius, className = "", style }) {
  return (
    <span
      className={`skeleton ${className}`.trim()}
      aria-hidden="true"
      style={{ width, height, borderRadius: radius, ...style }}
    />
  );
}

/** A few text lines; the last one shorter, like a real paragraph. */
export function SkeletonText({ lines = 3, gap = 10, lastWidth = "60%" }) {
  return (
    <span className="skeleton-text" aria-hidden="true" style={{ gap }}>
      {Array.from({ length: lines }, (_, index) => (
        <Skeleton key={index} width={index === lines - 1 ? lastWidth : "100%"} />
      ))}
    </span>
  );
}
